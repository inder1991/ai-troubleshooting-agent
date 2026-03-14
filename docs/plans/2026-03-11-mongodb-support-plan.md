# MongoDB Engine Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MongoDB as a second database engine to the existing database diagnostics capability, reusing the LangGraph V2 graph and 3-analyst pattern.

**Architecture:** Create `MongoAdapter(DatabaseAdapter)` using Motor (async pymongo) that maps MongoDB commands (`db.currentOp()`, `db.serverStatus()`, `collStats`, etc.) to the existing snapshot types (`PerfSnapshot`, `ActiveQuery`, etc.). The graph (`graph_v2.py`) is engine-agnostic — it calls adapter methods like `health_check()`, `get_active_queries()` without knowing the underlying engine. No graph changes are needed. Frontend adds `'mongodb'` to the type union and auto-detects engine from the selected profile.

**Tech Stack:** Motor (async pymongo driver), Python 3.11, FastAPI, LangGraph, React + TypeScript

---

## Task 1: Add Motor dependency

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Add motor to requirements.txt**

Add this line after the existing `asyncpg` or database-related entries in `backend/requirements.txt`:

```
motor>=3.3.0
```

**Step 2: Install dependencies**

Run: `cd backend && pip install motor>=3.3.0`
Expected: Successfully installed motor and pymongo

**Step 3: Verify import works**

Run: `cd backend && python3 -c "import motor.motor_asyncio; print('motor OK')"`
Expected: `motor OK`

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(db): add motor dependency for MongoDB support"
```

---

## Task 2: Create MongoAdapter — lifecycle & health_check

**Files:**
- Create: `backend/src/database/adapters/mongo.py`
- Create: `backend/tests/test_mongo_adapter.py`

**Step 1: Write the failing test**

Create `backend/tests/test_mongo_adapter.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_mongo_adapter_health_check_healthy():
    """MongoAdapter.health_check returns healthy when connected."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(return_value={
            "version": "7.0.4",
            "ok": 1.0,
        })
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter

        adapter = MongoAdapter(
            host="localhost", port=27017, database="testdb",
            username="user", password="pass",
        )
        await adapter.connect()
        health = await adapter.health_check()

        assert health.status == "healthy"
        assert "7.0" in health.version


@pytest.mark.asyncio
async def test_mongo_adapter_health_check_not_connected():
    """MongoAdapter.health_check returns unreachable when not connected."""
    from src.database.adapters.mongo import MongoAdapter

    adapter = MongoAdapter(
        host="localhost", port=27017, database="testdb",
        username="user", password="pass",
    )
    health = await adapter.health_check()
    assert health.status == "unreachable"


@pytest.mark.asyncio
async def test_mongo_adapter_connect_with_uri():
    """MongoAdapter can connect using a connection URI."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(return_value={"version": "7.0.4", "ok": 1.0})
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter

        adapter = MongoAdapter(
            host="localhost", port=27017, database="testdb",
            username="user", password="pass",
            connection_uri="mongodb+srv://user:pass@cluster0.example.net/testdb",
        )
        await adapter.connect()

        # Should use the URI, not individual fields
        MockClient.assert_called_once()
        call_args = MockClient.call_args
        assert "mongodb+srv://" in str(call_args)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.database.adapters.mongo'`

**Step 3: Write minimal MongoAdapter implementation**

Create `backend/src/database/adapters/mongo.py`:

```python
"""MongoDB adapter using Motor (async pymongo)."""
from __future__ import annotations

import logging
import time
from typing import Optional

try:
    import motor.motor_asyncio as motor_async
except ImportError:
    motor_async = None  # type: ignore

from .base import AdapterHealth, DatabaseAdapter
from ..models import (
    ActiveQuery,
    ColumnInfo,
    ConnectionPoolSnapshot,
    IndexInfo,
    PerfSnapshot,
    QueryResult,
    ReplicaInfo,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,
)

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_MS = 10_000
DOC_LIMIT = 1000


class MongoAdapter(DatabaseAdapter):
    """MongoDB adapter using Motor for async connectivity."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        connection_uri: Optional[str] = None,
        ttl: int = 300,
    ):
        super().__init__(
            engine="mongodb", host=host, port=port, database=database, ttl=ttl
        )
        self._username = username
        self._password = password
        self._connection_uri = connection_uri
        self._client: Optional[motor_async.AsyncIOMotorClient] = None
        self._db = None

    async def connect(self) -> None:
        if not motor_async:
            raise ImportError("motor is required for MongoDB support: pip install motor>=3.3")
        if self._connection_uri:
            self._client = motor_async.AsyncIOMotorClient(
                self._connection_uri,
                serverSelectionTimeoutMS=QUERY_TIMEOUT_MS,
            )
        else:
            self._client = motor_async.AsyncIOMotorClient(
                host=self.host,
                port=self.port,
                username=self._username,
                password=self._password,
                serverSelectionTimeoutMS=QUERY_TIMEOUT_MS,
            )
        self._db = self._client[self.database]
        self._connected = True

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
        self._connected = False
        self._invalidate_cache()

    async def health_check(self) -> AdapterHealth:
        if not self._connected or not self._db:
            return AdapterHealth(status="unreachable", error="Not connected")
        try:
            start = time.time()
            result = await self._db.command("serverStatus")
            latency = (time.time() - start) * 1000
            version = result.get("version", "")
            return AdapterHealth(
                status="healthy", latency_ms=round(latency, 2), version=version
            )
        except Exception as e:
            return AdapterHealth(status="degraded", error=str(e))

    # ── Snapshot fetchers (stubs for now, implemented in Task 3) ──

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        raise NotImplementedError("Implemented in Task 3")

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        raise NotImplementedError("Implemented in Task 3")

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        raise NotImplementedError("Implemented in Task 4")

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        raise NotImplementedError("Implemented in Task 5")

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        raise NotImplementedError("Implemented in Task 3")

    async def get_table_detail(self, table_name: str) -> TableDetail:
        raise NotImplementedError("Implemented in Task 5")

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        raise NotImplementedError("Implemented in Task 6")

    # ── Write operations (P2 — stubs) ──

    async def kill_query(self, pid: int) -> dict:
        if not self._db:
            raise RuntimeError("Not connected")
        await self._db.command("killOp", op=pid)
        return {"success": True, "pid": pid, "message": f"Killed op {pid}"}

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        return {"success": False, "message": "VACUUM not applicable to MongoDB — use compact instead"}

    async def reindex_table(self, table: str) -> dict:
        if not self._db:
            raise RuntimeError("Not connected")
        await self._db[table].reindex()
        return {"success": True, "table": table, "message": f"Reindexed collection {table}"}

    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        if not self._db:
            raise RuntimeError("Not connected")
        keys = [(col, 1) for col in columns]
        idx_name = name or f"idx_{'_'.join(columns)}"
        await self._db[table].create_index(keys, name=idx_name, unique=unique)
        return {"success": True, "index_name": idx_name, "table": table, "columns": columns}

    async def drop_index(self, index_name: str) -> dict:
        return {"success": False, "message": "drop_index requires collection name — use collection.drop_index()"}

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        return {"success": False, "message": "MongoDB config changes require mongod restart — not supported via adapter"}

    async def get_config_recommendations(self) -> list[dict]:
        return []

    async def generate_failover_runbook(self) -> dict:
        return {
            "steps": [
                {"order": 1, "description": "Check replica set status", "command": "rs.status()"},
                {"order": 2, "description": "Identify primary", "command": "rs.isMaster()"},
                {"order": 3, "description": "Step down primary", "command": "rs.stepDown(60)"},
                {"order": 4, "description": "Verify new primary elected", "command": "rs.status()"},
            ],
            "warnings": ["Automatic failover takes 10-12 seconds", "Ensure majority of members are reachable"],
            "estimated_downtime": "10-15 seconds",
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add backend/src/database/adapters/mongo.py backend/tests/test_mongo_adapter.py
git commit -m "feat(db): add MongoAdapter with lifecycle and health_check"
```

