"""Tests for InfluxDB query timeout handling."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_query_timeout_returns_empty():
    from src.network.metrics_store import MetricsStore

    store = MetricsStore.__new__(MetricsStore)
    store.bucket = "test"
    store._query_api = AsyncMock()
    store._write_api = AsyncMock()
    store._query_timeout = 0.1  # 100ms

    async def slow_query(*args, **kwargs):
        await asyncio.sleep(5)

    store._query_api.query = slow_query

    result = await store.query_device_metrics("dev-1", "cpu_pct", "1h")
    assert result == []


@pytest.mark.asyncio
async def test_query_succeeds_within_timeout():
    from src.network.metrics_store import MetricsStore

    store = MetricsStore.__new__(MetricsStore)
    store.bucket = "test"
    store._query_timeout = 30.0

    mock_record = MagicMock()
    mock_record.get_time.return_value = MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z")
    mock_record.get_value.return_value = 42.0
    mock_table = MagicMock()
    mock_table.records = [mock_record]
    store._query_api = AsyncMock()
    store._query_api.query = AsyncMock(return_value=[mock_table])

    result = await store.query_device_metrics("dev-1", "cpu_pct", "1h")
    assert len(result) == 1
    assert result[0]["value"] == 42.0
