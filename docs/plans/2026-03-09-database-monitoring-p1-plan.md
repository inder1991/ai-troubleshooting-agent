# Database Monitoring P1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship continuous database monitoring with time-series metrics, alert rules, and a schema browser for PostgreSQL.

**Architecture:** DBMonitor polling service writes snapshots to InfluxDB via MetricsStore, evaluates thresholds via existing AlertEngine, broadcasts updates via WebSocket. Frontend adds Monitoring tab (SVG charts + alert rules) and Schema tab (tree browser with table detail drill-down).

**Tech Stack:** Python 3.12, FastAPI, asyncio, InfluxDB (via existing MetricsStore), existing AlertEngine/NotificationDispatcher, React 18, TypeScript, Tailwind CSS, inline SVG polylines, pytest

**Design doc:** `docs/plans/2026-03-09-database-monitoring-p1-design.md`

---

## Task 1: Add Schema Models (TableDetail, ColumnInfo, IndexInfo)

**Files:**
- Modify: `backend/src/database/models.py:66-67` (after SchemaSnapshot)
- Test: `backend/tests/test_db_models.py`

**Step 1: Write the failing test**

```python
# Append to backend/tests/test_db_models.py

def test_column_info():
    from src.database.models import ColumnInfo
    c = ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True)
    assert c.is_pk is True
    assert c.nullable is False


def test_index_info():
    from src.database.models import IndexInfo
    i = IndexInfo(name="pk_orders", columns=["id"], unique=True, size_bytes=8192)
    assert i.unique is True


def test_table_detail():
    from src.database.models import TableDetail, ColumnInfo, IndexInfo
    td = TableDetail(
        name="orders", schema_name="public",
        columns=[ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True)],
        indexes=[IndexInfo(name="pk_orders", columns=["id"], unique=True, size_bytes=8192)],
        row_estimate=120000, total_size_bytes=256000000, bloat_ratio=0.05,
    )
    assert td.row_estimate == 120000
    assert len(td.columns) == 1
    assert td.bloat_ratio == 0.05
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_models.py::test_column_info tests/test_db_models.py::test_index_info tests/test_db_models.py::test_table_detail -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Add to `backend/src/database/models.py` after `SchemaSnapshot` (after line 67):

```python
class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    default: Optional[str] = None
    is_pk: bool = False


class IndexInfo(BaseModel):
    name: str
    columns: list[str] = []
    unique: bool = False
    size_bytes: int = 0


class TableDetail(BaseModel):
    name: str
    schema_name: str = "public"
    columns: list[ColumnInfo] = []
    indexes: list[IndexInfo] = []
    row_estimate: int = 0
    total_size_bytes: int = 0
    bloat_ratio: float = 0.0
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_models.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/database/models.py backend/tests/test_db_models.py
git commit -m "feat(db): add TableDetail, ColumnInfo, IndexInfo models"
```

---

## Task 2: Add get_table_detail() to Adapter ABC + Mock + Postgres

**Files:**
- Modify: `backend/src/database/adapters/base.py:96` (after _fetch_schema_snapshot)
- Modify: `backend/src/database/adapters/mock_adapter.py:75` (after _fetch_schema_snapshot)
- Modify: `backend/src/database/adapters/postgres.py:184` (after _fetch_schema_snapshot)
- Test: `backend/tests/test_db_adapter_base.py`

**Step 1: Write the failing test**

```python
# Append to backend/tests/test_db_adapter_base.py

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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_adapter_base.py::test_mock_get_table_detail -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

Add to `backend/src/database/adapters/base.py` after line 96 (after `_fetch_schema_snapshot` abstract method):

```python
    @abstractmethod
    async def get_table_detail(self, table_name: str):
        """Fetch detailed info for a single table (columns, indexes, size, bloat)."""
        ...
```

Also add import at top of `base.py`:
```python
from ..models import (
    ActiveQuery,
    ConnectionPoolSnapshot,
    PerfSnapshot,
    QueryResult,
    ReplicationSnapshot,
    SchemaSnapshot,
    TableDetail,  # NEW
)
```

And add return type annotation: `async def get_table_detail(self, table_name: str) -> TableDetail: ...`

Add to `backend/src/database/adapters/mock_adapter.py` (add `TableDetail, ColumnInfo, IndexInfo` to imports, then add method):

```python
    async def get_table_detail(self, table_name: str) -> TableDetail:
        return TableDetail(
            name=table_name,
            schema_name="public",
            columns=[
                ColumnInfo(name="id", data_type="integer", nullable=False, is_pk=True),
                ColumnInfo(name="name", data_type="varchar(255)", nullable=True),
                ColumnInfo(name="created_at", data_type="timestamp", nullable=False),
            ],
            indexes=[
                IndexInfo(name=f"pk_{table_name}", columns=["id"], unique=True, size_bytes=8192),
                IndexInfo(name=f"idx_{table_name}_created", columns=["created_at"], unique=False, size_bytes=16384),
            ],
            row_estimate=120000,
            total_size_bytes=256000000,
            bloat_ratio=0.05,
        )
```

Add to `backend/src/database/adapters/postgres.py` (add `TableDetail, ColumnInfo, IndexInfo` to imports, then add method after `_fetch_schema_snapshot`):

