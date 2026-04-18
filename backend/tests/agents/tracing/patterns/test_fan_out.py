"""FanOutDetector unit tests."""
from __future__ import annotations

from src.agents.tracing.patterns.fan_out import FanOutDetector
from src.models.schemas import SpanInfo


def _span(span_id, service="svc", duration=10.0, parent="p", start_us=1_000) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name="call",
        duration_ms=duration, status="ok", parent_span_id=parent,
        start_time_us=start_us,
    )


def test_detects_slow_leg_dominating():
    """5 concurrent children, 1 is 5× slower → fires."""
    parent = _span("p", parent=None, duration=500.0)
    peers = [_span(f"c{i}", service=f"svc{i}", duration=20.0, start_us=1_000) for i in range(4)]
    slow = _span("slow", service="laggard", duration=500.0, start_us=1_000)
    findings = FanOutDetector().detect([parent] + peers + [slow])
    assert len(findings) == 1
    f = findings[0]
    assert f.metadata["slowest_child_span_id"] == "slow"
    assert f.metadata["amplification_factor"] >= 2.0
    assert f.service_name == "laggard"


def test_sequential_children_excluded():
    """Non-overlapping children → not fan-out (that's N+1 or serial)."""
    parent = _span("p", parent=None)
    # Each child starts after the previous one ends.
    children = [
        _span(f"c{i}", duration=10.0, start_us=1_000 + i * 100_000)
        for i in range(5)
    ]
    assert FanOutDetector().detect([parent] + children) == []


def test_below_k_threshold():
    """< K concurrent children → no finding."""
    parent = _span("p", parent=None)
    children = [_span(f"c{i}", duration=10.0, start_us=1_000) for i in range(2)]  # K=3 default
    assert FanOutDetector().detect([parent] + children) == []


def test_below_amplification_threshold():
    """All children similar duration → no amplification."""
    parent = _span("p", parent=None)
    children = [_span(f"c{i}", duration=50.0, start_us=1_000) for i in range(5)]
    assert FanOutDetector().detect([parent] + children) == []


def test_spans_without_start_time_ignored():
    parent = _span("p", parent=None, start_us=None)
    children = [_span(f"c{i}", duration=10.0, start_us=None) for i in range(5)]
    assert FanOutDetector().detect([parent] + children) == []


def test_severity_scales_with_amplification_factor():
    parent = _span("p", parent=None)
    peers = [_span(f"c{i}", duration=10.0, start_us=1_000) for i in range(4)]

    # 3× slower = high
    slow_3x = _span("slow", duration=30.0, start_us=1_000)
    f1 = FanOutDetector().detect([parent] + peers + [slow_3x])[0]

    # 10× slower = critical
    slow_10x = _span("slow2", duration=100.0, start_us=1_000)
    f2 = FanOutDetector().detect([parent] + peers + [slow_10x])[0]

    # Critical trumps high.
    order = {"medium": 2, "high": 3, "critical": 4}
    assert order[f2.severity] >= order[f1.severity]
