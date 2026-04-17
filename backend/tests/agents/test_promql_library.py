"""Task 3.7 — PromQL library."""
from __future__ import annotations

import pytest

from src.agents.promql_library import (
    build_golden_signals,
    query_alerts_firing,
    query_offset_baseline,
    query_recording_rule_lag,
    query_scrape_health,
)
from src.tools.promql_safety import UnsafeQuery, validate_promql


class TestGoldenSignals:
    def test_golden_signals_query_includes_p50_p95_p99(self):
        qs = build_golden_signals(namespace="payments", service="api")
        assert "histogram_quantile(0.50" in qs["latency_p50"]
        assert "histogram_quantile(0.95" in qs["latency_p95"]
        assert "histogram_quantile(0.99" in qs["latency_p99"]
        assert "rate(http_requests_total" in qs["traffic_rps"]

    def test_all_queries_pass_safety_middleware(self):
        qs = build_golden_signals(namespace="payments", service="api")
        for q in qs.values():
            validate_promql(q, step_s=60, range_h=1)

    def test_error_rate_uses_clamp_min_to_avoid_divide_by_zero(self):
        qs = build_golden_signals(namespace="payments", service="api")
        assert "clamp_min(" in qs["error_rate"]

    def test_namespace_required(self):
        with pytest.raises(ValueError):
            build_golden_signals(namespace="", service="api")

    def test_quote_injection_rejected(self):
        with pytest.raises(ValueError):
            build_golden_signals(namespace='foo"evil', service="api")


class TestAlertsFiring:
    def test_query_includes_alertstate_firing(self):
        q = query_alerts_firing(namespace="payments")
        assert 'alertstate="firing"' in q
        assert 'namespace="payments"' in q
        validate_promql(q, step_s=60, range_h=1)


class TestScrapeHealth:
    def test_default_job_is_any(self):
        q = query_scrape_health(namespace="payments")
        assert 'job=~".+"' in q
        validate_promql(q, step_s=60, range_h=1)

    def test_custom_job_regex(self):
        q = query_scrape_health(namespace="payments", job="node-exporter")
        assert 'job=~"node-exporter"' in q


class TestOffsetBaseline:
    def test_wraps_query_with_offset(self):
        base = 'sum(rate(http_requests_total{namespace="payments"}[5m]))'
        q = query_offset_baseline(base, hours=24)
        assert "offset 24h" in q
        assert "http_requests_total" in q
        validate_promql(q, step_s=60, range_h=24)

    def test_out_of_range_hours_rejected(self):
        base = 'sum(rate(http_requests_total{namespace="payments"}[5m]))'
        with pytest.raises(ValueError):
            query_offset_baseline(base, hours=0)
        with pytest.raises(ValueError):
            query_offset_baseline(base, hours=200)


class TestRecordingRuleLag:
    def test_query_shape(self):
        q = query_recording_rule_lag(namespace="payments")
        assert "prometheus_rule_evaluation_duration_seconds" in q
        assert 'namespace="payments"' in q
        validate_promql(q, step_s=60, range_h=1)
