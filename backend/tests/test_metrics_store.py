# backend/tests/test_metrics_store.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.network.metrics_store import MetricsStore


@pytest.fixture
def mock_influx():
    with patch("src.network.metrics_store.InfluxDBClientAsync") as MockClient:
        client = MockClient.return_value
        client.write_api.return_value = AsyncMock()
        client.query_api.return_value = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        client.close = AsyncMock()
        yield client, MockClient


@pytest.mark.asyncio
async def test_write_device_metric(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    await store.write_device_metric("dev-1", "cpu_pct", 85.0)
    client.write_api.return_value.write.assert_called_once()


@pytest.mark.asyncio
async def test_write_link_metric(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    await store.write_link_metric("dev-1", "dev-2", bytes=1000, packets=10, latency_ms=5.0)
    client.write_api.return_value.write.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_success(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    assert await store.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure(mock_influx):
    client, MockClient = mock_influx
    client.ping = AsyncMock(side_effect=Exception("connection refused"))
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    assert await store.health_check() is False


@pytest.mark.asyncio
async def test_graceful_write_failure(mock_influx):
    """Writes should not raise if InfluxDB is down -- just log warning."""
    client, MockClient = mock_influx
    client.write_api.return_value.write = AsyncMock(side_effect=Exception("timeout"))
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    # Should not raise
    await store.write_device_metric("dev-1", "cpu_pct", 85.0)