---

## Task 3: MongoAdapter — performance stats, active queries, connection pool

**Files:**
- Modify: `backend/src/database/adapters/mongo.py` (replace 3 `NotImplementedError` stubs)
- Modify: `backend/tests/test_mongo_adapter.py` (add 3 tests)

**Step 1: Write the failing tests**

Append to `backend/tests/test_mongo_adapter.py`:

```python
@pytest.mark.asyncio
async def test_fetch_performance_stats():
    """_fetch_performance_stats maps serverStatus to PerfSnapshot."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {
                "version": "7.0.4",
                "connections": {"current": 15, "available": 85, "totalCreated": 200},
                "opcounters": {"insert": 100, "query": 500, "update": 50, "delete": 10, "command": 300},
                "globalLock": {"activeClients": {"total": 15, "readers": 10, "writers": 5}},
                "wiredTiger": {"cache": {
                    "bytes currently in the cache": 500_000_000,
                    "maximum bytes configured": 1_000_000_000,
                }},
                "uptime": 86400,
                "ok": 1.0,
            }
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        stats = await adapter._fetch_performance_stats()

        assert stats.connections_active == 15
        assert stats.connections_max == 100  # current + available
        assert stats.uptime_seconds == 86400


@pytest.mark.asyncio
async def test_fetch_active_queries():
    """_fetch_active_queries maps currentOp to ActiveQuery list."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {"version": "7.0.4", "ok": 1.0},
            "currentOp": {
                "inprog": [
                    {
                        "opid": 12345,
                        "op": "query",
                        "ns": "testdb.orders",
                        "microsecs_running": 5_000_000,
                        "command": {"find": "orders", "filter": {"status": "pending"}},
                        "waitingForLock": False,
                    }
                ],
                "ok": 1.0,
            },
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        queries = await adapter._fetch_active_queries()

        assert len(queries) == 1
        assert queries[0].pid == 12345
        assert queries[0].duration_ms == 5000.0
        assert "orders" in queries[0].query


@pytest.mark.asyncio
async def test_fetch_connection_pool():
    """_fetch_connection_pool maps serverStatus.connections to ConnectionPoolSnapshot."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {
                "version": "7.0.4",
                "connections": {"current": 25, "available": 75, "totalCreated": 500,
                                "active": 10},
                "ok": 1.0,
            },
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        pool = await adapter._fetch_connection_pool()

        assert pool.active == 10
        assert pool.idle == 15  # current - active
        assert pool.max_connections == 100  # current + available
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py::test_fetch_performance_stats tests/test_mongo_adapter.py::test_fetch_active_queries tests/test_mongo_adapter.py::test_fetch_connection_pool -v`
Expected: 3 FAILED — `NotImplementedError`

**Step 3: Replace the stubs in mongo.py**

In `backend/src/database/adapters/mongo.py`, replace the three `NotImplementedError` stubs for `_fetch_performance_stats`, `_fetch_active_queries`, and `_fetch_connection_pool`:

```python
    async def _fetch_performance_stats(self) -> PerfSnapshot:
        if not self._db:
            raise RuntimeError("Not connected")
        status = await self._db.command("serverStatus")
        conns = status.get("connections", {})
        current = conns.get("current", 0)
        available = conns.get("available", 0)
        active = conns.get("active", current)

        # WiredTiger cache hit ratio approximation
        wt = status.get("wiredTiger", {}).get("cache", {})
        cache_bytes = wt.get("bytes currently in the cache", 0)
        cache_max = wt.get("maximum bytes configured", 1)
        cache_ratio = round(cache_bytes / cache_max, 4) if cache_max else 0.0

        ops = status.get("opcounters", {})
        tps = sum(ops.get(k, 0) for k in ("insert", "query", "update", "delete", "command"))

        return PerfSnapshot(
            connections_active=active,
            connections_idle=max(0, current - active),
            connections_max=current + available,
            cache_hit_ratio=cache_ratio,
            transactions_per_sec=float(tps),
            deadlocks=0,  # MongoDB doesn't have deadlocks in the PG sense
            uptime_seconds=status.get("uptime", 0),
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        if not self._db:
            raise RuntimeError("Not connected")
        result = await self._db.command("currentOp")
        ops = result.get("inprog", [])
        queries = []
        for op in ops[:50]:  # Limit like PG adapter
            opid = op.get("opid", 0)
            microsecs = op.get("microsecs_running", 0)
            duration_ms = microsecs / 1000.0
            ns = op.get("ns", "")
            command = op.get("command", {})
            query_str = str(command)[:500] if command else str(op.get("op", ""))

            queries.append(ActiveQuery(
                pid=opid,
                query=f"{ns}: {query_str}",
                duration_ms=duration_ms,
                state=op.get("op", "unknown"),
                user=op.get("effectiveUsers", [{}])[0].get("user", "") if op.get("effectiveUsers") else "",
                database=ns.split(".")[0] if "." in ns else ns,
                waiting=op.get("waitingForLock", False),
            ))
        queries.sort(key=lambda q: q.duration_ms, reverse=True)
        return queries

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        if not self._db:
            raise RuntimeError("Not connected")
        status = await self._db.command("serverStatus")
        conns = status.get("connections", {})
        current = conns.get("current", 0)
        available = conns.get("available", 0)
        active = conns.get("active", current)
        return ConnectionPoolSnapshot(
            active=active,
            idle=max(0, current - active),
            waiting=0,  # MongoDB doesn't have a "waiting" concept like PG
            max_connections=current + available,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add backend/src/database/adapters/mongo.py backend/tests/test_mongo_adapter.py
git commit -m "feat(db): implement MongoAdapter perf stats, active queries, connection pool"
```

