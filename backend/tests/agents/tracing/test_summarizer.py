"""TraceSummarizer deterministic span-budget tests."""
from __future__ import annotations

from src.agents.tracing.summarizer import (
    SummarizerConfig,
    TraceSummarizer,
    SIDECAR_COLLAPSE_DELTA_MS,
)
from src.models.schemas import SpanInfo


def _span(span_id, service="a", op="call", duration=10.0, status="ok",
          parent=None, tags=None) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name=op,
        duration_ms=duration, status=status, parent_span_id=parent, tags=tags or {},
    )


def test_small_trace_passes_through_untouched():
    spans = [_span(f"s{i}", parent=f"s{i-1}" if i else None) for i in range(10)]
    out = TraceSummarizer(SummarizerConfig(max_analysis_spans=20)).summarize(spans)
    assert out.was_summarized is False
    assert out.was_truncated is False
    assert len(out.kept_spans) == 10


def test_empty_trace():
    out = TraceSummarizer().summarize([])
    assert out.kept_spans == []
    assert out.total_original_spans == 0


def test_summarizes_when_over_budget():
    spans = [_span(f"s{i}") for i in range(50)]
    out = TraceSummarizer(SummarizerConfig(max_analysis_spans=10)).summarize(spans)
    assert out.was_summarized is True
    assert len(out.kept_spans) <= 10


def test_preserves_error_spans_always():
    spans = [_span(f"s{i}") for i in range(100)]
    spans[42] = _span("s42", status="error")
    out = TraceSummarizer(SummarizerConfig(max_analysis_spans=20)).summarize(spans)
    assert any(s.span_id == "s42" for s in out.kept_spans), "error span must be kept"


def test_truncation_above_fetched_ceiling():
    spans = [_span(f"s{i}") for i in range(1000)]
    cfg = SummarizerConfig(max_fetched_spans=100, max_analysis_spans=50)
    out = TraceSummarizer(cfg).summarize(spans)
    assert out.was_truncated is True


def test_critical_path_annotated():
    # Build a chain of 5 spans with increasing duration.
    spans = [
        _span("s0", duration=100.0),
        _span("s1", parent="s0", duration=80.0),
        _span("s2", parent="s1", duration=50.0),
        _span("s3", parent="s2", duration=30.0),
        _span("s4", parent="s3", duration=10.0),
    ]
    out = TraceSummarizer().summarize(spans)
    critical_ids = [s.span_id for s in out.kept_spans if s.critical_path]
    # All 5 are on the single chain — all should be marked.
    assert set(critical_ids) == {"s0", "s1", "s2", "s3", "s4"}


def test_sidecar_collapse_merges_pair():
    """App span + matching sidecar span with <50ms delta should collapse."""
    app = _span("app1", service="svc", op="do", duration=100.0,
                tags={"span.kind": "server"})
    sidecar = _span("sc1", service="svc", op="outbound|80|default|svc",
                    duration=105.0, tags={"component": "proxy"})
    out = TraceSummarizer().summarize([app, sidecar])
    assert out.collapsed_sidecar_pairs == 1
    assert len(out.kept_spans) == 1


def test_sidecar_not_collapsed_when_mesh_delta_large():
    """If sidecar diverges from app span by more than threshold, keep both."""
    app = _span("app1", service="svc", op="do", duration=50.0,
                tags={"span.kind": "server"})
    sidecar = _span("sc1", service="svc", op="outbound|80|default|svc",
                    duration=250.0, tags={"component": "proxy"})
    # Delta = 200ms, above SIDECAR_COLLAPSE_DELTA_MS (50).
    assert abs(app.duration_ms - sidecar.duration_ms) > SIDECAR_COLLAPSE_DELTA_MS
    out = TraceSummarizer().summarize([app, sidecar])
    assert out.collapsed_sidecar_pairs == 0
    assert len(out.kept_spans) == 2


def test_buckets_repeated_siblings():
    """Many healthy SAME-service siblings → bucketed (service-boundary rule
    would keep them all otherwise)."""
    parent = _span("p", service="api")
    # Same service as parent → NOT kept as service-boundary; eligible for bucketing.
    siblings = [_span(f"c{i}", service="api", op="internal.step", parent="p", duration=5.0)
                for i in range(30)]
    out = TraceSummarizer(SummarizerConfig(max_analysis_spans=5)).summarize([parent] + siblings)
    assert out.was_summarized is True
    assert len(out.aggregates) >= 1
    bucket = next(b for b in out.aggregates if b.operation_name == "internal.step")
    assert bucket.span_count == 30
