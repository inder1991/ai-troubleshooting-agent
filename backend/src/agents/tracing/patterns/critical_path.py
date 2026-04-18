"""Critical-path hotspot detector.

Shape:
  one span on the critical path consumes > threshold % of total trace time.
  Tells the user "the time is going HERE" with a number rather than a hunch.

Rule:
  - compute longest root→leaf path by sum of durations
  - for each span on that path, compute (span.duration_ms / total_duration_ms)
  - emit finding for spans > threshold_percent (default 60%)

The critical path is already annotated on spans by ``TraceSummarizer``;
this detector computes the fraction and emits findings accordingly. When
the summarizer hasn't run yet, we compute it inline.

Severity:
  60-70%   medium
  70-85%   high
  85%+     critical
"""
from __future__ import annotations

from typing import Optional

from src.models.schemas import PatternFinding, SpanInfo


_DEFAULT_THRESHOLD = 0.60


class CriticalPathDetector:
    kind = "critical_path_hotspot"

    def __init__(self, threshold_percent: float = _DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold_percent

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans:
            return []

        total_duration = _total_trace_duration(spans)
        if total_duration <= 0:
            return []

        critical_ids = _compute_critical_path_ids(spans)
        findings: list[PatternFinding] = []

        for span in spans:
            if span.span_id not in critical_ids:
                continue
            fraction = span.duration_ms / total_duration
            if fraction < self._threshold:
                continue

            severity = _severity_for_fraction(fraction)
            findings.append(
                PatternFinding(
                    kind="critical_path_hotspot",
                    confidence=_confidence_for_fraction(fraction),
                    severity=severity,
                    human_summary=(
                        f"Critical-path hotspot: {span.service_name}/"
                        f"{span.operation_name} consumed {fraction * 100:.0f}% "
                        f"of the trace's total time ({span.duration_ms:.0f}ms "
                        f"of {total_duration:.0f}ms). Time spent anywhere "
                        f"else is dwarfed by this span."
                    ),
                    span_ids_involved=[span.span_id],
                    service_name=span.service_name,
                    metadata={
                        "operation": span.operation_name,
                        "duration_ms": round(span.duration_ms, 2),
                        "total_trace_duration_ms": round(total_duration, 2),
                        "fraction_of_trace": round(fraction, 4),
                    },
                )
            )
        return findings


# ── helpers ──────────────────────────────────────────────────────────────


def _total_trace_duration(spans: list[SpanInfo]) -> float:
    """Total duration = root span's duration (or max of root-like spans)."""
    parent_ids = {s.parent_span_id for s in spans if s.parent_span_id}
    roots = [s for s in spans if s.span_id not in parent_ids or s.parent_span_id is None]
    if not roots:
        return max((s.duration_ms for s in spans), default=0.0)
    return max(r.duration_ms for r in roots)


def _compute_critical_path_ids(spans: list[SpanInfo]) -> set[str]:
    """Compute longest-duration root→leaf chain; return its span IDs."""
    by_id = {s.span_id: s for s in spans}
    parent_ids = {s.parent_span_id for s in spans if s.parent_span_id}
    # Leaf spans = those not referenced as anyone's parent.
    all_ids = {s.span_id for s in spans}
    leaves = [s for s in spans if s.span_id not in parent_ids]
    if not leaves:
        leaves = spans

    best_total = 0.0
    best_chain: list[str] = []
    for leaf in leaves:
        chain: list[str] = []
        total = 0.0
        cur: Optional[SpanInfo] = leaf
        seen: set[str] = set()
        while cur is not None and cur.span_id not in seen:
            seen.add(cur.span_id)
            chain.append(cur.span_id)
            total += cur.duration_ms
            cur = by_id.get(cur.parent_span_id) if cur.parent_span_id else None
        if total > best_total:
            best_total = total
            best_chain = chain
    return set(best_chain)


def _severity_for_fraction(f: float) -> str:
    if f >= 0.85:
        return "critical"
    if f >= 0.70:
        return "high"
    return "medium"


def _confidence_for_fraction(f: float) -> int:
    # Higher fraction → higher confidence this is THE bottleneck.
    return min(70 + int((f - 0.60) * 100), 95)
