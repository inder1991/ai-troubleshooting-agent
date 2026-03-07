"""Tests for Prometheus metrics exporter and /metrics endpoint."""
from __future__ import annotations

import pytest

from src.network.prometheus_exporter import MetricsCollector


# ═══════════════════════════════════════════════════════════════════
# 1. MetricsCollector instantiation
# ═══════════════════════════════════════════════════════════════════


class TestMetricsCollectorCreation:
    def test_create_metrics_collector(self):
        """Creating a MetricsCollector should not raise."""
        collector = MetricsCollector()
        assert collector is not None


# ═══════════════════════════════════════════════════════════════════
# 2. Recording cycle duration
# ═══════════════════════════════════════════════════════════════════


class TestRecordCycleDuration:
    def test_record_cycle_duration_does_not_raise(self):
        """Recording a cycle duration should succeed without error."""
        collector = MetricsCollector()
        collector.record_cycle_duration(1.5)


# ═══════════════════════════════════════════════════════════════════
# 3. Recording pass duration with different names
# ═══════════════════════════════════════════════════════════════════


class TestRecordPassDuration:
    def test_record_pass_duration_different_names(self):
        """Recording pass durations for different pass names should work."""
        collector = MetricsCollector()
        collector.record_pass_duration("probe", 0.3)
        collector.record_pass_duration("adapter", 0.5)
        collector.record_pass_duration("drift", 0.2)


# ═══════════════════════════════════════════════════════════════════
# 4. Setting device count and active alerts
# ═══════════════════════════════════════════════════════════════════


class TestGaugeMetrics:
    def test_set_device_count(self):
        """Setting the device count gauge should not raise."""
        collector = MetricsCollector()
        collector.set_device_count(42)

    def test_set_active_alerts(self):
        """Setting the active alerts gauge should not raise."""
        collector = MetricsCollector()
        collector.set_active_alerts(7)


# ═══════════════════════════════════════════════════════════════════
# 5. Incrementing adapter errors
# ═══════════════════════════════════════════════════════════════════


class TestAdapterErrors:
    def test_increment_adapter_errors(self):
        """Incrementing adapter errors by type should not raise."""
        collector = MetricsCollector()
        collector.increment_adapter_errors("netbox")
        collector.increment_adapter_errors("meraki")


# ═══════════════════════════════════════════════════════════════════
# 6. generate_metrics() returns text with metric names
# ═══════════════════════════════════════════════════════════════════


class TestGenerateMetrics:
    def test_generate_metrics_contains_metric_names(self):
        """generate_metrics() output must include all registered metric names."""
        collector = MetricsCollector()
        # Record some data so metrics appear in output
        collector.record_cycle_duration(1.0)
        collector.increment_cycle_total()
        collector.record_pass_duration("probe", 0.5)
        collector.set_device_count(10)
        collector.set_active_alerts(2)
        collector.increment_adapter_errors("netbox")

        output = collector.generate_metrics()

        assert isinstance(output, str)
        assert "network_monitor_cycle_duration_seconds" in output
        assert "network_monitor_cycle_total" in output
        assert "network_monitor_pass_duration_seconds" in output
        assert "network_monitor_devices_total" in output
        assert "network_monitor_alerts_active" in output
        assert "network_monitor_adapter_errors_total" in output


# ═══════════════════════════════════════════════════════════════════
# 7. increment_cycle_total() increments counter
# ═══════════════════════════════════════════════════════════════════


class TestCycleTotalCounter:
    def test_increment_cycle_total(self):
        """Calling increment_cycle_total() multiple times should increase the counter."""
        collector = MetricsCollector()
        collector.increment_cycle_total()
        collector.increment_cycle_total()
        collector.increment_cycle_total()

        output = collector.generate_metrics()
        # The counter value should be 3.0
        assert "network_monitor_cycle_total 3.0" in output


# ═══════════════════════════════════════════════════════════════════
# 8. /metrics endpoint returns 200 with metric text
# ═══════════════════════════════════════════════════════════════════


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self):
        """GET /metrics should return 200 with Prometheus text format."""
        from fastapi.testclient import TestClient
        from src.api.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")

        assert resp.status_code == 200
        assert "network_monitor_cycle_duration_seconds" in resp.text
        assert "text/plain" in resp.headers.get("content-type", "")
