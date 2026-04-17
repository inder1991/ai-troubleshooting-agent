"""State-to-confidence adapter with env-flagged legacy fallback.

Bridges DiagnosticState into ``ConfidenceInputs`` for Phase-2's
deterministic ``compute_confidence``, and exposes the legacy per-
evidence-type averaging as a fallback so the rollout can be A/B flagged.

Env flag:
    DIAGNOSTIC_CONFIDENCE_MODE=deterministic (default) | legacy

Stage A.3 of the run_v5 orchestration swap.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from src.agents.confidence_calibrator import (
    DEFAULT_PRIOR,
    ConfidenceCalibrator,
    ConfidenceInputs,
    compute_confidence,
)


_EVIDENCE_TYPE_TO_SOURCE: dict[str, str] = {
    "log": "logs",
    "metric": "metrics",
    "k8s_event": "k8s",
    "k8s_resource": "k8s",
    "trace": "traces",
    "code": "code",
    "change": "changes",
}


def state_confidence_mode() -> str:
    """Returns 'deterministic' (default) or 'legacy' based on env var."""
    mode = os.getenv("DIAGNOSTIC_CONFIDENCE_MODE", "deterministic").strip().lower()
    return "legacy" if mode == "legacy" else "deterministic"


def compute_state_confidence(state: Any) -> float:
    """Return a single 0..1 confidence score for the investigation state.

    Determinism guarantee: under ``deterministic`` mode, same inputs =>
    same output, always. When DIAGNOSTIC_PRIORS_BIAS=on, the result is
    nudged by +/- up to 5 points based on the mean persisted prior
    across the agents currently feeding evidence (still deterministic
    w.r.t. the same DB snapshot).
    """
    if state_confidence_mode() == "legacy":
        return _legacy_confidence(state)
    base = compute_confidence(_confidence_inputs(state))
    if os.getenv("DIAGNOSTIC_PRIORS_BIAS", "off").strip().lower() == "on":
        return _apply_prior_bias(state, base)
    return base


async def compute_state_confidence_async(state: Any) -> float:
    """Async variant that reads persisted priors when bias is on.

    Priors are read from Postgres so this is async. The sync
    ``compute_state_confidence`` retains its signature for backwards
    compatibility and skips the bias when called synchronously (the
    Postgres round-trip can't be awaited).
    """
    base = (
        _legacy_confidence(state)
        if state_confidence_mode() == "legacy"
        else compute_confidence(_confidence_inputs(state))
    )
    if os.getenv("DIAGNOSTIC_PRIORS_BIAS", "off").strip().lower() != "on":
        return base
    agents = _agents_feeding_evidence(state)
    if not agents:
        return base
    try:
        cal = ConfidenceCalibrator()
        priors = [await cal.get_prior(a) for a in agents]
    except Exception:
        return base
    if not priors:
        return base
    return _apply_prior_tilt(base, priors)


def confidence_inputs_from_state(state: Any) -> ConfidenceInputs:
    """Public accessor for tests / diagnostics that want to see the raw
    breakdown without running the scorer."""
    return _confidence_inputs(state)


# ── internals ────────────────────────────────────────────────────────────


def _confidence_inputs(state: Any) -> ConfidenceInputs:
    pins = list(_evidence_pins(state))
    evidence_pin_count = len(pins)
    source_diversity = len(
        {
            _EVIDENCE_TYPE_TO_SOURCE.get(
                _pin_field(pin, "evidence_type") or "", ""
            )
            for pin in pins
            if _EVIDENCE_TYPE_TO_SOURCE.get(
                _pin_field(pin, "evidence_type") or "", ""
            )
        }
    )
    baseline_delta_pct = _max_baseline_delta(pins)
    contradiction_count = _contradiction_count(state)
    signature_match = bool(getattr(state, "signature_match", None))
    topology_path_length = _topology_path_length(state)
    return ConfidenceInputs(
        evidence_pin_count=evidence_pin_count,
        source_diversity=source_diversity,
        baseline_delta_pct=baseline_delta_pct,
        contradiction_count=contradiction_count,
        signature_match=signature_match,
        topology_path_length=topology_path_length,
    )


def _evidence_pins(state: Any) -> Iterable[Any]:
    return getattr(state, "evidence_pins", None) or []


def _pin_field(pin: Any, name: str) -> Any:
    if isinstance(pin, dict):
        return pin.get(name)
    return getattr(pin, name, None)


def _max_baseline_delta(pins: Iterable[Any]) -> float:
    """Return the max |baseline_delta_pct| across pins that carry one.

    Pin shape may be a Pydantic EvidencePin or a dict; both use the
    ``baseline_delta_pct`` key set by Phase-1 baseline logic.
    """
    best = 0.0
    for pin in pins:
        v = _pin_field(pin, "baseline_delta_pct")
        if v is None:
            continue
        try:
            fv = abs(float(v))
        except (TypeError, ValueError):
            continue
        if fv > best:
            best = fv
    return best


def _contradiction_count(state: Any) -> int:
    verdicts = getattr(state, "critic_verdicts", None) or []
    return sum(
        1
        for cv in verdicts
        if (cv.get("verdict") if isinstance(cv, dict) else getattr(cv, "verdict", None))
        == "challenged"
    )


def _topology_path_length(state: Any) -> int:
    graph = getattr(state, "evidence_graph", None)
    if graph is None:
        return 0
    if isinstance(graph, dict):
        roots = graph.get("root_causes") or []
    else:
        roots = getattr(graph, "root_causes", None) or []
    return len(roots)


# ── legacy fallback (pre-Phase-2 Bayesian blend) ─────────────────────────


def _legacy_confidence(state: Any) -> float:
    """Legacy per-evidence-type averaging. Kept for rollout A/B only."""
    pins = list(_evidence_pins(state))
    if not pins:
        return 0.0
    by_type: dict[str, list[float]] = {}
    for pin in pins:
        et = _pin_field(pin, "evidence_type") or "unknown"
        conf = _pin_field(pin, "confidence")
        try:
            c = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            c = None
        if c is None:
            continue
        by_type.setdefault(et, []).append(c)
    if not by_type:
        return 0.0
    per_type_avg = [sum(v) / len(v) for v in by_type.values() if v]
    if not per_type_avg:
        return 0.0
    # Equal-weighted mean across evidence types — rough match of the
    # old Bayesian blend that averaged the confidence ledger fields.
    return max(0.0, min(sum(per_type_avg) / len(per_type_avg), 1.0))


# ── prior-bias helpers (opt-in via DIAGNOSTIC_PRIORS_BIAS) ───────────────


def _agents_feeding_evidence(state: Any) -> list[str]:
    """Distinct source_agent names from evidence_pins (preserves order)."""
    seen: list[str] = []
    for pin in _evidence_pins(state):
        src = _pin_field(pin, "source_agent")
        if src and src not in seen:
            seen.append(str(src))
    return seen


def _apply_prior_tilt(base: float, priors: list[float]) -> float:
    """Nudge ``base`` by +/- up to 5 points based on the mean prior.

    Prior 0.65 (default) -> no tilt. Prior 1.0 -> +0.05. Prior 0.0 -> -0.05.
    Linear interpolation around DEFAULT_PRIOR. Clamped to [0, 1].
    """
    mean_prior = sum(priors) / len(priors)
    tilt = (mean_prior - DEFAULT_PRIOR) / max(1.0 - DEFAULT_PRIOR, 0.35) * 0.05
    return max(0.0, min(base + tilt, 1.0))


def _apply_prior_bias(state: Any, base: float) -> float:
    """Sync best-effort: when bias is on but we can't await, read priors
    from the supervisor-attached calibrator cache if present on state."""
    priors = getattr(state, "_agent_priors_cache", None)
    if not priors:
        return base
    values = [float(v) for v in priors.values() if isinstance(v, (int, float))]
    if not values:
        return base
    return _apply_prior_tilt(base, values)
