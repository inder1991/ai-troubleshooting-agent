"""Tests for MongoAdapter using mocked Motor client."""
from __future__ import annotations

import json
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.database.adapters.mongo import MongoAdapter
from src.database.adapters.base import AdapterHealth
from src.database.models import (
    ActiveQuery,
    ConnectionPoolSnapshot,
    PerfSnapshot,
    QueryResult,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,
)


# ── Helper for async iteration (list_indexes) ──

class AsyncIterator:
    """Mock async iterator for Motor cursor results."""

    def __init__(self, items):
        self._items = items
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# ── Fixtures ──

def _make_adapter(**kwargs) -> MongoAdapter:
    defaults = dict(
        host="localhost",
        port=27017,
        database="testdb",
        username="admin",
        password="secret",
    )
    defaults.update(kwargs)
    return MongoAdapter(**defaults)


def _mock_server_status():
    """Return a realistic serverStatus document."""
    return {
        "version": "7.0.4",
        "uptime": 86400,
        "connections": {
            "current": 20,
            "available": 480,
            "active": 12,
        },
        "opcounters": {
            "insert": 1000,
            "query": 5000,
            "update": 2000,
            "delete": 500,
            "getmore": 300,
            "command": 1200,
        },
        "wiredTiger": {
            "cache": {
                "bytes read into cache": 200000,
                "bytes currently in the cache": 800000,
            }
        },
    }


# ── Test: health_check healthy ──

@pytest.mark.asyncio
async def test_mongo_adapter_health_check_healthy():
    adapter = _make_adapter()
    adapter._connected = True

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"version": "7.0.4", "ok": 1})

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.health_check()

    assert isinstance(result, AdapterHealth)
    assert result.status == "healthy"
    assert result.version == "7.0.4"
    assert result.latency_ms >= 0
    assert result.error is None


# ── Test: health_check not connected ──

@pytest.mark.asyncio
async def test_mongo_adapter_health_check_not_connected():
    adapter = _make_adapter()
    adapter._connected = False
    adapter._client = None

    result = await adapter.health_check()

    assert isinstance(result, AdapterHealth)
    assert result.status == "unreachable"
    assert result.error == "Not connected"


# ── Test: connect with URI ──

@pytest.mark.asyncio
async def test_mongo_adapter_connect_with_uri():
    uri = "mongodb://admin:secret@mongo-host:27017/testdb?authSource=admin"
    adapter = _make_adapter(connection_uri=uri)

    with patch("src.database.adapters.mongo.AsyncIOMotorClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.admin.command = AsyncMock(return_value={"ok": 1})
        MockClient.return_value = mock_instance

        await adapter.connect()

        MockClient.assert_called_once_with(
            uri,
            serverSelectionTimeoutMS=10000,
        )
        assert adapter._connected is True


# ── Test: connect without URI ──

@pytest.mark.asyncio
async def test_mongo_adapter_connect_without_uri():
    adapter = _make_adapter()

    with patch("src.database.adapters.mongo.AsyncIOMotorClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.admin.command = AsyncMock(return_value={"ok": 1})
        MockClient.return_value = mock_instance

        await adapter.connect()

        MockClient.assert_called_once_with(
            host="localhost",
            port=27017,
            serverSelectionTimeoutMS=10000,
            username="admin",
            password="secret",
        )
        assert adapter._connected is True


# ── Test: _fetch_performance_stats ──

@pytest.mark.asyncio
async def test_fetch_performance_stats():
    adapter = _make_adapter()
    adapter._connected = True

    server_status = _mock_server_status()

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=server_status)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_performance_stats()

    assert isinstance(result, PerfSnapshot)
    assert result.connections_active == 12
    assert result.connections_idle == 8  # current(20) - active(12)
    assert result.connections_max == 500  # current(20) + available(480)
    assert result.cache_hit_ratio == 0.8  # 800000 / (200000 + 800000)
    assert result.transactions_per_sec == 10000.0  # sum of opcounters
    assert result.deadlocks == 0
    assert result.uptime_seconds == 86400


# ── Test: _fetch_active_queries ──

@pytest.mark.asyncio
async def test_fetch_active_queries():
    adapter = _make_adapter()
    adapter._connected = True

    current_op_result = {
        "inprog": [
            {
                "opid": 12345,
                "microsecs_running": 5000000,  # 5000ms
                "command": {"find": "orders", "filter": {"status": "pending"}},
                "op": "query",
                "waitingForLock": False,
                "ns": "testdb.orders",
                "effectiveUsers": [{"user": "appuser"}],
            },
            {
                "opid": 12346,
                "microsecs_running": 1000000,  # 1000ms
                "command": {"update": "users"},
                "op": "update",
                "waitingForLock": True,
                "ns": "testdb.users",
                "effectiveUsers": [{"user": "admin"}],
            },
        ]
    }

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=current_op_result)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_active_queries()

    assert len(result) == 2
    assert all(isinstance(q, ActiveQuery) for q in result)

    # Should be sorted by duration descending
    assert result[0].pid == 12345
    assert result[0].duration_ms == 5000.0
    assert result[0].state == "query"
    assert result[0].waiting is False
    assert result[0].user == "appuser"
    assert result[0].database == "testdb"

    assert result[1].pid == 12346
    assert result[1].duration_ms == 1000.0
    assert result[1].state == "update"
    assert result[1].waiting is True


