"""Tests for DNS metric write/query methods in MetricsStore."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock influxdb_client before importing
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from src.network.metrics_store import MetricsStore


@pytest.fixture
def store():
    with patch.object(MetricsStore, "__init__", lambda self, *a, **kw: None):
        s = MetricsStore.__new__(MetricsStore)
        s.org = "test-org"
        s.bucket = "test-bucket"
        # Use spec=MetricsStore for the overall object is not needed since we
        # construct via __new__; but we add explicit AsyncMock for sub-APIs
        s._write_api = AsyncMock()
        s._query_api = AsyncMock()
        s._client = AsyncMock()
        s._query_timeout = 30.0
        return s


class TestWriteDNSMetric:
    @pytest.mark.asyncio
    async def test_write_dns_metric_success(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="api.example.com", record_type="A",
            latency_ms=12.5, success=True, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_failure(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="bad.example.com", record_type="A",
            latency_ms=0.0, success=False, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_server_health(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="google.com", record_type="A",
            latency_ms=3.2, success=True, metric_type="server_health",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_handles_influx_error(self, store):
        store._write_api.write.side_effect = Exception("connection refused")
        # Should not raise
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="api.example.com", record_type="A",
            latency_ms=5.0, success=True, metric_type="query",
        )


class TestQueryDNSMetrics:
    @pytest.mark.asyncio
    async def test_query_dns_metrics_returns_data(self, store):
        mock_record = MagicMock()
        mock_record.get_time.return_value = MagicMock(isoformat=lambda: "2026-03-06T12:00:00Z")
        mock_record.get_value.return_value = 12.5
        mock_record.values = {"hostname": "api.example.com", "server_id": "dns-1"}
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        store._query_api.query = AsyncMock(return_value=[mock_table])

        data = await store.query_dns_metrics(
            server_id="dns-1", hostname="api.example.com", range_str="1h",
        )
        assert len(data) == 1
        assert data[0]["value"] == 12.5
        # Verify the query was called
        store._query_api.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_dns_metrics_empty(self, store):
        store._query_api.query = AsyncMock(return_value=[])
        data = await store.query_dns_metrics(server_id="dns-1", range_str="1h")
        assert data == []

    @pytest.mark.asyncio
    async def test_query_dns_metrics_handles_error(self, store):
        store._query_api.query = AsyncMock(side_effect=Exception("timeout"))
        data = await store.query_dns_metrics(server_id="dns-1", range_str="1h")
        assert data == []


class TestNegativeCases:
    """Negative tests for DNS metrics edge cases."""

    @pytest.mark.asyncio
    async def test_write_dns_metric_empty_server_id(self, store):
        """Writing with empty server_id should still call write (no crash)."""
        await store.write_dns_metric(
            server_id="", server_ip="8.8.8.8",
            hostname="test.com", record_type="A",
            latency_ms=1.0, success=True, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_zero_latency(self, store):
        """Zero latency should be accepted without error."""
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="test.com", record_type="A",
            latency_ms=0.0, success=True, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_dns_metrics_empty_server_id(self, store):
        """Querying with empty server_id should return empty list without error."""
        store._query_api.query = AsyncMock(return_value=[])
        data = await store.query_dns_metrics(server_id="", range_str="1h")
        assert data == []
