"""RetryClusterDetector unit tests."""
from __future__ import annotations

from src.agents.tracing.patterns.retry_cluster import RetryClusterDetector
from src.models.schemas import SpanInfo


def _span(span_id, status="ok", start_us=1_000, error=None, service="api") -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name="call_downstream",
        duration_ms=50.0, status=status, parent_span_id="p",
        start_time_us=start_us, error_message=error,
    )


def test_detects_retry_cluster():
    """3 attempts, first 2 fail, final succeeds → retry cluster."""
    spans = [
        SpanInfo(span_id="p", service_name="api", operation_name="x",
                 duration_ms=100.0, status="ok"),
        _span("a1", status="error", start_us=1_000, error="timeout"),
        _span("a2", status="error", start_us=2_000, error="timeout"),
        _span("a3", status="ok", start_us=3_000),
    ]
    findings = RetryClusterDetector().detect(spans)
    assert len(findings) == 1
    f = findings[0]
    assert f.metadata["attempts"] == 3
    assert f.metadata["final_outcome"] == "ok"
    assert f.metadata["first_error_message"] == "timeout"


def test_single_attempt_is_not_a_cluster():
    spans = [
        SpanInfo(span_id="p", service_name="api", operation_name="x",
                 duration_ms=100.0, status="ok"),
        _span("a1", status="error", start_us=1_000, error="x"),
    ]
    assert RetryClusterDetector().detect(spans) == []


def test_all_succeed_is_not_a_cluster():
    """3 same-op spans, all ok → just N concurrent siblings, not retries."""
    spans = [
        SpanInfo(span_id="p", service_name="api", operation_name="x",
                 duration_ms=100.0, status="ok"),
        _span("a1", status="ok", start_us=1_000),
        _span("a2", status="ok", start_us=2_000),
        _span("a3", status="ok", start_us=3_000),
    ]
    assert RetryClusterDetector().detect(spans) == []


def test_all_failing_marked_critical():
    spans = [
        SpanInfo(span_id="p", service_name="api", operation_name="x",
                 duration_ms=100.0, status="ok"),
        _span("a1", status="error", start_us=1_000, error="boom"),
        _span("a2", status="error", start_us=2_000, error="boom"),
        _span("a3", status="error", start_us=3_000, error="boom"),
    ]
    findings = RetryClusterDetector().detect(spans)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].metadata["all_failed"] is True


def test_different_services_do_not_cluster():
    """Retries are same (service, op) from same parent — different services
    means different downstreams, not retries."""
    spans = [
        SpanInfo(span_id="p", service_name="api", operation_name="x",
                 duration_ms=100.0, status="ok"),
        _span("a1", status="error", service="db1"),
        _span("a2", status="error", service="db2"),
        _span("a3", status="error", service="db3"),
    ]
    assert RetryClusterDetector().detect(spans) == []
