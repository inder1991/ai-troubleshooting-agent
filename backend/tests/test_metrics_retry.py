"""Tests for MetricsStore retry queue on failed writes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_store():
    """Create a MetricsStore with mocked InfluxDB client."""
    with patch("src.network.metrics_store.InfluxDBClientAsync") as MockClient:
        mock_client = MagicMock()
        mock_write_api = AsyncMock()
        mock_query_api = AsyncMock()
        mock_client.write_api.return_value = mock_write_api
        mock_client.query_api.return_value = mock_query_api
        MockClient.return_value = mock_client

        from src.network.metrics_store import MetricsStore
        store = MetricsStore(
            url="http://localhost:8086",
            token="test-token",
            org="test-org",
            bucket="test-bucket",
        )
        store._mock_write_api = mock_write_api
        yield store


class TestRetryQueue:
    @pytest.mark.asyncio
    async def test_successful_write_does_not_queue(self, mock_store):
        """A successful write should not add to the retry queue."""
        mock_store._mock_write_api.write = AsyncMock()
        await mock_store.write_device_metric("dev-1", "cpu_pct", 55.0)
        assert len(mock_store._retry_queue) == 0

    @pytest.mark.asyncio
    async def test_failed_write_queues_point(self, mock_store):
        """A failed write should add the point to the retry queue."""
        mock_store._mock_write_api.write = AsyncMock(side_effect=ConnectionError("timeout"))
        await mock_store.write_device_metric("dev-1", "cpu_pct", 55.0)
        assert len(mock_store._retry_queue) == 1

    @pytest.mark.asyncio
    async def test_flush_retry_queue_drains_on_success(self, mock_store):
        """flush_retry_queue should drain the queue when writes succeed."""
        # Cause 3 failures
        mock_store._mock_write_api.write = AsyncMock(side_effect=ConnectionError("down"))
        await mock_store.write_device_metric("dev-1", "cpu_pct", 10.0)
        await mock_store.write_device_metric("dev-1", "cpu_pct", 20.0)
        await mock_store.write_device_metric("dev-1", "cpu_pct", 30.0)
        assert len(mock_store._retry_queue) == 3

        # Now fix the write API
        mock_store._mock_write_api.write = AsyncMock()
        flushed = await mock_store.flush_retry_queue()
        assert flushed == 3
        assert len(mock_store._retry_queue) == 0

    @pytest.mark.asyncio
    async def test_flush_retry_queue_keeps_failures(self, mock_store):
        """Items that still fail during flush stay in the queue."""
        mock_store._mock_write_api.write = AsyncMock(side_effect=ConnectionError("down"))
        await mock_store.write_device_metric("dev-1", "cpu_pct", 10.0)
        await mock_store.write_device_metric("dev-1", "cpu_pct", 20.0)
        assert len(mock_store._retry_queue) == 2

        # Flush still fails
        flushed = await mock_store.flush_retry_queue()
        assert flushed == 0
        assert len(mock_store._retry_queue) == 2

    @pytest.mark.asyncio
    async def test_retry_queue_maxlen(self, mock_store):
        """Queue silently drops oldest items when maxlen (1000) is exceeded."""
        assert mock_store._retry_queue.maxlen == 1000

        mock_store._mock_write_api.write = AsyncMock(side_effect=ConnectionError("down"))
        for i in range(1005):
            await mock_store.write_device_metric("dev-1", f"metric_{i}", float(i))

        # Should be capped at 1000
        assert len(mock_store._retry_queue) == 1000

    @pytest.mark.asyncio
    async def test_flush_empty_queue(self, mock_store):
        """Flushing an empty queue returns 0."""
        flushed = await mock_store.flush_retry_queue()
        assert flushed == 0
        assert len(mock_store._retry_queue) == 0

    @pytest.mark.asyncio
    async def test_link_metric_failure_queues(self, mock_store):
        """write_link_metric failures also enqueue."""
        mock_store._mock_write_api.write = AsyncMock(side_effect=IOError("disk full"))
        await mock_store.write_link_metric("sw1", "sw2", bps_in=100.0)
        assert len(mock_store._retry_queue) == 1
