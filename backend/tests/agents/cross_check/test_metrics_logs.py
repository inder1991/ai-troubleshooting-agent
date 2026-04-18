"""Metrics ↔ Logs divergence checker unit tests."""
from __future__ import annotations

from datetime import datetime, timezone

from src.agents.cross_check import check_metrics_logs_divergence
from src.agents.cross_check.metrics_logs import (
    _clusters_from_logs,
    _looks_like_nonmetric_service,
    _services_from_metrics,
)
from src.models.schemas import (
    ErrorPattern,
    LogAnalysisResult,
    MetricAnomaly,
    MetricsAnalysisResult,
    TokenUsage,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _anomaly(promql: str, *, metric="latency", severity="high") -> MetricAnomaly:
    now = datetime.now(timezone.utc)
    return MetricAnomaly(
        metric_name=metric,
        promql_query=promql,
        baseline_value=10,
        peak_value=100,
        spike_start=now,
        spike_end=now,
        severity=severity,
        correlation_to_incident="x",
        confidence_score=80,
    )


def _metrics(anomalies=None) -> MetricsAnalysisResult:
    return MetricsAnalysisResult(
        anomalies=anomalies or [],
        time_series_data={},
        chart_highlights=[],
        negative_findings=[],
        breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(agent_name="m", input_tokens=0, output_tokens=0, total_tokens=0),
    )


def _pattern(
    *,
    exception="NullPointerException",
    frequency=10,
    affected=("checkout-service",),
    severity="high",
    pid="p1",
) -> ErrorPattern:
    return ErrorPattern(
        pattern_id=pid,
        exception_type=exception,
        error_message="boom",
        frequency=frequency,
        severity=severity,
        affected_components=list(affected),
        sample_logs=[],
        confidence_score=85,
        priority_rank=1,
        priority_reasoning="top",
    )


def _logs(*, primary=None, secondary=None) -> LogAnalysisResult:
    return LogAnalysisResult(
        primary_pattern=primary if primary is not None else _pattern(),
        secondary_patterns=list(secondary or []),
        negative_findings=[],
        breadcrumbs=[],
        overall_confidence=80,
        tokens_used=TokenUsage(agent_name="l", input_tokens=0, output_tokens=0, total_tokens=0),
    )


# ── No-input edge cases ────────────────────────────────────────────────


def test_both_none_returns_empty():
    assert check_metrics_logs_divergence(None, None) == []


def test_metrics_none_returns_empty():
    assert check_metrics_logs_divergence(None, _logs()) == []


def test_logs_none_returns_empty():
    assert check_metrics_logs_divergence(_metrics(), None) == []


def test_no_metric_services_no_log_services_returns_empty():
    # No anomalies, and a log pattern with no affected_components → nothing to compare.
    logs = _logs(primary=_pattern(affected=()))
    assert check_metrics_logs_divergence(_metrics([]), logs) == []


# ── Divergence 1: metric anomaly, silent logs ──────────────────────────


def test_d1_fires_when_metric_service_absent_from_logs():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("checkout-service",)))

    findings = check_metrics_logs_divergence(metrics, logs)

    d1 = [f for f in findings if f.kind == "metric_anomaly_no_error_logs"]
    assert len(d1) == 1
    assert d1[0].service_name == "payments-api"
    assert "payments-api" in d1[0].human_summary


def test_d1_silent_when_metric_service_also_in_logs():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("payments-api",)))

    findings = check_metrics_logs_divergence(metrics, logs)

    assert not [f for f in findings if f.kind == "metric_anomaly_no_error_logs"]


def test_d1_silent_when_logs_have_no_services_at_all():
    """If log_agent found nothing, 'silent logs' isn't informative."""
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=()))

    findings = check_metrics_logs_divergence(metrics, logs)

    assert not [f for f in findings if f.kind == "metric_anomaly_no_error_logs"]


# ── Divergence 2: log error cluster, no metric anomaly ─────────────────