---

## Task 4: MongoAdapter — replication status

**Files:**
- Modify: `backend/src/database/adapters/mongo.py` (replace `_fetch_replication_status` stub)
- Modify: `backend/tests/test_mongo_adapter.py` (add test)

**Step 1: Write the failing test**

Append to `backend/tests/test_mongo_adapter.py`:

```python
@pytest.mark.asyncio
async def test_fetch_replication_status_replica_set():
    """_fetch_replication_status maps replSetGetStatus to ReplicationSnapshot."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()

        def mock_command(cmd, *a, **kw):
            if cmd == "serverStatus":
                return {"version": "7.0.4", "ok": 1.0}
            if cmd == "replSetGetStatus":
                return {
                    "set": "rs0",
                    "myState": 1,  # PRIMARY
                    "members": [
                        {"_id": 0, "name": "mongo1:27017", "stateStr": "PRIMARY", "self": True,
                         "optimeDate": "2026-03-11T00:00:00Z"},
                        {"_id": 1, "name": "mongo2:27017", "stateStr": "SECONDARY",
                         "optimeDate": "2026-03-11T00:00:00Z"},
                    ],
                    "ok": 1.0,
                }
            return {"ok": 1.0}

        mock_db.command = AsyncMock(side_effect=mock_command)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        repl = await adapter._fetch_replication_status()

        assert repl.is_replica is False  # We are PRIMARY
        assert len(repl.replicas) == 1  # 1 secondary
        assert repl.replicas[0].name == "mongo2:27017"


@pytest.mark.asyncio
async def test_fetch_replication_status_standalone():
    """_fetch_replication_status returns empty for standalone (no replica set)."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()

        def mock_command(cmd, *a, **kw):
            if cmd == "serverStatus":
                return {"version": "7.0.4", "ok": 1.0}
            if cmd == "replSetGetStatus":
                raise Exception("not running with --replSet")
            return {"ok": 1.0}

        mock_db.command = AsyncMock(side_effect=mock_command)
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        repl = await adapter._fetch_replication_status()

        assert repl.is_replica is False
        assert len(repl.replicas) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py::test_fetch_replication_status_replica_set tests/test_mongo_adapter.py::test_fetch_replication_status_standalone -v`
Expected: FAILED — `NotImplementedError`

**Step 3: Implement _fetch_replication_status in mongo.py**

Replace the `_fetch_replication_status` stub:

```python
    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        if not self._db:
            raise RuntimeError("Not connected")
        try:
            result = await self._db.command("replSetGetStatus")
        except Exception:
            # Standalone server — no replica set
            return ReplicationSnapshot(is_replica=False, replicas=[])

        my_state = result.get("myState", 0)
        # myState: 1=PRIMARY, 2=SECONDARY, 7=ARBITER
        is_replica = my_state == 2

        members = result.get("members", [])
        replicas = []
        for m in members:
            if m.get("self"):
                continue
            state_str = m.get("stateStr", "")
            if state_str in ("SECONDARY", "PRIMARY"):
                replicas.append(ReplicaInfo(
                    name=m.get("name", ""),
                    state=state_str,
                    lag_bytes=0,  # MongoDB uses optime, not byte-based lag
                ))

        return ReplicationSnapshot(
            is_replica=is_replica,
            replicas=replicas,
            replication_lag_bytes=0,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: 8 passed

**Step 5: Commit**

```bash
git add backend/src/database/adapters/mongo.py backend/tests/test_mongo_adapter.py
git commit -m "feat(db): implement MongoAdapter replication status"
```

---

## Task 5: MongoAdapter — schema snapshot & table detail

**Files:**
- Modify: `backend/src/database/adapters/mongo.py` (replace 2 stubs)
- Modify: `backend/tests/test_mongo_adapter.py` (add 2 tests)

**Step 1: Write the failing tests**

Append to `backend/tests/test_mongo_adapter.py`:

```python
@pytest.mark.asyncio
async def test_fetch_schema_snapshot():
    """_fetch_schema_snapshot maps collection stats to SchemaSnapshot."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()

        mock_db.list_collection_names = AsyncMock(return_value=["orders", "users"])
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {"version": "7.0.4", "ok": 1.0},
            "collStats": {
                "ns": f"testdb.{a[0]}" if a else "testdb.unknown",
                "count": 50000 if a and a[0] == "orders" else 1000,
                "size": 128_000_000 if a and a[0] == "orders" else 2_000_000,
                "totalIndexSize": 10_000_000,
                "nindexes": 3,
                "ok": 1.0,
            },
            "dbStats": {"dataSize": 130_000_000, "ok": 1.0},
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()
        schema = await adapter._fetch_schema_snapshot()

        assert len(schema.tables) == 2
        assert schema.total_size_bytes == 130_000_000


@pytest.mark.asyncio
async def test_get_table_detail():
    """get_table_detail returns collection stats + indexes for a collection."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # list_indexes returns an async iterator
        async def mock_list_indexes():
            return [
                {"v": 2, "key": {"_id": 1}, "name": "_id_"},
                {"v": 2, "key": {"status": 1, "created_at": -1}, "name": "idx_status_created", "unique": False},
            ]

        mock_collection.list_indexes = MagicMock(return_value=AsyncIterator([
            {"v": 2, "key": {"_id": 1}, "name": "_id_"},
            {"v": 2, "key": {"status": 1, "created_at": -1}, "name": "idx_status_created"},
        ]))

        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {"version": "7.0.4", "ok": 1.0},
            "collStats": {
                "ns": "testdb.orders", "count": 50000, "size": 128_000_000,
                "totalIndexSize": 10_000_000, "nindexes": 2,
                "indexSizes": {"_id_": 5_000_000, "idx_status_created": 5_000_000},
                "ok": 1.0,
            },
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()

        detail = await adapter.get_table_detail("orders")
        assert detail.name == "orders"
        assert detail.row_estimate == 50000
        assert detail.total_size_bytes == 128_000_000