# ── Test: _fetch_connection_pool ──

@pytest.mark.asyncio
async def test_fetch_connection_pool():
    adapter = _make_adapter()
    adapter._connected = True

    server_status = _mock_server_status()

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=server_status)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_connection_pool()

    assert isinstance(result, ConnectionPoolSnapshot)
    assert result.active == 12
    assert result.idle == 8  # current(20) - active(12)
    assert result.waiting == 0
    assert result.max_connections == 500  # current(20) + available(480)


# ── Test: _fetch_replication_status with replica set ──

@pytest.mark.asyncio
async def test_fetch_replication_status_replica_set():
    adapter = _make_adapter()
    adapter._connected = True

    rs_status = {
        "set": "rs0",
        "myState": 2,  # SECONDARY
        "members": [
            {
                "name": "mongo-primary:27017",
                "stateStr": "PRIMARY",
                "self": False,
                "optimeDate": datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
            },
            {
                "name": "mongo-secondary-1:27017",
                "stateStr": "SECONDARY",
                "self": True,
                "optimeDate": datetime(2026, 3, 10, 11, 59, 55, tzinfo=timezone.utc),
            },
            {
                "name": "mongo-secondary-2:27017",
                "stateStr": "SECONDARY",
                "self": False,
                "lag": 3,
            },
        ],
    }

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=rs_status)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_replication_status()

    assert isinstance(result, ReplicationSnapshot)
    assert result.is_replica is True
    # Self is excluded; should have 2 replicas (primary + other secondary)
    assert len(result.replicas) == 2
    assert result.replicas[0].name == "mongo-primary:27017"
    assert result.replicas[0].state == "PRIMARY"
    assert result.replicas[1].name == "mongo-secondary-2:27017"
    assert result.replicas[1].state == "SECONDARY"


# ── Test: _fetch_replication_status standalone ──

@pytest.mark.asyncio
async def test_fetch_replication_status_standalone():
    adapter = _make_adapter()
    adapter._connected = True

    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=Exception("not running with --replSet"))

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_replication_status()

    assert isinstance(result, ReplicationSnapshot)
    assert result.is_replica is False
    assert result.replicas == []
    assert result.replication_lag_bytes == 0


# ── Test: _fetch_schema_snapshot ──

@pytest.mark.asyncio
async def test_fetch_schema_snapshot():
    adapter = _make_adapter()
    adapter._connected = True

    async def _mock_command(cmd, *args, **kwargs):
        if cmd == "collStats":
            coll_name = args[0] if args else "unknown"
            return {
                "count": 5000,
                "size": 1024000,
                "storageSize": 512000,
                "avgObjSize": 204,
                "indexSizes": {
                    "_id_": 32768,
                    "idx_status": 16384,
                },
            }
        elif cmd == "dbStats":
            return {
                "dataSize": 2048000,
                "indexSize": 65536,
            }
        return {}

    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=_mock_command)
    mock_db.list_collection_names = AsyncMock(return_value=["orders", "users"])

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter._fetch_schema_snapshot()

    assert isinstance(result, SchemaSnapshot)
    assert len(result.tables) == 2
    assert result.tables[0]["name"] == "orders"
    assert result.tables[0]["rows"] == 5000
    assert result.tables[0]["size_bytes"] == 1024000

    # Each collection has 2 indexes
    assert len(result.indexes) == 4
    assert result.total_size_bytes == 2048000 + 65536


# ── Test: get_table_detail ──