```python
    async def get_table_detail(self, table_name: str) -> TableDetail:
        if not self._conn:
            from .base import AdapterHealth
            raise RuntimeError("Not connected")

        # Columns
        col_rows = await self._conn.fetch("""
            SELECT c.column_name, c.data_type, c.is_nullable, c.column_default,
                   CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_pk
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                  ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = $1 AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON pk.column_name = c.column_name
            WHERE c.table_name = $1 AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
        """, table_name)

        columns = [
            ColumnInfo(
                name=r["column_name"], data_type=r["data_type"],
                nullable=r["is_nullable"] == "YES",
                default=r["column_default"], is_pk=r["is_pk"],
            ) for r in col_rows
        ]

        # Indexes
        idx_rows = await self._conn.fetch("""
            SELECT indexname, indexdef,
                   pg_relation_size(quote_ident(indexname)::regclass) AS size_bytes
            FROM pg_indexes
            WHERE tablename = $1 AND schemaname = 'public'
        """, table_name)

        indexes = [
            IndexInfo(
                name=r["indexname"],
                columns=[],  # parse from indexdef if needed
                unique="UNIQUE" in (r["indexdef"] or ""),
                size_bytes=r["size_bytes"] or 0,
            ) for r in idx_rows
        ]

        # Table stats
        stat_row = await self._conn.fetchrow("""
            SELECT n_live_tup AS row_estimate,
                   pg_total_relation_size(quote_ident($1)::regclass) AS total_size,
                   CASE WHEN n_live_tup > 0
                     THEN n_dead_tup::float / n_live_tup
                     ELSE 0 END AS bloat_ratio
            FROM pg_stat_user_tables
            WHERE relname = $1
        """, table_name)

        return TableDetail(
            name=table_name,
            schema_name="public",
            columns=columns,
            indexes=indexes,
            row_estimate=stat_row["row_estimate"] if stat_row else 0,
            total_size_bytes=stat_row["total_size"] if stat_row else 0,
            bloat_ratio=round(stat_row["bloat_ratio"], 4) if stat_row else 0.0,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_adapter_base.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/database/adapters/ backend/tests/test_db_adapter_base.py
git commit -m "feat(db): add get_table_detail to adapter ABC, mock, and postgres"
```

---

## Task 3: Add DB Metric Write/Query Methods to MetricsStore

**Files:**
- Modify: `backend/src/network/metrics_store.py:153` (after write_dns_metric)
- Test: `backend/tests/test_db_monitor.py` (new file, test the write method signatures)

**Step 1: Write the failing test**

```python
# backend/tests/test_db_monitor.py
"""Tests for DB monitoring components."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_write_db_metric():
    from src.network.metrics_store import MetricsStore
    store = MetricsStore.__new__(MetricsStore)
    store._write_api = AsyncMock()
    store._bucket = "test"
    await store.write_db_metric("profile-1", "postgresql", "cache_hit_ratio", 0.95)
    store._write_api.write.assert_called_once()


@pytest.mark.asyncio
async def test_query_db_metrics():
    from src.network.metrics_store import MetricsStore
    store = MetricsStore.__new__(MetricsStore)
    store._query_api = AsyncMock()
    store._bucket = "test"
    store._org = "testorg"
    store._query_api.query.return_value = MagicMock(records=[])
    result = await store.query_db_metrics("profile-1", "cache_hit_ratio", "1h", "1m")
    assert result == []
    store._query_api.query.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py::test_write_db_metric tests/test_db_monitor.py::test_query_db_metrics -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

Add to `backend/src/network/metrics_store.py` after the last write method (after `write_dns_metric`):

```python
    async def write_db_metric(
        self, profile_id: str, engine: str, metric: str, value: float,
    ) -> None:
        """Write a single DB metric point."""
        try:
            point = (
                Point("db_metrics")
                .tag("profile_id", profile_id)
                .tag("engine", engine)
                .tag("metric_type", metric)
                .field("value", float(value))
            )
            await self._write_api.write(bucket=self._bucket, record=point)
        except Exception as e:
            logger.warning("Failed to write DB metric: %s", e)

    async def write_db_metrics_batch(
        self, profile_id: str, engine: str, metrics: dict[str, float],
    ) -> None:
        """Write multiple DB metrics at once."""
        try:
            points = []
            for metric, value in metrics.items():
                points.append(
                    Point("db_metrics")
                    .tag("profile_id", profile_id)
                    .tag("engine", engine)
                    .tag("metric_type", metric)
                    .field("value", float(value))
                )
            await self._write_api.write(bucket=self._bucket, record=points)
        except Exception as e:
            logger.warning("Failed to write DB metrics batch: %s", e)

    async def query_db_metrics(
        self, profile_id: str, metric: str, duration: str = "1h",
        resolution: str = "1m",
    ) -> list[dict]:
        """Query time-series DB metrics."""
        if not self._validate_duration(duration) or not self._validate_duration(resolution):
            return []
        if not self._validate_id(profile_id):
            return []
        flux = f'''
            from(bucket: "{self._bucket}")
              |> range(start: -{duration})
              |> filter(fn: (r) => r._measurement == "db_metrics")
              |> filter(fn: (r) => r.profile_id == "{profile_id}")
              |> filter(fn: (r) => r.metric_type == "{metric}")
              |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
              |> yield(name: "mean")
        '''
        try:
            result = await self._query_api.query(flux, org=self._org)
            points = []
            for table in getattr(result, 'records', result):
                if hasattr(table, 'get_time'):
                    points.append({
                        "time": table.get_time().isoformat(),
                        "value": table.get_value(),
                    })
                elif hasattr(table, 'records'):
                    for rec in table.records:
                        points.append({
                            "time": rec.get_time().isoformat(),
                            "value": rec.get_value(),
                        })
            return points
        except Exception as e:
            logger.warning("Failed to query DB metrics: %s", e)
            return []
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/metrics_store.py backend/tests/test_db_monitor.py
git commit -m "feat(db): add write_db_metric, write_db_metrics_batch, query_db_metrics to MetricsStore"
```

---

## Task 4: Create DBMonitor Polling Service

**Files:**
- Create: `backend/src/database/db_monitor.py`
- Test: `backend/tests/test_db_monitor.py` (append tests)

**Step 1: Write the failing test**

```python
# Append to backend/tests/test_db_monitor.py