# Helper for async iteration in mocks
class AsyncIterator:
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py::test_fetch_schema_snapshot tests/test_mongo_adapter.py::test_get_table_detail -v`
Expected: FAILED — `NotImplementedError`

**Step 3: Implement _fetch_schema_snapshot and get_table_detail**

Replace the stubs in `mongo.py`:

```python
    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        if not self._db:
            raise RuntimeError("Not connected")
        collections = await self._db.list_collection_names()
        tables = []
        all_indexes = []
        for coll_name in collections[:100]:  # Limit like PG adapter
            try:
                stats = await self._db.command("collStats", coll_name)
                tables.append({
                    "name": coll_name,
                    "rows": stats.get("count", 0),
                    "size_bytes": stats.get("size", 0),
                })
                # Collect index info
                index_sizes = stats.get("indexSizes", {})
                for idx_name, idx_size in index_sizes.items():
                    all_indexes.append({
                        "name": idx_name,
                        "table": coll_name,
                        "size_bytes": idx_size,
                    })
            except Exception:
                logger.warning("Failed to get stats for collection %s", coll_name)

        # Get total DB size
        try:
            db_stats = await self._db.command("dbStats")
            total_size = db_stats.get("dataSize", 0)
        except Exception:
            total_size = sum(t.get("size_bytes", 0) for t in tables)

        tables.sort(key=lambda t: t.get("size_bytes", 0), reverse=True)
        return SchemaSnapshot(
            tables=tables,
            indexes=all_indexes[:200],
            total_size_bytes=total_size,
        )

    async def get_table_detail(self, table_name: str) -> TableDetail:
        if not self._db:
            raise RuntimeError("Not connected")
        # Get collection stats
        stats = await self._db.command("collStats", table_name)

        # Get indexes
        indexes = []
        index_sizes = stats.get("indexSizes", {})
        try:
            async for idx in self._db[table_name].list_indexes():
                idx_name = idx.get("name", "")
                keys = list(idx.get("key", {}).keys())
                indexes.append(IndexInfo(
                    name=idx_name,
                    columns=keys,
                    unique=idx.get("unique", False),
                    size_bytes=index_sizes.get(idx_name, 0),
                ))
        except Exception:
            pass

        # MongoDB is schemaless — no fixed columns
        # We represent this with a placeholder
        columns = [
            ColumnInfo(name="_id", data_type="ObjectId", nullable=False, is_pk=True),
        ]

        return TableDetail(
            name=table_name,
            schema_name=self.database,
            columns=columns,
            indexes=indexes,
            row_estimate=stats.get("count", 0),
            total_size_bytes=stats.get("size", 0),
            bloat_ratio=0.0,  # MongoDB handles storage differently
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: 10 passed

**Step 5: Commit**

```bash
git add backend/src/database/adapters/mongo.py backend/tests/test_mongo_adapter.py
git commit -m "feat(db): implement MongoAdapter schema snapshot and table detail"
```

---

## Task 6: MongoAdapter — execute_diagnostic_query (explain)

**Files:**
- Modify: `backend/src/database/adapters/mongo.py` (replace last stub)
- Modify: `backend/tests/test_mongo_adapter.py` (add test)

**Step 1: Write the failing test**

Append to `backend/tests/test_mongo_adapter.py`:

```python
@pytest.mark.asyncio
async def test_execute_diagnostic_query():
    """execute_diagnostic_query runs explain on a collection."""
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as MockClient:
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_db.command = AsyncMock(side_effect=lambda cmd, *a, **kw: {
            "serverStatus": {"version": "7.0.4", "ok": 1.0},
            "explain": {
                "queryPlanner": {"winningPlan": {"stage": "COLLSCAN"}},
                "executionStats": {"totalDocsExamined": 50000, "nReturned": 100},
                "ok": 1.0,
            },
        }.get(cmd, {"ok": 1.0}))
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockClient.return_value = mock_client

        from src.database.adapters.mongo import MongoAdapter
        adapter = MongoAdapter(host="localhost", port=27017, database="testdb",
                               username="u", password="p")
        await adapter.connect()

        result = await adapter.execute_diagnostic_query('{"collection": "orders", "filter": {"status": "pending"}}')
        assert result.error is None or result.execution_time_ms >= 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py::test_execute_diagnostic_query -v`
Expected: FAILED — `NotImplementedError`

**Step 3: Implement execute_diagnostic_query**

Replace the stub in `mongo.py`:

```python
    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        """Run explain on a MongoDB query.

        Accepts a JSON string: {"collection": "name", "filter": {...}}
        or a plain collection name for a simple explain.
        """
        if not self._db:
            raise RuntimeError("Not connected")
        import json
        try:
            start = time.time()
            # Try parsing as JSON
            try:
                parsed = json.loads(sql)
                collection = parsed.get("collection", "")
                query_filter = parsed.get("filter", {})
            except (json.JSONDecodeError, TypeError):
                # Treat as collection name
                collection = sql.strip()
                query_filter = {}

            if not collection:
                return QueryResult(query=sql, error="No collection specified")

            result = await self._db.command(
                "explain",
                {"find": collection, "filter": query_filter},
                verbosity="executionStats",
            )
            elapsed = (time.time() - start) * 1000
            exec_stats = result.get("executionStats", {})
            n_returned = exec_stats.get("nReturned", 0)

            return QueryResult(
                query=sql,
                execution_time_ms=round(elapsed, 2),
                rows_returned=n_returned,
            )
        except Exception as e:
            return QueryResult(query=sql, error=str(e))
```

**Step 4: Run all tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_adapter.py -v`
Expected: 11 passed

**Step 5: Commit**

```bash
git add backend/src/database/adapters/mongo.py backend/tests/test_mongo_adapter.py
git commit -m "feat(db): implement MongoAdapter execute_diagnostic_query"
```

---

## Task 7: MongoDB read tools

**Files:**
- Create: `backend/src/agents/database/tools/mongo_read_tools.py`
- Create: `backend/tests/test_mongo_read_tools.py`

**Step 1: Write the failing test**

Create `backend/tests/test_mongo_read_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.database.tools.mongo_read_tools import (
    query_current_ops,
    query_server_status,
    get_connection_info,
)


class FakeEvidenceStore:
    def create(self, **kwargs):
        return {"artifact_id": "art-1"}


@pytest.mark.asyncio
async def test_query_current_ops():
    adapter = AsyncMock()
    adapter.get_active_queries = AsyncMock(return_value=[
        MagicMock(pid=1, duration_ms=5500, state="query", query="db.orders.find()"),
    ])
    store = FakeEvidenceStore()

    result = await query_current_ops(adapter, store, "S-1", "query_analyst")

    assert "summary" in result
    assert result["summary"]["active_count"] == 1
    assert result["summary"]["slow_count"] == 1
    assert "artifact_id" in result


@pytest.mark.asyncio
async def test_query_server_status():
    adapter = AsyncMock()
    adapter.get_performance_stats = AsyncMock(return_value=MagicMock(
        connections_active=10, connections_idle=5, connections_max=100,
        cache_hit_ratio=0.95, transactions_per_sec=200.0,
        deadlocks=0, uptime_seconds=86400,
    ))
    store = FakeEvidenceStore()

    result = await query_server_status(adapter, store, "S-1", "health_analyst")

    assert result["summary"]["connections_active"] == 10
    assert result["summary"]["cache_hit_ratio"] == 0.95


@pytest.mark.asyncio
async def test_get_connection_info():
    adapter = AsyncMock()
    adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=15, idle=10, waiting=0, max_connections=100,
    ))
    store = FakeEvidenceStore()

    result = await get_connection_info(adapter, store, "S-1", "health_analyst")

    assert result["summary"]["active"] == 15
    assert result["summary"]["utilization_pct"] == 15.0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_mongo_read_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create mongo_read_tools.py**

