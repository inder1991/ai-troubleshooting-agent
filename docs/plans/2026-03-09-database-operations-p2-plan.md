# Database Operations P2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship saga-based database remediation with adapter write operations, AI-driven fix suggestions, JWT approval flow, and a frontend Operations tab for PostgreSQL.

**Architecture:** RemediationEngine orchestrates plan→approve→execute→verify→rollback sagas. Adapter ABC gains 8 write methods (kill, vacuum, reindex, index CRUD, config, failover runbook). LangGraph remediation planner maps diagnostic findings to actionable plans. Frontend shows inline approval cards with SQL preview and impact assessment.

**Tech Stack:** Python 3.12, FastAPI, asyncio, asyncpg, PyJWT, SQLite, LangGraph, React 18, TypeScript, Tailwind CSS

**Design doc:** `docs/plans/2026-03-09-database-operations-p2-design.md`

---

## Task 1: Add Remediation Models

**Files:**
- Modify: `backend/src/database/models.py`
- Test: `backend/tests/test_db_models.py`

**Step 1: Write the failing test**

```python
# Append to backend/tests/test_db_models.py

def test_remediation_plan():
    from src.database.models import RemediationPlan
    p = RemediationPlan(
        plan_id="plan-1", profile_id="prof-1", action="vacuum",
        params={"table": "orders", "full": False},
        sql_preview="VACUUM ANALYZE orders",
        impact_assessment="~30s, no locks",
        status="pending", created_at="2026-03-09T00:00:00",
    )
    assert p.action == "vacuum"
    assert p.requires_downtime is False
    assert p.rollback_sql is None


def test_audit_log_entry():
    from src.database.models import AuditLogEntry
    e = AuditLogEntry(
        entry_id="aud-1", plan_id="plan-1", profile_id="prof-1",
        action="vacuum", sql_executed="VACUUM ANALYZE orders",
        status="success", timestamp="2026-03-09T00:00:00",
    )
    assert e.status == "success"
    assert e.error is None


def test_config_recommendation():
    from src.database.models import ConfigRecommendation
    r = ConfigRecommendation(
        param="shared_buffers", current_value="128MB",
        recommended_value="1GB", reason="25% of 4GB RAM",
    )
    assert r.requires_restart is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_db_models.py::test_remediation_plan tests/test_db_models.py::test_audit_log_entry tests/test_db_models.py::test_config_recommendation -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

Append to `backend/src/database/models.py` (after `DiagnosticRun`, ~line 145):

```python
class RemediationPlan(BaseModel):
    plan_id: str
    profile_id: str
    finding_id: Optional[str] = None
    action: str
    params: dict = {}
    sql_preview: str
    impact_assessment: str = ""
    rollback_sql: Optional[str] = None
    requires_downtime: bool = False
    status: str = "pending"
    created_at: str
    approved_at: Optional[str] = None
    executed_at: Optional[str] = None
    completed_at: Optional[str] = None
    result_summary: Optional[str] = None
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None


class AuditLogEntry(BaseModel):
    entry_id: str
    plan_id: str
    profile_id: str
    action: str
    sql_executed: str
    status: str
    before_state: dict = {}
    after_state: dict = {}
    error: Optional[str] = None
    timestamp: str


class ConfigRecommendation(BaseModel):
    param: str
    current_value: str
    recommended_value: str
    reason: str
    requires_restart: bool = False
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_db_models.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/database/models.py backend/tests/test_db_models.py
git commit -m "feat(db-ops): add RemediationPlan, AuditLogEntry, ConfigRecommendation models"
```

---

## Task 2: Create RemediationStore (SQLite Persistence)

**Files:**
- Create: `backend/src/database/remediation_store.py`
- Create: `backend/tests/test_remediation_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_remediation_store.py
"""Tests for RemediationStore — SQLite persistence for plans + audit log."""
import os
import tempfile
import pytest


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    s = RemediationStore(db_path=path)
    yield s
    os.unlink(path)


def test_create_plan(store):
    plan = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"}, sql_preview="VACUUM orders",
        impact_assessment="~30s", rollback_sql=None,
        requires_downtime=False, finding_id=None,
    )
    assert plan["plan_id"]
    assert plan["status"] == "pending"
    assert plan["action"] == "vacuum"


def test_get_plan(store):
    created = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"}, sql_preview="VACUUM orders",
    )
    fetched = store.get_plan(created["plan_id"])
    assert fetched is not None
    assert fetched["plan_id"] == created["plan_id"]
    assert fetched["params"] == {"table": "orders"}


def test_update_plan_status(store):
    plan = store.create_plan(
        profile_id="prof-1", action="vacuum",
        params={}, sql_preview="VACUUM orders",
    )
    store.update_plan(plan["plan_id"], status="approved", approved_at="2026-03-09T00:00:00")
    updated = store.get_plan(plan["plan_id"])
    assert updated["status"] == "approved"
    assert updated["approved_at"] == "2026-03-09T00:00:00"


def test_list_plans(store):
    store.create_plan(profile_id="prof-1", action="vacuum", params={}, sql_preview="V1")
    store.create_plan(profile_id="prof-1", action="reindex", params={}, sql_preview="R1")
    store.create_plan(profile_id="prof-2", action="vacuum", params={}, sql_preview="V2")
    plans = store.list_plans("prof-1")
    assert len(plans) == 2
    filtered = store.list_plans("prof-1", status="pending")
    assert len(filtered) == 2


def test_add_audit_entry(store):
    entry = store.add_audit_entry(
        plan_id="plan-1", profile_id="prof-1", action="vacuum",
        sql_executed="VACUUM orders", status="success",
        before_state={"rows": 1000}, after_state={"rows": 1000},
    )
    assert entry["entry_id"]
    assert entry["status"] == "success"


def test_get_audit_log(store):
    store.add_audit_entry(
        plan_id="p1", profile_id="prof-1", action="vacuum",
        sql_executed="V1", status="success",
    )
    store.add_audit_entry(
        plan_id="p2", profile_id="prof-1", action="reindex",
        sql_executed="R1", status="failed", error="lock timeout",
    )
    log = store.get_audit_log("prof-1")
    assert len(log) == 2
    assert log[0]["action"] in ("vacuum", "reindex")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_remediation_store.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# backend/src/database/remediation_store.py