@pytest.mark.asyncio
async def test_get_table_detail():
    adapter = _make_adapter()
    adapter._connected = True

    coll_stats = {
        "count": 10000,
        "size": 2048000,
        "totalIndexSize": 65536,
        "indexSizes": {
            "_id_": 32768,
            "idx_email": 16384,
        },
    }

    mock_indexes = [
        {"name": "_id_", "key": {"_id": 1}, "unique": True},
        {"name": "idx_email", "key": {"email": 1}, "unique": False},
    ]

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=coll_stats)

    mock_collection = MagicMock()
    mock_collection.list_indexes = MagicMock(return_value=AsyncIterator(mock_indexes))
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.get_table_detail("users")

    assert isinstance(result, TableDetail)
    assert result.name == "users"
    assert result.schema_name == "testdb"
    assert result.row_estimate == 10000
    assert result.total_size_bytes == 2048000 + 65536

    # Columns — schemaless, just _id
    assert len(result.columns) == 1
    assert result.columns[0].name == "_id"
    assert result.columns[0].data_type == "ObjectId"
    assert result.columns[0].is_pk is True

    # Indexes
    assert len(result.indexes) == 2
    assert result.indexes[0].name == "_id_"
    assert result.indexes[0].unique is True
    assert result.indexes[0].columns == ["_id"]
    assert result.indexes[0].size_bytes == 32768

    assert result.indexes[1].name == "idx_email"
    assert result.indexes[1].unique is False
    assert result.indexes[1].columns == ["email"]
    assert result.indexes[1].size_bytes == 16384


# ── Test: execute_diagnostic_query ──

@pytest.mark.asyncio
async def test_execute_diagnostic_query():
    adapter = _make_adapter()
    adapter._connected = True

    explain_result = {
        "queryPlanner": {
            "winningPlan": {"stage": "COLLSCAN"},
        },
        "executionStats": {
            "nReturned": 42,
            "executionTimeMillis": 15,
        },
    }

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=explain_result)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    query_input = json.dumps({"collection": "orders", "filter": {"status": "pending"}})
    result = await adapter.execute_diagnostic_query(query_input)

    assert isinstance(result, QueryResult)
    assert result.query == query_input
    assert result.rows_returned == 42
    assert result.execution_time_ms > 0
    assert result.error is None

    # Verify explain was called with correct args
    mock_db.command.assert_called_once_with(
        "explain",
        {"find": "orders", "filter": {"status": "pending"}},
        verbosity="executionStats",
    )


# ── Test: execute_diagnostic_query with plain collection name ──

@pytest.mark.asyncio
async def test_execute_diagnostic_query_plain_collection():
    adapter = _make_adapter()
    adapter._connected = True

    explain_result = {
        "queryPlanner": {"winningPlan": {"stage": "COLLSCAN"}},
        "executionStats": {"nReturned": 100},
    }

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value=explain_result)

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.execute_diagnostic_query("orders")

    assert isinstance(result, QueryResult)
    assert result.rows_returned == 100
    assert result.error is None

    mock_db.command.assert_called_once_with(
        "explain",
        {"find": "orders", "filter": {}},
        verbosity="executionStats",
    )


# ── Test: disconnect invalidates cache ──

@pytest.mark.asyncio
async def test_disconnect_invalidates_cache():
    adapter = _make_adapter()
    adapter._connected = True
    adapter._perf_cache = PerfSnapshot(connections_active=5)
    adapter._snapshot_time = 999999

    mock_client = MagicMock()
    mock_client.close = MagicMock()
    adapter._client = mock_client

    await adapter.disconnect()

    assert adapter._connected is False
    assert adapter._client is None
    assert adapter._perf_cache is None
    assert adapter._snapshot_time == 0


# ── Test: health_check degraded on exception ──

@pytest.mark.asyncio
async def test_health_check_degraded_on_exception():
    adapter = _make_adapter()
    adapter._connected = True

    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=Exception("Connection refused"))

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.health_check()

    assert result.status == "degraded"
    assert "Connection refused" in result.error


# ── Test: kill_query ──

@pytest.mark.asyncio
async def test_kill_query():
    adapter = _make_adapter()
    adapter._connected = True

    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1})

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.kill_query(12345)

    assert result["success"] is True
    assert result["pid"] == 12345
    mock_db.command.assert_called_once_with("killOp", op=12345)


# ── Test: vacuum_table returns not-applicable ──

@pytest.mark.asyncio
async def test_vacuum_table_not_applicable():
    adapter = _make_adapter()
    result = await adapter.vacuum_table("orders")

    assert result["success"] is False
    assert "not applicable" in result["message"].lower()


# ── Test: generate_failover_runbook ──

@pytest.mark.asyncio
async def test_generate_failover_runbook_standalone():
    adapter = _make_adapter()
    adapter._connected = True

    # Mock replication status as standalone (exception → empty snapshot)
    mock_db = MagicMock()
    mock_db.command = AsyncMock(side_effect=Exception("not running with --replSet"))

    mock_client = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    adapter._client = mock_client

    result = await adapter.generate_failover_runbook()

    assert result["is_replica"] is False
    assert result["replica_count"] == 0
    assert len(result["steps"]) >= 1
    assert "rs.initiate" in result["steps"][0]["command"]