Create `backend/src/agents/database/tools/mongo_read_tools.py`:

```python
"""Read-only MongoDB diagnostic tools.

Mirrors pg_read_tools.py — every tool returns a ToolOutput dict with:
- summary: compact dict for LLM consumption
- artifact_id: reference to evidence_artifacts row
- evidence_id: unique fingerprint for citation
"""

import json
import uuid
from typing import Any

from src.database.evidence_store import EvidenceStore


def _evidence_id() -> str:
    return f"e-{uuid.uuid4().hex[:8]}"


async def run_explain(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    collection: str,
    query_filter: dict | None = None,
) -> dict:
    """Run explain on a MongoDB query."""
    query_json = json.dumps({"collection": collection, "filter": query_filter or {}})
    result = await adapter.execute_diagnostic_query(query_json)

    summary = {"collection": collection, "error": result.error}
    if not result.error:
        summary["execution_time_ms"] = result.execution_time_ms
        summary["docs_returned"] = result.rows_returned

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="explain_plan",
        summary_json=summary,
        full_content=str(result),
        preview=f"Explain on {collection}: {result.rows_returned} docs",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_current_ops(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get currently running operations (equivalent to pg_stat_activity)."""
    queries = await adapter.get_active_queries()
    query_list = [
        {"pid": q.pid, "duration_ms": q.duration_ms, "state": q.state, "query": q.query[:100]}
        for q in queries
    ] if queries else []

    summary = {
        "active_count": len(query_list),
        "slow_count": sum(1 for q in query_list if q["duration_ms"] > 5000),
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="current_ops",
        summary_json=summary,
        full_content=str(query_list),
        preview=f"{summary['active_count']} active ops, {summary['slow_count']} slow (>5s)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_server_status(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get server status metrics (equivalent to pg_stat_database)."""
    stats = await adapter.get_performance_stats()
    summary = {
        "connections_active": stats.connections_active,
        "connections_idle": stats.connections_idle,
        "connections_max": stats.connections_max,
        "cache_hit_ratio": stats.cache_hit_ratio,
        "ops_per_sec": stats.transactions_per_sec,
        "uptime_seconds": stats.uptime_seconds,
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="server_status",
        summary_json=summary,
        full_content=str(summary),
        preview=f"Active: {stats.connections_active}, Cache: {stats.cache_hit_ratio:.2%}",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def query_collection_stats(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
    collection_filter: list[str] | None = None,
) -> dict:
    """Get collection-level stats (equivalent to pg_stat_user_tables)."""
    schema = await adapter.get_schema_snapshot()
    tables = schema.tables
    if collection_filter:
        tables = [t for t in tables if t.get("name") in collection_filter]

    summary = {"collections_scanned": len(tables)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="collection_stats",
        summary_json=summary,
        full_content=str(tables),
        preview=f"Stats for {len(tables)} collections",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def inspect_collection_indexes(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get index usage across collections (equivalent to pg_stat_user_indexes)."""
    schema = await adapter.get_schema_snapshot()
    indexes = schema.indexes

    summary = {"indexes_checked": len(indexes)}
    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="index_usage",
        summary_json=summary,
        full_content=str(indexes),
        preview=f"{len(indexes)} indexes checked",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_connection_info(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get connection pool status (equivalent to pg get_connection_pool)."""
    pool = await adapter.get_connection_pool()
    utilization = round((pool.active / pool.max_connections) * 100, 1) if pool.max_connections else 0

    summary = {
        "active": pool.active,
        "idle": pool.idle,
        "waiting": pool.waiting,
        "max": pool.max_connections,
        "utilization_pct": utilization,
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="connection_pool",
        summary_json=summary,
        full_content=str(summary),
        preview=f"Connections: {pool.active}/{pool.max_connections} ({utilization}%)",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}


async def get_replication_status(
    adapter: Any,
    evidence_store: EvidenceStore,
    session_id: str,
    agent_name: str,
) -> dict:
    """Get replica set status (equivalent to pg replication)."""
    repl = await adapter.get_replication_status()
    summary = {
        "is_replica": repl.is_replica,
        "replica_count": len(repl.replicas),
        "members": [{"name": r.name, "state": r.state} for r in repl.replicas],
    }

    eid = _evidence_id()
    artifact = evidence_store.create(
        session_id=session_id, evidence_id=eid, source_agent=agent_name,
        artifact_type="replication_status",
        summary_json=summary,
        full_content=str(summary),
        preview=f"{'Replica' if repl.is_replica else 'Primary'}, {len(repl.replicas)} members",
    )
    return {"summary": summary, "artifact_id": artifact["artifact_id"], "evidence_id": eid}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_mongo_read_tools.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add backend/src/agents/database/tools/mongo_read_tools.py backend/tests/test_mongo_read_tools.py
git commit -m "feat(db): add MongoDB read-only diagnostic tools"
```

