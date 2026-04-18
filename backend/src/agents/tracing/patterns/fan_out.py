"""Fan-out amplification detector.

Shape:
  one parent span emits N concurrent children; one child is materially
  slower than its peers and gates the whole request. User sees "my API
  is slow"; root cause is "this ONE downstream is dragging 7 others."

Rule:
  - parent has ≥ K concurrent children (overlapping ``start_time_us`` ranges)
  - slowest child's duration > ``amplification_factor`` × median child duration
  - K ≥ 3 by default; amplification_factor ≥ 2.0

Severity:
  amplification 2-3×       medium
  3-5×                    high
  5×+                     critical
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Optional

from src.models.schemas import PatternFinding, SpanInfo


_DEFAULT_MIN_CONCURRENT = 3
_DEFAULT_AMPLIFICATION = 2.0


class FanOutDetector:
    kind = "fan_out_amplification"

    def __init__(
        self,
        min_concurrent: int = _DEFAULT_MIN_CONCURRENT,
        amplification_factor: float = _DEFAULT_AMPLIFICATION,
    ) -> None:
        self._min_concurrent = min_concurrent
        self._factor = amplification_factor

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans:
            return []

        # Group children by parent_span_id.
        children_of: dict[Optional[str], list[SpanInfo]] = defaultdict(list)
        for span in spans:
            if span.parent_span_id:
                children_of[span.parent_span_id].append(span)

        findings: list[PatternFinding] = []
        for parent_id, children in children_of.items():
            if len(children) < self._min_concurrent:
                continue

            # Require start_time_us on all — fan-out is a temporal concept.
            timed = [c for c in children if c.start_time_us is not None]
            if len(timed) < self._min_concurrent:
                continue

            # Check concurrency: at least K children whose windows overlap.
            if not _has_concurrent_cluster(timed, self._min_concurrent):
                continue

            durations = [c.duration_ms for c in timed if c.duration_ms > 0]
            if len(durations) < 2:
                continue
            median = statistics.median(durations)
            if median <= 0:
                continue
            slowest = max(timed, key=lambda c: c.duration_ms)
            factor = slowest.duration_ms / median
            if factor < self._factor:
                continue

            severity = _severity_for_factor(factor)
            findings.append(
                PatternFinding(
                    kind="fan_out_amplification",
                    confidence=_confidence_for_factor(factor, len(timed)),
                    severity=severity,
                    human_summary=(
                        f"Fan-out amplification at parent {parent_id}: "
                        f"{len(timed)} concurrent children, but "
                        f"{slowest.service_name}/{slowest.operation_name} "
                        f"ran {factor:.1f}× slower than the peer median "
                        f"({slowest.duration_ms:.0f}ms vs {median:.0f}ms median). "
                        f"The slowest leg gates the entire parent request."
                    ),
                    span_ids_involved=[slowest.span_id] + [
                        c.span_id for c in timed if c.span_id != slowest.span_id
                    ][:15],
                    service_name=slowest.service_name,
                    metadata={
                        "parent_span_id": parent_id,
                        "slowest_child_span_id": slowest.span_id,
                        "slowest_operation": slowest.operation_name,
                        "slowest_duration_ms": round(slowest.duration_ms, 2),
                        "median_duration_ms": round(median, 2),
                        "amplification_factor": round(factor, 2),
                        "concurrent_count": len(timed),
                    },
                )
            )
        return findings


# ── helpers ──────────────────────────────────────────────────────────────


def _has_concurrent_cluster(spans: list[SpanInfo], min_size: int) -> bool:
    """Sweep line: find any instant at which ≥ min_size spans are active."""
    events: list[tuple[int, int]] = []
    for s in spans:
        start = s.start_time_us or 0
        end = int(start + s.duration_ms * 1000)
        events.append((start, +1))
        events.append((end, -1))
    events.sort()
    active = 0
    for _, delta in events:
        active += delta
        if active >= min_size:
            return True
    return False


def _severity_for_factor(factor: float) -> str:
    if factor >= 5.0:
        return "critical"
    if factor >= 3.0:
        return "high"
    return "medium"


def _confidence_for_factor(factor: float, concurrent_count: int) -> int:
    # Higher factor + more peers → higher confidence.
    base = 55 + min(int((factor - 2.0) * 10), 30)
    peers_bonus = min(concurrent_count - 3, 5)
    return min(base + peers_bonus, 95)
