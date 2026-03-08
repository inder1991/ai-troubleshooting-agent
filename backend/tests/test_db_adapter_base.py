"""Tests for DatabaseAdapter ABC and MockDatabaseAdapter."""
import pytest
from src.database.models import PerfSnapshot, ActiveQuery, ReplicationSnapshot


@pytest.fixture
def mock_adapter():
    from src.database.adapters.mock_adapter import MockDatabaseAdapter
    return MockDatabaseAdapter(
        engine="postgresql", host="localhost", port=5432, database="testdb",
    )


class TestMockDatabaseAdapter:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, mock_adapter):
        await mock_adapter.connect()
        assert mock_adapter._connected is True
        await mock_adapter.disconnect()
        assert mock_adapter._connected is False

    @pytest.mark.asyncio
    async def test_health_check(self, mock_adapter):
        await mock_adapter.connect()
        health = await mock_adapter.health_check()
        assert health.status == "healthy"
        assert health.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self, mock_adapter):
        health = await mock_adapter.health_check()
        assert health.status == "unreachable"

    @pytest.mark.asyncio
    async def test_get_performance_stats(self, mock_adapter):
        await mock_adapter.connect()
        stats = await mock_adapter.get_performance_stats()
        assert isinstance(stats, PerfSnapshot)
        assert stats.connections_max > 0

    @pytest.mark.asyncio
    async def test_get_active_queries(self, mock_adapter):
        await mock_adapter.connect()
        queries = await mock_adapter.get_active_queries()
        assert isinstance(queries, list)
        assert all(isinstance(q, ActiveQuery) for q in queries)

    @pytest.mark.asyncio
    async def test_get_replication_status(self, mock_adapter):
        await mock_adapter.connect()
        repl = await mock_adapter.get_replication_status()
        assert isinstance(repl, ReplicationSnapshot)

    @pytest.mark.asyncio
    async def test_snapshot_caching(self, mock_adapter):
        """Subsequent calls within TTL should return cached data."""
        await mock_adapter.connect()
        stats1 = await mock_adapter.get_performance_stats()
        stats2 = await mock_adapter.get_performance_stats()
        assert stats1 is stats2

    @pytest.mark.asyncio
    async def test_execute_diagnostic_query(self, mock_adapter):
        await mock_adapter.connect()
        result = await mock_adapter.execute_diagnostic_query("SELECT 1")
        assert result.error is None
        assert result.rows_returned >= 0

    @pytest.mark.asyncio
    async def test_refresh_snapshot_clears_cache(self, mock_adapter):
        await mock_adapter.connect()
        stats1 = await mock_adapter.get_performance_stats()
        await mock_adapter.refresh_snapshot()
        stats2 = await mock_adapter.get_performance_stats()
        # After refresh, new object is fetched
        assert stats1 is not stats2


@pytest.mark.asyncio
async def test_mock_get_table_detail():
    from src.database.adapters.mock_adapter import MockDatabaseAdapter
    adapter = MockDatabaseAdapter(engine="postgresql", host="h", port=5432, database="d")
    await adapter.connect()
    detail = await adapter.get_table_detail("orders")
    assert detail.name == "orders"
    assert len(detail.columns) > 0
    assert len(detail.indexes) > 0
    await adapter.disconnect()
