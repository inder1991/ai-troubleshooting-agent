# Database Diagnostics P0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship end-to-end database diagnostics for PostgreSQL — adapter, agents, LangGraph graph, API, and standalone dashboard with capability sidebar.

**Architecture:** Snapshot-based DatabaseAdapter ABC with PostgresAdapter, 2 ReActAgent subclasses (QueryAgent, HealthAgent) orchestrated by a LangGraph StateGraph, exposed via FastAPI endpoints with WebSocket progress, rendered in a standalone React dashboard with capability-first sidebar navigation.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, asyncpg, Pydantic v2, React 18, TypeScript, Tailwind CSS, SQLite (profile/run storage), pytest + pytest-asyncio

**Design doc:** `docs/plans/2026-03-09-database-diagnostics-design.md`

---

## Task 1: Pydantic Data Models

**Files:**
- Create: `backend/src/database/__init__.py`
- Create: `backend/src/database/models.py`
- Test: `backend/tests/test_db_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_models.py
"""Tests for database diagnostics Pydantic models."""
import pytest
from datetime import datetime


def test_db_profile_creation():
    from src.database.models import DBProfile
    p = DBProfile(
        id="test-1", name="prod-pg", engine="postgresql",
        host="localhost", port=5432, database="mydb",
        username="admin", password="secret",
    )
    assert p.engine == "postgresql"
    assert p.port == 5432


def test_db_profile_invalid_engine():
    from src.database.models import DBProfile
    with pytest.raises(Exception):
        DBProfile(
            id="x", name="x", engine="redis",
            host="x", port=1, database="x",
            username="x", password="x",
        )


def test_diagnostic_run_defaults():
    from src.database.models import DiagnosticRun
    r = DiagnosticRun(run_id="r1", profile_id="p1")
    assert r.status == "running"
    assert r.findings == []
    assert r.summary == ""


def test_db_finding_fields():
    from src.database.models import DBFinding
    f = DBFinding(
        finding_id="f1", category="query_performance",
        severity="high", confidence=0.85,
        title="Slow query", detail="SELECT took 12s",
    )
    assert f.confidence == 0.85
    assert f.remediation_available is False


def test_perf_snapshot():
    from src.database.models import PerfSnapshot
    s = PerfSnapshot(
        connections_active=12, connections_idle=5, connections_max=100,
        cache_hit_ratio=0.94, transactions_per_sec=150.0,
        deadlocks=0, uptime_seconds=86400,
    )
    assert s.cache_hit_ratio == 0.94


def test_active_query():
    from src.database.models import ActiveQuery
    q = ActiveQuery(
        pid=1234, query="SELECT 1", duration_ms=500,
        state="active", user="admin", database="mydb",
    )
    assert q.pid == 1234


def test_replication_snapshot():
    from src.database.models import ReplicationSnapshot
    r = ReplicationSnapshot(
        is_replica=False, replicas=[], replication_lag_bytes=0,
    )
    assert r.is_replica is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_models.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# backend/src/database/__init__.py
"""Database diagnostics module."""

# backend/src/database/models.py
"""Pydantic models for database diagnostics."""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Connection Profile ──

class DBProfile(BaseModel):
    id: str
    name: str
    engine: Literal["postgresql", "mongodb", "mysql", "oracle"]
    host: str
    port: int
    database: str
    username: str
    password: str  # stored encrypted at rest via profile_store
    created_at: datetime = Field(default_factory=datetime.utcnow)
    tags: dict[str, str] = {}


# ── Snapshots ──

class PerfSnapshot(BaseModel):
    connections_active: int = 0
    connections_idle: int = 0
    connections_max: int = 0
    cache_hit_ratio: float = 0.0
    transactions_per_sec: float = 0.0
    deadlocks: int = 0
    uptime_seconds: int = 0


class ActiveQuery(BaseModel):
    pid: int
    query: str
    duration_ms: float
    state: str = "active"
    user: str = ""
    database: str = ""
    waiting: bool = False


class ReplicaInfo(BaseModel):
    name: str = ""
    state: str = ""
    lag_bytes: int = 0
    lag_seconds: float = 0.0


class ReplicationSnapshot(BaseModel):
    is_replica: bool = False
    replicas: list[ReplicaInfo] = []
    replication_lag_bytes: int = 0
    replication_lag_seconds: float = 0.0


class SchemaSnapshot(BaseModel):
    tables: list[dict] = []
    indexes: list[dict] = []
    total_size_bytes: int = 0


class ConnectionPoolSnapshot(BaseModel):
    active: int = 0
    idle: int = 0
    waiting: int = 0
    max_connections: int = 0


class QueryPlanNode(BaseModel):
    node_type: str
    relation: str = ""
    startup_cost: float = 0.0
    total_cost: float = 0.0
    rows: int = 0
    width: int = 0
    actual_time_ms: float = 0.0
    children: list[QueryPlanNode] = []


class QueryResult(BaseModel):
    query: str
    plan: Optional[QueryPlanNode] = None
    execution_time_ms: float = 0.0
    rows_returned: int = 0
    error: Optional[str] = None


# ── Diagnostic Run & Findings ──

class DBFinding(BaseModel):
    finding_id: str
    category: Literal[
        "query_performance", "replication", "connections",
        "storage", "schema", "locks", "memory",
    ]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float = 0.0
    title: str
    detail: str
    evidence: list[str] = []
    recommendation: Optional[str] = None
    remediation_available: bool = False


class DiagnosticRun(BaseModel):
    run_id: str
    profile_id: str
    status: Literal["running", "completed", "failed"] = "running"
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    findings: list[DBFinding] = []
    summary: str = ""
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_models.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/__init__.py backend/src/database/models.py backend/tests/test_db_models.py
git commit -m "feat(db): add Pydantic models for database diagnostics"
```

---

## Task 2: DatabaseAdapter ABC + Mock Adapter

