"""Tests for PostgresAdapter (unit tests with mocked asyncpg)."""
import pytest
from unittest.mock import AsyncMock, patch
from src.database.models import PerfSnapshot


@pytest.fixture
def pg_adapter():
    from src.database.adapters.postgres import PostgresAdapter
    return PostgresAdapter(
        host="localhost", port=5432, database="testdb",
        username="user", password="pass",
    )


class TestPostgresAdapter:
    @pytest.mark.asyncio
    @patch("src.database.adapters.postgres.asyncpg")
    async def test_connect(self, mock_asyncpg, pg_adapter):
        mock_conn = AsyncMock()
        mock_asyncpg.connect = AsyncMock(return_value=mock_conn)
        await pg_adapter.connect()
        assert pg_adapter._connected is True
        mock_asyncpg.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, pg_adapter):
        health = await pg_adapter.health_check()
        assert health.status == "unreachable"

    @pytest.mark.asyncio
    @patch("src.database.adapters.postgres.asyncpg")
    async def test_fetch_performance_stats(self, mock_asyncpg, pg_adapter):
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "active": 12, "idle": 5, "max": 100,
            "ratio": 0.94, "tps": 150.0, "deadlocks": 0, "uptime": 86400,
        })
        mock_asyncpg.connect = AsyncMock(return_value=mock_conn)
        await pg_adapter.connect()
        stats = await pg_adapter._fetch_performance_stats()
        assert isinstance(stats, PerfSnapshot)
        assert stats.connections_active == 12

    @pytest.mark.asyncio
    @patch("src.database.adapters.postgres.asyncpg")
    async def test_fetch_active_queries(self, mock_asyncpg, pg_adapter):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"pid": 1001, "query": "SELECT 1", "duration_ms": 500,
             "state": "active", "usename": "app", "datname": "testdb", "waiting": False},
        ])
        mock_asyncpg.connect = AsyncMock(return_value=mock_conn)
        await pg_adapter.connect()
        queries = await pg_adapter._fetch_active_queries()
        assert len(queries) == 1
        assert queries[0].pid == 1001

    @pytest.mark.asyncio
    @patch("src.database.adapters.postgres.asyncpg")
    async def test_execute_diagnostic_query(self, mock_asyncpg, pg_adapter):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"col": "val"}])
        mock_asyncpg.connect = AsyncMock(return_value=mock_conn)
        await pg_adapter.connect()
        result = await pg_adapter.execute_diagnostic_query("SELECT 1")
        assert result.error is None