def test_d2_fires_when_log_service_has_cluster_but_no_metric_anomaly():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("checkout-service",), frequency=15))

    findings = check_metrics_logs_divergence(metrics, logs)

    d2 = [f for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"]
    assert len(d2) == 1
    assert d2[0].service_name == "checkout-service"
    assert d2[0].metadata["pattern_frequency"] == 15


def test_d2_suppressed_below_min_frequency():
    """Single stray exception shouldn't fire a divergence."""
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("checkout-service",), frequency=1))

    findings = check_metrics_logs_divergence(metrics, logs)

    assert not [f for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"]


def test_d2_silent_when_metrics_found_nothing():
    """Metrics produced no anomalies at all → collection outage, not
    per-service gap. Don't per-service-blame."""
    metrics = _metrics([])  # empty
    logs = _logs(primary=_pattern(affected=("checkout-service",), frequency=15))

    findings = check_metrics_logs_divergence(metrics, logs)

    assert not [f for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"]


def test_d2_fans_out_secondary_patterns():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(
        primary=_pattern(affected=("payments-api",), frequency=20, pid="p1"),
        secondary=[
            _pattern(affected=("checkout-service",), frequency=10, pid="p2"),
            _pattern(affected=("user-service",), frequency=5, pid="p3"),
        ],
    )

    findings = check_metrics_logs_divergence(metrics, logs)

    d2_services = sorted(
        f.service_name for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"
    )
    assert d2_services == ["checkout-service", "user-service"]


# ── Divergence 3: log service not in metrics at all (blind spot) ───────


def test_d3_fires_for_url_path_style_service_name():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("/api/checkout",), frequency=10))

    findings = check_metrics_logs_divergence(metrics, logs)

    d3 = [f for f in findings if f.kind == "log_error_service_not_in_metrics"]
    assert len(d3) == 1
    assert d3[0].service_name == "/api/checkout"


def test_d3_silent_for_normal_service_name():
    """A clean service name is a D2 (coverage gap), not a D3 (blind spot)."""
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(affected=("checkout-service",), frequency=10))

    findings = check_metrics_logs_divergence(metrics, logs)

    assert not [f for f in findings if f.kind == "log_error_service_not_in_metrics"]


# ── Helpers ────────────────────────────────────────────────────────────


def test_services_from_metrics_parses_common_conventions():
    anomalies = [
        _anomaly('http_requests_total{service="a"}'),
        _anomaly('rate(x{app="b"}[1m])'),
        _anomaly('sum by (destination_workload) (istio_requests_total{destination_workload="c"})'),
        _anomaly('up{job="d"}'),
    ]
    assert _services_from_metrics(anomalies) == {"a", "b", "c", "d"}


def test_services_from_metrics_ignores_wildcard():
    anomalies = [_anomaly('up{service="*"}')]
    assert _services_from_metrics(anomalies) == set()


def test_clusters_from_logs_fans_out_affected_components():
    logs = _logs(
        primary=_pattern(affected=("a", "b"), frequency=5, pid="p1"),
        secondary=[_pattern(affected=("c",), frequency=3, pid="p2")],
    )
    pairs = _clusters_from_logs(logs)
    services = sorted(svc for svc, _ in pairs)
    assert services == ["a", "b", "c"]


def test_looks_like_nonmetric_service():
    assert _looks_like_nonmetric_service("/api/x") is True
    assert _looks_like_nonmetric_service("human readable name") is True
    assert _looks_like_nonmetric_service("checkout-service") is False
    assert _looks_like_nonmetric_service("payments_api") is False


# ── Severity capping ───────────────────────────────────────────────────


def test_severity_capped_at_high():
    """Meta-findings shouldn't out-rank source findings, so D2 can't be critical."""
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(
        affected=("checkout-service",), frequency=50, severity="critical",
    ))

    findings = check_metrics_logs_divergence(metrics, logs)
    d2 = [f for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"]
    assert d2 and d2[0].severity in ("high", "medium")


def test_severity_low_for_medium_source():
    metrics = _metrics([_anomaly('rate(errors{service="payments-api"}[5m])')])
    logs = _logs(primary=_pattern(
        affected=("checkout-service",), frequency=5, severity="medium",
    ))

    findings = check_metrics_logs_divergence(metrics, logs)
    d2 = [f for f in findings if f.kind == "log_error_cluster_no_metric_anomaly"]
    assert d2 and d2[0].severity == "medium"
