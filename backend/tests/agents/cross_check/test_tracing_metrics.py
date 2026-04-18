"""Tracing ↔ Metrics divergence checker unit tests."""
from __future__ import annotations

from datetime import datetime, timezone

from src.agents.cross_check import check_tracing_metrics_divergence
from src.agents.cross_check.tracing_metrics import _services_from_metrics
from src.models.schemas import (
    LatencyRegressionHint,
    MetricAnomaly,
    MetricsAnalysisResult,
    SpanInfo,
    TokenUsage,
    TraceAnalysisResult,
)


def _anomaly(promql: str, *, metric="latency", severity="high") -> MetricAnomaly:
    now = datetime.now(timezone.utc)
    return MetricAnomaly(
        metric_name=metric, promql_query=promql, baseline_value=10, peak_value=100,
        spike_start=now, spike_end=now, severity=severity,
        correlation_to_incident="x", confidence_score=80,
    )


def _metrics(anomalies=None) -> MetricsAnalysisResult:
    return MetricsAnalysisResult(
        anomalies=anomalies or [],
        time_series_data={}, chart_highlights=[], negative_findings=[], breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(agent_name="m", input_tokens=0, output_tokens=0, total_tokens=0),
    )


def _trace(
    *,
    failure_service: str | None = None,
    services_in_chain=None,
    baseline_regressions=None,
) -> TraceAnalysisResult:
    fp = None
    if failure_service:
        fp = SpanInfo(
            span_id="fp", service_name=failure_service,
            operation_name="op", duration_ms=100, status="error",
        )
    return TraceAnalysisResult(
        trace_id="t1", total_duration_ms=100, total_services=2, total_spans=5,
        call_chain=[], cascade_path=[], latency_bottlenecks=[], retry_detected=False,
        service_dependency_graph={}, trace_source="jaeger", findings=[],
        negative_findings=[], breadcrumbs=[], overall_confidence=85,
        tokens_used=TokenUsage(agent_name="t", input_tokens=0, output_tokens=0, total_tokens=0),
        failure_point=fp,
        services_in_chain=services_in_chain or [],
        baseline_regressions=baseline_regressions or [],
    )


# ── No-input edge cases ────────────────────────────────────────────────


def test_both_none_returns_empty():
    assert check_tracing_metrics_divergence(None, None) == []


def test_metrics_none_returns_empty():
    assert check_tracing_metrics_divergence(None, _trace(failure_service="x")) == []


def test_trace_none_returns_empty():
    assert check_tracing_metrics_divergence(_metrics([_anomaly('{service="x"}')]), None) == []


def test_both_empty_returns_empty():
    """No anomalies + no trace signals → nothing to compare."""
    assert check_tracing_metrics_divergence(_metrics([]), _trace()) == []


# ── Divergence 1: trace failure service, no metric anomaly ──────────────


def test_trace_failure_not_in_metrics_fires():
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(http{service="other"}[1m])')]),
        _trace(failure_service="payments", services_in_chain=["api", "payments"]),
    )
    kinds = {d.kind for d in divs}
    assert "trace_failure_service_no_metric_anomaly" in kinds
    payments_div = next(d for d in divs
                        if d.kind == "trace_failure_service_no_metric_anomaly")
    assert payments_div.service_name == "payments"
    assert payments_div.severity == "high"


def test_trace_failure_matches_metric_no_fire():
    """Metrics DOES have anomaly on payments → no divergence emitted."""
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(http{service="payments"}[1m])')]),
        _trace(failure_service="payments", services_in_chain=["api", "payments"]),
    )
    assert not any(
        d.kind == "trace_failure_service_no_metric_anomaly" for d in divs
    )


# ── Divergence 2: tracing baseline regression, no metric anomaly ────────


def test_baseline_regression_no_metric_fires():
    hint = LatencyRegressionHint(
        service_name="db", operation_name="SELECT",
        observed_duration_ms=2000, baseline_p99_ms=200, z_score=5.0,
    )
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(cpu{service="api"}[1m])')]),
        _trace(baseline_regressions=[hint]),
    )
    kinds = [d.kind for d in divs]
    assert "trace_baseline_regression_no_metric_anomaly" in kinds


def test_baseline_regression_severity_scales_with_ratio():
    small = LatencyRegressionHint(
        service_name="db", operation_name="SELECT",
        observed_duration_ms=400, baseline_p99_ms=200, z_score=1.0,  # 2×
    )
    big = LatencyRegressionHint(
        service_name="cache", operation_name="GET",
        observed_duration_ms=2000, baseline_p99_ms=200, z_score=9.0,  # 10×
    )
    divs = check_tracing_metrics_divergence(
        _metrics([]),
        _trace(baseline_regressions=[small, big]),
    )
    by_svc = {d.service_name: d for d in divs
              if d.kind == "trace_baseline_regression_no_metric_anomaly"}
    assert by_svc["db"].severity in ("low", "medium")
    assert by_svc["cache"].severity == "critical"


# ── Divergence 3: metric anomaly on a service tracing didn't see ────────


def test_metric_on_service_not_in_trace_fires():
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(http{service="ghost"}[1m])')]),
        _trace(services_in_chain=["api", "payments"]),
    )
    kinds = [d.kind for d in divs]
    assert "metric_anomaly_service_absent_from_trace" in kinds
    ghost = next(d for d in divs
                 if d.kind == "metric_anomaly_service_absent_from_trace")
    assert ghost.service_name == "ghost"


def test_metric_on_known_service_no_fire():
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(http{service="api"}[1m])')]),
        _trace(services_in_chain=["api", "payments"]),
    )
    assert not any(
        d.kind == "metric_anomaly_service_absent_from_trace" for d in divs
    )


def test_empty_services_in_chain_suppresses_rule_3():
    """No services_in_chain = tracing may not have run properly;
    can't conclude divergence."""
    divs = check_tracing_metrics_divergence(
        _metrics([_anomaly('rate(http{service="x"}[1m])')]),
        _trace(services_in_chain=[]),
    )
    assert not any(
        d.kind == "metric_anomaly_service_absent_from_trace" for d in divs
    )


# ── PromQL label extraction ─────────────────────────────────────────────


def test_extracts_service_label():
    assert _services_from_metrics([_anomaly('rate({service="x"}[1m])')]) == {"x"}


def test_extracts_app_label():
    assert _services_from_metrics([_anomaly('rate({app="y"}[1m])')]) == {"y"}


def test_extracts_istio_destination_workload():
    assert _services_from_metrics(
        [_anomaly('rate({destination_workload="reviews"}[1m])')]
    ) == {"reviews"}


def test_extracts_multiple_services_from_different_anomalies():
    services = _services_from_metrics([
        _anomaly('rate({service="a"}[1m])'),
        _anomaly('rate({app="b"}[1m])'),
    ])
    assert services == {"a", "b"}


def test_ignores_wildcard():
    assert _services_from_metrics([_anomaly('rate({service="*"}[1m])')]) == set()