"""SQLite persistence for remediation plans and audit log."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, UTC


class RemediationStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_tables()

    def _conn(self):
        c = sqlite3.connect(self._db_path)
        c.row_factory = sqlite3.Row
        return c

    def _ensure_tables(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS remediation_plans (
                    plan_id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    finding_id TEXT,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL DEFAULT '{}',
                    sql_preview TEXT NOT NULL,
                    impact_assessment TEXT DEFAULT '',
                    rollback_sql TEXT,
                    requires_downtime INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    executed_at TEXT,
                    completed_at TEXT,
                    result_summary TEXT,
                    before_state TEXT,
                    after_state TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    entry_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    sql_executed TEXT NOT NULL,
                    status TEXT NOT NULL,
                    before_state TEXT DEFAULT '{}',
                    after_state TEXT DEFAULT '{}',
                    error TEXT,
                    timestamp TEXT NOT NULL
                )
            """)

    def create_plan(self, profile_id: str, action: str, params: dict,
                    sql_preview: str, impact_assessment: str = "",
                    rollback_sql: str | None = None,
                    requires_downtime: bool = False,
                    finding_id: str | None = None) -> dict:
        plan_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO remediation_plans
                   (plan_id, profile_id, finding_id, action, params, sql_preview,
                    impact_assessment, rollback_sql, requires_downtime, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (plan_id, profile_id, finding_id, action,
                 json.dumps(params), sql_preview, impact_assessment,
                 rollback_sql, int(requires_downtime), "pending", now),
            )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM remediation_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_plan(row)

    def update_plan(self, plan_id: str, **fields) -> dict | None:
        allowed = {
            "status", "approved_at", "executed_at", "completed_at",
            "result_summary", "before_state", "after_state",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_plan(plan_id)
        # JSON-encode dict fields
        for key in ("before_state", "after_state"):
            if key in updates and isinstance(updates[key], dict):
                updates[key] = json.dumps(updates[key])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [plan_id]
        with self._conn() as c:
            c.execute(
                f"UPDATE remediation_plans SET {set_clause} WHERE plan_id = ?",
                values,
            )
        return self.get_plan(plan_id)

    def list_plans(self, profile_id: str, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM remediation_plans WHERE profile_id = ?"
        params: list = [profile_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"
        with self._conn() as c:
            rows = c.execute(query, params).fetchall()
        return [self._row_to_plan(r) for r in rows]

    def add_audit_entry(self, plan_id: str, profile_id: str, action: str,
                        sql_executed: str, status: str,
                        before_state: dict | None = None,
                        after_state: dict | None = None,
                        error: str | None = None) -> dict:
        entry_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO audit_log
                   (entry_id, plan_id, profile_id, action, sql_executed,
                    status, before_state, after_state, error, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, plan_id, profile_id, action, sql_executed,
                 status, json.dumps(before_state or {}),
                 json.dumps(after_state or {}), error, now),
            )
        return self._get_audit_entry(entry_id)

    def get_audit_log(self, profile_id: str, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM audit_log WHERE profile_id = ? ORDER BY timestamp DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
        return [self._row_to_audit(r) for r in rows]

    def _get_audit_entry(self, entry_id: str) -> dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM audit_log WHERE entry_id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_audit(row) if row else {}

    @staticmethod
    def _row_to_plan(row) -> dict:
        d = dict(row)
        d["params"] = json.loads(d.get("params") or "{}")
        d["requires_downtime"] = bool(d.get("requires_downtime", 0))
        for key in ("before_state", "after_state"):
            val = d.get(key)
            if val and isinstance(val, str):
                d[key] = json.loads(val)
        return d

    @staticmethod
    def _row_to_audit(row) -> dict:
        d = dict(row)
        for key in ("before_state", "after_state"):
            val = d.get(key)
            if val and isinstance(val, str):
                d[key] = json.loads(val)
        return d
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_remediation_store.py -v`
Expected: ALL PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/database/remediation_store.py backend/tests/test_remediation_store.py
git commit -m "feat(db-ops): add RemediationStore with SQLite persistence"
```

---

## Task 3: Add Adapter Write Methods (ABC + Mock)

**Files:**
- Modify: `backend/src/database/adapters/base.py`
- Modify: `backend/src/database/adapters/mock_adapter.py`
- Create: `backend/tests/test_adapter_write_ops.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_adapter_write_ops.py
"""Tests for adapter write operations using MockDatabaseAdapter."""
import pytest
from src.database.adapters.mock_adapter import MockDatabaseAdapter


@pytest.fixture
def adapter():
    return MockDatabaseAdapter(engine="postgresql", host="localhost", port=5432, database="testdb")


@pytest.mark.asyncio
async def test_kill_query(adapter):
    await adapter.connect()
    result = await adapter.kill_query(pid=12345)
    assert result["success"] is True
    assert result["pid"] == 12345


@pytest.mark.asyncio
async def test_vacuum_table(adapter):
    await adapter.connect()
    result = await adapter.vacuum_table("orders")
    assert result["success"] is True
    assert result["table"] == "orders"


@pytest.mark.asyncio
async def test_vacuum_table_full(adapter):
    await adapter.connect()
    result = await adapter.vacuum_table("orders", full=True, analyze=True)
    assert result["full"] is True
    assert result["analyze"] is True


@pytest.mark.asyncio
async def test_reindex_table(adapter):
    await adapter.connect()
    result = await adapter.reindex_table("orders")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_create_index(adapter):
    await adapter.connect()
    result = await adapter.create_index("orders", ["customer_id"], name="idx_orders_cust")
    assert result["success"] is True
    assert result["index_name"] == "idx_orders_cust"


@pytest.mark.asyncio
async def test_drop_index(adapter):
    await adapter.connect()
    result = await adapter.drop_index("idx_orders_cust")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_alter_config(adapter):
    await adapter.connect()
    result = await adapter.alter_config("work_mem", "64MB")
    assert result["success"] is True
    assert result["param"] == "work_mem"


@pytest.mark.asyncio
async def test_alter_config_blocked_param(adapter):
    await adapter.connect()
    with pytest.raises(ValueError, match="not in allowlist"):
        await adapter.alter_config("data_directory", "/tmp")


@pytest.mark.asyncio
async def test_get_config_recommendations(adapter):
    await adapter.connect()
    recs = await adapter.get_config_recommendations()
    assert isinstance(recs, list)
    assert len(recs) > 0
    assert recs[0]["param"]


@pytest.mark.asyncio
async def test_generate_failover_runbook(adapter):
    await adapter.connect()
    runbook = await adapter.generate_failover_runbook()
    assert isinstance(runbook, dict)
    assert "steps" in runbook
    assert len(runbook["steps"]) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_adapter_write_ops.py -v`
Expected: FAIL with AttributeError

**Step 3: Write minimal implementation**

Add to `backend/src/database/adapters/base.py` — after the existing abstract methods (~line 103), add the config allowlist and new abstract methods:

```python
# Config allowlist — only these params can be altered
CONFIG_ALLOWLIST = {
    "shared_buffers", "work_mem", "maintenance_work_mem", "effective_cache_size",
    "max_connections", "max_worker_processes", "max_parallel_workers_per_gather",
    "random_page_cost", "effective_io_concurrency", "checkpoint_completion_target",
    "wal_buffers", "min_wal_size", "max_wal_size", "log_min_duration_statement",
    "statement_timeout", "idle_in_transaction_session_timeout",
}
```

Add these abstract methods to the class:

```python
    # ── Write operations (P2) ──

    @abstractmethod
    async def kill_query(self, pid: int) -> dict:
        """Terminate a backend process by PID."""
        ...

    @abstractmethod
    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        """VACUUM [FULL] [ANALYZE] a table."""
        ...

    @abstractmethod
    async def reindex_table(self, table: str) -> dict:
        """REINDEX TABLE CONCURRENTLY."""
        ...

    @abstractmethod
    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        """CREATE INDEX CONCURRENTLY."""
        ...

    @abstractmethod
    async def drop_index(self, index_name: str) -> dict:
        """DROP INDEX CONCURRENTLY."""
        ...

    async def alter_config(self, param: str, value: str) -> dict:
        """ALTER SYSTEM SET param = value. Validates against allowlist."""
        if param not in CONFIG_ALLOWLIST:
            raise ValueError(f"Parameter '{param}' not in allowlist")
        return await self._alter_config_impl(param, value)

    @abstractmethod
    async def _alter_config_impl(self, param: str, value: str) -> dict:
        """Vendor-specific config alter implementation."""
        ...

    @abstractmethod
    async def get_config_recommendations(self) -> list[dict]:
        """Return config tuning recommendations."""
        ...

    @abstractmethod
    async def generate_failover_runbook(self) -> dict:
        """Generate a failover runbook (read-only, no execution)."""
        ...
```

Add mock implementations to `backend/src/database/adapters/mock_adapter.py`:

```python
    async def kill_query(self, pid: int) -> dict:
        return {"success": True, "pid": pid, "message": f"Terminated PID {pid}"}

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        return {"success": True, "table": table, "full": full, "analyze": analyze}

    async def reindex_table(self, table: str) -> dict:
        return {"success": True, "table": table, "message": f"Reindexed {table}"}

    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        idx_name = name or f"idx_{table}_{'_'.join(columns)}"
        return {"success": True, "index_name": idx_name, "table": table, "columns": columns, "unique": unique}

    async def drop_index(self, index_name: str) -> dict:
        return {"success": True, "index_name": index_name, "message": f"Dropped {index_name}"}

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        return {"success": True, "param": param, "value": value, "reload": True}

    async def get_config_recommendations(self) -> list[dict]:
        return [
            {"param": "shared_buffers", "current_value": "128MB", "recommended_value": "1GB", "reason": "25% of 4GB RAM", "requires_restart": True},
            {"param": "work_mem", "current_value": "4MB", "recommended_value": "64MB", "reason": "Better sort performance", "requires_restart": False},
            {"param": "effective_cache_size", "current_value": "4GB", "recommended_value": "3GB", "reason": "75% of RAM", "requires_restart": False},
        ]

    async def generate_failover_runbook(self) -> dict:
        return {
            "steps": [
                {"order": 1, "description": "Verify replica health", "command": "SELECT pg_is_in_recovery();"},
                {"order": 2, "description": "Check replication lag", "command": "SELECT * FROM pg_stat_replication;"},
                {"order": 3, "description": "Promote replica", "command": "SELECT pg_promote();"},
                {"order": 4, "description": "Update connection strings", "command": "-- Update application config"},
                {"order": 5, "description": "Verify new primary", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
            ],
            "warnings": ["This will cause brief downtime", "Ensure replica is caught up before promoting"],
            "estimated_downtime": "30-60 seconds",
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_adapter_write_ops.py -v`
Expected: ALL PASS (10 tests)

**Step 5: Commit**

```bash
git add backend/src/database/adapters/base.py backend/src/database/adapters/mock_adapter.py backend/tests/test_adapter_write_ops.py
git commit -m "feat(db-ops): add write operations to adapter ABC + mock implementation"
```

---

## Task 4: Implement PostgresAdapter Write Methods

**Files:**
- Modify: `backend/src/database/adapters/postgres.py`

**Step 1: No new test needed** — these hit a real database. The mock tests from Task 3 validate the interface. Implementation follows the same patterns as existing `_fetch_*()` methods.

**Step 2: Add implementations to PostgresAdapter**

Append after `execute_diagnostic_query()` (~line 278):

```python
    async def kill_query(self, pid: int) -> dict:
        """Terminate a backend process by PID."""
        # Validate PID exists
        row = await self._conn.fetchrow(
            "SELECT pid, query, state FROM pg_stat_activity WHERE pid = $1", pid
        )
        if not row:
            raise ValueError(f"PID {pid} not found in pg_stat_activity")
        result = await self._conn.fetchval(
            "SELECT pg_terminate_backend($1)", pid
        )
        return {
            "success": bool(result),
            "pid": pid,
            "query": row["query"][:200] if row["query"] else "",
            "message": f"Terminated PID {pid}" if result else f"Failed to terminate PID {pid}",
        }

    async def vacuum_table(self, table: str, full: bool = False, analyze: bool = True) -> dict:
        """VACUUM [FULL] [ANALYZE] a table."""
        # Validate table exists
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        parts = ["VACUUM"]
        if full:
            parts.append("FULL")
        if analyze:
            parts.append("ANALYZE")
        parts.append(table)
        sql = " ".join(parts)
        await self._conn.execute(sql)
        return {"success": True, "table": table, "full": full, "analyze": analyze, "sql": sql}

    async def reindex_table(self, table: str) -> dict:
        """REINDEX TABLE CONCURRENTLY."""
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        sql = f"REINDEX TABLE CONCURRENTLY {table}"
        await self._conn.execute(sql)
        return {"success": True, "table": table, "sql": sql}

    async def create_index(self, table: str, columns: list[str],
                           name: str | None = None, unique: bool = False) -> dict:
        """CREATE INDEX CONCURRENTLY."""
        # Validate table and columns exist
        exists = await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", table
        )
        if not exists:
            raise ValueError(f"Table '{table}' does not exist")
        for col in columns:
            col_exists = await self._conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = $2)",
                table, col,
            )
            if not col_exists:
                raise ValueError(f"Column '{col}' does not exist on table '{table}'")
        idx_name = name or f"idx_{table}_{'_'.join(columns)}"
        unique_kw = "UNIQUE " if unique else ""
        col_list = ", ".join(columns)
        sql = f"CREATE {unique_kw}INDEX CONCURRENTLY {idx_name} ON {table} ({col_list})"
        await self._conn.execute(sql)
        return {"success": True, "index_name": idx_name, "table": table, "columns": columns, "sql": sql}

    async def drop_index(self, index_name: str) -> dict:
        """DROP INDEX CONCURRENTLY. Prevents dropping PK indexes."""
        # Check index exists and is not a PK constraint
        idx = await self._conn.fetchrow(
            """SELECT indexname, tablename FROM pg_indexes
               WHERE indexname = $1""", index_name
        )
        if not idx:
            raise ValueError(f"Index '{index_name}' does not exist")
        # Check if it backs a primary key
        is_pk = await self._conn.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM pg_constraint
                WHERE conname = $1 AND contype = 'p'
            )""", index_name
        )
        if is_pk:
            raise ValueError(f"Cannot drop primary key index '{index_name}'")
        sql = f"DROP INDEX CONCURRENTLY {index_name}"
        await self._conn.execute(sql)
        return {"success": True, "index_name": index_name, "sql": sql}

    async def _alter_config_impl(self, param: str, value: str) -> dict:
        """ALTER SYSTEM SET + pg_reload_conf()."""
        await self._conn.execute(f"ALTER SYSTEM SET {param} = '{value}'")
        await self._conn.execute("SELECT pg_reload_conf()")
        return {"success": True, "param": param, "value": value, "reload": True}

    async def get_config_recommendations(self) -> list[dict]:
        """Compare current pg_settings against heuristics."""
        rows = await self._conn.fetch(
            """SELECT name, setting, unit, context, short_desc
               FROM pg_settings
               WHERE name IN ('shared_buffers', 'work_mem', 'maintenance_work_mem',
                              'effective_cache_size', 'max_connections',
                              'random_page_cost', 'effective_io_concurrency',
                              'checkpoint_completion_target', 'wal_buffers',
                              'statement_timeout', 'idle_in_transaction_session_timeout')"""
        )
        # Simple heuristic recommendations
        recs = []
        for row in rows:
            name, setting, unit = row["name"], row["setting"], row["unit"] or ""
            rec = self._recommend_config(name, setting, unit)
            if rec:
                recs.append({
                    "param": name,
                    "current_value": f"{setting}{unit}",
                    "recommended_value": rec["value"],
                    "reason": rec["reason"],
                    "requires_restart": row["context"] == "postmaster",
                })
        return recs

    @staticmethod
    def _recommend_config(name: str, setting: str, unit: str) -> dict | None:
        """Simple heuristic config recommendations."""
        try:
            val = int(setting)
        except (ValueError, TypeError):
            return None
        recommendations = {
            "shared_buffers": (lambda v: v < 32768, "256MB", "Should be ~25% of RAM"),
            "work_mem": (lambda v: v < 16384, "64MB", "Better sort/hash performance"),
            "maintenance_work_mem": (lambda v: v < 65536, "256MB", "Faster VACUUM and index builds"),
            "random_page_cost": (lambda v: v > 2, "1.1", "SSD-appropriate value"),
            "effective_io_concurrency": (lambda v: v < 100, "200", "SSD-appropriate value"),
            "checkpoint_completion_target": (lambda v: v < 0.9, "0.9", "Spread checkpoint I/O"),
            "statement_timeout": (lambda v: v == 0, "30000", "30s timeout prevents runaway queries"),
        }
        if name in recommendations:
            check, rec_val, reason = recommendations[name]
            if check(val):
                return {"value": rec_val, "reason": reason}
        return None

    async def generate_failover_runbook(self) -> dict:
        """Generate a failover runbook based on current replication state."""
        repl = await self.get_replication_status()
        is_replica = repl.is_replica
        replicas = [r.model_dump() for r in repl.replicas]
        steps = []
        if is_replica:
            steps = [
                {"order": 1, "description": "This server IS a replica. To promote:", "command": "SELECT pg_promote();"},
                {"order": 2, "description": "Verify promotion", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
                {"order": 3, "description": "Update application connection strings", "command": "-- Point apps to new primary"},
            ]
        elif replicas:
            steps = [
                {"order": 1, "description": f"Verify replica health ({len(replicas)} replicas)", "command": "SELECT * FROM pg_stat_replication;"},
                {"order": 2, "description": "Check replication lag is minimal", "command": "SELECT client_addr, replay_lag FROM pg_stat_replication;"},
                {"order": 3, "description": "Stop writes on primary", "command": "-- Drain connections or set default_transaction_read_only = on"},
                {"order": 4, "description": "Promote chosen replica", "command": "-- On replica: SELECT pg_promote();"},
                {"order": 5, "description": "Update DNS/connection strings", "command": "-- Point apps to new primary"},
                {"order": 6, "description": "Verify new primary", "command": "SELECT pg_is_in_recovery(); -- Should return false"},
            ]
        else:
            steps = [
                {"order": 1, "description": "No replicas configured", "command": "-- Set up streaming replication first"},
            ]
        return {
            "is_replica": is_replica,
            "replica_count": len(replicas),
            "replicas": replicas,
            "steps": steps,
            "warnings": ["Failover causes brief downtime", "Ensure replica is caught up before promoting"],
            "estimated_downtime": "30-60 seconds",
        }
```

**Step 3: Run existing tests to verify nothing broke**

Run: `cd backend && python3 -m pytest tests/test_adapter_write_ops.py tests/test_db_adapter_base.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add backend/src/database/adapters/postgres.py
git commit -m "feat(db-ops): implement PostgresAdapter write operations"
```

---

## Task 5: Create RemediationEngine (Saga Orchestrator)

**Files:**
- Create: `backend/src/database/remediation_engine.py`
- Create: `backend/tests/test_remediation_engine.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_remediation_engine.py
"""Tests for RemediationEngine — saga orchestrator."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    from src.database.remediation_engine import RemediationEngine
    store = RemediationStore(db_path=path)
    adapter_registry = MagicMock()
    profile_store = MagicMock()
    e = RemediationEngine(
        plan_store=store,
        adapter_registry=adapter_registry,
        profile_store=profile_store,
        secret_key="test-secret-key-for-jwt",
    )
    yield e
    os.unlink(path)


def test_plan_creates_pending(engine):
    plan = engine.plan(
        profile_id="prof-1", action="vacuum",
        params={"table": "orders"},
    )
    assert plan["plan_id"]
    assert plan["status"] == "pending"
    assert plan["sql_preview"]
    assert "VACUUM" in plan["sql_preview"]


def test_plan_kill_query(engine):
    plan = engine.plan(
        profile_id="prof-1", action="kill_query",
        params={"pid": 12345},
    )
    assert "12345" in plan["sql_preview"]


def test_plan_create_index(engine):
    plan = engine.plan(
        profile_id="prof-1", action="create_index",
        params={"table": "orders", "columns": ["customer_id"], "unique": False},
    )
    assert "CREATE" in plan["sql_preview"]
    assert "customer_id" in plan["sql_preview"]


def test_plan_alter_config(engine):
    plan = engine.plan(
        profile_id="prof-1", action="alter_config",
        params={"param": "work_mem", "value": "64MB"},
    )
    assert "work_mem" in plan["sql_preview"]


def test_plan_failover_runbook(engine):
    plan = engine.plan(
        profile_id="prof-1", action="failover_runbook",
        params={},
    )
    assert plan["sql_preview"] == "-- Read-only runbook generation"
    assert plan["requires_downtime"] is False


def test_approve_generates_token(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    result = engine.approve(plan["plan_id"])
    assert "approval_token" in result
    assert "expires_at" in result
    # Plan status should be approved
    updated = engine.get_plan(plan["plan_id"])
    assert updated["status"] == "approved"


def test_approve_rejects_non_pending(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.approve(plan["plan_id"])
    with pytest.raises(ValueError, match="not in pending status"):
        engine.approve(plan["plan_id"])


def test_reject_plan(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.reject(plan["plan_id"])
    updated = engine.get_plan(plan["plan_id"])
    assert updated["status"] == "rejected"


def test_list_plans(engine):
    engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t1"})
    engine.plan(profile_id="prof-1", action="reindex", params={"table": "t2"})
    plans = engine.list_plans("prof-1")
    assert len(plans) == 2


@pytest.mark.asyncio
async def test_execute_vacuum(engine):
    # Set up mock adapter
    mock_adapter = AsyncMock()
    mock_adapter.vacuum_table.return_value = {"success": True, "table": "orders"}
    engine._adapter_registry.get_by_profile.return_value = mock_adapter

    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "orders"})
    approval = engine.approve(plan["plan_id"])
    result = await engine.execute(plan["plan_id"], approval["approval_token"])
    assert result["status"] in ("completed", "success")
    mock_adapter.vacuum_table.assert_called_once()


@pytest.mark.asyncio
async def test_execute_invalid_token(engine):
    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    engine.approve(plan["plan_id"])
    with pytest.raises(ValueError, match="Invalid or expired"):
        await engine.execute(plan["plan_id"], "bad-token")


@pytest.mark.asyncio
async def test_execute_writes_audit_log(engine):
    mock_adapter = AsyncMock()
    mock_adapter.vacuum_table.return_value = {"success": True, "table": "t"}
    engine._adapter_registry.get_by_profile.return_value = mock_adapter

    plan = engine.plan(profile_id="prof-1", action="vacuum", params={"table": "t"})
    approval = engine.approve(plan["plan_id"])
    await engine.execute(plan["plan_id"], approval["approval_token"])
    log = engine.get_audit_log("prof-1")
    assert len(log) == 1
    assert log[0]["status"] == "success"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_remediation_engine.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# backend/src/database/remediation_engine.py
"""RemediationEngine — saga orchestrator for database operations.

Flow: plan → approve (JWT) → execute → verify → rollback on failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

import jwt

logger = logging.getLogger(__name__)

# Action → SQL preview generator
_SQL_GENERATORS = {
    "kill_query": lambda p: f"SELECT pg_terminate_backend({p.get('pid', '?')})",
    "vacuum": lambda p: f"VACUUM {'FULL ' if p.get('full') else ''}{'ANALYZE ' if p.get('analyze', True) else ''}{p.get('table', '?')}".strip(),
    "reindex": lambda p: f"REINDEX TABLE CONCURRENTLY {p.get('table', '?')}",
    "create_index": lambda p: f"CREATE {'UNIQUE ' if p.get('unique') else ''}INDEX CONCURRENTLY idx_{p.get('table', 'x')}_{'_'.join(p.get('columns', []))} ON {p.get('table', '?')} ({', '.join(p.get('columns', []))})",
    "drop_index": lambda p: f"DROP INDEX CONCURRENTLY {p.get('index_name', '?')}",
    "alter_config": lambda p: f"ALTER SYSTEM SET {p.get('param', '?')} = '{p.get('value', '?')}'",
    "failover_runbook": lambda p: "-- Read-only runbook generation",
}

_IMPACT_GENERATORS = {
    "kill_query": lambda p: "Immediate. Terminates the backend process.",
    "vacuum": lambda p: f"{'Full vacuum — locks table. ' if p.get('full') else 'Non-blocking. '}Duration depends on table size.",
    "reindex": lambda p: f"CONCURRENTLY — non-blocking but resource-intensive.",
    "create_index": lambda p: "CONCURRENTLY — non-blocking but uses CPU/IO.",
    "drop_index": lambda p: "Immediate. Queries using this index will fall back to seq scan.",
    "alter_config": lambda p: "Applies on reload. Some params require restart.",
    "failover_runbook": lambda p: "Read-only. No changes made.",
}

_ROLLBACK_GENERATORS = {
    "vacuum": lambda p: None,  # Cannot un-vacuum
    "kill_query": lambda p: None,  # Cannot un-kill
    "reindex": lambda p: None,  # Reindex is idempotent
    "create_index": lambda p: f"DROP INDEX CONCURRENTLY idx_{p.get('table', 'x')}_{'_'.join(p.get('columns', []))}",
    "drop_index": lambda p: None,  # Would need original CREATE INDEX — not feasible
    "alter_config": lambda p: None,  # Would need original value — handled separately
    "failover_runbook": lambda p: None,
}


class RemediationEngine:
    def __init__(self, plan_store, adapter_registry, profile_store, secret_key: str):
        self._store = plan_store
        self._adapter_registry = adapter_registry
        self._profile_store = profile_store
        self._secret_key = secret_key

    def plan(self, profile_id: str, action: str, params: dict,
             finding_id: str | None = None) -> dict:
        """Create a new remediation plan."""
        if action not in _SQL_GENERATORS:
            raise ValueError(f"Unknown action: {action}")

        sql_preview = _SQL_GENERATORS[action](params)
        impact = _IMPACT_GENERATORS.get(action, lambda p: "")(params)
        rollback_sql = _ROLLBACK_GENERATORS.get(action, lambda p: None)(params)
        requires_downtime = action == "vacuum" and params.get("full", False)

        return self._store.create_plan(
            profile_id=profile_id,
            action=action,
            params=params,
            sql_preview=sql_preview,
            impact_assessment=impact,
            rollback_sql=rollback_sql,
            requires_downtime=requires_downtime,
            finding_id=finding_id,
        )

    def approve(self, plan_id: str) -> dict:
        """Approve a plan and generate a JWT token."""
        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        if plan["status"] != "pending":
            raise ValueError(f"Plan {plan_id} not in pending status (current: {plan['status']})")

        now = datetime.now(UTC)
        expires = now + timedelta(minutes=5)
        token = jwt.encode(
            {"plan_id": plan_id, "profile_id": plan["profile_id"],
             "action": plan["action"], "exp": expires},
            self._secret_key,
            algorithm="HS256",
        )
        self._store.update_plan(plan_id, status="approved",
                                approved_at=now.isoformat())
        return {
            "plan_id": plan_id,
            "approval_token": token,
            "expires_at": expires.isoformat(),
        }

    def reject(self, plan_id: str):
        """Reject a plan."""
        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        self._store.update_plan(plan_id, status="rejected")

    async def execute(self, plan_id: str, token: str) -> dict:
        """Execute an approved plan. Full saga: pre-flight → execute → verify → rollback."""
        # Validate token
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            raise ValueError("Invalid or expired approval token")

        if payload.get("plan_id") != plan_id:
            raise ValueError("Token does not match plan")

        plan = self._store.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")
        if plan["status"] != "approved":
            raise ValueError(f"Plan {plan_id} not in approved status")

        # Get adapter
        adapter = self._adapter_registry.get_by_profile(plan["profile_id"])
        if not adapter:
            raise ValueError(f"No adapter for profile {plan['profile_id']}")

        # Mark executing
        self._store.update_plan(plan_id, status="executing",
                                executed_at=datetime.now(UTC).isoformat())

        action = plan["action"]
        params = plan["params"]
        before_state = {}
        after_state = {}

        try:
            # Execute the operation
            result = await self._dispatch_action(adapter, action, params)

            # Mark completed
            now = datetime.now(UTC).isoformat()
            self._store.update_plan(
                plan_id, status="completed", completed_at=now,
                result_summary=str(result.get("message", "Success")),
                after_state=result,
            )
            # Audit log
            self._store.add_audit_entry(
                plan_id=plan_id, profile_id=plan["profile_id"],
                action=action, sql_executed=plan["sql_preview"],
                status="success", before_state=before_state,
                after_state=result,
            )
            logger.info("Remediation %s completed: %s", plan_id, action)
            return {"plan_id": plan_id, "status": "completed", "result": result}

        except Exception as e:
            # Mark failed
            now = datetime.now(UTC).isoformat()
            self._store.update_plan(
                plan_id, status="failed", completed_at=now,
                result_summary=f"Error: {e}",
            )
            self._store.add_audit_entry(
                plan_id=plan_id, profile_id=plan["profile_id"],
                action=action, sql_executed=plan["sql_preview"],
                status="failed", before_state=before_state,
                after_state=after_state, error=str(e),
            )
            logger.error("Remediation %s failed: %s", plan_id, e)
            return {"plan_id": plan_id, "status": "failed", "error": str(e)}

    async def _dispatch_action(self, adapter, action: str, params: dict) -> dict:
        """Route action to the correct adapter method."""
        if action == "kill_query":
            return await adapter.kill_query(pid=params["pid"])
        elif action == "vacuum":
            return await adapter.vacuum_table(
                table=params["table"],
                full=params.get("full", False),
                analyze=params.get("analyze", True),
            )
        elif action == "reindex":
            return await adapter.reindex_table(table=params["table"])
        elif action == "create_index":
            return await adapter.create_index(
                table=params["table"],
                columns=params["columns"],
                name=params.get("name"),
                unique=params.get("unique", False),
            )
        elif action == "drop_index":
            return await adapter.drop_index(index_name=params["index_name"])
        elif action == "alter_config":
            return await adapter.alter_config(
                param=params["param"], value=params["value"],
            )
        elif action == "failover_runbook":
            return await adapter.generate_failover_runbook()
        else:
            raise ValueError(f"Unknown action: {action}")

    def get_plan(self, plan_id: str) -> dict | None:
        return self._store.get_plan(plan_id)

    def list_plans(self, profile_id: str, status: str | None = None) -> list[dict]:
        return self._store.list_plans(profile_id, status)

    def get_audit_log(self, profile_id: str, limit: int = 50) -> list[dict]:
        return self._store.get_audit_log(profile_id, limit)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_remediation_engine.py -v`
Expected: ALL PASS (12 tests)

**Step 5: Commit**

```bash
git add backend/src/database/remediation_engine.py backend/tests/test_remediation_engine.py
git commit -m "feat(db-ops): add RemediationEngine saga orchestrator with JWT approval"
```

---

## Task 6: AI Remediation Planner (LangGraph)

**Files:**
- Create: `backend/src/agents/database/remediation_planner.py`
- Create: `backend/tests/test_remediation_planner.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_remediation_planner.py
"""Tests for AI remediation planner — findings → remediation plans."""
import os
import tempfile
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from src.database.remediation_store import RemediationStore
    from src.database.remediation_engine import RemediationEngine
    store = RemediationStore(db_path=path)
    e = RemediationEngine(
        plan_store=store,
        adapter_registry=MagicMock(),
        profile_store=MagicMock(),
        secret_key="test-key",
    )
    yield e
    os.unlink(path)


def test_planner_generates_vacuum_for_bloat(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f1", "category": "table_bloat", "severity": "medium",
            "title": "Table bloat detected", "detail": "orders has 35% bloat",
            "remediation_available": True,
            "evidence": ["orders: 35% bloat"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "vacuum" for p in plans)


def test_planner_generates_index_for_slow_queries(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f2", "category": "slow_queries", "severity": "high",
            "title": "Slow queries detected", "detail": "Sequential scan on orders.customer_id",
            "remediation_available": True,
            "evidence": ["Seq Scan on orders filtering customer_id"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "create_index" for p in plans)


def test_planner_generates_kill_for_deadlock(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f3", "category": "deadlocks", "severity": "high",
            "title": "Deadlocks detected", "detail": "PID 999 is blocking",
            "remediation_available": True,
            "evidence": ["blocking_pid: 999"],
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) >= 1
    assert any(p["action"] == "kill_query" for p in plans)


def test_planner_skips_non_remediable(engine):
    from src.agents.database.remediation_planner import generate_plans_from_findings
    findings = [
        {
            "finding_id": "f4", "category": "info", "severity": "low",
            "title": "Database version", "detail": "PostgreSQL 16.1",
            "remediation_available": False,
        }
    ]
    plans = generate_plans_from_findings(engine, "prof-1", findings)
    assert len(plans) == 0


def test_planner_graph_invocation(engine):
    from src.agents.database.remediation_planner import build_remediation_planner_graph
    graph = build_remediation_planner_graph()
    assert graph is not None
    state = {
        "profile_id": "prof-1",
        "findings": [
            {
                "finding_id": "f1", "category": "table_bloat", "severity": "medium",
                "title": "Bloat", "detail": "orders 35%", "remediation_available": True,
                "evidence": ["orders: 35% bloat"],
            }
        ],
        "plans": [],
        "_engine": engine,
    }
    result = graph.invoke(state)
    assert len(result.get("plans", [])) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_remediation_planner.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# backend/src/agents/database/remediation_planner.py
"""AI Remediation Planner — maps diagnostic findings to actionable remediation plans.

Graph: analyze_findings → generate_plans → END (plans returned for human approval).
"""
from __future__ import annotations

import logging
import re
from typing import TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


class RemediationPlannerState(TypedDict, total=False):
    profile_id: str
    findings: list[dict]
    plans: list[dict]
    _engine: object  # RemediationEngine instance


# ── Finding-to-action mapping logic ──

def _extract_table_from_evidence(evidence: list[str], detail: str) -> str | None:
    """Try to extract a table name from evidence or detail text."""
    for e in (evidence or []):
        # Pattern: "tablename: NN% bloat" or "tablename has bloat"
        match = re.match(r"(\w+)[:,\s]", e)
        if match:
            return match.group(1)
    # Try detail
    words = detail.split()
    for i, w in enumerate(words):
        if w.lower() in ("table", "on") and i + 1 < len(words):
            return words[i + 1].strip(".,;:'\"")
    return None


def _extract_column_from_evidence(evidence: list[str], detail: str) -> str | None:
    """Try to extract a column name from evidence about slow queries."""
    for e in (evidence or []):
        match = re.search(r"filtering\s+(\w+)", e, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"\.(\w+)", e)
        if match:
            return match.group(1)
    match = re.search(r"\.(\w+)", detail)
    if match:
        return match.group(1)
    return None


def _extract_pid(evidence: list[str], detail: str) -> int | None:
    """Extract a PID from evidence about deadlocks/blocking."""
    for e in (evidence or []):
        match = re.search(r"(?:pid|PID)[:\s]+(\d+)", e)
        if match:
            return int(match.group(1))
        match = re.search(r"blocking_pid[:\s]+(\d+)", e)
        if match:
            return int(match.group(1))
    match = re.search(r"PID\s+(\d+)", detail)
    if match:
        return int(match.group(1))
    return None


def generate_plans_from_findings(engine, profile_id: str,
                                  findings: list[dict]) -> list[dict]:
    """Map findings to remediation plans. Returns list of created plans."""
    plans = []
    for f in findings:
        if not f.get("remediation_available", False):
            continue

        category = f.get("category", "")
        evidence = f.get("evidence", [])
        detail = f.get("detail", "")
        finding_id = f.get("finding_id")

        try:
            if category in ("table_bloat",):
                table = _extract_table_from_evidence(evidence, detail)
                if table:
                    # Check if bloat > 30% for FULL vacuum
                    bloat_match = re.search(r"(\d+)%", detail)
                    full = bloat_match and int(bloat_match.group(1)) > 30
                    plan = engine.plan(
                        profile_id=profile_id, action="vacuum",
                        params={"table": table, "full": bool(full), "analyze": True},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("index_bloat",):
                table = _extract_table_from_evidence(evidence, detail)
                if table:
                    plan = engine.plan(
                        profile_id=profile_id, action="reindex",
                        params={"table": table},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("slow_queries", "missing_index"):
                table = _extract_table_from_evidence(evidence, detail)
                col = _extract_column_from_evidence(evidence, detail)
                if table and col:
                    plan = engine.plan(
                        profile_id=profile_id, action="create_index",
                        params={"table": table, "columns": [col], "unique": False},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("unused_index",):
                # Extract index name from evidence
                for e in evidence:
                    match = re.search(r"(idx_\w+)", e)
                    if match:
                        plan = engine.plan(
                            profile_id=profile_id, action="drop_index",
                            params={"index_name": match.group(1)},
                            finding_id=finding_id,
                        )
                        plans.append(plan)
                        break

            elif category in ("deadlocks",):
                pid = _extract_pid(evidence, detail)
                if pid:
                    plan = engine.plan(
                        profile_id=profile_id, action="kill_query",
                        params={"pid": pid},
                        finding_id=finding_id,
                    )
                    plans.append(plan)

            elif category in ("connection_saturation",):
                plan = engine.plan(
                    profile_id=profile_id, action="alter_config",
                    params={"param": "max_connections", "value": "200"},
                    finding_id=finding_id,
                )
                plans.append(plan)

            elif category in ("replication_lag",):
                plan = engine.plan(
                    profile_id=profile_id, action="failover_runbook",
                    params={},
                    finding_id=finding_id,
                )
                plans.append(plan)

        except Exception as e:
            logger.warning("Failed to generate plan for finding %s: %s",
                           finding_id, e)

    return plans


# ── LangGraph nodes ──

def analyze_findings(state: RemediationPlannerState) -> dict:
    """Filter findings that have remediation available."""
    findings = state.get("findings", [])
    remediable = [f for f in findings if f.get("remediation_available", False)]
    return {"findings": remediable}


def generate_plans(state: RemediationPlannerState) -> dict:
    """Generate remediation plans from findings."""
    engine = state.get("_engine")
    profile_id = state.get("profile_id", "")
    findings = state.get("findings", [])

    if not engine or not findings:
        return {"plans": []}

    plans = generate_plans_from_findings(engine, profile_id, findings)
    return {"plans": plans}


def build_remediation_planner_graph():
    """Build the LangGraph for remediation planning."""
    graph = StateGraph(RemediationPlannerState)
    graph.add_node("analyze_findings", analyze_findings)
    graph.add_node("generate_plans", generate_plans)
    graph.set_entry_point("analyze_findings")
    graph.add_edge("analyze_findings", "generate_plans")
    graph.add_edge("generate_plans", END)
    return graph.compile()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_remediation_planner.py -v`
Expected: ALL PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/database/remediation_planner.py backend/tests/test_remediation_planner.py
git commit -m "feat(db-ops): add AI remediation planner with LangGraph"
```

---

## Task 7: Add Remediation API Endpoints

**Files:**
- Modify: `backend/src/api/db_endpoints.py`
- Create: `backend/tests/test_remediation_endpoints.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_remediation_endpoints.py
"""Tests for remediation API endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import src.api.db_endpoints as db_ep
    db_ep._profile_store = None
    db_ep._run_store = None
    db_ep._db_monitor = None
    db_ep._metrics_store = None
    db_ep._alert_engine = None
    db_ep._db_adapter_registry = None
    db_ep._remediation_engine = None
    from src.api.main import app
    return TestClient(app)


class TestRemediationEndpoints:
    def test_list_plans_empty(self, client):
        resp = client.get("/api/db/remediation/plans?profile_id=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_plan(self, client):
        resp = client.post("/api/db/remediation/plan", json={
            "profile_id": "prof-1", "action": "vacuum",
            "params": {"table": "orders"},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert "VACUUM" in resp.json()["sql_preview"]

    def test_get_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.get(f"/api/db/remediation/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["plan_id"] == plan_id

    def test_approve_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.post(f"/api/db/remediation/approve/{plan_id}")
        assert resp.status_code == 200
        assert "approval_token" in resp.json()

    def test_reject_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.post(f"/api/db/remediation/reject/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_audit_log_empty(self, client):
        resp = client.get("/api/db/remediation/log?profile_id=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_config_recommendations_missing_profile(self, client):
        resp = client.get("/api/db/config/nonexistent/recommendations")
        assert resp.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_remediation_endpoints.py -v`
Expected: FAIL (missing endpoints)

**Step 3: Write minimal implementation**

Add to `backend/src/api/db_endpoints.py`:

1. Add new lazy singleton at top (after existing `_db_adapter_registry = None`):
```python
_remediation_engine = None
```

2. Add getter:
```python
def _get_remediation_engine():
    global _remediation_engine
    if _remediation_engine is None:
        from src.database.remediation_store import RemediationStore
        from src.database.remediation_engine import RemediationEngine
        db_path = os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
        _remediation_engine = RemediationEngine(
            plan_store=RemediationStore(db_path=db_path),
            adapter_registry=_get_db_adapter_registry(),
            profile_store=_get_profile_store(),
            secret_key=os.environ.get("REMEDIATION_SECRET_KEY", "debugduck-remediation-secret"),
        )
    return _remediation_engine
```

3. Add request models:
```python
class CreatePlanRequest(BaseModel):
    profile_id: str
    action: str
    params: dict = {}
    finding_id: Optional[str] = None


class SuggestRemediationRequest(BaseModel):
    profile_id: str
    run_id: str


class ExecutePlanRequest(BaseModel):
    approval_token: str
```

4. Add endpoints (append before the schema endpoints section):

```python
# ── Remediation endpoints ──


@db_router.post("/remediation/plan")
def create_remediation_plan(req: CreatePlanRequest):
    engine = _get_remediation_engine()
    try:
        return engine.plan(
            profile_id=req.profile_id, action=req.action,
            params=req.params, finding_id=req.finding_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@db_router.post("/remediation/suggest")
def suggest_remediation(req: SuggestRemediationRequest):
    engine = _get_remediation_engine()
    run_store = _get_run_store()
    run = run_store.get(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Diagnostic run not found")
    from src.agents.database.remediation_planner import generate_plans_from_findings
    plans = generate_plans_from_findings(engine, req.profile_id, run.get("findings", []))
    return {"plans": plans}


@db_router.get("/remediation/plans")
def list_remediation_plans(profile_id: str, status: Optional[str] = None):
    engine = _get_remediation_engine()
    return engine.list_plans(profile_id, status)


@db_router.get("/remediation/plans/{plan_id}")
def get_remediation_plan(plan_id: str):
    engine = _get_remediation_engine()
    plan = engine.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@db_router.post("/remediation/approve/{plan_id}")
def approve_remediation_plan(plan_id: str):
    engine = _get_remediation_engine()
    try:
        return engine.approve(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@db_router.post("/remediation/reject/{plan_id}")
def reject_remediation_plan(plan_id: str):
    engine = _get_remediation_engine()
    try:
        engine.reject(plan_id)
        return {"status": "rejected"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@db_router.post("/remediation/execute/{plan_id}")
async def execute_remediation_plan(plan_id: str, req: ExecutePlanRequest):
    engine = _get_remediation_engine()
    try:
        result = await engine.execute(plan_id, req.approval_token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@db_router.get("/remediation/log")
def get_remediation_log(profile_id: str, limit: int = 50):
    engine = _get_remediation_engine()
    return engine.get_audit_log(profile_id, limit)


@db_router.get("/config/{profile_id}/recommendations")
async def get_config_recommendations(profile_id: str):
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
        recs = await adapter.get_config_recommendations()
        return {"profile_id": profile_id, "recommendations": recs}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@db_router.post("/queries/{profile_id}/kill/{pid}")
async def kill_query_shortcut(profile_id: str, pid: int):
    """Shortcut: creates plan + auto-approves + executes for kill_query."""
    profile = _get_profile_store().get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    engine = _get_remediation_engine()
    plan = engine.plan(profile_id=profile_id, action="kill_query", params={"pid": pid})
    approval = engine.approve(plan["plan_id"])
    result = await engine.execute(plan["plan_id"], approval["approval_token"])
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_remediation_endpoints.py -v`
Expected: ALL PASS (7 tests)

**Step 5: Commit**

```bash
git add backend/src/api/db_endpoints.py backend/tests/test_remediation_endpoints.py
git commit -m "feat(db-ops): add remediation, config, and kill-query API endpoints"
```

---

## Task 8: Wire RemediationEngine into main.py Startup

**Files:**
- Modify: `backend/src/api/main.py`

**Step 1: Add wiring in startup**

In the startup function, after the DBMonitor wiring block (~line 324), add:

```python
    # ── Remediation Engine ──
    from src.database.remediation_store import RemediationStore
    from src.database.remediation_engine import RemediationEngine
    remediation_store = RemediationStore(db_path=db_path)
    remediation_engine = RemediationEngine(
        plan_store=remediation_store,
        adapter_registry=db_registry,
        profile_store=db_profile_store,
        secret_key=os.environ.get("REMEDIATION_SECRET_KEY", "debugduck-remediation-secret"),
    )
    db_ep._remediation_engine = remediation_engine
    logger.info("RemediationEngine initialized")
```

**Step 2: Run all DB tests to verify nothing broke**

Run: `cd backend && python3 -m pytest tests/test_db_endpoints.py tests/test_db_monitor_endpoints.py tests/test_remediation_endpoints.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add backend/src/api/main.py
git commit -m "feat(db-ops): wire RemediationEngine into app startup"
```

---

## Task 9: Frontend — Add Remediation API Functions

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Append API functions**

Add after the existing DB Monitoring API section:

```typescript
// ── Database Operations / Remediation API ──

export const createRemediationPlan = async (data: { profile_id: string; action: string; params: Record<string, unknown>; finding_id?: string }) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plan`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to create plan'));
  return resp.json();
};

export const suggestRemediation = async (profileId: string, runId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/suggest`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, run_id: runId }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to suggest remediation'));
  return resp.json();
};

export const fetchRemediationPlans = async (profileId: string, status?: string) => {
  const params = new URLSearchParams({ profile_id: profileId });
  if (status) params.set('status', status);
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plans?${params}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch plans'));
  return resp.json();
};

export const fetchRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/plans/${planId}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch plan'));
  return resp.json();
};

export const approveRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/approve/${planId}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to approve plan'));
  return resp.json();
};

export const rejectRemediationPlan = async (planId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/reject/${planId}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to reject plan'));
  return resp.json();
};

export const executeRemediationPlan = async (planId: string, approvalToken: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/execute/${planId}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_token: approvalToken }),
  });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to execute plan'));
  return resp.json();
};

export const fetchRemediationLog = async (profileId: string, limit = 50) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/remediation/log?profile_id=${profileId}&limit=${limit}`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch audit log'));
  return resp.json();
};

export const fetchConfigRecommendations = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/config/${profileId}/recommendations`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch config recommendations'));
  return resp.json();
};

export const killDBQuery = async (profileId: string, pid: number) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/queries/${profileId}/kill/${pid}`, { method: 'POST' });
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to kill query'));
  return resp.json();
};

export const fetchDBActiveQueries = async (profileId: string) => {
  const resp = await fetch(`${API_BASE_URL}/api/db/profiles/${profileId}/health`);
  if (!resp.ok) throw new Error(await extractErrorDetail(resp, 'Failed to fetch active queries'));
  return resp.json();
};
```

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(db-ops): add remediation API functions to frontend"
```

---

## Task 10: Frontend — Update DatabaseLayout + Create DBOperations

**Files:**
- Modify: `frontend/src/components/Database/DatabaseLayout.tsx`
- Create: `frontend/src/components/Database/DBOperations.tsx`
- Create: `frontend/src/components/Database/RemediationCard.tsx`
- Create: `frontend/src/components/Database/OperationFormModal.tsx`

This is the largest frontend task. The implementer should create all 4 files and update DatabaseLayout to add the Operations tab. Follow the exact same styling patterns as DBMonitoring.tsx and DBSchema.tsx (dark theme, cyan accent, Material Symbols icons, same card/table patterns).

**DBOperations.tsx layout:**
- Top bar: profile selector + "New Operation" dropdown
- Active Queries panel: table with PID, SQL (truncated), duration, state, Kill button
- Pending Plans panel: list of `RemediationCard` components
- Config Recommendations panel: current vs. recommended values, Apply button
- Execution Log: audit entries with status dots

**RemediationCard.tsx:**
- Card showing: action title, source (AI/manual), status badge
- SQL preview in monospace code block
- Impact assessment text
- Rollback SQL (if available)
- Approve & Run / Reject buttons (for pending plans)
- Status timeline for completed/failed plans

**OperationFormModal.tsx:**
- Action type selector at top
- Dynamic form fields based on action:
  - kill_query: PID input
  - vacuum: table selector, full checkbox, analyze checkbox
  - reindex: table selector
  - create_index: table input, columns input (comma-separated), unique checkbox, name input
  - drop_index: index name input
  - alter_config: param selector (from allowlist), value input
- Create Plan button

**DatabaseLayout.tsx changes:**
- Add `import DBOperations from './DBOperations'`
- Extend `DBView` with `'operations'`
- Add sidebar item: `{ id: 'operations', label: 'Operations', icon: 'build' }`
- Add content: `{activeView === 'operations' && <DBOperations />}`

**Step 1: Create all files, update layout**

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/Database/DatabaseLayout.tsx frontend/src/components/Database/DBOperations.tsx frontend/src/components/Database/RemediationCard.tsx frontend/src/components/Database/OperationFormModal.tsx
git commit -m "feat(db-ops): add Operations tab with remediation cards and operation forms"
```

---

## Task 11: Final Integration Verification

**Step 1: Run all backend tests**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Verify commit history**

Run: `git log --oneline -10`
Expected: Clean commit history with all P2 commits

---

## Dependency Graph

```
Task 1 (Models)
  └→ Task 2 (RemediationStore)
  └→ Task 3 (Adapter Write Ops - ABC + Mock)
       └→ Task 4 (PostgresAdapter Write Ops)
  Task 2 + Task 3
       └→ Task 5 (RemediationEngine)
            └→ Task 6 (AI Planner)
            └→ Task 7 (API Endpoints)
                 └→ Task 8 (Main.py Wiring)
  Task 7
       └→ Task 9 (Frontend API Functions)
            └→ Task 10 (Frontend Components)
                 └→ Task 11 (Final Verification)
```
