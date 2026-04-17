"""Signal extractor — translate DiagnosticState evidence into the
``Signal`` enum vocabulary the signature library matches against.

The goal is narrow: surface whatever unambiguous signals the state carries
(OOM kills, deploys, error spikes, etc.) so ``try_signature_match`` has
typed inputs to work with. Ambiguous or noisy state fields are NOT mapped;
we'd rather under-match than hallucinate a pattern.

Stage A.2 of the run_v5 orchestration swap.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from src.patterns.schema import Signal, SignalKind


# Keyword heuristics — deliberately narrow. Each signal maps to a small set
# of unambiguous tokens. Tune here when a real incident proves a tighter
# mapping is needed; do NOT expand to near-synonyms.
_SIGNAL_KEYWORDS: dict[SignalKind, tuple[str, ...]] = {
    "oom_killed": ("oomkilled", "out of memory", "oom-killer"),
    "memory_pressure": ("memorypressure", "memory pressure", "memory limit"),
    "pod_restart": ("crashloopbackoff", "pod restart", "restarted"),
    "error_rate_spike": ("error rate spike", "5xx spike", "error spike"),
    "latency_spike": ("latency spike", "p95 spike", "p99 spike"),
    "deploy": ("deploy", "rollout", "deployment updated"),
    "config_change": ("config change", "configmap updated", "secret rotated"),
    "retry_storm": ("retry storm", "retries exhausted"),
    "circuit_open": ("circuit open", "circuit breaker opened"),
    "cert_expiry": ("cert expired", "certificate expired", "x509: certificate"),
    "hot_key": ("hot key", "hot partition", "hot shard"),
    "thread_pool_exhausted": ("thread pool exhausted", "executor saturated"),
    "dns_failure": ("dns failure", "no such host", "dns resolution"),
    "image_pull_backoff": ("imagepullbackoff", "errimagepull"),
    "quota_exceeded": ("quota exceeded", "resourcequota"),
    "network_policy_denial": ("networkpolicy", "denied by policy", "connection refused"),
    "connection_refused": ("connection refused", "connection reset"),
    "traffic_drop": ("traffic drop", "rps drop", "no traffic"),
}


def extract_signals_from_state(state: Any) -> list[Signal]:
    """Return a list of ``Signal``s derived from evidence pins + typed
    state sub-structures.

    Deterministic: the same state produces the same signals in the same
    order (scan order = evidence pins first, then typed analyses).
    Deduplicated on (kind, source_service, rounded_t).
    """
    out: list[Signal] = []
    seen: set[tuple[SignalKind, Optional[str], int]] = set()

    # Reference time for relative seconds. Prefer patient_zero timestamp
    # if present; otherwise the earliest evidence-pin timestamp.
    origin = _origin_time(state)

    for pin in _evidence_pins(state):
        claim = _pin_field(pin, "claim") or ""
        raw = (_pin_field(pin, "raw_output") or "") + " " + claim
        service = _pin_field(pin, "service") or _pin_field(pin, "source_agent")
        ts = _pin_field(pin, "timestamp")
        for kind in _matching_kinds(raw):
            t_rel = _relative_seconds(ts, origin)
            key = (kind, service, int(t_rel))
            if key in seen:
                continue
            seen.add(key)
            out.append(Signal(kind=kind, t=t_rel, service=service))

    # K8s typed analysis gives us high-signal OOM + restart markers.
    k8s = getattr(state, "k8s_analysis", None)
    if k8s is not None:
        for pod in getattr(k8s, "pod_statuses", None) or []:
            svc = _pod_service(pod)
            if getattr(pod, "oom_killed", False):
                _add(out, seen, "oom_killed", 0.0, svc)
            if getattr(pod, "crash_loop", False):
                _add(out, seen, "pod_restart", 1.0, svc)

    # Metrics analysis surfaces spikes.
    metrics = getattr(state, "metrics_analysis", None)
    if metrics is not None:
        for anomaly in getattr(metrics, "anomalies", None) or []:
            name = (getattr(anomaly, "metric_name", "") or "").lower()
            svc = getattr(anomaly, "service", None)
            if "error" in name or "5xx" in name:
                _add(out, seen, "error_rate_spike", 2.0, svc)
            elif "latency" in name or "p95" in name or "p99" in name:
                _add(out, seen, "latency_spike", 2.0, svc)

    # Change analysis surfaces deploys.
    change = getattr(state, "change_analysis", None)
    if change is not None:
        deploys = _change_deploys(change)
        for d in deploys:
            _add(out, seen, "deploy", -60.0, d.get("service") if isinstance(d, dict) else getattr(d, "service", None))

    return out


# ── internals ────────────────────────────────────────────────────────────


def _evidence_pins(state: Any) -> Iterable[Any]:
    return getattr(state, "evidence_pins", None) or []


def _pin_field(pin: Any, name: str) -> Optional[Any]:
    if isinstance(pin, dict):
        return pin.get(name)
    return getattr(pin, name, None)


def _matching_kinds(text: str) -> list[SignalKind]:
    low = text.lower()
    hits: list[SignalKind] = []
    for kind, keywords in _SIGNAL_KEYWORDS.items():
        for kw in keywords:
            if kw in low:
                hits.append(kind)
                break
    return hits


def _origin_time(state: Any) -> Optional[datetime]:
    pz = getattr(state, "patient_zero", None)
    if isinstance(pz, dict):
        ts = pz.get("timestamp")
    else:
        ts = getattr(pz, "timestamp", None) if pz else None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    # Fall back to earliest pin timestamp.
    earliest: Optional[datetime] = None
    for pin in _evidence_pins(state):
        pts = _pin_field(pin, "timestamp")
        if isinstance(pts, datetime):
            if earliest is None or pts < earliest:
                earliest = pts
    return earliest


def _relative_seconds(ts: Any, origin: Optional[datetime]) -> float:
    if origin is None:
        return 0.0
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if origin.tzinfo is None:
            origin = origin.replace(tzinfo=timezone.utc)
        return (ts - origin).total_seconds()
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return _relative_seconds(parsed, origin)
        except ValueError:
            return 0.0
    return 0.0


def _pod_service(pod: Any) -> Optional[str]:
    if isinstance(pod, dict):
        return pod.get("service") or pod.get("namespace")
    return getattr(pod, "service", None) or getattr(pod, "namespace", None)


def _change_deploys(change: Any) -> list[Any]:
    if isinstance(change, dict):
        return change.get("deploys") or change.get("recent_deploys") or []
    return (
        getattr(change, "deploys", None)
        or getattr(change, "recent_deploys", None)
        or []
    )


def _add(
    out: list[Signal],
    seen: set,
    kind: SignalKind,
    t: float,
    service: Optional[str],
) -> None:
    key = (kind, service, int(t))
    if key in seen:
        return
    seen.add(key)
    out.append(Signal(kind=kind, t=t, service=service))