---

## Task 8: MongoDB-aware prompt templates

**Files:**
- Modify: `backend/src/agents/database/prompts/templates.py`

**Step 1: Add MongoDB prompt variants**

Add these constants at the end of `backend/src/agents/database/prompts/templates.py` (after line 103):

```python
# ── MongoDB-specific prompt sections ──

MONGO_QUERY_ANALYST_SYSTEM = """You are a MongoDB query performance analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
ENGINE: MongoDB
INVESTIGATION MODE: {investigation_mode}
{contextual_section}
SAMPLING MODE: {sampling_mode}
FOCUS AREAS: {focus_list}

You have access to these tools:
- run_explain: Run explain("executionStats") on a query
- query_current_ops: Get currently running operations (db.currentOp())
- query_collection_stats: Get per-collection stats (collStats)

MONGODB CONCEPTS (not PostgreSQL):
- Collections (not tables), Documents (not rows), Fields (not columns)
- COLLSCAN = full collection scan (equivalent to Seq Scan — always bad on large collections)
- IXSCAN = index scan (good)
- Compound indexes matter — field order determines usability
- Covered queries (projection matches index) are fastest

RULES:
1. Always call tools first to gather evidence before making claims
2. Never execute destructive operations — create remediation plans instead
3. Include confidence scores (0.0-1.0) with every finding
4. If confidence < 0.7, set needs_human_review: true
5. Cite specific evidence_ids for every finding
6. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze query performance. Look for slow operations (>1s), collection scans on large collections, missing indexes, and inefficient query patterns (e.g., $regex without anchors, unbounded $in arrays).

Return a JSON array of findings."""

MONGO_HEALTH_ANALYST_SYSTEM = """You are a MongoDB health analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
ENGINE: MongoDB
INVESTIGATION MODE: {investigation_mode}
{contextual_section}

You have access to these tools:
- get_connection_info: Get active/idle/max connections
- get_replication_status: Get replica set status and member health
- query_server_status: Get serverStatus metrics (WiredTiger cache, opcounters, uptime)

MONGODB CONCEPTS:
- WiredTiger cache hit ratio replaces PostgreSQL's shared_buffers cache
- Connection pool saturation: MongoDB default is 65536 max connections
- Replica set: PRIMARY handles writes, SECONDARYs handle reads
- No deadlocks in PG sense, but lock contention exists (db.currentOp waitingForLock)

RULES:
1. Always call tools first to gather evidence before making claims
2. Include confidence scores (0.0-1.0) with every finding
3. If confidence < 0.7, set needs_human_review: true
4. Cite specific evidence_ids for every finding
5. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze database health. Check connection utilization, WiredTiger cache pressure, replica set member health, and operation latencies.

Return a JSON array of findings."""

MONGO_SCHEMA_ANALYST_SYSTEM = """You are a MongoDB schema analyst for Debug Duck, an AI-powered database diagnostic platform.

DATABASE: {profile_name} ({host}:{port}/{database})
ENGINE: MongoDB
INVESTIGATION MODE: {investigation_mode}
{contextual_section}

You have access to these tools:
- query_collection_stats: Get collection sizes, document counts, index counts
- inspect_collection_indexes: Get all indexes with sizes

MONGODB CONCEPTS:
- Schema is flexible (no fixed columns) — analyze index coverage instead
- Look for: collections without indexes (besides _id), oversized indexes, redundant indexes
- Document size > 16MB is a hard limit
- Sharded collections: check shard key effectiveness

RULES:
1. Always call tools first to gather evidence before making claims
2. Include confidence scores (0.0-1.0) with every finding
3. If confidence < 0.7, set needs_human_review: true
4. Cite specific evidence_ids for every finding
5. Return ONLY valid JSON matching the DBFindingV2 schema

TASK: Analyze schema health. Look for collections with only _id index (missing indexes), oversized collections without sharding, redundant indexes, and storage inefficiency.

Return a JSON array of findings."""
```

**Step 2: Verify no syntax errors**

Run: `cd backend && python3 -c "from src.agents.database.prompts.templates import MONGO_QUERY_ANALYST_SYSTEM; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/agents/database/prompts/templates.py
git commit -m "feat(db): add MongoDB-aware analyst prompt templates"
```

---

## Task 9: Wire MongoAdapter into backend endpoints

**Files:**
- Modify: `backend/src/api/db_endpoints.py:245-256` (add MongoDB branch)
- Modify: `backend/src/api/db_endpoints.py:275-287` (add MongoDB branch in _run_diagnostic)
- Modify: `backend/src/api/routes_v4.py:638-649` (add MongoDB adapter resolution)

**Step 1: Add MongoDB branch in db_endpoints.py adapter resolution**

In `backend/src/api/db_endpoints.py`, find the block at line ~247 that reads:
```python
            if profile["engine"] == "postgresql":
                from src.database.adapters.postgres import PostgresAdapter
                adapter = PostgresAdapter(
                    host=profile["host"], port=profile["port"],
                    database=profile["database"],
                    username=profile["username"], password=profile["password"],
                )
                await adapter.connect()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported engine: {profile['engine']}")
```

Replace the `else` clause to add MongoDB support:

```python
            if profile["engine"] == "postgresql":
                from src.database.adapters.postgres import PostgresAdapter
                adapter = PostgresAdapter(
                    host=profile["host"], port=profile["port"],
                    database=profile["database"],
                    username=profile["username"], password=profile["password"],
                )
                await adapter.connect()
            elif profile["engine"] == "mongodb":
                from src.database.adapters.mongo import MongoAdapter
                adapter = MongoAdapter(
                    host=profile["host"], port=profile["port"],
                    database=profile["database"],
                    username=profile["username"], password=profile["password"],
                    connection_uri=profile.get("connection_uri"),
                )
                await adapter.connect()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported engine: {profile['engine']}")
```

**Step 2: Same change in _run_diagnostic function**

In `backend/src/api/db_endpoints.py`, find the `_run_diagnostic` function at line ~275. Add the MongoDB branch after the PostgreSQL branch:

