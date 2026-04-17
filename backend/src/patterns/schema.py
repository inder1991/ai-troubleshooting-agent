"""SignaturePattern schema — deterministic incident-signature matching.

A SignaturePattern is a closed rule: given a set of typed signals, does
this incident look like a known failure mode? Matching is pure rule-based
(no LLM). A match produces a ``MatchResult`` with a confidence floor the
supervisor can trust without further investigation — and a suggested
remediation the user can act on.

The point: the LLM doesn't pattern-match. The library does, deterministically.
The LLM summarises findings and explains trade-offs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


# Signal kinds a pattern can require. Keep this list small and explicit;
# new signals land as deliberate additions, not as arbitrary strings the
# LLM can invent.
SignalKind = Literal[
    "memory_pressure",
    "oom_killed",
    "pod_restart",
    "error_rate_spike",
    "latency_spike",
    "deploy",
    "config_change",
    "retry_storm",
    "circuit_open",
    "cert_expiry",
    "hot_key",
    "thread_pool_exhausted",
    "dns_failure",
    "image_pull_backoff",
    "quota_exceeded",
    "network_policy_denial",
    "connection_refused",
    "traffic_drop",
]


@dataclass(frozen=True)
class Signal:
    """Observed signal at a given time, optionally scoped to a service."""

    kind: SignalKind
    t: float                       # seconds since incident start (monotonic)
    service: Optional[str] = None
    attrs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    confidence: float
    missing: tuple[SignalKind, ...] = ()
    matched_kinds: tuple[SignalKind, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class TemporalRule:
    """Constraint: ``earlier`` must precede ``later`` by <= max_gap_s."""

    earlier: SignalKind
    later: SignalKind
    max_gap_s: float


@dataclass(frozen=True)
class SignaturePattern:
    """Closed rule matching a known incident shape against observed signals."""

    SCHEMA_VERSION: int = 1

    name: str = ""
    required_signals: tuple[SignalKind, ...] = ()
    temporal_constraints: tuple[TemporalRule, ...] = ()
    # Optional signals boost the score when present; missing ones don't fail the match.
    optional_signals: tuple[SignalKind, ...] = ()
    confidence_floor: float = 0.70
    summary_template: str = ""
    suggested_remediation: Optional[str] = None

    def matches(self, signals: list[Signal]) -> MatchResult:
        """Evaluate this pattern against observed signals.

        Scoring:
          - base = 1.0 if all required signals present, else 0.0
          - + 0.05 per optional signal present (capped at 0.20 cumulative)
          - - 0.15 per violated temporal rule (earlier must precede later)
          - clamped to [0, 1]
        Returns ``matched=True`` only when base=1 AND no temporal violations.
        """
        kinds_present = {s.kind for s in signals}
        by_kind_earliest: dict[SignalKind, float] = {}
        for s in signals:
            prev = by_kind_earliest.get(s.kind)
            if prev is None or s.t < prev:
                by_kind_earliest[s.kind] = s.t

        missing = tuple(k for k in self.required_signals if k not in kinds_present)
        matched_required = tuple(
            k for k in self.required_signals if k in kinds_present
        )

        # Temporal rule evaluation (only when both sides present).
        temporal_violations: list[str] = []
        for rule in self.temporal_constraints:
            t_early = by_kind_earliest.get(rule.earlier)
            t_late = by_kind_earliest.get(rule.later)
            if t_early is None or t_late is None:
                continue
            gap = t_late - t_early
            if gap < 0 or gap > rule.max_gap_s:
                temporal_violations.append(
                    f"{rule.earlier}->{rule.later}: gap {gap:.1f}s not in (0, {rule.max_gap_s}]"
                )

        if missing:
            return MatchResult(
                matched=False,
                confidence=0.0,
                missing=missing,
                matched_kinds=matched_required,
                reason=f"missing required: {', '.join(missing)}",
            )
        if temporal_violations:
            return MatchResult(
                matched=False,
                confidence=0.0,
                missing=(),
                matched_kinds=matched_required,
                reason="; ".join(temporal_violations),
            )

        score = 1.0
        optional_present = sum(1 for k in self.optional_signals if k in kinds_present)
        score = min(score, 1.0) * self.confidence_floor + min(optional_present * 0.05, 0.20)
        score = min(score, 1.0)
        # Ensure matched result >= floor (matching preserves the floor).
        score = max(score, self.confidence_floor)

        return MatchResult(
            matched=True,
            confidence=round(score, 4),
            missing=(),
            matched_kinds=tuple(self.required_signals),
            reason=f"all required present; {optional_present} optional matched",
        )

    def render_summary(self, signals: list[Signal]) -> str:
        """Deterministic summary using the template + present signals."""
        service = next((s.service for s in signals if s.service), "unknown")
        return self.summary_template.format(service=service)
