"""BaselineRegressionDetector unit tests."""
from __future__ import annotations

from src.agents.tracing.patterns.baseline_regression import BaselineRegressionDetector
from src.models.schemas import SpanInfo


def _span(duration, service="api", op="op") -> SpanInfo:
    return SpanInfo(
        span_id="s", service_name=service, operation_name=op,
        duration_ms=duration, status="ok",
    )


def test_no_fetcher_means_no_findings():
    """Without a baseline fetcher → gracefully returns nothing."""
    d = BaselineRegressionDetector(fetcher=None)
    assert d.detect([_span(5000.0)]) == []


def test_fires_when_duration_exceeds_baseline():
    """observed 4000ms vs baseline 200ms → 20× → fires."""
    def fetcher(svc, op):
        return (200.0, 100)  # p99_ms, sample_count
    d = BaselineRegressionDetector(fetcher=fetcher)
    findings = d.detect([_span(4000.0)])
    assert len(findings) == 1
    f = findings[0]
    assert f.severity in ("high", "critical")
    assert f.metadata["ratio"] > 10.0
    assert f.metadata["observed_duration_ms"] == 4000.0


def test_within_baseline_no_finding():
    def fetcher(svc, op):
        return (500.0, 100)
    d = BaselineRegressionDetector(fetcher=fetcher)
    assert d.detect([_span(300.0)]) == []


def test_low_sample_count_baseline_skipped():
    """Baseline with < 10 samples isn't trustworthy → skip."""
    def fetcher(svc, op):
        return (200.0, 5)
    d = BaselineRegressionDetector(fetcher=fetcher)
    assert d.detect([_span(5000.0)]) == []


def test_as_hints_converts_findings():
    def fetcher(svc, op):
        return (200.0, 100)
    d = BaselineRegressionDetector(fetcher=fetcher)
    findings = d.detect([_span(2000.0)])
    hints = d.as_hints(findings)
    assert len(hints) == 1
    h = hints[0]
    assert h.observed_duration_ms == 2000.0
    assert h.baseline_p99_ms == 200.0
    assert h.z_score > 0