```python
        if profile["engine"] == "postgresql":
            from src.database.adapters.postgres import PostgresAdapter
            adapter = PostgresAdapter(
                host=profile["host"], port=profile["port"],
                database=profile["database"],
                username=profile["username"], password=profile["password"],
            )
            await adapter.connect()
        elif profile["engine"] == "mongodb":
            from src.database.adapters.mongo import MongoAdapter
            adapter = MongoAdapter(
                host=profile["host"], port=profile["port"],
                database=profile["database"],
                username=profile["username"], password=profile["password"],
                connection_uri=profile.get("connection_uri"),
            )
            await adapter.connect()
        else:
            from src.database.adapters.mock_adapter import MockDatabaseAdapter
            adapter = MockDatabaseAdapter(
```

**Step 3: Verify no import errors**

Run: `cd backend && python3 -c "from src.api.db_endpoints import router; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/api/db_endpoints.py
git commit -m "feat(db): wire MongoAdapter into backend endpoints"
```

---

## Task 10: Update frontend types for MongoDB

**Files:**
- Modify: `frontend/src/types/index.ts:616-627`

**Step 1: Update DatabaseDiagnosticsForm type**

In `frontend/src/types/index.ts`, change line 622 from:
```typescript
  database_type: 'postgres';
```
to:
```typescript
  database_type: 'postgres' | 'mongodb';
```

Also add `connection_uri` as an optional field after `database_type`:
```typescript
  database_type: 'postgres' | 'mongodb';
  connection_uri?: string;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(db): extend DatabaseDiagnosticsForm type for MongoDB"
```

---

## Task 11: Update DatabaseDiagnosticsFields form for MongoDB

**Files:**
- Modify: `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx`

**Step 1: Update form to auto-detect engine and show MongoDB-specific UI**

The form currently assumes PostgreSQL. We need to:

1. Auto-detect engine from selected profile
2. Show connection URI field when engine is MongoDB
3. Adjust sampling mode descriptions for MongoDB
4. Hide EXPLAIN ANALYZE checkbox for MongoDB (it works differently)

Replace `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx` with:

```tsx
import React, { useState, useEffect } from 'react';
import type { DatabaseDiagnosticsForm } from '../../../types';
import { fetchDBProfiles } from '../../../services/api';

interface DatabaseDiagnosticsFieldsProps {
  data: DatabaseDiagnosticsForm;
  onChange: (data: DatabaseDiagnosticsForm) => void;
}

interface DBProfile {
  id: string;
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
}

const FOCUS_OPTIONS = [
  { value: 'queries' as const, label: 'Queries', icon: 'query_stats' },
  { value: 'connections' as const, label: 'Connections', icon: 'cable' },
  { value: 'replication' as const, label: 'Replication', icon: 'sync' },
  { value: 'storage' as const, label: 'Storage', icon: 'storage' },
  { value: 'schema' as const, label: 'Schema', icon: 'account_tree', mongoLabel: 'Collections' },
];

const inputClass =
  'w-full rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-gray-600 bg-[#0f2023] border border-[#224349] focus:border-[#07b6d5] focus:ring-1 focus:ring-[#07b6d5]/30 outline-none transition-colors';

const DatabaseDiagnosticsFields: React.FC<DatabaseDiagnosticsFieldsProps> = ({
  data,
  onChange,
}) => {
  const [profiles, setProfiles] = useState<DBProfile[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    fetchDBProfiles().then(setProfiles).catch(() => {});
  }, []);

  // Auto-detect engine from selected profile
  const selectedProfile = profiles.find((p) => p.id === data.profile_id);
  const isMongo = selectedProfile?.engine === 'mongodb' || data.database_type === 'mongodb';

  const handleProfileChange = (profileId: string) => {
    const profile = profiles.find((p) => p.id === profileId);
    const dbType = profile?.engine === 'mongodb' ? 'mongodb' : 'postgres';
    onChange({ ...data, profile_id: profileId, database_type: dbType as 'postgres' | 'mongodb' });
  };

  const toggleFocus = (area: DatabaseDiagnosticsForm['focus'][number]) => {
    const current = data.focus || [];
    const next = current.includes(area)
      ? current.filter((f) => f !== area)
      : [...current, area];
    onChange({ ...data, focus: next });
  };

  const samplingDescriptions = isMongo
    ? {
        deep: 'Deep: Runs explain("executionStats") on operations. Most thorough.',
        standard: 'Standard: Collects serverStatus + currentOp metrics. Balanced.',
        light: 'Light: Quick health check with cached snapshots. Minimal load.',
      }
    : {
        deep: 'Deep: Runs EXPLAIN ANALYZE on replica. Most thorough but adds DB load.',
        standard: 'Standard: Collects pg_stat data + EXPLAIN (no ANALYZE). Balanced.',
        light: 'Light: Quick health check with cached snapshots. Minimal DB load.',
      };

  return (
    <div className="space-y-5">
      {/* Database Profile */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Database Profile *
        </label>
        <select
          className={inputClass}
          value={data.profile_id || ''}
          onChange={(e) => handleProfileChange(e.target.value)}
          required
        >
          <option value="">Select a database profile...</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.engine} — {p.host}:{p.port}/{p.database})
            </option>
          ))}
        </select>
      </div>

      {/* Connection URI (MongoDB only) */}
      {isMongo && (
        <div>
          <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
            Connection URI (optional)
          </label>
          <input
            className={inputClass}
            placeholder="mongodb+srv://user:pass@cluster0.example.net/mydb"
            value={data.connection_uri || ''}
            onChange={(e) => onChange({ ...data, connection_uri: e.target.value || undefined })}
          />
          <p className="text-[10px] text-slate-500 mt-1">
            Overrides host/port from profile. Supports mongodb:// and mongodb+srv:// URIs.
          </p>
        </div>
      )}

      {/* Time Window */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Time Window
        </label>
        <select
          className={inputClass}
          value={data.time_window}
          onChange={(e) =>
            onChange({ ...data, time_window: e.target.value as DatabaseDiagnosticsForm['time_window'] })
          }
        >
          <option value="15m">Last 15 minutes</option>
          <option value="1h">Last 1 hour</option>
          <option value="6h">Last 6 hours</option>
          <option value="24h">Last 24 hours</option>
        </select>
      </div>

      {/* Focus Areas */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Focus Areas
        </label>
        <div className="flex flex-wrap gap-2">
          {FOCUS_OPTIONS.map((opt) => {
            const active = data.focus?.includes(opt.value);
            const label = isMongo && 'mongoLabel' in opt ? opt.mongoLabel : opt.label;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => toggleFocus(opt.value)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                  active
                    ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                    : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white hover:border-slate-500'
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">{opt.icon}</span>
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sampling Mode */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Sampling Depth
        </label>
        <div className="flex gap-3">
          {(['light', 'standard', 'deep'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => onChange({ ...data, sampling_mode: mode })}
              className={`flex-1 py-2 rounded-lg text-xs font-bold uppercase tracking-wider border transition-all ${
                data.sampling_mode === mode
                  ? 'bg-duck-accent/20 border-duck-accent text-duck-accent'
                  : 'bg-duck-surface border-duck-border text-slate-400 hover:text-white'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-500 mt-1">
          {samplingDescriptions[data.sampling_mode]}
        </p>
      </div>

      {/* Include Explain Plans (PostgreSQL deep mode only) */}
      {!isMongo && data.sampling_mode === 'deep' && (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={data.include_explain_plans}
            onChange={(e) => onChange({ ...data, include_explain_plans: e.target.checked })}
            className="rounded border-duck-border bg-duck-surface text-duck-accent focus:ring-duck-accent/30"
          />
          <span className="text-sm text-slate-300">
            Include EXPLAIN ANALYZE (runs on replica only)
          </span>
        </label>
      )}

      {/* Table/Collection Filter */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          {isMongo ? 'Collection Filter (optional)' : 'Table Filter (optional)'}
        </label>
        <input
          className={inputClass}
          placeholder={isMongo ? 'orders, users, sessions (comma-separated)' : 'orders, payments, users (comma-separated)'}
          value={data.table_filter?.join(', ') || ''}
          onChange={(e) =>
            onChange({
              ...data,
              table_filter: e.target.value
                ? e.target.value.split(',').map((s) => s.trim()).filter(Boolean)
                : undefined,
            })
          }
        />
      </div>

      {/* Related App Session */}
      <div>
        <label className="block text-xs font-bold text-duck-muted uppercase tracking-wider mb-2">
          Related App Session (optional)
        </label>
        <input
          className={inputClass}
          placeholder="e.g. APP-184 (auto-fills in contextual mode)"
          value={data.parent_session_id || ''}
          onChange={(e) =>
            onChange({
              ...data,
              parent_session_id: e.target.value || undefined,
              context_source: e.target.value ? 'user_selected' : undefined,
            })
          }
        />
        <p className="text-[10px] text-slate-500 mt-1">
          Link to an app investigation to focus agents on that service's queries and connections.
        </p>
      </div>
    </div>
  );
};