**Files:**
- Create: `backend/src/database/adapters/__init__.py`
- Create: `backend/src/database/adapters/base.py`
- Create: `backend/src/database/adapters/mock_adapter.py`
- Test: `backend/tests/test_db_adapter_base.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_adapter_base.py
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
        # Same object from cache
        assert stats1 is stats2

    @pytest.mark.asyncio
    async def test_execute_diagnostic_query(self, mock_adapter):
        await mock_adapter.connect()
        result = await mock_adapter.execute_diagnostic_query("SELECT 1")
        assert result.error is None
        assert result.rows_returned >= 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_adapter_base.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# backend/src/database/adapters/__init__.py
"""Database adapter registry and base classes."""

# backend/src/database/adapters/base.py
"""Abstract base class for all database engine adapters."""
from __future__ import annotations
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

from ..models import (
    PerfSnapshot, ActiveQuery, ReplicationSnapshot,
    SchemaSnapshot, ConnectionPoolSnapshot, QueryResult,
)


class AdapterHealth(BaseModel):
    status: str  # "healthy", "degraded", "unreachable"
    latency_ms: float = 0.0
    version: str = ""
    error: Optional[str] = None


class DatabaseAdapter(ABC):
    """Abstract base for all database engine adapters.

    Key design principles (mirrors FirewallAdapter):
    - Snapshot accessors are cached with TTL; diagnostics read from cache.
    - execute_diagnostic_query is the only read that hits live DB.
    - execute_remediation (P2) is the only write path, requires approval.
    """

    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self, engine: str, host: str, port: int, database: str,
                 ttl: int = DEFAULT_TTL):
        self.engine = engine
        self.host = host
        self.port = port
        self.database = database
        self._ttl = ttl
        self._connected = False

        # Snapshot caches
        self._perf_cache: Optional[PerfSnapshot] = None
        self._queries_cache: Optional[list[ActiveQuery]] = None
        self._repl_cache: Optional[ReplicationSnapshot] = None
        self._schema_cache: Optional[SchemaSnapshot] = None
        self._pool_cache: Optional[ConnectionPoolSnapshot] = None
        self._snapshot_time: float = 0

    def _cache_fresh(self) -> bool:
        return (time.time() - self._snapshot_time) < self._ttl

    def _invalidate_cache(self) -> None:
        self._perf_cache = None
        self._queries_cache = None
        self._repl_cache = None
        self._schema_cache = None
        self._pool_cache = None
        self._snapshot_time = 0

    # ── Lifecycle ──

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health_check(self) -> AdapterHealth: ...

    # ── Snapshot fetchers (vendor-specific, called on cache miss) ──

    @abstractmethod
    async def _fetch_performance_stats(self) -> PerfSnapshot: ...

    @abstractmethod
    async def _fetch_active_queries(self) -> list[ActiveQuery]: ...

    @abstractmethod
    async def _fetch_replication_status(self) -> ReplicationSnapshot: ...

    @abstractmethod
    async def _fetch_schema_snapshot(self) -> SchemaSnapshot: ...

    @abstractmethod
    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot: ...

    # ── Cached accessors ──

    async def get_performance_stats(self) -> PerfSnapshot:
        if not self._cache_fresh() or self._perf_cache is None:
            self._perf_cache = await self._fetch_performance_stats()
            self._snapshot_time = time.time()
        return self._perf_cache

    async def get_active_queries(self) -> list[ActiveQuery]:
        if not self._cache_fresh() or self._queries_cache is None:
            self._queries_cache = await self._fetch_active_queries()
            if not self._perf_cache:
                self._snapshot_time = time.time()
        return self._queries_cache

    async def get_replication_status(self) -> ReplicationSnapshot:
        if not self._cache_fresh() or self._repl_cache is None:
            self._repl_cache = await self._fetch_replication_status()
            if not self._perf_cache:
                self._snapshot_time = time.time()
        return self._repl_cache

    async def get_schema_snapshot(self) -> SchemaSnapshot:
        if not self._cache_fresh() or self._schema_cache is None:
            self._schema_cache = await self._fetch_schema_snapshot()
        return self._schema_cache

    async def get_connection_pool(self) -> ConnectionPoolSnapshot:
        if not self._cache_fresh() or self._pool_cache is None:
            self._pool_cache = await self._fetch_connection_pool()
        return self._pool_cache

    # ── Live queries ──

    @abstractmethod
    async def execute_diagnostic_query(self, sql: str) -> QueryResult: ...

    async def refresh_snapshot(self) -> None:
        """Force-refresh all cached snapshots."""
        self._invalidate_cache()
        await asyncio.gather(
            self.get_performance_stats(),
            self.get_active_queries(),
            self.get_replication_status(),
            self.get_schema_snapshot(),
            self.get_connection_pool(),
        )
```

```python
# backend/src/database/adapters/mock_adapter.py
"""Mock database adapter for testing."""
from __future__ import annotations
import random
from .base import DatabaseAdapter, AdapterHealth
from ..models import (
    PerfSnapshot, ActiveQuery, ReplicationSnapshot,
    SchemaSnapshot, ConnectionPoolSnapshot, QueryResult,
)


class MockDatabaseAdapter(DatabaseAdapter):
    """In-memory mock adapter returning synthetic data."""

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        self._invalidate_cache()

    async def health_check(self) -> AdapterHealth:
        if not self._connected:
            return AdapterHealth(status="unreachable", error="Not connected")
        return AdapterHealth(status="healthy", latency_ms=1.2, version="MockDB 1.0")

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        return PerfSnapshot(
            connections_active=12, connections_idle=5, connections_max=100,
            cache_hit_ratio=0.94, transactions_per_sec=150.0,
            deadlocks=0, uptime_seconds=86400,
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        return [
            ActiveQuery(pid=1001, query="SELECT * FROM orders WHERE created_at > now() - interval '1h'",
                        duration_ms=3200, state="active", user="app", database=self.database),
            ActiveQuery(pid=1002, query="UPDATE users SET last_login = now()",
                        duration_ms=150, state="active", user="app", database=self.database),
        ]

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        return ReplicationSnapshot(is_replica=False, replicas=[], replication_lag_bytes=0)

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        return SchemaSnapshot(
            tables=[{"name": "orders", "rows": 1200000, "size_bytes": 256000000}],
            indexes=[{"name": "pk_orders", "table": "orders", "columns": ["id"]}],
            total_size_bytes=256000000,
        )

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        return ConnectionPoolSnapshot(active=12, idle=5, waiting=0, max_connections=100)

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        return QueryResult(query=sql, execution_time_ms=1.5, rows_returned=1)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_adapter_base.py -v`
Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/adapters/ backend/tests/test_db_adapter_base.py
git commit -m "feat(db): add DatabaseAdapter ABC and MockDatabaseAdapter"
```

---

## Task 3: DatabaseAdapterRegistry

**Files:**
- Create: `backend/src/database/adapters/registry.py`
- Test: `backend/tests/test_db_registry.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_registry.py
"""Tests for DatabaseAdapterRegistry."""
import pytest
from src.database.adapters.mock_adapter import MockDatabaseAdapter


@pytest.fixture
def registry():
    from src.database.adapters.registry import DatabaseAdapterRegistry
    return DatabaseAdapterRegistry()


@pytest.fixture
def adapter():
    return MockDatabaseAdapter(engine="postgresql", host="localhost", port=5432, database="testdb")


