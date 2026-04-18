"""PatternsRunner orchestration tests."""
from __future__ import annotations

from src.agents.tracing.patterns.base import PatternDetector
from src.agents.tracing.patterns_runner import PatternsRunner
from src.models.schemas import PatternFinding, SpanInfo


def _span(span_id, parent=None, duration=10.0, status="ok", service="svc",
          op="op", start_us=None) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name=op,
        duration_ms=duration, status=status, parent_span_id=parent,
        start_time_us=start_us,
    )


def test_empty_trace_returns_empty():
    assert PatternsRunner().run([]) == []


def test_all_detectors_run_on_n_plus_one_case():
    """15 sequential children → N+1 fires; other detectors may also fire."""
    parent = _span("p", service="api", duration=200.0)
    children = [_span(f"c{i}", parent="p", service="db", op="SELECT",
                      duration=5.0, start_us=i * 10_000) for i in range(15)]
    findings = PatternsRunner().run([parent] + children)
    kinds = {f.kind for f in findings}
    assert "n_plus_one" in kinds


def test_sorted_by_severity_then_confidence():
    """Runner should return findings sorted most-severe first."""
    parent = _span("p", parent=None, duration=1000.0)
    # Critical-path hotspot (root at 100%).
    findings = PatternsRunner().run([parent])
    # If any findings, they should be sorted descending.
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    vals = [severity_order.get(f.severity, 0) for f in findings]
    assert vals == sorted(vals, reverse=True)


def test_crashed_detector_does_not_break_others():
    class BrokenDetector:
        kind = "broken"
        def detect(self, spans):
            raise RuntimeError("boom")

    class SuccessDetector:
        kind = "success"
        def detect(self, spans):
            return [PatternFinding(
                kind="n_plus_one", confidence=80, severity="medium",
                human_summary="fine", service_name="x", metadata={},
            )]

    runner = PatternsRunner(detectors=[BrokenDetector(), SuccessDetector()])
    findings = runner.run([_span("s1")])
    assert len(findings) == 1
    assert findings[0].kind == "n_plus_one"


def test_hints_for_metrics_returns_only_baseline():
    from src.agents.tracing.patterns.baseline_regression import BaselineRegressionDetector

    def fetcher(svc, op):
        return (100.0, 50)

    runner = PatternsRunner(baseline_fetcher=fetcher)
    spans = [_span("s1", service="api", op="op", duration=500.0)]
    findings = runner.run(spans)
    # Only baseline finding should produce hints.
    baseline_findings = [f for f in findings if f.kind == "baseline_latency_regression"]
    hints = runner.hints_for_metrics(findings)
    assert len(hints) == len(baseline_findings)