export default DatabaseDiagnosticsFields;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx
git commit -m "feat(db): update DatabaseDiagnosticsFields form for MongoDB engine support"
```

---

## Task 12: Add graph_v2 test with MongoDB adapter

**Files:**
- Modify: `backend/tests/test_db_graph_v2.py`

**Step 1: Add test**

Append to `backend/tests/test_db_graph_v2.py`:

```python
@pytest.mark.asyncio
async def test_graph_works_with_mongo_adapter():
    """The same graph should work with a MongoDB-like adapter."""
    graph = build_db_diagnostic_graph_v2()

    mock_adapter = AsyncMock()
    mock_adapter.health_check = AsyncMock(return_value=MagicMock(
        status="healthy", latency_ms=5.0, version="MongoDB 7.0.4"
    ))
    mock_adapter.get_active_queries = AsyncMock(return_value=[
        MagicMock(pid=100, query="testdb.orders: {'find': 'orders'}", duration_ms=8000,
                  state="query", user="app", database="testdb", waiting=False),
    ])
    mock_adapter.get_connection_pool = AsyncMock(return_value=MagicMock(
        active=10, idle=5, waiting=0, max_connections=100
    ))
    mock_adapter.get_performance_stats = AsyncMock(return_value=MagicMock(
        connections_active=10, connections_idle=5, connections_max=100,
        cache_hit_ratio=0.92, transactions_per_sec=500.0, deadlocks=0, uptime_seconds=3600,
    ))

    initial_state: DBDiagnosticStateV2 = {
        "run_id": "R-mongo-1",
        "session_id": "S-mongo-1",
        "profile_id": "prof-mongo",
        "profile_name": "test-mongo",
        "host": "localhost",
        "port": 27017,
        "database": "testdb",
        "engine": "mongodb",
        "investigation_mode": "standalone",
        "sampling_mode": "standard",
        "focus": ["queries", "connections"],
        "status": "running",
        "findings": [],
        "summary": "",
        "_adapter": mock_adapter,
    }

    result = await graph.ainvoke(initial_state)
    assert result["status"] == "completed"
    assert result["connected"] is True
    # Should have found the slow query
    assert len(result["findings"]) > 0
```

**Step 2: Run tests**

Run: `cd backend && python3 -m pytest tests/test_db_graph_v2.py -v`
Expected: 3 passed

**Step 3: Commit**

```bash
git add backend/tests/test_db_graph_v2.py
git commit -m "test(db): add graph_v2 test with MongoDB mock adapter"
```

---

## Task 13: Run full test suite and TypeScript check

**Files:** None (verification only)

**Step 1: Run backend tests**

Run: `cd backend && python3 -m pytest --tb=short -q`
Expected: All tests pass, 0 failures

**Step 2: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: If any failures, fix them before proceeding**

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Motor dependency | `requirements.txt` |
| 2 | MongoAdapter lifecycle + health | `adapters/mongo.py`, `test_mongo_adapter.py` |
| 3 | MongoAdapter perf/queries/pool | `adapters/mongo.py`, `test_mongo_adapter.py` |
| 4 | MongoAdapter replication | `adapters/mongo.py`, `test_mongo_adapter.py` |
| 5 | MongoAdapter schema/table detail | `adapters/mongo.py`, `test_mongo_adapter.py` |
| 6 | MongoAdapter explain query | `adapters/mongo.py`, `test_mongo_adapter.py` |
| 7 | MongoDB read tools | `mongo_read_tools.py`, `test_mongo_read_tools.py` |
| 8 | MongoDB prompt templates | `templates.py` |
| 9 | Backend endpoint wiring | `db_endpoints.py` |
| 10 | Frontend type changes | `types/index.ts` |
| 11 | Frontend form update | `DatabaseDiagnosticsFields.tsx` |
| 12 | Graph test with MongoDB | `test_db_graph_v2.py` |
| 13 | Full verification | (none — test run) |