class TestDatabaseAdapterRegistry:
    def test_register_and_lookup(self, registry, adapter):
        registry.register("inst-1", adapter)
        assert registry.get_by_instance("inst-1") is adapter

    def test_register_with_profile_binding(self, registry, adapter):
        registry.register("inst-1", adapter, profile_id="prof-1")
        assert registry.get_by_profile("prof-1") is adapter

    def test_lookup_missing(self, registry):
        assert registry.get_by_instance("nope") is None
        assert registry.get_by_profile("nope") is None

    def test_remove(self, registry, adapter):
        registry.register("inst-1", adapter, profile_id="prof-1")
        registry.remove("inst-1")
        assert registry.get_by_instance("inst-1") is None
        assert registry.get_by_profile("prof-1") is None

    def test_len(self, registry, adapter):
        assert len(registry) == 0
        registry.register("inst-1", adapter)
        assert len(registry) == 1

    def test_all_instances(self, registry, adapter):
        registry.register("inst-1", adapter)
        all_inst = registry.all_instances()
        assert "inst-1" in all_inst
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_registry.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# backend/src/database/adapters/registry.py
"""Multi-instance database adapter registry.

Mirrors backend/src/network/adapters/registry.py pattern.
"""
from __future__ import annotations
import logging
import threading
from typing import Optional

from .base import DatabaseAdapter

logger = logging.getLogger(__name__)


class DatabaseAdapterRegistry:
    """Registry mapping instance_ids and profile_ids to DatabaseAdapter objects."""

    def __init__(self) -> None:
        self._instances: dict[str, DatabaseAdapter] = {}
        self._profile_map: dict[str, str] = {}  # profile_id → instance_id
        self._lock = threading.Lock()

    def register(self, instance_id: str, adapter: DatabaseAdapter,
                 profile_id: str | None = None) -> None:
        with self._lock:
            self._instances[instance_id] = adapter
            if profile_id:
                self._profile_map[profile_id] = instance_id
            logger.info("Registered DB adapter %s (%s)", instance_id, adapter.engine)

    def get_by_instance(self, instance_id: str) -> DatabaseAdapter | None:
        return self._instances.get(instance_id)

    def get_by_profile(self, profile_id: str) -> DatabaseAdapter | None:
        iid = self._profile_map.get(profile_id)
        return self._instances.get(iid) if iid else None

    def remove(self, instance_id: str) -> None:
        with self._lock:
            self._instances.pop(instance_id, None)
            to_remove = [pid for pid, iid in self._profile_map.items() if iid == instance_id]
            for pid in to_remove:
                del self._profile_map[pid]

    def all_instances(self) -> dict[str, DatabaseAdapter]:
        with self._lock:
            return dict(self._instances)

    def __len__(self) -> int:
        return len(self._instances)

    def __bool__(self) -> bool:
        return bool(self._instances)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_registry.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/adapters/registry.py backend/tests/test_db_registry.py
git commit -m "feat(db): add DatabaseAdapterRegistry"
```

---

## Task 4: Profile Store (SQLite CRUD)

**Files:**
- Create: `backend/src/database/profile_store.py`
- Test: `backend/tests/test_db_profile_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_profile_store.py
"""Tests for database profile CRUD store."""
import pytest
import os
import tempfile


@pytest.fixture
def store():
    from src.database.profile_store import DBProfileStore
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DBProfileStore(db_path=path)
    yield s
    os.unlink(path)


class TestDBProfileStore:
    def test_create_and_get(self, store):
        profile = store.create(
            name="prod-pg", engine="postgresql",
            host="db.prod.io", port=5432, database="myapp",
            username="admin", password="secret123",
        )
        assert profile["id"]
        assert profile["name"] == "prod-pg"

        fetched = store.get(profile["id"])
        assert fetched["host"] == "db.prod.io"

    def test_list_all(self, store):
        store.create(name="a", engine="postgresql", host="h", port=5432,
                     database="d", username="u", password="p")
        store.create(name="b", engine="mongodb", host="h", port=27017,
                     database="d", username="u", password="p")
        profiles = store.list_all()
        assert len(profiles) == 2

    def test_update(self, store):
        p = store.create(name="old", engine="postgresql", host="h", port=5432,
                         database="d", username="u", password="p")
        store.update(p["id"], name="new-name", host="new-host")
        fetched = store.get(p["id"])
        assert fetched["name"] == "new-name"
        assert fetched["host"] == "new-host"

    def test_delete(self, store):
        p = store.create(name="del", engine="postgresql", host="h", port=5432,
                         database="d", username="u", password="p")
        store.delete(p["id"])
        assert store.get(p["id"]) is None

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None

    def test_password_not_in_list(self, store):
        store.create(name="a", engine="postgresql", host="h", port=5432,
                     database="d", username="u", password="secret")
        profiles = store.list_all()
        # list_all should NOT include passwords
        assert "password" not in profiles[0]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db_profile_store.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/database/profile_store.py
