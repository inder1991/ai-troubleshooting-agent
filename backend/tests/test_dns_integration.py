"""Tests for DNS integration into NetworkMonitor and AlertEngine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor
from src.network.models import (
    DNSServerConfig, DNSWatchedHostname, DNSMonitorConfig, DNSRecordType,
)
from src.network.alert_engine import DEFAULT_RULES


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def adapters():
    return AdapterRegistry()


@pytest.fixture
def dns_config():
    return DNSMonitorConfig(
        servers=[DNSServerConfig(id="dns-1", name="Primary", ip="8.8.8.8")],
        watched_hostnames=[
            DNSWatchedHostname(
                hostname="api.example.com",
                record_type=DNSRecordType.A,
                expected_values=["10.0.0.1"],
                critical=True,
            ),
        ],
    )


class TestDNSPassIntegration:
    @pytest.mark.asyncio
    async def test_monitor_creates_dns_monitor(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        assert monitor.dns_monitor is not None

    @pytest.mark.asyncio
    async def test_monitor_dns_pass_runs(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[])

        await monitor._dns_pass()
        monitor.dns_monitor.run_pass.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_dns_pass_stores_drift(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[{
            "server_id": "dns-1",
            "server_ip": "8.8.8.8",
            "hostname": "api.example.com",
            "record_type": "A",
            "latency_ms": 5.0,
            "success": True,
            "nxdomain": False,
            "critical": True,
            "drift": {
                "expected": ["10.0.0.1"],
                "actual": ["10.0.0.2"],
                "missing": ["10.0.0.1"],
                "extra": ["10.0.0.2"],
            },
        }])

        await monitor._dns_pass()
        drifts = store.list_active_drift_events()
        assert len(drifts) == 1
        assert drifts[0]["drift_type"] == "dns_record_mismatch"

    @pytest.mark.asyncio
    async def test_monitor_without_dns_config(self, store, kg, adapters):
        monitor = NetworkMonitor(store, kg, adapters)
        assert monitor.dns_monitor is None
        # Should not raise
        await monitor._dns_pass()

    @pytest.mark.asyncio
    async def test_collect_cycle_includes_dns(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[])

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock):
            await monitor._collect_cycle()

        monitor.dns_monitor.run_pass.assert_called_once()

    @pytest.mark.asyncio
    async def test_dns_pass_writes_metrics(self, store, kg, adapters, dns_config):
        mock_metrics = AsyncMock()
        mock_metrics.write_dns_metric = AsyncMock()
        monitor = NetworkMonitor(store, kg, adapters, metrics_store=mock_metrics, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[{
            "server_id": "dns-1", "server_ip": "8.8.8.8",
            "hostname": "api.example.com", "record_type": "A",
            "latency_ms": 10.0, "success": True, "nxdomain": False,
            "critical": True, "drift": None,
        }])

        await monitor._dns_pass()
        mock_metrics.write_dns_metric.assert_called_once()


class TestDNSAlertRules:
    def test_default_rules_include_dns(self):
        dns_rules = [r for r in DEFAULT_RULES if r.id.startswith("default-dns")]
        assert len(dns_rules) >= 2

    def test_dns_resolution_failure_rule(self):
        rule = next((r for r in DEFAULT_RULES if r.id == "default-dns-failure"), None)
        assert rule is not None
        assert rule.severity == "critical"
        assert rule.metric == "dns_success"
        assert rule.condition == "lt"

    def test_dns_latency_rule(self):
        rule = next((r for r in DEFAULT_RULES if r.id == "default-dns-latency"), None)
        assert rule is not None
        assert rule.severity == "warning"
        assert rule.metric == "dns_latency_ms"
        assert rule.condition == "gt"