@pytest.mark.asyncio
async def test_db_monitor_collect_cycle():
    """DBMonitor should collect metrics for each profile and write to InfluxDB."""
    from src.database.db_monitor import DBMonitor
    from src.database.adapters.mock_adapter import MockDatabaseAdapter
    from src.database.adapters.registry import DatabaseAdapterRegistry

    # Set up mock profile store
    mock_profile_store = MagicMock()
    mock_profile_store.list_all.return_value = [
        {"id": "p1", "name": "test-pg", "engine": "postgresql",
         "host": "localhost", "port": 5432, "database": "testdb",
         "username": "u", "password": "p"},
    ]

    # Set up adapter registry with a mock adapter
    registry = DatabaseAdapterRegistry()
    adapter = MockDatabaseAdapter(engine="postgresql", host="localhost", port=5432, database="testdb")
    await adapter.connect()
    registry.register("p1", adapter, profile_id="p1")

    # Mock metrics store
    mock_metrics = AsyncMock()

    # Mock alert engine
    mock_alert_engine = AsyncMock()

    # Mock broadcast
    mock_broadcast = AsyncMock()

    monitor = DBMonitor(
        profile_store=mock_profile_store,
        adapter_registry=registry,
        metrics_store=mock_metrics,
        alert_engine=mock_alert_engine,
        broadcast_callback=mock_broadcast,
    )

    await monitor._collect_cycle()

    # Verify metrics were written
    assert mock_metrics.write_db_metrics_batch.call_count >= 1
    # Verify broadcast was called
    mock_broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_db_monitor_snapshot():
    """DBMonitor.get_snapshot() should return current state."""
    from src.database.db_monitor import DBMonitor

    mock_profile_store = MagicMock()
    mock_profile_store.list_all.return_value = []
    registry = MagicMock()

    monitor = DBMonitor(
        profile_store=mock_profile_store,
        adapter_registry=registry,
        metrics_store=None,
        alert_engine=None,
        broadcast_callback=AsyncMock(),
    )

    snapshot = monitor.get_snapshot()
    assert snapshot["running"] is False
    assert snapshot["profiles"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py::test_db_monitor_collect_cycle tests/test_db_monitor.py::test_db_monitor_snapshot -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# backend/src/database/db_monitor.py
"""DBMonitor — continuous polling service for database metrics.

Mirrors NetworkMonitor pattern: async loop, multi-profile collection,
InfluxDB writes, AlertEngine evaluation, WebSocket broadcast.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class DBMonitor:
    """Polls all enabled DB profiles on a configurable interval."""

    def __init__(
        self,
        profile_store,
        adapter_registry,
        metrics_store,
        alert_engine,
        broadcast_callback: Optional[Callable[..., Coroutine]] = None,
        interval: int = 30,
    ):
        self.profile_store = profile_store
        self.adapter_registry = adapter_registry
        self.metrics_store = metrics_store
        self.alert_engine = alert_engine
        self._broadcast = broadcast_callback
        self.interval = interval

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._profile_statuses: dict[str, dict] = {}
        self._last_cycle_at: Optional[float] = None
        self._cycle_duration: float = 0.0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("DBMonitor started (interval=%ds)", self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("DBMonitor stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._collect_cycle()
            except Exception as e:
                logger.error("DBMonitor cycle error: %s", e)
            await asyncio.sleep(self.interval)

    async def _collect_cycle(self) -> None:
        start = time.time()
        profiles = self.profile_store.list_all()

        for profile in profiles:
            pid = profile["id"]
            try:
                adapter = self.adapter_registry.get_by_profile(pid)
                if not adapter:
                    self._profile_statuses[pid] = {
                        "id": pid, "name": profile["name"],
                        "status": "not_connected", "last_collected_at": None,
                    }
                    continue

                if not adapter._connected:
                    await adapter.connect()

                await self._collect_profile_metrics(profile, adapter)

                self._profile_statuses[pid] = {
                    "id": pid, "name": profile["name"],
                    "status": "healthy", "last_collected_at": time.time(),
                }

                # Evaluate alerts for this profile
                if self.alert_engine:
                    try:
                        await self.alert_engine.evaluate(f"db:{pid}")
                    except Exception as e:
                        logger.warning("Alert evaluation failed for %s: %s", pid, e)

            except Exception as e:
                logger.warning("DBMonitor collection failed for %s: %s", pid, e)
                self._profile_statuses[pid] = {
                    "id": pid, "name": profile.get("name", pid),
                    "status": "error", "error": str(e),
                    "last_collected_at": None,
                }

        self._last_cycle_at = time.time()
        self._cycle_duration = time.time() - start

        # Broadcast update
        if self._broadcast:
            await self._broadcast({
                "type": "db_monitor_update",
                "data": self.get_snapshot(),
            })

    async def _collect_profile_metrics(self, profile: dict, adapter) -> None:
        """Collect all metrics from a single profile and write to InfluxDB."""
        pid = profile["id"]
        engine = profile.get("engine", "unknown")

        # Refresh adapter caches
        await adapter.refresh_snapshot()

        stats = await adapter.get_performance_stats()
        pool = await adapter.get_connection_pool()
        repl = await adapter.get_replication_status()
        queries = await adapter.get_active_queries()

        if not self.metrics_store:
            return

        # Compute derived metrics
        utilization_pct = 0.0
        if pool.max_connections > 0:
            utilization_pct = (pool.active + pool.waiting) / pool.max_connections * 100

        slow_queries = [q for q in queries if q.duration_ms > 5000]
        max_duration = max((q.duration_ms for q in queries), default=0)
        avg_duration = (
            sum(q.duration_ms for q in queries) / len(queries) if queries else 0
        )

        metrics = {
            "cache_hit_ratio": stats.cache_hit_ratio,
            "transactions_per_sec": stats.transactions_per_sec,
            "deadlocks": float(stats.deadlocks),
            "uptime_seconds": float(stats.uptime_seconds),
            "conn_active": float(pool.active),
            "conn_idle": float(pool.idle),
            "conn_waiting": float(pool.waiting),
            "conn_max": float(pool.max_connections),
            "conn_utilization_pct": utilization_pct,
            "repl_lag_bytes": float(repl.replication_lag_bytes),
            "repl_lag_seconds": repl.replication_lag_seconds,
            "slow_query_count": float(len(slow_queries)),
            "max_query_duration_ms": max_duration,
            "avg_query_duration_ms": avg_duration,
            "total_active_queries": float(len(queries)),
        }

        await self.metrics_store.write_db_metrics_batch(pid, engine, metrics)

    def get_snapshot(self) -> dict:
        return {
            "running": self._running,
            "interval": self.interval,
            "last_cycle_at": self._last_cycle_at,
            "cycle_duration": self._cycle_duration,
            "profiles": list(self._profile_statuses.values()),
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/database/db_monitor.py backend/tests/test_db_monitor.py
git commit -m "feat(db): add DBMonitor polling service"
```

---

## Task 5: Create Default DB Alert Rules

**Files:**
- Create: `backend/src/database/db_alert_rules.py`
- Test: `backend/tests/test_db_monitor.py` (append test)

**Step 1: Write the failing test**

```python
# Append to backend/tests/test_db_monitor.py

def test_default_db_alert_rules():
    from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
    assert len(DEFAULT_DB_ALERT_RULES) >= 5
    rule_ids = [r.id for r in DEFAULT_DB_ALERT_RULES]
    assert "db-conn-pool-warning" in rule_ids
    assert "db-cache-hit-low" in rule_ids
    for rule in DEFAULT_DB_ALERT_RULES:
        assert rule.entity_type == "database"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py::test_default_db_alert_rules -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# backend/src/database/db_alert_rules.py
"""Default alert rules for database monitoring."""
from __future__ import annotations

from src.network.alert_engine import AlertRule

DEFAULT_DB_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        id="db-conn-pool-warning",
        name="DB Connection Pool Saturation",
        severity="warning",
        entity_type="database",
        entity_filter="*",
        metric="conn_utilization_pct",
        condition="gt",
        threshold=80.0,
        duration_seconds=60,
        cooldown_seconds=300,
        description="Connection pool usage above 80%",
    ),
    AlertRule(
        id="db-conn-pool-critical",
        name="DB Connection Pool Critical",
        severity="critical",
        entity_type="database",
        entity_filter="*",
        metric="conn_utilization_pct",
        condition="gt",
        threshold=95.0,
        duration_seconds=30,
        cooldown_seconds=300,
        description="Connection pool usage above 95%",
    ),
    AlertRule(
        id="db-cache-hit-low",
        name="DB Low Cache Hit Ratio",
        severity="warning",
        entity_type="database",
        entity_filter="*",
        metric="cache_hit_ratio",
        condition="lt",
        threshold=0.9,
        duration_seconds=120,
        cooldown_seconds=600,
        description="Cache hit ratio below 90%",
    ),
    AlertRule(
        id="db-repl-lag-warning",
        name="DB Replication Lag Warning",
        severity="warning",
        entity_type="database",
        entity_filter="*",
        metric="repl_lag_bytes",
        condition="gt",
        threshold=10_000_000.0,
        duration_seconds=60,
        cooldown_seconds=300,
        description="Replication lag above 10 MB",
    ),
    AlertRule(
        id="db-repl-lag-critical",
        name="DB Replication Lag Critical",
        severity="critical",
        entity_type="database",
        entity_filter="*",
        metric="repl_lag_bytes",
        condition="gt",
        threshold=100_000_000.0,
        duration_seconds=30,
        cooldown_seconds=300,
        description="Replication lag above 100 MB",
    ),
    AlertRule(
        id="db-deadlocks",
        name="DB Deadlocks Detected",
        severity="warning",
        entity_type="database",
        entity_filter="*",
        metric="deadlocks",
        condition="gt",
        threshold=0.0,
        duration_seconds=30,
        cooldown_seconds=600,
        description="Deadlocks detected since last snapshot",
    ),
    AlertRule(
        id="db-slow-queries",
        name="DB Slow Query Spike",
        severity="warning",
        entity_type="database",
        entity_filter="*",
        metric="slow_query_count",
        condition="gt",
        threshold=5.0,
        duration_seconds=60,
        cooldown_seconds=300,
        description="More than 5 slow queries (>5s) active",
    ),
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_monitor.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/database/db_alert_rules.py backend/tests/test_db_monitor.py
git commit -m "feat(db): add default DB alert rules"
```

---

## Task 6: Add Monitoring + Alert + Schema API Endpoints

**Files:**
- Modify: `backend/src/api/db_endpoints.py:274` (append new endpoints)
- Test: `backend/tests/test_db_monitor_endpoints.py` (new file)

**Step 1: Write the failing test**

```python
# backend/tests/test_db_monitor_endpoints.py
"""Tests for /api/db/monitor, /api/db/alerts, /api/db/schema endpoints."""
import pytest
from fastapi.testclient import TestClient
import tempfile
import os


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DB_DIAGNOSTICS_DB_PATH"] = path

    import src.api.db_endpoints as mod
    mod._profile_store = None
    mod._run_store = None
    mod._db_monitor = None

    from src.api.db_endpoints import db_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(db_router)
    yield TestClient(app)
    os.unlink(path)


class TestMonitorEndpoints:
    def test_monitor_status(self, client):
        resp = client.get("/api/db/monitor/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data

    def test_monitor_metrics_no_influx(self, client):
        """Without InfluxDB, metrics endpoint returns empty."""
        resp = client.get("/api/db/monitor/metrics/fake-profile/cache_hit_ratio?duration=1h&resolution=1m")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAlertEndpoints:
    def test_list_alert_rules(self, client):
        resp = client.get("/api/db/alerts/rules")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_active_alerts_empty(self, client):
        resp = client.get("/api/db/alerts/active")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSchemaEndpoints:
    def test_schema_missing_profile(self, client):
        resp = client.get("/api/db/schema/nonexistent")
        assert resp.status_code == 404

    def test_table_detail_missing_profile(self, client):
        resp = client.get("/api/db/schema/nonexistent/table/orders")
        assert resp.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_monitor_endpoints.py -v`
Expected: FAIL (404s on new routes)

**Step 3: Write minimal implementation**

Append to `backend/src/api/db_endpoints.py` after the last endpoint:

```python
# ── Module-level monitoring state ──

_db_monitor = None
_metrics_store = None
_alert_engine = None
_db_adapter_registry = None


def _get_db_monitor():
    return _db_monitor


def _get_metrics_store():
    return _metrics_store


def _get_alert_engine():
    return _alert_engine


def _get_db_adapter_registry():
    global _db_adapter_registry
    if _db_adapter_registry is None:
        from src.database.adapters.registry import DatabaseAdapterRegistry
        _db_adapter_registry = DatabaseAdapterRegistry()
    return _db_adapter_registry


# ── Monitor endpoints ──


@db_router.get("/monitor/status")
def monitor_status():
    monitor = _get_db_monitor()
    if monitor:
        return monitor.get_snapshot()
    return {"running": False, "interval": 30, "profiles": []}


@db_router.get("/monitor/metrics/{profile_id}/{metric}")
async def monitor_metrics(profile_id: str, metric: str, duration: str = "1h", resolution: str = "1m"):
    ms = _get_metrics_store()
    if not ms:
        return []
    return await ms.query_db_metrics(profile_id, metric, duration, resolution)


@db_router.post("/monitor/start")
async def monitor_start():
    monitor = _get_db_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="DBMonitor not initialized")
    await monitor.start()
    return {"status": "started"}


@db_router.post("/monitor/stop")
async def monitor_stop():
    monitor = _get_db_monitor()
    if not monitor:
        raise HTTPException(status_code=503, detail="DBMonitor not initialized")
    await monitor.stop()
    return {"status": "stopped"}


# ── Alert endpoints ──


@db_router.get("/alerts/rules")
def list_alert_rules():
    engine = _get_alert_engine()
    if not engine:
        from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
        return [
            {"id": r.id, "name": r.name, "severity": r.severity,
             "metric": r.metric, "condition": r.condition,
             "threshold": r.threshold, "enabled": r.enabled}
            for r in DEFAULT_DB_ALERT_RULES
        ]
    rules = engine.list_rules()
    return [
        r for r in rules
        if getattr(r, 'entity_type', '') == 'database'
           or (isinstance(r, dict) and r.get('entity_type') == 'database')
    ]


@db_router.post("/alerts/rules")
def create_alert_rule(rule: dict):
    engine = _get_alert_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")
    rule["entity_type"] = "database"
    from src.network.alert_engine import AlertRule
    new_rule = AlertRule(**rule)
    engine.add_rule(new_rule)
    return {"id": new_rule.id, "status": "created"}


@db_router.put("/alerts/rules/{rule_id}")
def update_alert_rule(rule_id: str, updates: dict):
    engine = _get_alert_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")
    engine.update_rule(rule_id, **updates)
    return {"id": rule_id, "status": "updated"}


@db_router.delete("/alerts/rules/{rule_id}")
def delete_alert_rule(rule_id: str):
    engine = _get_alert_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="AlertEngine not initialized")
    engine.remove_rule(rule_id)
    return {"status": "deleted"}


@db_router.get("/alerts/active")
def active_alerts():
    engine = _get_alert_engine()
    if not engine:
        return []
    all_alerts = engine.get_active_alerts()
    return [a for a in all_alerts if a.get("entity_id", "").startswith("db:")]


@db_router.get("/alerts/history")
def alert_history(profile_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 50):
    engine = _get_alert_engine()
    if not engine:
        return []
    history = engine.get_alert_history(
        entity_id=f"db:{profile_id}" if profile_id else None,
        severity=severity,
        limit=limit,
    )
    return history


# ── Schema endpoints ──


@db_router.get("/schema/{profile_id}")
async def get_schema(profile_id: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    registry = _get_db_adapter_registry()
    adapter = registry.get_by_profile(profile_id)

    if not adapter:
        # Create temporary adapter for schema fetch
        try:
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
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    try:
        schema = await adapter.get_schema_snapshot()
        return schema.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@db_router.get("/schema/{profile_id}/table/{table_name}")
async def get_table_detail(profile_id: str, table_name: str):
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    registry = _get_db_adapter_registry()
    adapter = registry.get_by_profile(profile_id)

    if not adapter:
        try:
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
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    try:
        detail = await adapter.get_table_detail(table_name)
        return detail.model_dump()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_monitor_endpoints.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/api/db_endpoints.py backend/tests/test_db_monitor_endpoints.py
git commit -m "feat(db): add monitoring, alert, and schema API endpoints"
```

---

## Task 7: Wire DBMonitor into main.py Startup

**Files:**
- Modify: `backend/src/api/main.py:290` (before shutdown handler)

**Step 1: Add DBMonitor startup**

In `backend/src/api/main.py` inside the `startup()` function, after the search endpoints initialization (around line 290), add:

```python
        # ── Initialize DB Monitor ──
        try:
            from src.database.db_monitor import DBMonitor
            from src.database.db_alert_rules import DEFAULT_DB_ALERT_RULES
            import src.api.db_endpoints as db_ep

            db_profile_store = db_ep._get_profile_store()
            db_registry = db_ep._get_db_adapter_registry()

            # Create alert engine with DB default rules
            db_alert_engine = None
            if hasattr(monitor, 'alert_engine') and monitor.alert_engine:
                db_alert_engine = monitor.alert_engine
                for rule in DEFAULT_DB_ALERT_RULES:
                    try:
                        db_alert_engine.add_rule(rule)
                    except Exception:
                        pass  # rule may already exist

            db_monitor = DBMonitor(
                profile_store=db_profile_store,
                adapter_registry=db_registry,
                metrics_store=metrics_store,
                alert_engine=db_alert_engine,
                broadcast_callback=manager.broadcast,
            )
            db_ep._db_monitor = db_monitor
            db_ep._metrics_store = metrics_store
            db_ep._alert_engine = db_alert_engine
            db_ep._db_adapter_registry = db_registry

            asyncio.create_task(db_monitor.start())
            logger.info("DBMonitor started")
        except Exception as e:
            logger.warning("DBMonitor startup failed: %s", e)
```

Also add to `shutdown()`:

```python
        import src.api.db_endpoints as db_ep
        if db_ep._db_monitor:
            await db_ep._db_monitor.stop()
            logger.info("DBMonitor stopped")
```

**Step 2: Run all DB tests to verify no regressions**

Run: `cd backend && python3 -m pytest tests/test_db_models.py tests/test_db_adapter_base.py tests/test_db_registry.py tests/test_db_profile_store.py tests/test_db_diagnostic_store.py tests/test_db_endpoints.py tests/test_db_graph.py tests/test_db_monitor.py tests/test_db_monitor_endpoints.py tests/test_postgres_adapter.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add backend/src/api/main.py
git commit -m "feat(db): wire DBMonitor into app startup/shutdown"
```

---

## Task 8: Frontend — Add Monitoring + Schema Tabs to DatabaseLayout

**Files:**
- Modify: `frontend/src/components/Database/DatabaseLayout.tsx:5-16` (imports and sidebar items)
- Create: `frontend/src/components/Database/DBMonitoring.tsx`
- Create: `frontend/src/components/Database/DBSchema.tsx`
- Modify: `frontend/src/services/api.ts` (append new API functions)

**Step 1: Add API functions**

Append to `frontend/src/services/api.ts`:

```typescript
// ── DB Monitoring API ──

export const fetchDBMonitorStatus = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/status`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch monitor status'));
  return resp.json();
};

export const fetchDBMonitorMetrics = async (profileId: string, metric: string, duration = '1h', resolution = '1m') => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/metrics/${profileId}/${metric}?duration=${duration}&resolution=${resolution}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch DB metrics'));
  return resp.json();
};

export const startDBMonitor = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/start`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to start monitor'));
  return resp.json();
};

export const stopDBMonitor = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/monitor/stop`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to stop monitor'));
  return resp.json();
};

export const fetchDBAlertRules = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/rules`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alert rules'));
  return resp.json();
};

export const fetchDBActiveAlerts = async () => {
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/active`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch active alerts'));
  return resp.json();
};

export const fetchDBAlertHistory = async (profileId?: string, severity?: string, limit = 50) => {
  const params = new URLSearchParams();
  if (profileId) params.set('profile_id', profileId);
  if (severity) params.set('severity', severity);
  params.set('limit', String(limit));
  const resp = await fetch(`${API_BASE_URL}/api/db/alerts/history?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch alert history'));
  return resp.json();
};

export const fetchDBSchema = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/schema/${profileId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch schema'));
  return resp.json();
};

export const fetchDBTableDetail = async (profileId: string, tableName: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/schema/${profileId}/table/${tableName}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch table detail'));
  return resp.json();
};
```

**Step 2: Update DatabaseLayout**

Replace lines 5-16 of `frontend/src/components/Database/DatabaseLayout.tsx`:

```typescript
import DBOverview from './DBOverview';
import DBConnections from './DBConnections';
import DBDiagnostics from './DBDiagnostics';
import DBMonitoring from './DBMonitoring';
import DBSchema from './DBSchema';

type DBView = 'overview' | 'connections' | 'diagnostics' | 'monitoring' | 'schema';

const sidebarItems: { id: DBView; label: string; icon: string }[] = [
  { id: 'overview', label: 'Overview', icon: 'dashboard' },
  { id: 'connections', label: 'Connections', icon: 'cable' },
  { id: 'diagnostics', label: 'Diagnostics', icon: 'troubleshoot' },
  { id: 'monitoring', label: 'Monitoring', icon: 'monitoring' },
  { id: 'schema', label: 'Schema', icon: 'account_tree' },
];
```

And add view rendering (lines 50-52 area):

```typescript
          {activeView === 'monitoring' && <DBMonitoring />}
          {activeView === 'schema' && <DBSchema />}
```

**Step 3: Create DBMonitoring.tsx**

Create `frontend/src/components/Database/DBMonitoring.tsx` — full component with time-series charts, active alerts, alert rules table. (See Task 9 for full code.)

**Step 4: Create DBSchema.tsx**

Create `frontend/src/components/Database/DBSchema.tsx` — full component with tree browser and table detail. (See Task 10 for full code.)

**Step 5: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 6: Commit**

```bash
git add frontend/src/components/Database/ frontend/src/services/api.ts
git commit -m "feat(db): add Monitoring and Schema tabs to DatabaseLayout"
```

---

## Task 9: Frontend — DBMonitoring Component

**Files:**
- Create: `frontend/src/components/Database/DBMonitoring.tsx`

Full component:

```tsx
/**
 * DBMonitoring — Time-series charts, active alerts, alert rules.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchDBProfiles,
  fetchDBMonitorStatus,
  fetchDBMonitorMetrics,
  fetchDBActiveAlerts,
  fetchDBAlertRules,
} from '../../services/api';

interface MetricPoint { time: string; value: number }
interface Alert { key: string; rule_name: string; severity: string; message: string; fired_at: string; entity_id: string }
interface AlertRule { id: string; name: string; severity: string; metric: string; condition: string; threshold: number; enabled: boolean }

const METRICS = [
  { key: 'conn_utilization_pct', label: 'Connection Utilization %', color: '#07b6d5', unit: '%' },
  { key: 'cache_hit_ratio', label: 'Cache Hit Ratio', color: '#10b981', unit: '' },
  { key: 'transactions_per_sec', label: 'Transactions / sec', color: '#f59e0b', unit: '' },
  { key: 'repl_lag_bytes', label: 'Replication Lag', color: '#ef4444', unit: 'B' },
];

const TIME_RANGES = [
  { label: '1h', duration: '1h', resolution: '1m' },
  { label: '6h', duration: '6h', resolution: '5m' },
  { label: '24h', duration: '24h', resolution: '15m' },
  { label: '7d', duration: '7d', resolution: '1h' },
];

function MiniChart({ points, color, height = 60 }: { points: MetricPoint[]; color: string; height?: number }) {
  if (points.length === 0) return <div className="text-xs text-slate-600 text-center py-4">No data</div>;
  const values = points.map((p) => p.value);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const svgPoints = points.map((p, i) =>
    `${(i / (points.length - 1)) * 100},${height - ((p.value - min) / range) * (height - 8) - 4}`
  ).join(' ');

  return (
    <svg viewBox={`0 0 100 ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={svgPoints} />
    </svg>
  );
}

const DBMonitoring: React.FC = () => {
  const [profiles, setProfiles] = useState<{ id: string; name: string; engine: string }[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [timeRange, setTimeRange] = useState(TIME_RANGES[0]);
  const [chartData, setChartData] = useState<Record<string, MetricPoint[]>>({});
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [monitorStatus, setMonitorStatus] = useState<{ running: boolean }>({ running: false });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDBProfiles().then((list: { id: string; name: string; engine: string }[]) => {
      setProfiles(list);
      if (list.length > 0 && !selectedProfileId) setSelectedProfileId(list[0].id);
    }).catch(() => {});
    fetchDBMonitorStatus().then(setMonitorStatus).catch(() => {});
    fetchDBAlertRules().then(setAlertRules).catch(() => {});
    fetchDBActiveAlerts().then(setAlerts).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadCharts = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoading(true);
    const data: Record<string, MetricPoint[]> = {};
    await Promise.all(
      METRICS.map(async (m) => {
        try {
          data[m.key] = await fetchDBMonitorMetrics(selectedProfileId, m.key, timeRange.duration, timeRange.resolution);
        } catch { data[m.key] = []; }
      }),
    );
    setChartData(data);
    setLoading(false);
  }, [selectedProfileId, timeRange]);

  useEffect(() => { loadCharts(); }, [loadCharts]);

  const latestValue = (key: string) => {
    const pts = chartData[key];
    if (!pts || pts.length === 0) return '—';
    const v = pts[pts.length - 1].value;
    if (key === 'cache_hit_ratio') return (v * 100).toFixed(1) + '%';
    if (key === 'repl_lag_bytes') return v > 1_000_000 ? (v / 1_000_000).toFixed(1) + ' MB' : (v / 1_000).toFixed(0) + ' KB';
    return v.toFixed(1);
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-100">Monitoring</h2>
          <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 outline-none">
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="flex rounded-lg border border-slate-600 overflow-hidden">
            {TIME_RANGES.map((tr) => (
              <button key={tr.label} onClick={() => setTimeRange(tr)}
                className={`px-2.5 py-1 text-xs ${timeRange.label === tr.label ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'}`}>
                {tr.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${monitorStatus.running ? 'bg-emerald-400' : 'bg-slate-500'}`} />
          <span className="text-xs text-slate-500">{monitorStatus.running ? 'Collecting' : 'Stopped'}</span>
          <button onClick={loadCharts} className="p-1.5 text-slate-400 hover:text-slate-200">
            <span className="material-symbols-outlined text-[16px]">refresh</span>
          </button>
        </div>
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-2 gap-4">
        {METRICS.map((m) => (
          <div key={m.key} className="rounded-xl border border-slate-700/50 bg-[#0d2328] p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400">{m.label}</span>
              <span className="text-sm font-semibold" style={{ color: m.color }}>{latestValue(m.key)}</span>
            </div>
            {loading ? (
              <div className="h-[60px] flex items-center justify-center"><span className="material-symbols-outlined animate-spin text-slate-600">progress_activity</span></div>
            ) : (
              <MiniChart points={chartData[m.key] || []} color={m.color} />
            )}
          </div>
        ))}
      </div>

      {/* Active alerts */}
      {alerts.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-2">Active Alerts</h3>
          <div className="space-y-1">
            {alerts.map((a) => (
              <div key={a.key} className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
                a.severity === 'critical' ? 'border-red-500/30 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'
              }`}>
                <div className="flex items-center gap-2">
                  <span className={`material-symbols-outlined text-[16px] ${a.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}`}>
                    {a.severity === 'critical' ? 'error' : 'warning'}
                  </span>
                  <span className="text-sm text-slate-200">{a.message || a.rule_name}</span>
                </div>
                <span className="text-xs text-slate-500">{new Date(a.fired_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alert rules */}
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">Alert Rules</h3>
        {alertRules.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No alert rules configured.</p>
        ) : (
          <div className="rounded-xl border border-slate-700/50 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/50 text-slate-400">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Rule</th>
                  <th className="text-left px-3 py-2 font-medium">Metric</th>
                  <th className="text-left px-3 py-2 font-medium">Condition</th>
                  <th className="text-left px-3 py-2 font-medium">Severity</th>
                  <th className="text-left px-3 py-2 font-medium">Enabled</th>
                </tr>
              </thead>
              <tbody>
                {alertRules.map((r) => (
                  <tr key={r.id} className="border-t border-slate-700/50 text-slate-300">
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.metric}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.condition} {r.threshold}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        r.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'
                      }`}>{r.severity}</span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`w-2 h-2 rounded-full inline-block ${r.enabled ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default DBMonitoring;
```

Verify: `cd frontend && npx tsc --noEmit` → 0 errors

---

## Task 10: Frontend — DBSchema Component

**Files:**
- Create: `frontend/src/components/Database/DBSchema.tsx`

Full component:

```tsx
/**
 * DBSchema — Schema browser with table tree and detail view.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchDBProfiles,
  fetchDBSchema,
  fetchDBTableDetail,
} from '../../services/api';

interface SchemaData {
  tables: { name: string; rows?: number; size_bytes?: number }[];
  indexes: { name: string; table?: string; columns?: string[] }[];
  total_size_bytes: number;
}

interface Column { name: string; data_type: string; nullable: boolean; default?: string; is_pk: boolean }
interface Index { name: string; columns: string[]; unique: boolean; size_bytes: number }
interface TableDetailData {
  name: string; schema_name: string; columns: Column[]; indexes: Index[];
  row_estimate: number; total_size_bytes: number; bloat_ratio: number;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

const DBSchema: React.FC = () => {
  const [profiles, setProfiles] = useState<{ id: string; name: string; engine: string }[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [schema, setSchema] = useState<SchemaData | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetail, setTableDetail] = useState<TableDetailData | null>(null);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchDBProfiles().then((list: { id: string; name: string; engine: string }[]) => {
      setProfiles(list);
      if (list.length > 0 && !selectedProfileId) setSelectedProfileId(list[0].id);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSchema = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoading(true);
    try { setSchema(await fetchDBSchema(selectedProfileId)); } catch { setSchema(null); }
    finally { setLoading(false); }
  }, [selectedProfileId]);

  useEffect(() => { loadSchema(); setSelectedTable(null); setTableDetail(null); }, [loadSchema]);

  const handleSelectTable = async (tableName: string) => {
    setSelectedTable(tableName);
    setDetailLoading(true);
    try { setTableDetail(await fetchDBTableDetail(selectedProfileId, tableName)); } catch { setTableDetail(null); }
    finally { setDetailLoading(false); }
  };

  const filteredTables = schema?.tables.filter((t) =>
    t.name.toLowerCase().includes(filter.toLowerCase())
  ) || [];

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: tree */}
      <div className="w-72 flex-shrink-0 border-r border-slate-700/50 flex flex-col">
        <div className="p-3 space-y-2 border-b border-slate-700/50">
          <select value={selectedProfileId} onChange={(e) => setSelectedProfileId(e.target.value)}
            className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 outline-none">
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter tables..."
            className="w-full px-2 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-sm text-slate-100 outline-none" />
        </div>
        <div className="flex-1 overflow-auto p-2">
          {loading ? (
            <div className="text-center py-8"><span className="material-symbols-outlined animate-spin text-slate-600">progress_activity</span></div>
          ) : (
            <>
              <p className="text-xs text-slate-500 px-2 py-1 font-medium uppercase tracking-wide">
                Tables ({filteredTables.length})
                {schema && <span className="ml-1 normal-case">• {formatBytes(schema.total_size_bytes)}</span>}
              </p>
              {filteredTables.map((t) => (
                <button key={t.name} onClick={() => handleSelectTable(t.name)}
                  className={`w-full text-left px-2 py-1.5 rounded text-sm flex items-center justify-between transition-colors ${
                    selectedTable === t.name ? 'bg-cyan-500/10 text-cyan-400' : 'text-slate-300 hover:bg-slate-800/50'
                  }`}>
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[14px] text-slate-500">table_chart</span>
                    <span className="truncate">{t.name}</span>
                  </div>
                  {t.size_bytes !== undefined && (
                    <span className="text-xs text-slate-600 flex-shrink-0">{formatBytes(t.size_bytes)}</span>
                  )}
                </button>
              ))}
            </>
          )}
        </div>
      </div>

      {/* Right: detail */}
      <div className="flex-1 overflow-auto p-6">
        {!selectedTable ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
            <span className="material-symbols-outlined text-3xl">table_chart</span>
            <p>Select a table to view its details</p>
          </div>
        ) : detailLoading ? (
          <div className="flex items-center justify-center h-full"><span className="material-symbols-outlined animate-spin text-slate-600">progress_activity</span></div>
        ) : !tableDetail ? (
          <p className="text-sm text-red-400">Failed to load table detail.</p>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div>
              <h3 className="text-lg font-semibold text-slate-100">{tableDetail.schema_name}.{tableDetail.name}</h3>
              <div className="flex gap-4 mt-1 text-xs text-slate-500">
                <span>~{tableDetail.row_estimate.toLocaleString()} rows</span>
                <span>{formatBytes(tableDetail.total_size_bytes)}</span>
                <span>Bloat: {(tableDetail.bloat_ratio * 100).toFixed(1)}%</span>
              </div>
            </div>

            {/* Columns */}
            <div>
              <h4 className="text-sm font-medium text-slate-400 mb-2">Columns ({tableDetail.columns.length})</h4>
              <div className="rounded-xl border border-slate-700/50 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/50 text-slate-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Name</th>
                      <th className="text-left px-3 py-2 font-medium">Type</th>
                      <th className="text-left px-3 py-2 font-medium">Nullable</th>
                      <th className="text-left px-3 py-2 font-medium">Default</th>
                      <th className="text-left px-3 py-2 font-medium">PK</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableDetail.columns.map((c) => (
                      <tr key={c.name} className="border-t border-slate-700/50 text-slate-300">
                        <td className="px-3 py-1.5 font-mono text-xs">{c.name}</td>
                        <td className="px-3 py-1.5 text-xs text-cyan-400">{c.data_type}</td>
                        <td className="px-3 py-1.5 text-xs">{c.nullable ? 'YES' : 'NO'}</td>
                        <td className="px-3 py-1.5 text-xs text-slate-500">{c.default || '—'}</td>
                        <td className="px-3 py-1.5">
                          {c.is_pk && <span className="material-symbols-outlined text-[14px] text-amber-400">key</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Indexes */}
            <div>
              <h4 className="text-sm font-medium text-slate-400 mb-2">Indexes ({tableDetail.indexes.length})</h4>
              <div className="rounded-xl border border-slate-700/50 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-slate-800/50 text-slate-400">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium">Name</th>
                      <th className="text-left px-3 py-2 font-medium">Columns</th>
                      <th className="text-left px-3 py-2 font-medium">Unique</th>
                      <th className="text-left px-3 py-2 font-medium">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tableDetail.indexes.map((idx) => (
                      <tr key={idx.name} className="border-t border-slate-700/50 text-slate-300">
                        <td className="px-3 py-1.5 font-mono text-xs">{idx.name}</td>
                        <td className="px-3 py-1.5 text-xs">{idx.columns.join(', ') || '—'}</td>
                        <td className="px-3 py-1.5 text-xs">{idx.unique ? 'YES' : '—'}</td>
                        <td className="px-3 py-1.5 text-xs text-slate-500">{formatBytes(idx.size_bytes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DBSchema;
```

Verify: `cd frontend && npx tsc --noEmit` → 0 errors

---

## Task 11: Final Integration Verification

**Step 1: Run all backend tests**

Run: `cd backend && python3 -m pytest tests/test_db_*.py tests/test_postgres_adapter.py -v`
Expected: ALL PASS

**Step 2: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat(db): complete Database Monitoring P1 — monitor, alerts, schema browser"
```
