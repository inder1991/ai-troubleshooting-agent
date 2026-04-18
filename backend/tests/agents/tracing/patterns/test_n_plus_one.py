"""NPlusOneDetector unit tests."""
from __future__ import annotations

from src.agents.tracing.patterns.n_plus_one import NPlusOneDetector
from src.models.schemas import SpanInfo


def _span(span_id, service="db", op="SELECT", parent="p", duration=5.0,
          status="ok", start_us=None) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name=op,
        duration_ms=duration, status=status, parent_span_id=parent,
        start_time_us=start_us,
    )


def test_detects_classic_n_plus_one():
    """15 sequential SELECTs under one parent → fires."""
    parent = _span("p", service="api", op="GET /users", parent=None)
    children = [
        _span(f"c{i}", start_us=1_000 + i * 10_000)  # non-overlapping
        for i in range(15)
    ]
    findings = NPlusOneDetector().detect([parent] + children)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "n_plus_one"
    assert f.metadata["child_count"] == 15
    assert f.service_name == "db"


def test_below_threshold_does_not_fire():
    parent = _span("p", service="api", parent=None)
    children = [_span(f"c{i}") for i in range(9)]  # 9 < default 10
    assert NPlusOneDetector().detect([parent] + children) == []


def test_concurrent_children_excluded():
    """Overlapping windows → fan-out territory, not N+1."""
    parent = _span("p", service="api", parent=None)
    # All start at same time — maximally concurrent.
    children = [_span(f"c{i}", duration=100.0, start_us=1_000) for i in range(15)]
    findings = NPlusOneDetector().detect([parent] + children)
    assert findings == []


def test_different_operations_do_not_merge():
    """Same parent, mix of SELECT/UPDATE/DELETE → each op tallied separately."""
    parent = _span("p", service="api", parent=None)
    selects = [_span(f"s{i}", op="SELECT", start_us=i * 10_000) for i in range(12)]
    updates = [_span(f"u{i}", op="UPDATE", start_us=(i + 20) * 10_000) for i in range(5)]
    findings = NPlusOneDetector().detect([parent] + selects + updates)
    # Only SELECTs cross threshold.
    assert len(findings) == 1
    assert findings[0].metadata["operation"] == "SELECT"


def test_severity_scales_with_count():
    parent = _span("p", service="api", parent=None)
    tiny = [_span(f"t{i}", start_us=i * 10_000) for i in range(12)]
    big = [_span(f"b{i}", start_us=i * 10_000) for i in range(55)]
    t_findings = NPlusOneDetector().detect([parent] + tiny)
    b_findings = NPlusOneDetector().detect([parent] + big)
    assert t_findings[0].severity in ("low", "medium")
    assert b_findings[0].severity in ("high", "critical")


def test_no_start_time_still_works():
    """Spans without start_time_us should still be eligible for N+1 detection."""
    parent = _span("p", service="api", parent=None, start_us=None)
    children = [_span(f"c{i}", start_us=None) for i in range(12)]
    findings = NPlusOneDetector().detect([parent] + children)
    # Without start times we can't prove concurrency, so N+1 fires (conservative).
    assert len(findings) == 1
