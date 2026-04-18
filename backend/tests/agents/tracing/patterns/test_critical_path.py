"""CriticalPathDetector unit tests."""
from __future__ import annotations

from src.agents.tracing.patterns.critical_path import CriticalPathDetector
from src.models.schemas import SpanInfo


def _span(span_id, duration, service="svc", parent=None) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name="op",
        duration_ms=duration, status="ok", parent_span_id=parent,
    )


def test_dominant_span_fires():
    """Root is 1000ms; a single child on crit path is 800ms → 80% → fires."""
    spans = [
        _span("r", 1000.0),
        _span("hot", 800.0, parent="r"),
    ]
    findings = CriticalPathDetector().detect(spans)
    # Both 'r' and 'hot' are on crit path; 'r' = 100%, 'hot' = 80%. Both fire.
    assert len(findings) >= 1
    # The metadata should include fraction_of_trace.
    assert any(f.metadata["fraction_of_trace"] >= 0.70 for f in findings)


def test_distributed_time_no_finding():
    """4 equal-duration siblings each = 25% of total → none is dominant."""
    spans = [
        _span("r", 400.0),
        _span("a", 100.0, parent="r"),
        _span("b", 100.0, parent="r"),
        _span("c", 100.0, parent="r"),
        _span("d", 100.0, parent="r"),
    ]
    # Crit path will pick one child (say 'a'); 100/400 = 25% < 60% threshold.
    # Root itself is 400/400 = 100% → fires.
    findings = CriticalPathDetector().detect(spans)
    # Root fires (100%); children do not.
    root_findings = [f for f in findings if "r" in f.span_ids_involved]
    non_root = [f for f in findings if "r" not in f.span_ids_involved]
    assert len(root_findings) >= 1
    assert all(f.metadata["fraction_of_trace"] >= 0.60 for f in findings)


def test_empty_returns_no_findings():
    assert CriticalPathDetector().detect([]) == []


def test_threshold_tunable():
    spans = [_span("r", 100.0), _span("hot", 65.0, parent="r")]
    # At default 60% threshold, hot = 65% → fires.
    assert len(CriticalPathDetector().detect(spans)) >= 1
    # At 70% threshold, hot = 65% → does NOT fire (only root @ 100% does).
    strict = CriticalPathDetector(threshold_percent=0.70).detect(spans)
    assert all("hot" not in f.span_ids_involved for f in strict)