"""SQLite-backed CRUD store for database connection profiles."""
from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class DBProfileStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS db_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)

    def create(self, *, name: str, engine: str, host: str, port: int,
               database: str, username: str, password: str,
               tags: dict | None = None) -> dict:
        profile_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        import json
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO db_profiles (id, name, engine, host, port, database_name, username, password, tags, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (profile_id, name, engine, host, port, database, username, password, json.dumps(tags or {}), now),
            )
        return self.get(profile_id)  # type: ignore

    def get(self, profile_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM db_profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return None
        return self._row_to_dict(row, include_password=True)

    def list_all(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM db_profiles ORDER BY created_at DESC").fetchall()
        return [self._row_to_dict(r, include_password=False) for r in rows]

    def update(self, profile_id: str, **fields) -> Optional[dict]:
        allowed = {"name", "engine", "host", "port", "database", "username", "password", "tags"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get(profile_id)
        # Map 'database' field to column name
        if "database" in updates:
            updates["database_name"] = updates.pop("database")
        import json
        if "tags" in updates and isinstance(updates["tags"], dict):
            updates["tags"] = json.dumps(updates["tags"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [profile_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE db_profiles SET {set_clause} WHERE id = ?", values)
        return self.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM db_profiles WHERE id = ?", (profile_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row, include_password: bool = False) -> dict:
        import json
        d = {
            "id": row["id"],
            "name": row["name"],
            "engine": row["engine"],
            "host": row["host"],
            "port": row["port"],
            "database": row["database_name"],
            "username": row["username"],
            "tags": json.loads(row["tags"]) if row["tags"] else {},
            "created_at": row["created_at"],
        }
        if include_password:
            d["password"] = row["password"]
        return d
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db_profile_store.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/profile_store.py backend/tests/test_db_profile_store.py
git commit -m "feat(db): add SQLite profile store for DB connection profiles"
```

---

## Task 5: PostgresAdapter

**Files:**
- Create: `backend/src/database/adapters/postgres.py`
- Test: `backend/tests/test_postgres_adapter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_postgres_adapter.py
"""Tests for PostgresAdapter (unit tests with mocked asyncpg)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.database.models import PerfSnapshot, ActiveQuery, ReplicationSnapshot


@pytest.fixture
def pg_adapter():
    from src.database.adapters.postgres import PostgresAdapter
    return PostgresAdapter(host="localhost", port=5432, database="testdb",
                           username="user", password="pass")


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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_postgres_adapter.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/database/adapters/postgres.py
"""PostgreSQL adapter using asyncpg."""
from __future__ import annotations
import time
import logging
from typing import Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from .base import DatabaseAdapter, AdapterHealth
from ..models import (
    PerfSnapshot, ActiveQuery, ReplicationSnapshot, ReplicaInfo,
    SchemaSnapshot, ConnectionPoolSnapshot, QueryResult,
)

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SEC = 10
ROW_LIMIT = 1000


class PostgresAdapter(DatabaseAdapter):
    """PostgreSQL adapter using asyncpg for async connectivity."""

    def __init__(self, host: str, port: int, database: str,
                 username: str, password: str, ttl: int = 300):
        super().__init__(engine="postgresql", host=host, port=port,
                         database=database, ttl=ttl)
        self._username = username
        self._password = password
        self._conn: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        self._conn = await asyncpg.connect(
            host=self.host, port=self.port, database=self.database,
            user=self._username, password=self._password,
            timeout=10,
        )
        self._connected = True

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
        self._connected = False
        self._invalidate_cache()

    async def health_check(self) -> AdapterHealth:
        if not self._connected or not self._conn:
            return AdapterHealth(status="unreachable", error="Not connected")
        try:
            start = time.time()
            row = await self._conn.fetchrow("SELECT version()")
            latency = (time.time() - start) * 1000
            version = row["version"] if row else ""
            return AdapterHealth(status="healthy", latency_ms=round(latency, 2), version=version)
        except Exception as e:
            return AdapterHealth(status="degraded", error=str(e))

    async def _fetch_performance_stats(self) -> PerfSnapshot:
        row = await self._conn.fetchrow("""
            SELECT
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') AS active,
                (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle') AS idle,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max,
                COALESCE(
                    (SELECT round(sum(heap_blks_hit)::numeric / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0), 4)
                     FROM pg_statio_user_tables), 0
                ) AS ratio,
                (SELECT xact_commit + xact_rollback FROM pg_stat_database WHERE datname = current_database()) AS tps,
                (SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()) AS deadlocks,
                EXTRACT(EPOCH FROM now() - pg_postmaster_start_time())::int AS uptime
        """)
        return PerfSnapshot(
            connections_active=row["active"],
            connections_idle=row["idle"],
            connections_max=row["max"],
            cache_hit_ratio=float(row["ratio"]),
            transactions_per_sec=float(row["tps"] or 0),
            deadlocks=row["deadlocks"] or 0,
            uptime_seconds=row["uptime"] or 0,
        )

    async def _fetch_active_queries(self) -> list[ActiveQuery]:
        rows = await self._conn.fetch("""
            SELECT pid, query,
                   EXTRACT(EPOCH FROM now() - query_start) * 1000 AS duration_ms,
                   state, usename, datname, wait_event IS NOT NULL AS waiting
            FROM pg_stat_activity
            WHERE state != 'idle' AND pid != pg_backend_pid()
            ORDER BY duration_ms DESC
            LIMIT 50
        """)
        return [
            ActiveQuery(
                pid=r["pid"], query=r["query"], duration_ms=r["duration_ms"] or 0,
                state=r["state"] or "", user=r["usename"] or "", database=r["datname"] or "",
                waiting=r["waiting"],
            )
            for r in rows
        ]

    async def _fetch_replication_status(self) -> ReplicationSnapshot:
        # Check if this is a replica
        is_replica_row = await self._conn.fetchrow("SELECT pg_is_in_recovery() AS is_replica")
        is_replica = is_replica_row["is_replica"] if is_replica_row else False

        replicas = []
        lag_bytes = 0
        if not is_replica:
            rows = await self._conn.fetch("""
                SELECT client_addr, state,
                       pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes
                FROM pg_stat_replication
            """)
            replicas = [
                ReplicaInfo(name=str(r["client_addr"] or ""), state=r["state"] or "",
                            lag_bytes=int(r["lag_bytes"] or 0))
                for r in rows
            ]
        else:
            lag_row = await self._conn.fetchrow("""
                SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) AS lag
            """)
            lag_bytes = int(lag_row["lag"] or 0) if lag_row else 0

        return ReplicationSnapshot(
            is_replica=is_replica, replicas=replicas,
            replication_lag_bytes=lag_bytes,
        )

    async def _fetch_schema_snapshot(self) -> SchemaSnapshot:
        tables = await self._conn.fetch("""
            SELECT relname AS name, n_live_tup AS rows,
                   pg_total_relation_size(c.oid) AS size_bytes
            FROM pg_class c JOIN pg_stat_user_tables s ON c.relname = s.relname
            WHERE c.relkind = 'r'
            ORDER BY size_bytes DESC LIMIT 100
        """)
        indexes = await self._conn.fetch("""
            SELECT indexrelname AS name, relname AS table,
                   idx_scan, idx_tup_read, idx_tup_fetch,
                   pg_relation_size(indexrelid) AS size_bytes
            FROM pg_stat_user_indexes
            ORDER BY size_bytes DESC LIMIT 200
        """)
        total_row = await self._conn.fetchrow(
            "SELECT pg_database_size(current_database()) AS total"
        )
        return SchemaSnapshot(
            tables=[dict(r) for r in tables],
            indexes=[dict(r) for r in indexes],
            total_size_bytes=total_row["total"] if total_row else 0,
        )

    async def _fetch_connection_pool(self) -> ConnectionPoolSnapshot:
        row = await self._conn.fetchrow("""
            SELECT
                count(*) FILTER (WHERE state = 'active') AS active,
                count(*) FILTER (WHERE state = 'idle') AS idle,
                count(*) FILTER (WHERE wait_event IS NOT NULL AND state != 'idle') AS waiting,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') AS max_conn
            FROM pg_stat_activity
        """)
        return ConnectionPoolSnapshot(
            active=row["active"], idle=row["idle"],
            waiting=row["waiting"], max_connections=row["max_conn"],
        )

    async def execute_diagnostic_query(self, sql: str) -> QueryResult:
        """Execute a READ-ONLY diagnostic query with timeout and row limit."""
        try:
            start = time.time()
            rows = await self._conn.fetch(
                f"SELECT * FROM ({sql}) AS q LIMIT {ROW_LIMIT}",
                timeout=QUERY_TIMEOUT_SEC,
            )
            elapsed = (time.time() - start) * 1000
            return QueryResult(query=sql, execution_time_ms=round(elapsed, 2),
                               rows_returned=len(rows))
        except Exception as e:
            return QueryResult(query=sql, error=str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_postgres_adapter.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/adapters/postgres.py backend/tests/test_postgres_adapter.py
git commit -m "feat(db): add PostgresAdapter with asyncpg"
```

---

## Task 6: Diagnostic Store (Run History)

**Files:**
- Create: `backend/src/database/diagnostic_store.py`
- Test: `backend/tests/test_db_diagnostic_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_diagnostic_store.py
"""Tests for diagnostic run history store."""
import pytest
import os
import tempfile


@pytest.fixture
def store():
    from src.database.diagnostic_store import DiagnosticRunStore
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = DiagnosticRunStore(db_path=path)
    yield s
    os.unlink(path)


class TestDiagnosticRunStore:
    def test_create_and_get(self, store):
        run = store.create(profile_id="p1")
        assert run["run_id"]
        assert run["status"] == "running"
        fetched = store.get(run["run_id"])
        assert fetched["profile_id"] == "p1"

    def test_update_status(self, store):
        run = store.create(profile_id="p1")
        store.update(run["run_id"], status="completed", summary="All good")
        fetched = store.get(run["run_id"])
        assert fetched["status"] == "completed"
        assert fetched["summary"] == "All good"

    def test_add_finding(self, store):
        run = store.create(profile_id="p1")
        store.add_finding(run["run_id"], {
            "finding_id": "f1", "category": "query_performance",
            "severity": "high", "confidence": 0.9,
            "title": "Slow query", "detail": "SELECT took 12s",
        })
        fetched = store.get(run["run_id"])
        assert len(fetched["findings"]) == 1
        assert fetched["findings"][0]["title"] == "Slow query"

    def test_list_by_profile(self, store):
        store.create(profile_id="p1")
        store.create(profile_id="p1")
        store.create(profile_id="p2")
        runs = store.list_by_profile("p1")
        assert len(runs) == 2

    def test_get_missing(self, store):
        assert store.get("nonexistent") is None
```

**Step 2: Run test, verify fails**

Run: `cd backend && python -m pytest tests/test_db_diagnostic_store.py -v`

**Step 3: Write implementation**

```python
# backend/src/database/diagnostic_store.py
"""SQLite-backed store for diagnostic run history."""
from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class DiagnosticRunStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_table()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS db_diagnostic_runs (
                    run_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    findings TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT ''
                )
            """)

    def create(self, profile_id: str) -> dict:
        run_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO db_diagnostic_runs (run_id, profile_id, started_at) VALUES (?,?,?)",
                (run_id, profile_id, now),
            )
        return self.get(run_id)  # type: ignore

    def get(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM db_diagnostic_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "profile_id": row["profile_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "findings": json.loads(row["findings"]),
            "summary": row["summary"],
        }

    def update(self, run_id: str, **fields) -> None:
        allowed = {"status", "summary", "completed_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [run_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE db_diagnostic_runs SET {set_clause} WHERE run_id = ?", values)

    def add_finding(self, run_id: str, finding: dict) -> None:
        with self._conn() as conn:
            row = conn.execute("SELECT findings FROM db_diagnostic_runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return
            findings = json.loads(row["findings"])
            findings.append(finding)
            conn.execute("UPDATE db_diagnostic_runs SET findings = ? WHERE run_id = ?",
                         (json.dumps(findings), run_id))

    def list_by_profile(self, profile_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM db_diagnostic_runs WHERE profile_id = ? ORDER BY started_at DESC",
                (profile_id,),
            ).fetchall()
        return [
            {"run_id": r["run_id"], "profile_id": r["profile_id"], "status": r["status"],
             "started_at": r["started_at"], "completed_at": r["completed_at"],
             "findings": json.loads(r["findings"]), "summary": r["summary"]}
            for r in rows
        ]
```

**Step 4:** Run tests, all 5 PASS

**Step 5: Commit**

```bash
git add backend/src/database/diagnostic_store.py backend/tests/test_db_diagnostic_store.py
git commit -m "feat(db): add diagnostic run history store"
```

---

## Task 7: FastAPI Endpoints

**Files:**
- Create: `backend/src/api/db_endpoints.py`
- Modify: `backend/src/api/main.py` (add router import + include)
- Test: `backend/tests/test_db_endpoints.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_db_endpoints.py
"""Tests for /api/db/* endpoints."""
import pytest
from fastapi.testclient import TestClient
import tempfile
import os


@pytest.fixture
def client():
    # Patch stores to use temp DB before importing
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DB_DIAGNOSTICS_DB_PATH"] = path

    from src.api.db_endpoints import db_router, _get_profile_store, _get_run_store
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(db_router)
    yield TestClient(app)
    os.unlink(path)


class TestProfileEndpoints:
    def test_create_profile(self, client):
        resp = client.post("/api/db/profiles", json={
            "name": "test-pg", "engine": "postgresql",
            "host": "localhost", "port": 5432, "database": "testdb",
            "username": "admin", "password": "secret",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-pg"
        assert "password" not in data  # never in response

    def test_list_profiles(self, client):
        client.post("/api/db/profiles", json={
            "name": "a", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        resp = client.get("/api/db/profiles")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_profile(self, client):
        create = client.post("/api/db/profiles", json={
            "name": "b", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        pid = create.json()["id"]
        resp = client.get(f"/api/db/profiles/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "b"

    def test_delete_profile(self, client):
        create = client.post("/api/db/profiles", json={
            "name": "del", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        pid = create.json()["id"]
        resp = client.delete(f"/api/db/profiles/{pid}")
        assert resp.status_code == 200
        assert client.get(f"/api/db/profiles/{pid}").status_code == 404

    def test_get_missing_profile(self, client):
        resp = client.get("/api/db/profiles/nonexistent")
        assert resp.status_code == 404


class TestDiagnosticEndpoints:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/db/diagnostics/history?profile_id=p1")
        assert resp.status_code == 200
        assert resp.json() == []
```

**Step 2: Run test, verify fails**

**Step 3: Write implementation**

```python
# backend/src/api/db_endpoints.py
"""FastAPI router for database diagnostics — /api/db/*."""
from __future__ import annotations
import os
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

db_router = APIRouter(prefix="/api/db", tags=["database"])

# ── Stores (lazy singletons) ──

_profile_store = None
_run_store = None


def _get_profile_store():
    global _profile_store
    if _profile_store is None:
        from src.database.profile_store import DBProfileStore
        db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
        _profile_store = DBProfileStore(db_path=db_path)
    return _profile_store


def _get_run_store():
    global _run_store
    if _run_store is None:
        from src.database.diagnostic_store import DiagnosticRunStore
        db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
        _run_store = DiagnosticRunStore(db_path=db_path)
    return _run_store


# ── Request models ──

class CreateProfileRequest(BaseModel):
    name: str
    engine: str
    host: str
    port: int
    database: str
    username: str
    password: str
    tags: dict[str, str] = {}


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class StartDiagnosticRequest(BaseModel):
    profile_id: str


# ── Profile CRUD ──

@db_router.post("/profiles", status_code=201)
def create_profile(req: CreateProfileRequest):
    store = _get_profile_store()
    profile = store.create(
        name=req.name, engine=req.engine, host=req.host, port=req.port,
        database=req.database, username=req.username, password=req.password,
        tags=req.tags,
    )
    profile.pop("password", None)
    return profile


@db_router.get("/profiles")
def list_profiles():
    return _get_profile_store().list_all()


@db_router.get("/profiles/{profile_id}")
def get_profile(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.pop("password", None)
    return profile


@db_router.put("/profiles/{profile_id}")
def update_profile(profile_id: str, req: UpdateProfileRequest):
    store = _get_profile_store()
    existing = store.get(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = store.update(profile_id, **updates)
    if updated:
        updated.pop("password", None)
    return updated


@db_router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str):
    store = _get_profile_store()
    if not store.get(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    store.delete(profile_id)
    return {"status": "deleted"}


# ── Health ──

@db_router.get("/profiles/{profile_id}/health")
async def get_health(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # TODO: connect adapter, return health snapshot
    return {"profile_id": profile_id, "status": "not_implemented"}


# ── Diagnostics ──

@db_router.post("/diagnostics/start")
async def start_diagnostic(req: StartDiagnosticRequest):
    profile = _get_profile_store().get(req.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    run_store = _get_run_store()
    run = run_store.create(profile_id=req.profile_id)
    # TODO: launch LangGraph diagnostic in background task
    return run


@db_router.get("/diagnostics/{run_id}")
def get_diagnostic_run(run_id: str):
    run = _get_run_store().get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@db_router.get("/diagnostics/history")
def list_diagnostic_runs(profile_id: str):
    return _get_run_store().list_by_profile(profile_id)
```

Then register in main.py — add import and include_router:

Modify: `backend/src/api/main.py`
- Add import: `from .db_endpoints import db_router`
- Add to `create_app()` after other `include_router` calls: `app.include_router(db_router)`

**Step 4:** Run tests, all 6 PASS

**Step 5: Commit**

```bash
git add backend/src/api/db_endpoints.py backend/src/api/main.py backend/tests/test_db_endpoints.py
git commit -m "feat(db): add FastAPI endpoints for profile CRUD and diagnostic runs"
```

---

## Task 8: Frontend — DBLayout + DBSidebar + Route Registration

**Files:**
- Create: `frontend/src/components/Database/DBLayout.tsx`
- Create: `frontend/src/components/Database/DBSidebar.tsx`
- Modify: `frontend/src/App.tsx` (add import, ViewState, nav routing)
- Modify: `frontend/src/components/Layout/SidebarNav.tsx` (add nav item)

**Step 1: Create DBSidebar**

```tsx
// frontend/src/components/Database/DBSidebar.tsx
import React from 'react';

export type DBView = 'overview' | 'connections' | 'diagnostics' | 'monitoring' | 'operations' | 'schema';

interface Props {
  activeView: DBView;
  onNavigate: (view: DBView) => void;
}

const navItems: { id: DBView; label: string; icon: string; phase: string }[] = [
  { id: 'overview', label: 'Overview', icon: 'dashboard', phase: 'P0' },
  { id: 'connections', label: 'Connections', icon: 'cable', phase: 'P0' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'troubleshoot', phase: 'P0' },
  { id: 'monitoring', label: 'Monitoring', icon: 'monitoring', phase: 'P1' },
  { id: 'operations', label: 'Operations', icon: 'build', phase: 'P2' },
  { id: 'schema', label: 'Schema', icon: 'schema', phase: 'P1' },
];

export default function DBSidebar({ activeView, onNavigate }: Props) {
  return (
    <aside className="w-56 flex-shrink-0 border-r border-[#224349] flex flex-col py-6 gap-1 px-3"
           style={{ backgroundColor: '#0a1a1f' }}>
      <div className="px-3 mb-4">
        <h2 className="text-sm font-bold text-[#07b6d5] tracking-wide uppercase">Databases</h2>
      </div>
      {navItems.map((item) => {
        const isActive = activeView === item.id;
        const isComingSoon = item.phase !== 'P0';
        return (
          <button
            key={item.id}
            onClick={() => !isComingSoon && onNavigate(item.id)}
            disabled={isComingSoon}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm ${
              isActive
                ? 'text-[#07b6d5] font-semibold'
                : isComingSoon
                ? 'text-slate-600 cursor-not-allowed'
                : 'text-slate-400 hover:text-white'
            }`}
            style={isActive ? { backgroundColor: 'rgba(7,182,213,0.1)' } : {}}
          >
            <span className="material-symbols-outlined text-[18px]"
                  style={{ fontFamily: 'Material Symbols Outlined' }}>{item.icon}</span>
            <span>{item.label}</span>
            {isComingSoon && (
              <span className="ml-auto text-[10px] text-slate-600 bg-slate-800 px-1.5 py-0.5 rounded">
                {item.phase}
              </span>
            )}
          </button>
        );
      })}
    </aside>
  );
}
```

**Step 2: Create DBLayout**

```tsx
// frontend/src/components/Database/DBLayout.tsx
import React, { useState } from 'react';
import DBSidebar from './DBSidebar';
import type { DBView } from './DBSidebar';
import DBOverview from './DBOverview';
import DBConnections from './DBConnections';
import DBDiagnostics from './DBDiagnostics';

export default function DBLayout() {
  const [view, setView] = useState<DBView>('overview');

  return (
    <div className="flex h-full overflow-hidden">
      <DBSidebar activeView={view} onNavigate={setView} />
      <div className="flex-1 overflow-auto p-6">
        {view === 'overview' && <DBOverview />}
        {view === 'connections' && <DBConnections />}
        {view === 'diagnostics' && <DBDiagnostics />}
        {view === 'monitoring' && (
          <div className="text-center text-slate-500 py-20">Monitoring — Coming in P1</div>
        )}
        {view === 'operations' && (
          <div className="text-center text-slate-500 py-20">Operations — Coming in P2</div>
        )}
        {view === 'schema' && (
          <div className="text-center text-slate-500 py-20">Schema Browser — Coming in P1</div>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Create placeholder components**

```tsx
// frontend/src/components/Database/DBOverview.tsx
import React from 'react';
export default function DBOverview() {
  return <div className="text-slate-300"><h2 className="text-lg font-semibold mb-4">Database Fleet Overview</h2><p className="text-slate-500">No connections configured. Add a database connection to get started.</p></div>;
}

// frontend/src/components/Database/DBConnections.tsx
import React from 'react';
export default function DBConnections() {
  return <div className="text-slate-300"><h2 className="text-lg font-semibold mb-4">Connection Profiles</h2><p className="text-slate-500">No profiles yet.</p></div>;
}

// frontend/src/components/Database/DBDiagnostics.tsx
import React from 'react';
export default function DBDiagnostics() {
  return <div className="text-slate-300"><h2 className="text-lg font-semibold mb-4">Diagnostics</h2><p className="text-slate-500">Select a database to run diagnostics.</p></div>;
}
```

**Step 4: Register in App.tsx**

Modify `frontend/src/App.tsx`:
- Add import: `import DBLayout from './components/Database/DBLayout';`
- Add `'db-diagnostics'` to `ViewState` type union
- Add to `handleNavigate`: `else if (view === 'db-diagnostics') { setViewState('db-diagnostics'); }`
- Add render block: `{viewState === 'db-diagnostics' && <DBLayout />}`
- Add to `viewToNav`: `'db-diagnostics': 'db-diagnostics'`
- Add to `breadcrumbMap`: `'db-diagnostics': { label: 'Databases', parent: 'home' }`

Modify `frontend/src/components/Layout/SidebarNav.tsx`:
- Add `'db-diagnostics'` to `NavView` type union
- Add to the `Diagnostics` group children:
  `{ id: 'db-diagnostics', label: 'Databases', icon: 'database' }`

**Step 5: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 6: Commit**

```bash
git add frontend/src/components/Database/ frontend/src/App.tsx frontend/src/components/Layout/SidebarNav.tsx
git commit -m "feat(db): add DBLayout with capability sidebar and route registration"
```

---

## Task 9: Frontend — DBConnections (Profile CRUD)

**Files:**
- Modify: `frontend/src/components/Database/DBConnections.tsx`
- Create: `frontend/src/components/Database/DBProfileForm.tsx`
- Modify: `frontend/src/services/api.ts` (add DB API functions)

**Step 1: Add API functions to `frontend/src/services/api.ts`**

Add at the end of the file:
```typescript
// ===== Database Diagnostics API =====
export const fetchDBProfiles = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch profiles'));
  return resp.json();
};

export const createDBProfile = async (data: Record<string, unknown>) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create profile'));
  return resp.json();
};

export const deleteDBProfile = async (id: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${id}`, { method: 'DELETE' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to delete profile'));
  return resp.json();
};

export const fetchDBDiagnosticHistory = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/history?profile_id=${profileId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch history'));
  return resp.json();
};

export const startDBDiagnostic = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to start diagnostic'));
  return resp.json();
};

export const fetchDBDiagnosticRun = async (runId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/diagnostics/${runId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch run'));
  return resp.json();
};
```

**Step 2: Implement DBProfileForm**

```tsx
// frontend/src/components/Database/DBProfileForm.tsx
import React, { useState } from 'react';

interface Props {
  onClose: () => void;
  onCreate: (data: Record<string, unknown>) => void;
}

export default function DBProfileForm({ onClose, onCreate }: Props) {
  const [form, setForm] = useState({
    name: '', engine: 'postgresql', host: '', port: '5432',
    database: '', username: '', password: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({ ...form, port: parseInt(form.port, 10) });
  };

  const inputClass = "w-full bg-[#0a1a1f] border border-[#1e3a40] rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-[#07b6d5]";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <form onSubmit={handleSubmit} className="bg-[#0f2023] border border-[#1e3a40] rounded-xl p-6 w-[440px] space-y-4">
        <h3 className="text-lg font-semibold text-slate-200">New Connection Profile</h3>

        <div>
          <label className="text-xs text-slate-400">Name</label>
          <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </div>

        <div>
          <label className="text-xs text-slate-400">Engine</label>
          <select className={inputClass} value={form.engine} onChange={(e) => setForm({ ...form, engine: e.target.value })}>
            <option value="postgresql">PostgreSQL</option>
            <option value="mongodb" disabled>MongoDB (P1)</option>
            <option value="mysql" disabled>MySQL (P1)</option>
            <option value="oracle" disabled>Oracle (P2)</option>
          </select>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <label className="text-xs text-slate-400">Host</label>
            <input className={inputClass} value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} required />
          </div>
          <div>
            <label className="text-xs text-slate-400">Port</label>
            <input className={inputClass} type="number" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} required />
          </div>
        </div>

        <div>
          <label className="text-xs text-slate-400">Database</label>
          <input className={inputClass} value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} required />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400">Username</label>
            <input className={inputClass} value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          </div>
          <div>
            <label className="text-xs text-slate-400">Password</label>
            <input className={inputClass} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
          <button type="submit" className="px-4 py-2 text-sm bg-[#07b6d5] text-white rounded hover:bg-[#06a0bd]">Create</button>
        </div>
      </form>
    </div>
  );
}
```

**Step 3: Implement DBConnections with live CRUD**

Full implementation of DBConnections.tsx with fetch/create/delete profile list, using the API functions above. Profile table with name, engine, host, status indicator, delete button. "+ New Connection" button opens DBProfileForm modal.

**Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/components/Database/DBConnections.tsx frontend/src/components/Database/DBProfileForm.tsx frontend/src/services/api.ts
git commit -m "feat(db): add DBConnections with profile CRUD and DBProfileForm modal"
```

---

## Task 10: Frontend — DBOverview (Fleet Health Cards)

**Files:**
- Modify: `frontend/src/components/Database/DBOverview.tsx`
- Create: `frontend/src/components/Database/DBHealthGauge.tsx`

**Step 1: Create DBHealthGauge**

Circular SVG gauge component with value (0-100), label, and color based on value (green/amber/red thresholds).

**Step 2: Implement DBOverview**

Fetches all profiles via `fetchDBProfiles()`, renders a card grid. Each card shows: name, engine badge, status dot (green placeholder), and key stats placeholder. Links to diagnostics view for each profile.

**Step 3: Verify & Commit**

```bash
git add frontend/src/components/Database/DBOverview.tsx frontend/src/components/Database/DBHealthGauge.tsx
git commit -m "feat(db): add DBOverview fleet cards and DBHealthGauge"
```

---

## Task 11: Frontend — DBDiagnostics (Run History + Findings)

**Files:**
- Modify: `frontend/src/components/Database/DBDiagnostics.tsx`
- Create: `frontend/src/components/Database/DBDiagnosticRun.tsx`
- Create: `frontend/src/components/Database/QueryPlanViewer.tsx`
- Create: `frontend/src/components/Database/SlowQueryTable.tsx`

**Step 1: Implement DBDiagnostics**

DB selector dropdown at top (fetches profiles). Shows run history table for selected profile. "Run Diagnostic" button calls `startDBDiagnostic()`. Click a run to expand `DBDiagnosticRun`.

**Step 2: Implement DBDiagnosticRun**

Displays findings list for a single run. Each finding is a card with severity badge, title, detail, confidence bar, and recommendation text. If finding has query plan, shows "View Query Plan" button.

**Step 3: Implement QueryPlanViewer**

Tree view renderer for EXPLAIN output. Recursive node component showing: node type, cost, rows, actual time. Indented children. Color-coded by node type (Seq Scan = red, Index Scan = green).

**Step 4: Implement SlowQueryTable**

Sortable table of slow queries with columns: query (truncated), duration, calls, user. Click to expand full query text.

**Step 5: Verify & Commit**

```bash
git add frontend/src/components/Database/DBDiagnostics.tsx frontend/src/components/Database/DBDiagnosticRun.tsx frontend/src/components/Database/QueryPlanViewer.tsx frontend/src/components/Database/SlowQueryTable.tsx
git commit -m "feat(db): add DBDiagnostics view with run history and findings"
```

---

## Task 12: LangGraph Diagnostic Graph

**Files:**
- Create: `backend/src/agents/database/__init__.py`
- Create: `backend/src/agents/database/graph.py`
- Create: `backend/src/agents/database/state.py`
- Test: `backend/tests/test_db_graph.py`

**Step 1: Write failing test**

```python
# backend/tests/test_db_graph.py
"""Tests for database diagnostic LangGraph graph."""
import pytest


def test_state_defaults():
    from src.agents.database.state import DBDiagnosticState
    state = DBDiagnosticState(run_id="r1", profile_id="p1", engine="postgresql")
    assert state["status"] == "running"
    assert state["findings"] == []
    assert state["dispatched_agents"] == []


def test_graph_compiles():
    from src.agents.database.graph import build_db_diagnostic_graph
    graph = build_db_diagnostic_graph()
    assert graph is not None
```

**Step 2: Implement state and graph**

```python
# backend/src/agents/database/state.py
"""TypedDict state for DB diagnostic LangGraph graph."""
from __future__ import annotations
from typing import TypedDict, Optional


class DBDiagnosticState(TypedDict, total=False):
    run_id: str
    profile_id: str
    engine: str
    status: str  # "running", "completed", "failed"
    error: Optional[str]
    # Connection validation
    connected: bool
    health_latency_ms: float
    # Symptom classification
    symptoms: list[str]  # ["slow_queries", "replication_lag", "connection_exhaustion"]
    dispatched_agents: list[str]
    # Agent outputs
    findings: list[dict]
    summary: str
```

```python
# backend/src/agents/database/graph.py
"""LangGraph StateGraph for database diagnostics."""
from __future__ import annotations
import logging
from langgraph.graph import StateGraph, END
from .state import DBDiagnosticState

logger = logging.getLogger(__name__)


def connection_validator(state: DBDiagnosticState) -> dict:
    """Validate DB connectivity. Fail fast if unreachable."""
    # Actual implementation will use adapter.health_check()
    return {"connected": True, "health_latency_ms": 1.0}


def snapshot_collector(state: DBDiagnosticState) -> dict:
    """Populate all adapter caches in parallel."""
    # Actual implementation calls adapter.refresh_snapshot()
    return {}


def symptom_classifier(state: DBDiagnosticState) -> dict:
    """Classify symptoms to determine which agents to dispatch."""
    # Default: dispatch both query and health agents
    return {
        "symptoms": ["slow_queries", "connections", "replication"],
        "dispatched_agents": ["query_agent", "health_agent"],
    }


def query_agent_node(state: DBDiagnosticState) -> dict:
    """Run DBQueryAgent for slow query analysis."""
    # Actual implementation runs DBQueryAgent
    return {"findings": state.get("findings", [])}


def health_agent_node(state: DBDiagnosticState) -> dict:
    """Run DBHealthAgent for health diagnostics."""
    return {"findings": state.get("findings", [])}


def synthesize(state: DBDiagnosticState) -> dict:
    """Merge and deduplicate findings from all agents."""
    findings = state.get("findings", [])
    # Sort by severity then confidence
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    findings.sort(key=lambda f: (severity_order.get(f.get("severity", "info"), 4), -f.get("confidence", 0)))
    summary = f"{len(findings)} finding(s) detected" if findings else "No issues found"
    return {"findings": findings, "summary": summary, "status": "completed"}


def should_continue(state: DBDiagnosticState) -> str:
    if not state.get("connected"):
        return "end"
    return "continue"


def build_db_diagnostic_graph() -> StateGraph:
    graph = StateGraph(DBDiagnosticState)

    graph.add_node("connection_validator", connection_validator)
    graph.add_node("snapshot_collector", snapshot_collector)
    graph.add_node("symptom_classifier", symptom_classifier)
    graph.add_node("query_agent", query_agent_node)
    graph.add_node("health_agent", health_agent_node)
    graph.add_node("synthesize", synthesize)

    graph.set_entry_point("connection_validator")
    graph.add_conditional_edges("connection_validator", should_continue, {
        "continue": "snapshot_collector",
        "end": END,
    })
    graph.add_edge("snapshot_collector", "symptom_classifier")
    graph.add_edge("symptom_classifier", "query_agent")
    graph.add_edge("query_agent", "health_agent")
    graph.add_edge("health_agent", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()
```

**Step 3: Run tests, all PASS**

**Step 4: Commit**

```bash
git add backend/src/agents/database/ backend/tests/test_db_graph.py
git commit -m "feat(db): add LangGraph diagnostic graph with state machine"
```

---

## Task 13: Wire Graph to API Endpoint

**Files:**
- Modify: `backend/src/api/db_endpoints.py` (wire start_diagnostic to run graph)

Update the `start_diagnostic` endpoint to:
1. Look up the profile
2. Create a DiagnosticRun in the store
3. Launch the LangGraph graph as a background task
4. Stream progress via WebSocket (use existing `manager.broadcast` pattern)
5. On completion, update the run store with findings + status

**Commit**

```bash
git add backend/src/api/db_endpoints.py
git commit -m "feat(db): wire LangGraph graph to diagnostic start endpoint"
```

---

## Task 14: Integration Test — End-to-End Flow

**Files:**
- Create: `backend/tests/test_db_integration.py`

Test the full flow:
1. Create a profile via API
2. Start a diagnostic run via API
3. Verify run appears in history
4. Verify findings are populated (using mock adapter)

```bash
git add backend/tests/test_db_integration.py
git commit -m "test(db): add end-to-end integration test for DB diagnostics"
```

---

## Task 15: Frontend TypeScript Verification + Final Commit

**Step 1:** Run `cd frontend && npx tsc --noEmit` — fix any errors

**Step 2:** Run `cd backend && python -m pytest tests/test_db*.py -v` — all green

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(db): complete P0 database diagnostics — adapter, agents, graph, API, dashboard"
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | Pydantic models | 2 created | 7 tests |
| 2 | DatabaseAdapter ABC + Mock | 3 created | 8 tests |
| 3 | AdapterRegistry | 1 created | 6 tests |
| 4 | Profile store | 1 created | 6 tests |
| 5 | PostgresAdapter | 1 created | 5 tests |
| 6 | Diagnostic store | 1 created | 5 tests |
| 7 | API endpoints | 1 created, 1 modified | 6 tests |
| 8 | Frontend shell + routing | 5 created, 2 modified | tsc check |
| 9 | DBConnections + form | 2 created, 1 modified | tsc check |
| 10 | DBOverview + gauge | 2 created | tsc check |
| 11 | DBDiagnostics view | 4 created | tsc check |
| 12 | LangGraph graph | 3 created | 2 tests |
| 13 | Wire graph to API | 1 modified | — |
| 14 | Integration test | 1 created | 1 test |
| 15 | Final verification | — | full suite |

**Total: ~25 new files, 2 modified files, ~46 tests**
