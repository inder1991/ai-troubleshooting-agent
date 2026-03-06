"""Tests for DNSMonitor core — query timing, health checks, and drift detection."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.network.models import (
    DNSMonitorConfig,
    DNSRecordType,
    DNSServerConfig,
    DNSWatchedHostname,
)
from src.network.dns_monitor import DNSMonitor, DNSQueryResult


# ── Fixtures ──

@pytest.fixture
def server():
    return DNSServerConfig(id="dns1", name="Primary DNS", ip="10.0.0.53")


@pytest.fixture
def watched():
    return DNSWatchedHostname(
        hostname="api.example.com",
        record_type=DNSRecordType.A,
        expected_values=["10.1.1.1"],
        critical=True,
    )


@pytest.fixture
def config(server, watched):
    return DNSMonitorConfig(
        servers=[server],
        watched_hostnames=[watched],
        query_timeout=2.0,
        enabled=True,
    )


@pytest.fixture
def monitor(config):
    return DNSMonitor(config)


# ── TestDNSQueryResult ──

class TestDNSQueryResult:
    def test_success_result(self):
        r = DNSQueryResult(
            server_id="dns1",
            server_ip="10.0.0.53",
            hostname="api.example.com",
            record_type="A",
            values=["10.1.1.1"],
            latency_ms=12.5,
            success=True,
        )
        assert r.success is True
        assert r.values == ["10.1.1.1"]
        assert r.latency_ms == 12.5
        assert r.error == ""
        assert r.nxdomain is False

    def test_failure_result(self):
        r = DNSQueryResult(
            server_id="dns1",
            server_ip="10.0.0.53",
            hostname="missing.example.com",
            record_type="A",
            success=False,
            error="NXDOMAIN: missing.example.com",
            nxdomain=True,
        )
        assert r.success is False
        assert r.nxdomain is True
        assert "NXDOMAIN" in r.error
        assert r.values == []


# ── TestDNSMonitor ──

class TestDNSMonitor:
    def test_init(self, monitor, config):
        assert monitor.config is config
        assert monitor.get_nxdomain_counts() == {}

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_query_success(self, mock_resolve, monitor, server, watched):
        mock_resolve.return_value = ["10.1.1.1"]
        result = await monitor.query_hostname(server, watched)
        assert result.success is True
        assert result.values == ["10.1.1.1"]
        assert result.latency_ms >= 0
        assert result.error == ""
        mock_resolve.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_query_nxdomain(self, mock_resolve, monitor, server, watched):
        mock_resolve.side_effect = Exception("NXDOMAIN: api.example.com does not exist")
        result = await monitor.query_hostname(server, watched)
        assert result.success is False
        assert result.nxdomain is True
        assert monitor.get_nxdomain_counts()["api.example.com"] == 1

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_query_timeout(self, mock_resolve, monitor, server, watched):
        mock_resolve.side_effect = Exception("Timeout: query timed out")
        result = await monitor.query_hostname(server, watched)
        assert result.success is False
        assert result.nxdomain is False
        assert "Timeout" in result.error

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_health_check_up(self, mock_resolve, monitor, server):
        mock_resolve.return_value = ["a.root-servers.net."]
        healthy = await monitor.check_server_health(server)
        assert healthy is True
        assert monitor._server_health[server.id] is True

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_health_check_down(self, mock_resolve, monitor, server):
        mock_resolve.side_effect = Exception("Timeout: no response")
        healthy = await monitor.check_server_health(server)
        assert healthy is False
        assert monitor._server_health[server.id] is False

    def test_drift_with_expected_match(self, monitor, watched):
        result = DNSQueryResult(
            server_id="dns1",
            server_ip="10.0.0.53",
            hostname="api.example.com",
            record_type="A",
            values=["10.1.1.1"],
            success=True,
        )
        drift = monitor.detect_drift(result, watched)
        assert drift is None

    def test_drift_with_expected_mismatch(self, monitor, watched):
        result = DNSQueryResult(
            server_id="dns1",
            server_ip="10.0.0.53",
            hostname="api.example.com",
            record_type="A",
            values=["10.2.2.2"],
            success=True,
        )
        drift = monitor.detect_drift(result, watched)
        assert drift is not None
        assert drift["hostname"] == "api.example.com"
        assert "10.1.1.1" in drift["missing"]
        assert "10.2.2.2" in drift["extra"]

    def test_drift_without_expected(self, monitor):
        no_expected = DNSWatchedHostname(hostname="open.example.com")
        result = DNSQueryResult(
            server_id="dns1",
            server_ip="10.0.0.53",
            hostname="open.example.com",
            record_type="A",
            values=["1.2.3.4"],
            success=True,
        )
        drift = monitor.detect_drift(result, no_expected)
        assert drift is None

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_run_pass_metrics(self, mock_resolve, monitor, config):
        mock_resolve.return_value = ["10.1.1.1"]
        metrics = await monitor.run_pass()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["measurement"] == "dns_query"
        assert m["hostname"] == "api.example.com"
        assert m["success"] is True
        assert m["latency_ms"] >= 0
        assert m["drift"] is None
        assert m["critical"] is True

    @pytest.mark.asyncio
    async def test_run_pass_disabled(self):
        cfg = DNSMonitorConfig(enabled=False)
        mon = DNSMonitor(cfg)
        metrics = await mon.run_pass()
        assert metrics == []

    def test_nxdomain_counts_reset(self, monitor):
        monitor._nxdomain_counts["bad.example.com"] = 5
        assert monitor.get_nxdomain_counts() == {"bad.example.com": 5}
        monitor.reset_nxdomain_counts()
        assert monitor.get_nxdomain_counts() == {}
