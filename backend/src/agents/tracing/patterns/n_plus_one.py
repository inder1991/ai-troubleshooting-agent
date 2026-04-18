"""N+1 query detector.

Classic ORM lazy-loading anti-pattern: one parent span emits many sequential
child spans with identical ``(service, operation)``. Example: ``checkout-api``
emits 47 ``postgres/SELECT users.*`` children in a single request.

Rule:
  parent span has ≥ N children where
    - all share identical ``(service_name, operation_name)``
    - they do NOT overlap in time (fan-out amplification path handles overlap)
  emits one finding per matching (parent, service, op) group.

Severity:
  10-19 children  low
  20-49 children  medium
  50-99 children  high
  100+  critical
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from src.models.schemas import PatternFinding, SpanInfo


_DEFAULT_MIN_COUNT = 10


class NPlusOneDetector:
    kind = "n_plus_one"

    def __init__(self, min_count: int = _DEFAULT_MIN_COUNT) -> None:
        self._min_count = min_count

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans:
            return []

        # Group by (parent_span_id, service_name, operation_name).
        by_id = {s.span_id: s for s in spans}
        groups: dict[tuple[Optional[str], str, str], list[SpanInfo]] = defaultdict(list)
        for span in spans:
            if not span.parent_span_id:
                continue  # root spans can't be part of a child-group
            key = (span.parent_span_id, span.service_name, span.operation_name)
            groups[key].append(span)

        findings: list[PatternFinding] = []
        for (parent_id, service, op), members in groups.items():
            if len(members) < self._min_count:
                continue

            # Exclude clearly-concurrent patterns — those belong to fan_out.
            if _is_concurrent(members):
                continue

            total_ms = round(sum(m.duration_ms for m in members), 2)
            count = len(members)
            severity = _severity_for_count(count)

            findings.append(
                PatternFinding(
                    kind="n_plus_one",
                    confidence=_confidence_for_count(count),
                    severity=severity,
                    human_summary=(
                        f"N+1 pattern: {service}/{op} called {count} times "
                        f"sequentially under a single parent span "
                        f"(total {total_ms}ms). Typical root cause: ORM "
                        f"lazy-loading or a loop issuing one query per item."
                    ),
                    span_ids_involved=[m.span_id for m in members[:20]],  # cap
                    service_name=service,
                    metadata={
                        "parent_span_id": parent_id,
                        "operation": op,
                        "child_count": count,
                        "total_time_ms": total_ms,
                    },
                )
            )
        return findings


# ── helpers ──────────────────────────────────────────────────────────────


def _severity_for_count(count: int) -> str:
    if count >= 100:
        return "critical"
    if count >= 50:
        return "high"
    if count >= 20:
        return "medium"
    return "low"


def _confidence_for_count(count: int) -> int:
    # Deterministic — the more children, the more confident the diagnosis.
    return min(60 + (count - 10) * 2, 95)


def _is_concurrent(spans: list[SpanInfo]) -> bool:
    """True if the span group exhibits significant temporal overlap.

    Uses ``start_time_us`` when present. When absent (older/missing data)
    we can't discriminate concurrent vs sequential, so we conservatively
    return False — the group counts as sequential and the N+1 rule can fire.
    """
    with_time = [s for s in spans if s.start_time_us is not None]
    if len(with_time) < 2:
        return False

    # Compute overlap ratio: fraction of spans whose window overlaps any sibling.
    intervals = sorted(
        ((s.start_time_us, int(s.start_time_us + s.duration_ms * 1000))
         for s in with_time),
        key=lambda t: t[0],
    )

    overlap_count = 0
    for i in range(1, len(intervals)):
        prev_start, prev_end = intervals[i - 1]
        cur_start, _ = intervals[i]
        if cur_start < prev_end:
            overlap_count += 1

    # If ≥ 30% of adjacent pairs overlap, call it concurrent.
    return overlap_count >= max(2, int(0.3 * (len(intervals) - 1)))
