# Phase 6: Management UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add workflow lifecycle management (delete, rename, duplicate, version rollback/diff) and run management (filtering, rerun, scoped run lists) to make workflows usable at scale.

**Architecture:** Backend API additions (6 new endpoints + filter params on existing) + DB migration for soft-delete column and indexes + frontend component enhancements. No new infrastructure, no new tables.

**Tech Stack:** Python FastAPI + aiosqlite (backend), React + TypeScript + Tailwind (frontend), Vitest (frontend tests), pytest + pytest-asyncio (backend tests).

---

## Task 1: DB Migration — Soft Delete Column + Indexes

**Files:**
- Create: `backend/src/workflows/migrations/002_management_ui.sql`
- Modify: `backend/src/workflows/repository.py:12-14` (add migration path)

**Step 1: Write the migration SQL**

Create `backend/src/workflows/migrations/002_management_ui.sql`:

```sql
ALTER TABLE workflows ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status_created
  ON workflow_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created
  ON workflow_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflows_deleted
  ON workflows(deleted_at);
```

**Step 2: Update repository to run both migrations**

In `backend/src/workflows/repository.py`, change the migration loading (lines 12-14) to run both migration files in order:

```python
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
```

Then update `init()` (lines 30-35) to apply migrations in order:

```python
async def init(self) -> None:
    async with aiosqlite.connect(self._db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            await db.executescript(sql_file.read_text())
        await db.commit()
```

**Step 3: Write the test**

Create `backend/tests/test_migration_002.py`:

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from src.workflows.repository import WorkflowRepository


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "workflows.db")


@pytest_asyncio.fixture
async def repo(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    return r


@pytest.mark.asyncio
async def test_workflows_has_deleted_at_column(repo):
    """002 migration adds deleted_at to workflows."""
    import aiosqlite
    async with aiosqlite.connect(repo._db_path) as db:
        async with db.execute("PRAGMA table_info(workflows)") as cur:
            cols = [row[1] async for row in cur]
    assert "deleted_at" in cols


@pytest.mark.asyncio
async def test_indexes_exist(repo):
    """002 migration adds performance indexes."""
    import aiosqlite
    async with aiosqlite.connect(repo._db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ) as cur:
            indexes = {row[0] async for row in cur}
    assert "idx_workflow_runs_status_created" in indexes
    assert "idx_workflow_runs_created" in indexes
    assert "idx_workflows_deleted" in indexes


@pytest.mark.asyncio
async def test_migration_idempotent(db_path):
    """Running init() twice doesn't error."""
    r = WorkflowRepository(db_path)
    await r.init()
    await r.init()
    wf_id = await r.create_workflow(name="wf", description=None, created_by=None)
    assert wf_id
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_migration_002.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add backend/src/workflows/migrations/002_management_ui.sql backend/src/workflows/repository.py backend/tests/test_migration_002.py
git commit -m "feat(phase6): add migration 002 — soft delete column + indexes"
```

---

## Task 2: Repository — Soft Delete, Rename, Duplicate, Rollback, Run Listing

**Files:**
- Modify: `backend/src/workflows/repository.py`
- Test: `backend/tests/test_phase6_repository.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_phase6_repository.py`:

```python
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from src.workflows.repository import WorkflowRepository


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "workflows.db")


@pytest_asyncio.fixture
async def repo(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    return r


# --- Helpers ---

async def _make_workflow(repo, name="wf", desc="d"):
    return await repo.create_workflow(name=name, description=desc, created_by=None)


async def _make_version(repo, wf_id, version=1):
    dag = json.dumps({"inputs_schema": {}, "steps": []})
    compiled = json.dumps({"topo_order": [], "steps": {}, "inputs_schema": {}})
    return await repo.create_version(wf_id, version, dag, compiled)


async def _make_run(repo, version_id, status="succeeded"):
    run_id = await repo.create_run(
        workflow_version_id=version_id, inputs_json="{}", idempotency_key=None
    )
    if status != "pending":
        await repo.update_run_status(run_id, status)
    return run_id


# --- Soft Delete ---

@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(repo):
    wf_id = await _make_workflow(repo)
    await repo.soft_delete_workflow(wf_id)
    wf = await repo.get_workflow(wf_id)
    assert wf is not None
    assert wf["deleted_at"] is not None


@pytest.mark.asyncio
async def test_list_workflows_excludes_deleted(repo):
    wf1 = await _make_workflow(repo, name="keep")
    wf2 = await _make_workflow(repo, name="delete-me")
    await repo.soft_delete_workflow(wf2)
    rows = await repo.list_workflows()
    ids = [r["id"] for r in rows]
    assert wf1 in ids
    assert wf2 not in ids


@pytest.mark.asyncio
async def test_soft_delete_idempotent(repo):
    wf_id = await _make_workflow(repo)
    await repo.soft_delete_workflow(wf_id)
    await repo.soft_delete_workflow(wf_id)  # no error


@pytest.mark.asyncio
async def test_has_active_runs(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await _make_run(repo, v_id, status="running")
    assert await repo.has_active_runs(wf_id) is True


@pytest.mark.asyncio
async def test_has_active_runs_false_when_terminal(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    await _make_run(repo, v_id, status="succeeded")
    assert await repo.has_active_runs(wf_id) is False


# --- Rename ---

@pytest.mark.asyncio
async def test_update_workflow_name(repo):
    wf_id = await _make_workflow(repo, name="old")
    await repo.update_workflow(wf_id, name="new-name")
    wf = await repo.get_workflow(wf_id)
    assert wf["name"] == "new-name"


@pytest.mark.asyncio
async def test_update_workflow_description(repo):
    wf_id = await _make_workflow(repo, name="wf", desc="old")
    await repo.update_workflow(wf_id, description="new desc")
    wf = await repo.get_workflow(wf_id)
    assert wf["description"] == "new desc"


# --- Duplicate ---

@pytest.mark.asyncio
async def test_duplicate_workflow(repo):
    wf_id = await _make_workflow(repo, name="orig")
    await _make_version(repo, wf_id, version=1)
    await _make_version(repo, wf_id, version=2)
    new_id = await repo.duplicate_workflow(wf_id, new_name="orig (copy)")
    assert new_id != wf_id

    new_wf = await repo.get_workflow(new_id)
    assert new_wf["name"] == "orig (copy)"

    # Only latest version copied
    versions = await repo.list_versions(new_id)
    assert len(versions) == 1
    assert versions[0]["version"] == 1


# --- Rollback ---

@pytest.mark.asyncio
async def test_rollback_version(repo):
    wf_id = await _make_workflow(repo)
    v1_id = await _make_version(repo, wf_id, version=1)
    v2_id = await _make_version(repo, wf_id, version=2)

    new_v_id, new_v_num = await repo.rollback_version(wf_id, target_version=1)
    assert new_v_num == 3

    v3 = await repo.get_version(wf_id, 3)
    v1 = await repo.get_version(wf_id, 1)
    assert v3["dag_json"] == v1["dag_json"]
    assert v3["compiled_json"] == v1["compiled_json"]


# --- Run listing with filters ---

@pytest.mark.asyncio
async def test_list_runs_basic(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    r1 = await _make_run(repo, v_id, status="succeeded")
    r2 = await _make_run(repo, v_id, status="failed")

    rows, total = await repo.list_runs()
    assert total == 2


@pytest.mark.asyncio
async def test_list_runs_filter_status(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    await _make_run(repo, v_id, status="succeeded")
    await _make_run(repo, v_id, status="failed")

    rows, total = await repo.list_runs(statuses=["failed"])
    assert total == 1
    assert rows[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_list_runs_filter_workflow(repo):
    wf1 = await _make_workflow(repo, name="wf1")
    wf2 = await _make_workflow(repo, name="wf2")
    v1 = await _make_version(repo, wf1)
    v2 = await _make_version(repo, wf2)
    await _make_run(repo, v1, status="succeeded")
    await _make_run(repo, v2, status="succeeded")

    rows, total = await repo.list_runs(workflow_id=wf1)
    assert total == 1


@pytest.mark.asyncio
async def test_list_runs_pagination(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    for _ in range(5):
        await _make_run(repo, v_id, status="succeeded")

    rows, total = await repo.list_runs(limit=2, offset=0)
    assert len(rows) == 2
    assert total == 5


@pytest.mark.asyncio
async def test_list_runs_for_workflow(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    await _make_run(repo, v_id, status="succeeded")

    rows, total = await repo.list_runs(workflow_id=wf_id)
    assert total == 1


@pytest.mark.asyncio
async def test_get_run_with_inputs(repo):
    """get_run returns inputs_json so rerun can read them."""
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await repo.create_run(
        workflow_version_id=v_id,
        inputs_json='{"env": "prod"}',
        idempotency_key=None,
    )
    row = await repo.get_run(run_id)
    assert row["inputs_json"] == '{"env": "prod"}'


@pytest.mark.asyncio
async def test_get_latest_run_for_workflow(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    r1 = await _make_run(repo, v_id, status="succeeded")
    r2 = await _make_run(repo, v_id, status="failed")

    latest = await repo.get_latest_run_for_workflow(wf_id)
    assert latest is not None
    assert latest["id"] == r2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_phase6_repository.py -v`
Expected: FAIL — methods don't exist yet

**Step 3: Implement repository methods**

Add the following methods to `WorkflowRepository` in `backend/src/workflows/repository.py`:

```python
async def soft_delete_workflow(self, id: str) -> None:
    async with self._conn() as db:
        await db.execute(
            "UPDATE workflows SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (_now(), id),
        )
        await db.commit()

async def has_active_runs(self, workflow_id: str) -> bool:
    async with self._conn() as db:
        async with db.execute(
            "SELECT 1 FROM workflow_runs wr "
            "JOIN workflow_versions wv ON wr.workflow_version_id = wv.id "
            "WHERE wv.workflow_id = ? AND wr.status IN ('running', 'pending', 'cancelling') "
            "LIMIT 1",
            (workflow_id,),
        ) as cur:
            return await cur.fetchone() is not None

async def update_workflow(
    self, id: str, *, name: str | None = None, description: str | None = None
) -> None:
    parts: list[str] = []
    vals: list[Any] = []
    if name is not None:
        parts.append("name = ?")
        vals.append(name)
    if description is not None:
        parts.append("description = ?")
        vals.append(description)
    if not parts:
        return
    vals.append(id)
    async with self._conn() as db:
        await db.execute(
            f"UPDATE workflows SET {', '.join(parts)} WHERE id = ?",
            tuple(vals),
        )
        await db.commit()

async def duplicate_workflow(self, source_id: str, new_name: str) -> str:
    source = await self.get_workflow(source_id)
    if source is None:
        raise LookupError("source workflow not found")
    latest = await self.get_latest_version(source_id)
    if latest is None:
        raise LookupError("source has no versions")

    new_id = _new_id()
    async with self._conn() as db:
        await db.execute(
            "INSERT INTO workflows (id, name, description, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_id, new_name, source["description"], _now(), source.get("created_by")),
        )
        v_id = _new_id()
        await db.execute(
            "INSERT INTO workflow_versions "
            "(id, workflow_id, version, dag_json, compiled_json, is_active, created_at) "
            "VALUES (?, ?, 1, ?, ?, 1, ?)",
            (v_id, new_id, latest["dag_json"], latest["compiled_json"], _now()),
        )
        await db.commit()
    return new_id

async def rollback_version(
    self, workflow_id: str, target_version: int
) -> tuple[str, int]:
    target = await self.get_version(workflow_id, target_version)
    if target is None:
        raise LookupError("target version not found")
    latest = await self.get_latest_version(workflow_id)
    next_version = (latest["version"] + 1) if latest else 1
    v_id = await self.create_version(
        workflow_id, next_version, target["dag_json"], target["compiled_json"]
    )
    return v_id, next_version

async def list_runs(
    self,
    *,
    workflow_id: str | None = None,
    statuses: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = []
    params: list[Any] = []

    if workflow_id is not None:
        where.append(
            "wr.workflow_version_id IN "
            "(SELECT id FROM workflow_versions WHERE workflow_id = ?)"
        )
        params.append(workflow_id)
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        where.append(f"wr.status IN ({placeholders})")
        params.extend(statuses)
    if from_date:
        where.append("wr.started_at >= ?")
        params.append(from_date)
    if to_date:
        where.append("wr.started_at <= ?")
        params.append(to_date)

    where_clause = " AND ".join(where) if where else "1=1"

    sort_col = "wr.started_at" if sort == "started_at" else "wr.started_at"
    order_dir = "DESC" if order == "desc" else "ASC"

    async with self._conn() as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM workflow_runs wr WHERE {where_clause}",
            tuple(params),
        ) as cur:
            total = (await cur.fetchone())[0]

        async with db.execute(
            f"SELECT wr.* FROM workflow_runs wr "
            f"WHERE {where_clause} "
            f"ORDER BY {sort_col} {order_dir} "
            f"LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    return rows, total

async def get_latest_run_for_workflow(
    self, workflow_id: str
) -> dict[str, Any] | None:
    async with self._conn() as db:
        async with db.execute(
            "SELECT wr.* FROM workflow_runs wr "
            "JOIN workflow_versions wv ON wr.workflow_version_id = wv.id "
            "WHERE wv.workflow_id = ? "
            "ORDER BY wr.started_at DESC LIMIT 1",
            (workflow_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
```

Also update `list_workflows()` (line 65-71) to exclude deleted:

```python
async def list_workflows(self) -> list[dict[str, Any]]:
    async with self._conn() as db:
        async with db.execute(
            "SELECT * FROM workflows WHERE deleted_at IS NULL ORDER BY created_at ASC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_phase6_repository.py -v`
Expected: ALL PASS

**Step 5: Run existing repo tests for non-regression**

Run: `cd backend && python3 -m pytest tests/test_workflow_repository.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/workflows/repository.py backend/tests/test_phase6_repository.py
git commit -m "feat(phase6): repository — soft delete, rename, duplicate, rollback, run listing"
```

---

## Task 3: Service — Business Logic for New Operations

**Files:**
- Modify: `backend/src/workflows/service.py`
- Test: `backend/tests/test_phase6_service.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_phase6_service.py`:

```python
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService, RunTerminal
from src.contracts.registry import ContractRegistry


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "workflows.db")


@pytest_asyncio.fixture
async def repo(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    return r


@pytest_asyncio.fixture
async def svc(repo):
    contracts = ContractRegistry()
    return WorkflowService(repo, contracts)


async def _seed(svc, name="wf"):
    wf = await svc.create_workflow(name=name, description="d", created_by=None)
    dag = {"inputs_schema": {}, "steps": []}
    v = await svc.create_version(wf["id"], dag)
    return wf, v


# --- Delete ---

@pytest.mark.asyncio
async def test_delete_workflow(svc):
    wf, _ = await _seed(svc)
    result = await svc.delete_workflow(wf["id"])
    assert result is True

    # Should not appear in list
    wfs = await svc.list_workflows()
    assert all(w["id"] != wf["id"] for w in wfs)


@pytest.mark.asyncio
async def test_delete_workflow_not_found(svc):
    result = await svc.delete_workflow("nonexistent")
    assert result is False


@pytest.mark.asyncio
async def test_delete_workflow_with_active_runs_returns_conflict(svc, repo):
    wf, v = await _seed(svc)
    # Create a running run directly in the repo
    run_id = await repo.create_run(
        workflow_version_id=v["version_id"],
        inputs_json="{}",
        idempotency_key=None,
    )
    await repo.update_run_status(run_id, "running")

    with pytest.raises(svc.ActiveRunsError):
        await svc.delete_workflow(wf["id"])


@pytest.mark.asyncio
async def test_delete_idempotent(svc):
    wf, _ = await _seed(svc)
    await svc.delete_workflow(wf["id"])
    result = await svc.delete_workflow(wf["id"])
    assert result is True  # no error


# --- Rename ---

@pytest.mark.asyncio
async def test_rename_workflow(svc):
    wf, _ = await _seed(svc)
    updated = await svc.update_workflow(wf["id"], name="new-name")
    assert updated["name"] == "new-name"


@pytest.mark.asyncio
async def test_update_description(svc):
    wf, _ = await _seed(svc)
    updated = await svc.update_workflow(wf["id"], description="new desc")
    assert updated["description"] == "new desc"


# --- Duplicate ---

@pytest.mark.asyncio
async def test_duplicate_workflow(svc):
    wf, _ = await _seed(svc)
    dup = await svc.duplicate_workflow(wf["id"])
    assert dup["id"] != wf["id"]
    assert dup["name"] == "wf (copy)"


@pytest.mark.asyncio
async def test_duplicate_name_collision(svc):
    wf, _ = await _seed(svc)
    dup1 = await svc.duplicate_workflow(wf["id"])
    assert dup1["name"] == "wf (copy)"

    dup2 = await svc.duplicate_workflow(wf["id"])
    assert dup2["name"] == "wf (copy 2)"


# --- Rollback ---

@pytest.mark.asyncio
async def test_rollback_version(svc):
    wf, v1 = await _seed(svc)
    dag2 = {"inputs_schema": {}, "steps": []}
    v2 = await svc.create_version(wf["id"], dag2)

    result = await svc.rollback_version(wf["id"], target_version=1)
    assert result["version"] == 3


@pytest.mark.asyncio
async def test_rollback_nonexistent_version(svc):
    wf, _ = await _seed(svc)
    with pytest.raises(LookupError):
        await svc.rollback_version(wf["id"], target_version=99)


# --- Run listing ---

@pytest.mark.asyncio
async def test_list_runs(svc, repo):
    wf, v = await _seed(svc)
    r1 = await repo.create_run(
        workflow_version_id=v["version_id"], inputs_json="{}", idempotency_key=None
    )
    await repo.update_run_status(r1, "succeeded")

    result = await svc.list_runs()
    assert result["total"] >= 1
    assert len(result["runs"]) >= 1
    assert "id" in result["runs"][0]
    assert "status" in result["runs"][0]


@pytest.mark.asyncio
async def test_list_runs_with_filters(svc, repo):
    wf, v = await _seed(svc)
    r1 = await repo.create_run(
        workflow_version_id=v["version_id"], inputs_json="{}", idempotency_key=None
    )
    await repo.update_run_status(r1, "succeeded")
    r2 = await repo.create_run(
        workflow_version_id=v["version_id"], inputs_json="{}", idempotency_key=None
    )
    await repo.update_run_status(r2, "failed")

    result = await svc.list_runs(statuses=["failed"])
    assert result["total"] == 1


# --- Rerun ---

@pytest.mark.asyncio
async def test_rerun_returns_version_and_inputs(svc, repo):
    wf, v = await _seed(svc)
    run_id = await repo.create_run(
        workflow_version_id=v["version_id"],
        inputs_json='{"env": "prod"}',
        idempotency_key=None,
    )
    await repo.update_run_status(run_id, "succeeded")

    rerun_data = await svc.get_rerun_data(run_id)
    assert rerun_data["workflow_version_id"] == v["version_id"]
    assert rerun_data["inputs"] == {"env": "prod"}
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_phase6_service.py -v`
Expected: FAIL

**Step 3: Implement service methods**

Add to `WorkflowService` in `backend/src/workflows/service.py`:

```python
class ActiveRunsError(Exception):
    """Raised when trying to delete a workflow with active runs."""
    pass

# Add as class attribute inside WorkflowService:
ActiveRunsError = ActiveRunsError
```

Wait — the `ActiveRunsError` needs to be accessible both as `svc.ActiveRunsError` and importable. Define it at module level next to `RunTerminal` and `InputsInvalid`:

```python
class ActiveRunsError(Exception):
    """Raised when trying to delete a workflow with active runs."""
    pass
```

Then add to `WorkflowService.__init__`:
(No change needed — just use `ActiveRunsError` directly.)

Add these methods to `WorkflowService`:

```python
async def delete_workflow(self, workflow_id: str) -> bool:
    wf = await self._repo.get_workflow(workflow_id)
    if wf is None:
        return False
    if wf.get("deleted_at"):
        return True  # already deleted, idempotent
    if await self._repo.has_active_runs(workflow_id):
        raise ActiveRunsError("workflow has active runs")
    await self._repo.soft_delete_workflow(workflow_id)
    return True

async def update_workflow(
    self, workflow_id: str, *, name: str | None = None, description: str | None = None
) -> dict[str, Any] | None:
    wf = await self._repo.get_workflow(workflow_id)
    if wf is None:
        return None
    await self._repo.update_workflow(workflow_id, name=name, description=description)
    return await self.get_workflow(workflow_id)

async def duplicate_workflow(self, workflow_id: str) -> dict[str, Any]:
    wf = await self._repo.get_workflow(workflow_id)
    if wf is None:
        raise LookupError("workflow not found")
    base_name = wf["name"]

    # Find unique name
    new_name = f"{base_name} (copy)"
    suffix = 1
    while True:
        existing = await self._repo.list_workflows()
        names = {w["name"] for w in existing}
        # Also check the raw table for deleted workflows
        if new_name not in names:
            try:
                new_id = await self._repo.duplicate_workflow(workflow_id, new_name)
                break
            except Exception:
                pass
        suffix += 1
        new_name = f"{base_name} (copy {suffix})"

    return await self.get_workflow(new_id)

async def rollback_version(
    self, workflow_id: str, target_version: int
) -> dict[str, Any]:
    v_id, v_num = await self._repo.rollback_version(workflow_id, target_version)
    return {"version_id": v_id, "version": v_num, "workflow_id": workflow_id}

async def list_runs(
    self,
    *,
    workflow_id: str | None = None,
    statuses: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    rows, total = await self._repo.list_runs(
        workflow_id=workflow_id,
        statuses=statuses,
        from_date=from_date,
        to_date=to_date,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {
        "runs": [self._run_summary(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

async def get_rerun_data(self, run_id: str) -> dict[str, Any]:
    row = await self._repo.get_run(run_id)
    if row is None:
        raise LookupError("run not found")
    return {
        "workflow_version_id": row["workflow_version_id"],
        "inputs": json.loads(row["inputs_json"]),
    }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_phase6_service.py -v`
Expected: ALL PASS

**Step 5: Run existing service tests for non-regression**

Run: `cd backend && python3 -m pytest tests/test_workflows_save_path.py tests/test_workflows_run_path.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/workflows/service.py backend/tests/test_phase6_service.py
git commit -m "feat(phase6): service — delete, rename, duplicate, rollback, run listing, rerun data"
```

---

## Task 4: Routes — New API Endpoints

**Files:**
- Modify: `backend/src/api/routes_workflows.py`
- Test: `backend/tests/test_phase6_routes.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_phase6_routes.py`:

```python
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.api.routes_workflows import router, set_workflow_service
from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService
from src.contracts.registry import ContractRegistry
from src import config


@pytest.fixture(autouse=True)
def enable_flag(monkeypatch):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", True)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "wf.db")


@pytest_asyncio.fixture
async def app(db_path):
    repo = WorkflowRepository(db_path)
    await repo.init()
    svc = WorkflowService(repo, ContractRegistry())
    set_workflow_service(svc)

    app = FastAPI()
    app.include_router(router)
    yield app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_wf(client, name="wf"):
    resp = await client.post("/api/v4/workflows", json={"name": name})
    return resp.json()


async def _create_version(client, wf_id):
    dag = {"inputs_schema": {}, "steps": []}
    resp = await client.post(f"/api/v4/workflows/{wf_id}/versions", json=dag)
    return resp.json()


# --- DELETE ---

@pytest.mark.asyncio
async def test_delete_workflow(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])

    resp = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/v4/workflows/{wf['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found(client):
    resp = await client.delete("/api/v4/workflows/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_idempotent(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])
    await client.delete(f"/api/v4/workflows/{wf['id']}")
    resp = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp.status_code == 204


# --- PATCH (rename) ---

@pytest.mark.asyncio
async def test_patch_rename(client):
    wf = await _create_wf(client)
    resp = await client.patch(
        f"/api/v4/workflows/{wf['id']}",
        json={"name": "renamed"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"


@pytest.mark.asyncio
async def test_patch_not_found(client):
    resp = await client.patch(
        "/api/v4/workflows/nonexistent",
        json={"name": "x"},
    )
    assert resp.status_code == 404


# --- POST duplicate ---

@pytest.mark.asyncio
async def test_duplicate(client):
    wf = await _create_wf(client, name="orig")
    await _create_version(client, wf["id"])

    resp = await client.post(f"/api/v4/workflows/{wf['id']}/duplicate")
    assert resp.status_code == 201
    assert resp.json()["name"] == "orig (copy)"


# --- POST rollback ---

@pytest.mark.asyncio
async def test_rollback(client):
    wf = await _create_wf(client)
    v1 = await _create_version(client, wf["id"])
    v2 = await _create_version(client, wf["id"])

    resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/versions/1/rollback"
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == 3


@pytest.mark.asyncio
async def test_rollback_not_found(client):
    wf = await _create_wf(client)
    resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/versions/99/rollback"
    )
    assert resp.status_code == 404


# --- GET /runs (with filters) ---

@pytest.mark.asyncio
async def test_list_runs(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])
    await client.post(f"/api/v4/workflows/{wf['id']}/runs", json={"inputs": {}})

    resp = await client.get("/api/v4/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


@pytest.mark.asyncio
async def test_list_runs_status_filter(client):
    resp = await client.get("/api/v4/runs", params={"status": "failed"})
    assert resp.status_code == 200


# --- GET /workflows/{id}/runs ---

@pytest.mark.asyncio
async def test_workflow_runs(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])
    await client.post(f"/api/v4/workflows/{wf['id']}/runs", json={"inputs": {}})

    resp = await client.get(f"/api/v4/workflows/{wf['id']}/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert "total" in data


# --- POST /runs/{id}/rerun ---

@pytest.mark.asyncio
async def test_rerun(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])
    run_resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/runs", json={"inputs": {"env": "prod"}}
    )
    run_id = run_resp.json()["run"]["id"]

    resp = await client.post(f"/api/v4/runs/{run_id}/rerun")
    assert resp.status_code == 200
    data = resp.json()
    assert "workflow_version_id" in data
    assert data["inputs"] == {"env": "prod"}
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_phase6_routes.py -v`
Expected: FAIL

**Step 3: Implement route endpoints**

Add to `backend/src/api/routes_workflows.py`:

```python
# Add import at top:
from src.workflows.service import ActiveRunsError

# Add Pydantic model:
class UpdateWorkflowBody(BaseModel):
    name: str | None = None
    description: str | None = None


# --- New endpoints ---

@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_flag)],
)
async def delete_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
):
    try:
        result = await svc.delete_workflow(workflow_id)
    except ActiveRunsError:
        raise HTTPException(
            status_code=409,
            detail={"type": "active_runs", "message": "workflow has active runs"},
        )
    if not result:
        raise HTTPException(status_code=404, detail="workflow not found")
    return None


@router.patch(
    "/workflows/{workflow_id}",
    dependencies=[Depends(require_flag)],
)
async def update_workflow(
    workflow_id: str,
    body: UpdateWorkflowBody,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    result = await svc.update_workflow(
        workflow_id, name=body.name, description=body.description
    )
    if result is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return result


@router.post(
    "/workflows/{workflow_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def duplicate_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.duplicate_workflow(workflow_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/workflows/{workflow_id}/versions/{version}/rollback",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def rollback_version(
    workflow_id: str,
    version: int,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.rollback_version(workflow_id, version)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs", dependencies=[Depends(require_flag)])
async def list_runs(
    status_filter: str | None = None,
    workflow_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    statuses = status_filter.split(",") if status_filter else None
    return await svc.list_runs(
        workflow_id=workflow_id,
        statuses=statuses,
        from_date=from_date,
        to_date=to_date,
        sort=sort,
        order=order,
        limit=min(limit, 200),
        offset=offset,
    )


@router.get(
    "/workflows/{workflow_id}/runs",
    dependencies=[Depends(require_flag)],
)
async def list_workflow_runs(
    workflow_id: str,
    status_filter: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    statuses = status_filter.split(",") if status_filter else None
    return await svc.list_runs(
        workflow_id=workflow_id,
        statuses=statuses,
        from_date=from_date,
        to_date=to_date,
        sort=sort,
        order=order,
        limit=min(limit, 200),
        offset=offset,
    )


@router.post(
    "/runs/{run_id}/rerun",
    dependencies=[Depends(require_flag)],
)
async def rerun(
    run_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.get_rerun_data(run_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

**Important:** The `list_runs` endpoint uses query param named `status` in the design but use `status_filter` in FastAPI to avoid conflict with the `status` module import. Frontend will send `?status=failed` — we'll alias it. Actually, use FastAPI's `Query` alias:

```python
from fastapi import Query

# In list_runs and list_workflow_runs:
status_filter: str | None = Query(default=None, alias="status"),
```

Also update `get_workflow` to return 404 for deleted workflows. Modify the existing `get_workflow` route handler (line 72-80):

```python
@router.get("/workflows/{workflow_id}", dependencies=[Depends(require_flag)])
async def get_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf
```

The `get_workflow` service method needs to check `deleted_at`. Update `service.py`'s `get_workflow`:

```python
async def get_workflow(self, id: str) -> dict[str, Any] | None:
    row = await self._repo.get_workflow(id)
    if row is None or row.get("deleted_at"):
        return None
    # ... rest unchanged
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_phase6_routes.py -v`
Expected: ALL PASS

**Step 5: Run existing route tests for non-regression**

Run: `cd backend && python3 -m pytest tests/test_workflows_save_path.py tests/test_workflows_run_path.py tests/test_workflows_feature_flag.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes_workflows.py backend/src/workflows/service.py backend/tests/test_phase6_routes.py
git commit -m "feat(phase6): routes — DELETE, PATCH, duplicate, rollback, list runs, rerun endpoints"
```

---

## Task 5: Frontend Types + Services

**Files:**
- Modify: `frontend/src/types/index.ts:2553-2654`
- Modify: `frontend/src/services/workflows.ts`
- Modify: `frontend/src/services/runs.ts`

**Step 1: Add new types**

Add to `frontend/src/types/index.ts` after the existing `RunDetail` interface (after line 2654):

```typescript
export interface RunListResponse {
  runs: Array<{
    id: string;
    workflow_version_id: string;
    status: RunStatus;
    started_at?: string;
    ended_at?: string;
  }>;
  total: number;
  limit: number;
  offset: number;
}

export interface RerunData {
  workflow_version_id: string;
  inputs: Record<string, unknown>;
}
```

Update `WorkflowSummary` to add optional `last_run` field:

```typescript
export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  created_by?: string;
  last_run?: {
    status: RunStatus;
    started_at: string;
  };
}
```

**Step 2: Add new service functions to `workflows.ts`**

Add to `frontend/src/services/workflows.ts`:

```typescript
export function deleteWorkflow(id: string): Promise<void> {
  return callWorkflowsApi<void>(
    `/api/v4/workflows/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
  );
}

export function updateWorkflow(
  id: string,
  body: { name?: string; description?: string },
): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>(
    `/api/v4/workflows/${encodeURIComponent(id)}`,
    { method: 'PATCH', body: JSON.stringify(body) },
  );
}

export function duplicateWorkflow(id: string): Promise<WorkflowDetail> {
  return callWorkflowsApi<WorkflowDetail>(
    `/api/v4/workflows/${encodeURIComponent(id)}/duplicate`,
    { method: 'POST' },
  );
}

export function rollbackVersion(
  workflowId: string,
  version: number,
): Promise<VersionSummary> {
  return callWorkflowsApi<VersionSummary>(
    `/api/v4/workflows/${encodeURIComponent(workflowId)}/versions/${version}/rollback`,
    { method: 'POST' },
  );
}
```

Fix `callWorkflowsApi` to handle 204 (no body) and 409 (conflict):

```typescript
export async function callWorkflowsApi<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (resp.status === 204) return undefined as T;
  if (resp.status === 404) throw new WorkflowsDisabledError();
  if (resp.status === 409) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as { type?: string; message?: string };
    throw new Error(d.message ?? 'conflict');
  }
  if (resp.status === 422) {
    const body = await resp.json().catch(() => ({}));
    const d = (body?.detail ?? {}) as {
      type?: string;
      message?: string;
      path?: string;
      errors?: unknown[];
    };
    throw new CompileError(
      d.type ?? 'compile_error',
      d.message ?? 'invalid',
      d.path,
      d.errors,
    );
  }
  if (!resp.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}
```

**Step 3: Add new service functions to `runs.ts`**

Add to `frontend/src/services/runs.ts`:

```typescript
import type { RunListResponse, RerunData } from '../types';

export async function listRuns(params?: {
  status?: string;
  workflow_id?: string;
  from?: string;
  to?: string;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
}): Promise<RunListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.workflow_id) query.set('workflow_id', params.workflow_id);
  if (params?.from) query.set('from', params.from);
  if (params?.to) query.set('to', params.to);
  if (params?.sort) query.set('sort', params.sort);
  if (params?.order) query.set('order', params.order);
  if (params?.limit != null) query.set('limit', String(params.limit));
  if (params?.offset != null) query.set('offset', String(params.offset));

  const qs = query.toString();
  const path = `/api/v4/runs${qs ? `?${qs}` : ''}`;
  const resp = await runsFetch(path);
  return (await handleCommon(resp, path, 'GET')) as RunListResponse;
}

export async function getRerunData(runId: string): Promise<RerunData> {
  const path = `/api/v4/runs/${encodeURIComponent(runId)}/rerun`;
  const resp = await runsFetch(path, { method: 'POST' });
  return (await handleCommon(resp, path, 'POST')) as RerunData;
}
```

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/workflows.ts frontend/src/services/runs.ts
git commit -m "feat(phase6): frontend types + service functions for management UI"
```

---

## Task 6: ConfirmDeleteDialog Component

**Files:**
- Create: `frontend/src/components/Workflows/Shared/ConfirmDeleteDialog.tsx`
- Test: `frontend/src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`

**Step 1: Write the test**

Create `frontend/src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmDeleteDialog } from '../ConfirmDeleteDialog';

describe('ConfirmDeleteDialog', () => {
  const defaultProps = {
    workflowName: 'my-workflow',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  it('renders with workflow name prompt', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />);
    expect(screen.getByText(/type.*my-workflow.*to confirm/i)).toBeInTheDocument();
  });

  it('delete button is disabled until name matches', () => {
    render(<ConfirmDeleteDialog {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /delete/i });
    expect(btn).toBeDisabled();
  });

  it('enables delete button when name matches', async () => {
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} />);
    const input = screen.getByPlaceholderText('my-workflow');
    await user.type(input, 'my-workflow');
    const btn = screen.getByRole('button', { name: /delete/i });
    expect(btn).not.toBeDisabled();
  });

  it('calls onConfirm when delete clicked', async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} onConfirm={onConfirm} />);
    const input = screen.getByPlaceholderText('my-workflow');
    await user.type(input, 'my-workflow');
    await user.click(screen.getByRole('button', { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel clicked', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<ConfirmDeleteDialog {...defaultProps} onCancel={onCancel} />);
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('shows deleting state', () => {
    render(<ConfirmDeleteDialog {...defaultProps} deleting />);
    expect(screen.getByText(/deleting/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`
Expected: FAIL

**Step 3: Implement the component**

Create `frontend/src/components/Workflows/Shared/ConfirmDeleteDialog.tsx`:

```tsx
import { useState } from 'react';

interface Props {
  workflowName: string;
  onConfirm: () => void;
  onCancel: () => void;
  deleting?: boolean;
}

export function ConfirmDeleteDialog({ workflowName, onConfirm, onCancel, deleting }: Props) {
  const [input, setInput] = useState('');
  const matches = input === workflowName;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-wr-border bg-wr-surface p-6 space-y-4">
        <h2 className="text-lg font-semibold text-wr-text">Delete workflow</h2>
        <p className="text-sm text-wr-text-muted">
          This will permanently remove this workflow from the list. Existing runs and
          their data will remain accessible.
        </p>
        <p className="text-sm text-wr-text">
          Type <span className="font-mono font-semibold text-red-400">{workflowName}</span> to confirm.
        </p>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={workflowName}
          className="w-full rounded-md border border-wr-border bg-wr-bg px-3 py-2 text-sm text-wr-text focus:outline focus:outline-2 focus:outline-red-500"
          autoFocus
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-wr-border bg-wr-surface px-4 py-1.5 text-sm text-wr-text hover:bg-wr-elevated"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!matches || deleting}
            className="rounded-md bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/Workflows/Shared/ConfirmDeleteDialog.tsx frontend/src/components/Workflows/Shared/__tests__/ConfirmDeleteDialog.test.tsx
git commit -m "feat(phase6): ConfirmDeleteDialog component with type-to-confirm"
```

---

## Task 7: RunFilterBar Component

**Files:**
- Create: `frontend/src/components/Workflows/Runs/RunFilterBar.tsx`
- Test: `frontend/src/components/Workflows/Runs/__tests__/RunFilterBar.test.tsx`

**Step 1: Write the test**

Create `frontend/src/components/Workflows/Runs/__tests__/RunFilterBar.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RunFilterBar } from '../RunFilterBar';

describe('RunFilterBar', () => {
  const defaultProps = {
    statuses: [] as string[],
    onStatusToggle: vi.fn(),
    sortBy: 'started_at' as const,
    sortOrder: 'desc' as const,
    onSortChange: vi.fn(),
  };

  it('renders status chip buttons', () => {
    render(<RunFilterBar {...defaultProps} />);
    expect(screen.getByRole('button', { name: /succeeded/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /failed/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /running/i })).toBeInTheDocument();
  });

  it('highlights active status chips', () => {
    render(<RunFilterBar {...defaultProps} statuses={['failed']} />);
    const btn = screen.getByRole('button', { name: /failed/i });
    expect(btn.className).toContain('bg-red');
  });

  it('calls onStatusToggle when chip clicked', async () => {
    const onStatusToggle = vi.fn();
    const user = userEvent.setup();
    render(<RunFilterBar {...defaultProps} onStatusToggle={onStatusToggle} />);
    await user.click(screen.getByRole('button', { name: /failed/i }));
    expect(onStatusToggle).toHaveBeenCalledWith('failed');
  });

  it('shows sort dropdown', () => {
    render(<RunFilterBar {...defaultProps} />);
    expect(screen.getByLabelText(/sort/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/RunFilterBar.test.tsx`
Expected: FAIL

**Step 3: Implement the component**

Create `frontend/src/components/Workflows/Runs/RunFilterBar.tsx`:

```tsx
const ALL_STATUSES = [
  { value: 'succeeded', label: 'Succeeded', activeClass: 'bg-emerald-600 text-white' },
  { value: 'failed', label: 'Failed', activeClass: 'bg-red-600 text-white' },
  { value: 'running', label: 'Running', activeClass: 'bg-amber-600 text-white' },
  { value: 'pending', label: 'Pending', activeClass: 'bg-neutral-600 text-white' },
  { value: 'cancelled', label: 'Cancelled', activeClass: 'bg-slate-600 text-white' },
] as const;

interface RunFilterBarProps {
  statuses: string[];
  onStatusToggle: (status: string) => void;
  sortBy: 'started_at' | 'duration';
  sortOrder: 'asc' | 'desc';
  onSortChange: (sort: 'started_at' | 'duration', order: 'asc' | 'desc') => void;
}

export function RunFilterBar({
  statuses,
  onStatusToggle,
  sortBy,
  sortOrder,
  onSortChange,
}: RunFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex flex-wrap gap-1.5">
        {ALL_STATUSES.map((s) => {
          const active = statuses.includes(s.value);
          return (
            <button
              key={s.value}
              type="button"
              onClick={() => onStatusToggle(s.value)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                active
                  ? s.activeClass
                  : 'bg-wr-surface text-wr-text-muted border border-wr-border hover:bg-wr-elevated'
              }`}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <label htmlFor="run-sort" className="text-xs text-wr-text-muted">
          Sort
        </label>
        <select
          id="run-sort"
          aria-label="Sort"
          value={`${sortBy}-${sortOrder}`}
          onChange={(e) => {
            const [sort, order] = e.target.value.split('-') as ['started_at' | 'duration', 'asc' | 'desc'];
            onSortChange(sort, order);
          }}
          className="rounded-md border border-wr-border bg-wr-bg px-2 py-1 text-xs text-wr-text"
        >
          <option value="started_at-desc">Newest first</option>
          <option value="started_at-asc">Oldest first</option>
        </select>
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/RunFilterBar.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/Workflows/Runs/RunFilterBar.tsx frontend/src/components/Workflows/Runs/__tests__/RunFilterBar.test.tsx
git commit -m "feat(phase6): RunFilterBar component with status chips + sort"
```

---

## Task 8: VersionDiff Component

**Files:**
- Create: `frontend/src/components/Workflows/Shared/VersionDiff.tsx`
- Test: `frontend/src/components/Workflows/Shared/__tests__/VersionDiff.test.tsx`

**Step 1: Write the test**

Create `frontend/src/components/Workflows/Shared/__tests__/VersionDiff.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VersionDiff } from '../VersionDiff';
import type { StepSpec } from '../../../../types';

function makeStep(overrides: Partial<StepSpec> & { id: string }): StepSpec {
  return {
    agent: 'log_agent',
    agent_version: 1,
    inputs: {},
    ...overrides,
  };
}

describe('VersionDiff', () => {
  it('shows added steps in green', () => {
    const oldSteps: StepSpec[] = [];
    const newSteps: StepSpec[] = [makeStep({ id: 'new_step' })];

    render(<VersionDiff oldSteps={oldSteps} newSteps={newSteps} />);
    const row = screen.getByTestId('diff-row-new_step');
    expect(row.className).toContain('green');
    expect(screen.getByText('Added')).toBeInTheDocument();
  });

  it('shows removed steps in red', () => {
    const oldSteps: StepSpec[] = [makeStep({ id: 'old_step' })];
    const newSteps: StepSpec[] = [];

    render(<VersionDiff oldSteps={oldSteps} newSteps={newSteps} />);
    const row = screen.getByTestId('diff-row-old_step');
    expect(row.className).toContain('red');
    expect(screen.getByText('Removed')).toBeInTheDocument();
  });

  it('shows modified steps in amber when agent differs', () => {
    const oldSteps: StepSpec[] = [makeStep({ id: 's1', agent: 'log_agent' })];
    const newSteps: StepSpec[] = [makeStep({ id: 's1', agent: 'metrics_agent' })];

    render(<VersionDiff oldSteps={oldSteps} newSteps={newSteps} />);
    const row = screen.getByTestId('diff-row-s1');
    expect(row.className).toContain('amber');
    expect(screen.getByText('Modified')).toBeInTheDocument();
    expect(screen.getByText(/agent/)).toBeInTheDocument();
  });

  it('shows unchanged steps as dimmed', () => {
    const steps: StepSpec[] = [makeStep({ id: 's1' })];
    render(<VersionDiff oldSteps={steps} newSteps={steps} />);
    const row = screen.getByTestId('diff-row-s1');
    expect(row.className).toContain('opacity');
  });

  it('handles empty diff', () => {
    render(<VersionDiff oldSteps={[]} newSteps={[]} />);
    expect(screen.getByText(/no changes/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Workflows/Shared/__tests__/VersionDiff.test.tsx`
Expected: FAIL

**Step 3: Implement the component**

Create `frontend/src/components/Workflows/Shared/VersionDiff.tsx`:

```tsx
import type { StepSpec } from '../../../types';

interface VersionDiffProps {
  oldSteps: StepSpec[];
  newSteps: StepSpec[];
}

type DiffKind = 'added' | 'removed' | 'modified' | 'unchanged';

interface DiffEntry {
  stepId: string;
  kind: DiffKind;
  changedFields: string[];
  oldStep?: StepSpec;
  newStep?: StepSpec;
}

const COMPARE_FIELDS: (keyof StepSpec)[] = [
  'agent',
  'agent_version',
  'on_failure',
  'timeout_seconds_override',
];

function shallowEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function computeDiff(oldSteps: StepSpec[], newSteps: StepSpec[]): DiffEntry[] {
  const oldMap = new Map(oldSteps.map((s) => [s.id, s]));
  const newMap = new Map(newSteps.map((s) => [s.id, s]));
  const allIds = new Set([...oldMap.keys(), ...newMap.keys()]);
  const entries: DiffEntry[] = [];

  for (const id of allIds) {
    const old = oldMap.get(id);
    const curr = newMap.get(id);

    if (!old && curr) {
      entries.push({ stepId: id, kind: 'added', changedFields: [], newStep: curr });
    } else if (old && !curr) {
      entries.push({ stepId: id, kind: 'removed', changedFields: [], oldStep: old });
    } else if (old && curr) {
      const changed: string[] = [];
      for (const field of COMPARE_FIELDS) {
        if (!shallowEqual(old[field], curr[field])) changed.push(field);
      }
      if (!shallowEqual(old.inputs, curr.inputs)) changed.push('inputs');
      if (!shallowEqual(old.when, curr.when)) changed.push('when');

      entries.push({
        stepId: id,
        kind: changed.length > 0 ? 'modified' : 'unchanged',
        changedFields: changed,
        oldStep: old,
        newStep: curr,
      });
    }
  }

  return entries;
}

const KIND_STYLES: Record<DiffKind, { bg: string; label: string; labelClass: string }> = {
  added: { bg: 'bg-green-900/20 border-green-700', label: 'Added', labelClass: 'text-green-400' },
  removed: { bg: 'bg-red-900/20 border-red-700', label: 'Removed', labelClass: 'text-red-400' },
  modified: { bg: 'bg-amber-900/20 border-amber-700', label: 'Modified', labelClass: 'text-amber-400' },
  unchanged: { bg: 'opacity-40 border-wr-border', label: '', labelClass: '' },
};

export function VersionDiff({ oldSteps, newSteps }: VersionDiffProps) {
  const diff = computeDiff(oldSteps, newSteps);

  if (diff.length === 0) {
    return <p className="text-sm text-wr-text-muted py-4">No changes between versions.</p>;
  }

  const hasChanges = diff.some((d) => d.kind !== 'unchanged');
  if (!hasChanges) {
    return <p className="text-sm text-wr-text-muted py-4">No changes between versions.</p>;
  }

  return (
    <div className="space-y-2">
      {diff.map((entry) => {
        const style = KIND_STYLES[entry.kind];
        return (
          <div
            key={entry.stepId}
            data-testid={`diff-row-${entry.stepId}`}
            className={`rounded-md border p-3 ${style.bg}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-wr-text">
                {entry.stepId}
              </span>
              {style.label && (
                <span className={`text-xs font-semibold ${style.labelClass}`}>
                  {style.label}
                </span>
              )}
            </div>
            {entry.changedFields.length > 0 && (
              <div className="mt-1 text-xs text-wr-text-muted">
                Changed: {entry.changedFields.join(', ')}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Workflows/Shared/__tests__/VersionDiff.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/Workflows/Shared/VersionDiff.tsx frontend/src/components/Workflows/Shared/__tests__/VersionDiff.test.tsx
git commit -m "feat(phase6): VersionDiff component — side-by-side step comparison by step_id"
```

---

## Task 9: WorkflowListPage — Three-Dot Menu, Rename, Duplicate, Delete

**Files:**
- Modify: `frontend/src/components/Workflows/Builder/WorkflowListPage.tsx`

**Step 1: Update WorkflowListPage**

Replace the workflow card rendering in `WorkflowListPage.tsx` with a three-dot menu supporting rename, duplicate, and delete. Key changes:

```tsx
// Add imports at top:
import { deleteWorkflow, duplicateWorkflow, updateWorkflow } from '../../../services/workflows';
import { ConfirmDeleteDialog } from '../Shared/ConfirmDeleteDialog';

// Add state for menu, rename, delete:
const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
const [renamingId, setRenamingId] = useState<string | null>(null);
const [renameValue, setRenameValue] = useState('');
const [deleteTarget, setDeleteTarget] = useState<WorkflowSummary | null>(null);
const [deleting, setDeleting] = useState(false);
```

Add handlers:

```tsx
const handleRename = useCallback(async (wfId: string, newName: string) => {
  if (!newName.trim()) return;
  try {
    await updateWorkflow(wfId, { name: newName.trim() });
    setWorkflows((prev) =>
      prev.map((w) => (w.id === wfId ? { ...w, name: newName.trim() } : w)),
    );
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Rename failed');
  }
  setRenamingId(null);
}, []);

const handleDuplicate = useCallback(async (wfId: string) => {
  setMenuOpenId(null);
  try {
    const dup = await duplicateWorkflow(wfId);
    navigate(`/workflows/${dup.id}`);
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Duplicate failed');
  }
}, [navigate]);

const handleDelete = useCallback(async () => {
  if (!deleteTarget) return;
  setDeleting(true);
  try {
    await deleteWorkflow(deleteTarget.id);
    setWorkflows((prev) => prev.filter((w) => w.id !== deleteTarget.id));
    setDeleteTarget(null);
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Delete failed');
  } finally {
    setDeleting(false);
  }
}, [deleteTarget]);
```

Replace the workflow card with:

```tsx
{workflows.map((wf) => (
  <div
    key={wf.id}
    className="flex w-full items-center gap-4 rounded-md border border-wr-border bg-wr-surface px-4 py-3 hover:bg-wr-elevated transition-colors"
  >
    {/* Clickable area */}
    <button
      type="button"
      onClick={() => navigate(`/workflows/${wf.id}`)}
      className="flex-1 min-w-0 text-left"
    >
      {renamingId === wf.id ? (
        <input
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onBlur={() => handleRename(wf.id, renameValue)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleRename(wf.id, renameValue);
            if (e.key === 'Escape') setRenamingId(null);
          }}
          onClick={(e) => e.stopPropagation()}
          className="w-full rounded border border-wr-accent bg-wr-bg px-2 py-0.5 text-sm text-wr-text focus:outline-none"
          autoFocus
        />
      ) : (
        <div className="text-sm font-medium text-wr-text">{wf.name}</div>
      )}
      {wf.description && (
        <div className="mt-0.5 text-xs text-wr-text-muted truncate">
          {wf.description}
        </div>
      )}
    </button>

    <div className="shrink-0 text-xs text-wr-text-muted">
      {new Date(wf.created_at).toLocaleDateString()}
    </div>

    {/* Three-dot menu */}
    <div className="relative">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpenId(menuOpenId === wf.id ? null : wf.id);
        }}
        className="rounded p-1 text-wr-text-muted hover:bg-wr-elevated hover:text-wr-text"
        aria-label="Workflow actions"
      >
        <span className="material-symbols-outlined text-lg">more_vert</span>
      </button>
      {menuOpenId === wf.id && (
        <div className="absolute right-0 top-full mt-1 w-36 rounded-md border border-wr-border bg-wr-surface shadow-lg z-10">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpenId(null);
              setRenamingId(wf.id);
              setRenameValue(wf.name);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-wr-text hover:bg-wr-elevated"
          >
            Rename
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleDuplicate(wf.id);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-wr-text hover:bg-wr-elevated"
          >
            Duplicate
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpenId(null);
              setDeleteTarget(wf);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 hover:bg-wr-elevated"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  </div>
))}

{/* Delete dialog */}
{deleteTarget && (
  <ConfirmDeleteDialog
    workflowName={deleteTarget.name}
    onConfirm={handleDelete}
    onCancel={() => setDeleteTarget(null)}
    deleting={deleting}
  />
)}
```

**Step 2: Run existing WorkflowListPage tests**

Run: `cd frontend && npx vitest run src/components/Workflows/Builder/__tests__/WorkflowListPage.test.tsx`
Expected: PASS (adjust tests if needed for changed DOM structure)

**Step 3: Commit**

```bash
git add frontend/src/components/Workflows/Builder/WorkflowListPage.tsx
git commit -m "feat(phase6): WorkflowListPage — three-dot menu with rename, duplicate, delete"
```

---

## Task 10: WorkflowBuilderPage — Version Diff + Rollback

**Files:**
- Modify: `frontend/src/components/Workflows/Builder/WorkflowBuilderPage.tsx`
- Modify: `frontend/src/components/Workflows/Shared/WorkflowHeader.tsx`

**Step 1: Add rollback + diff to WorkflowBuilderPage**

In `WorkflowBuilderPage.tsx`, add state and handlers:

```tsx
// Add imports:
import { rollbackVersion } from '../../../services/workflows';
import { VersionDiff } from '../Shared/VersionDiff';

// Add state:
const [showDiff, setShowDiff] = useState(false);
const [diffVersions, setDiffVersions] = useState<{ old: StepSpec[]; new: StepSpec[] } | null>(null);
const [rollingBack, setRollingBack] = useState(false);

// Add handlers:
const handleRollback = useCallback(async (version: number) => {
  if (!workflowId || rollingBack) return;
  setRollingBack(true);
  try {
    const result = await rollbackVersion(workflowId, version);
    const updatedVersions = await listVersions(workflowId);
    setVersions(updatedVersions);
    const versionDetail = await getVersion(workflowId, result.version);
    builder.loadVersion(versionDetail.dag, result.version);
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Rollback failed');
  } finally {
    setRollingBack(false);
  }
}, [workflowId, rollingBack, builder]);

const handleShowDiff = useCallback(async (versionNum: number) => {
  if (!workflowId) return;
  try {
    const latestVersion = Math.max(...versions.map((v) => v.version));
    const [oldDetail, newDetail] = await Promise.all([
      getVersion(workflowId, versionNum),
      getVersion(workflowId, latestVersion),
    ]);
    setDiffVersions({
      old: oldDetail.dag.steps,
      new: newDetail.dag.steps,
    });
    setShowDiff(true);
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Failed to load diff');
  }
}, [workflowId, versions]);
```

Pass new props to `WorkflowHeader`:

```tsx
<WorkflowHeader
  workflow={workflow}
  versions={versions}
  activeVersion={versions.length > 0 ? Math.max(...versions.map((v) => v.version)) : undefined}
  selectedVersion={builder.baseVersion ?? undefined}
  baseVersion={builder.dirty ? (builder.baseVersion ?? undefined) : undefined}
  canSave={builder.dirty && !saving}
  onSelectVersion={handleVersionSelect}
  onForkVersion={handleVersionFork}
  onSave={handleSave}
  onRun={handleRun}
  onRollback={handleRollback}
  onShowDiff={handleShowDiff}
  saving={saving}
  rollingBack={rollingBack}
/>
```

Add diff modal below the main content:

```tsx
{/* Version diff modal */}
{showDiff && diffVersions && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div className="w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-lg border border-wr-border bg-wr-surface p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-wr-text">Version Diff</h2>
        <button
          type="button"
          onClick={() => setShowDiff(false)}
          className="text-wr-text-muted hover:text-wr-text"
        >
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>
      <VersionDiff oldSteps={diffVersions.old} newSteps={diffVersions.new} />
    </div>
  </div>
)}
```

**Step 2: Update WorkflowHeader to add rollback + diff buttons**

Update `WorkflowHeader` props interface:

```tsx
interface Props {
  // ... existing props
  onRollback?: (version: number) => void;
  onShowDiff?: (version: number) => void;
  rollingBack?: boolean;
}
```

Add rollback and diff buttons to the version selector area. In the `VersionSwitcher`, add these actions for non-latest versions. Since the `VersionSwitcher` is a separate component, we'll add the buttons in the header after the `VersionSwitcher`:

```tsx
{selectedVersion !== undefined && activeVersion !== undefined && selectedVersion !== activeVersion && (
  <div className="flex items-center gap-2">
    {onRollback && (
      <button
        type="button"
        onClick={() => onRollback(selectedVersion)}
        disabled={rollingBack}
        className="rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated disabled:opacity-50"
      >
        {rollingBack ? 'Restoring...' : 'Restore this version'}
      </button>
    )}
    {onShowDiff && (
      <button
        type="button"
        onClick={() => onShowDiff(selectedVersion)}
        className="rounded-md border border-wr-border bg-wr-surface px-2 py-1 text-xs text-wr-text hover:bg-wr-elevated"
      >
        Diff
      </button>
    )}
  </div>
)}
```

**Step 3: Run existing tests**

Run: `cd frontend && npx vitest run src/components/Workflows/Builder/__tests__/WorkflowBuilderPage.test.tsx`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/Workflows/Builder/WorkflowBuilderPage.tsx frontend/src/components/Workflows/Shared/WorkflowHeader.tsx
git commit -m "feat(phase6): WorkflowBuilderPage — version diff modal + rollback button"
```

---

## Task 11: WorkflowRunsPage — Server-Side Run List + Filters + Pagination

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/WorkflowRunsPage.tsx`

**Step 1: Rewrite WorkflowRunsPage to use server-side run listing**

Replace the localStorage-based run list with server-side listing via `GET /api/v4/runs`. Key changes:

```tsx
// Replace imports:
import { listRuns } from '../../../services/runs';
import { RunFilterBar } from './RunFilterBar';
import type { RunListResponse } from '../../../types';

// Replace state:
const [runData, setRunData] = useState<RunListResponse | null>(null);
const [loading, setLoading] = useState(true);

// Filter state (synced to URL):
const [searchParams, setSearchParams] = useSearchParams();
const statuses = searchParams.get('status')?.split(',').filter(Boolean) ?? [];
const sortBy = (searchParams.get('sort') ?? 'started_at') as 'started_at' | 'duration';
const sortOrder = (searchParams.get('order') ?? 'desc') as 'asc' | 'desc';
const page = Number(searchParams.get('page') ?? '0');
const workflowFilter = searchParams.get('workflow_id') ?? undefined;
const LIMIT = 50;

// Fetch runs when filters change:
useEffect(() => {
  let cancelled = false;
  setLoading(true);
  listRuns({
    status: statuses.length > 0 ? statuses.join(',') : undefined,
    workflow_id: workflowFilter,
    sort: sortBy,
    order: sortOrder,
    limit: LIMIT,
    offset: page * LIMIT,
  })
    .then((data) => {
      if (!cancelled) setRunData(data);
    })
    .catch(() => {})
    .finally(() => {
      if (!cancelled) setLoading(false);
    });
  return () => { cancelled = true; };
}, [statuses.join(','), sortBy, sortOrder, page, workflowFilter]);
```

Add filter handlers:

```tsx
const handleStatusToggle = useCallback((status: string) => {
  setSearchParams((prev) => {
    const current = prev.get('status')?.split(',').filter(Boolean) ?? [];
    const next = current.includes(status)
      ? current.filter((s) => s !== status)
      : [...current, status];
    const params = new URLSearchParams(prev);
    if (next.length > 0) params.set('status', next.join(','));
    else params.delete('status');
    params.delete('page');
    return params;
  });
}, [setSearchParams]);

const handleSortChange = useCallback((sort: 'started_at' | 'duration', order: 'asc' | 'desc') => {
  setSearchParams((prev) => {
    const params = new URLSearchParams(prev);
    params.set('sort', sort);
    params.set('order', order);
    params.delete('page');
    return params;
  });
}, [setSearchParams]);
```

Render the filter bar above the runs table:

```tsx
<RunFilterBar
  statuses={statuses}
  onStatusToggle={handleStatusToggle}
  sortBy={sortBy}
  sortOrder={sortOrder}
  onSortChange={handleSortChange}
/>
```

Add pagination controls at the bottom:

```tsx
{runData && runData.total > LIMIT && (
  <div className="flex items-center justify-between">
    <span className="text-xs text-wr-text-muted">
      {runData.offset + 1}–{Math.min(runData.offset + LIMIT, runData.total)} of {runData.total}
    </span>
    <div className="flex gap-2">
      <button
        disabled={page === 0}
        onClick={() => setSearchParams((p) => {
          const params = new URLSearchParams(p);
          params.set('page', String(page - 1));
          return params;
        })}
        className="rounded px-2 py-1 text-xs text-wr-text border border-wr-border hover:bg-wr-elevated disabled:opacity-40"
      >
        Previous
      </button>
      <button
        disabled={runData.offset + LIMIT >= runData.total}
        onClick={() => setSearchParams((p) => {
          const params = new URLSearchParams(p);
          params.set('page', String(page + 1));
          return params;
        })}
        className="rounded px-2 py-1 text-xs text-wr-text border border-wr-border hover:bg-wr-elevated disabled:opacity-40"
      >
        Next
      </button>
    </div>
  </div>
)}
```

Remove the localStorage-based `getRecentRuns`, `addRecentRun`, `updateRunStatus` imports and the footer note about "browser only".

**Step 2: Run existing WorkflowRunsPage tests**

Run: `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/WorkflowRunsPage.test.tsx`
Expected: Some tests will need updates for new DOM structure. Adjust MSW handlers to mock `GET /api/v4/runs`.

**Step 3: Commit**

```bash
git add frontend/src/components/Workflows/Runs/WorkflowRunsPage.tsx
git commit -m "feat(phase6): WorkflowRunsPage — server-side run listing with filters + pagination"
```

---

## Task 12: RunDetailPage — Rerun Buttons

**Files:**
- Modify: `frontend/src/components/Workflows/Runs/RunDetailPage.tsx`

**Step 1: Add rerun buttons**

Add imports and state:

```tsx
import { getRerunData } from '../../../services/runs';
import { InputsForm } from './InputsForm';

const [rerunning, setRerunning] = useState(false);
const [showRerunInputs, setShowRerunInputs] = useState(false);
const [rerunData, setRerunData] = useState<{ workflow_version_id: string; inputs: Record<string, unknown> } | null>(null);
```

Add handlers:

```tsx
async function handleRerun() {
  if (!runId || rerunning) return;
  setRerunning(true);
  try {
    const data = await getRerunData(runId);
    // Create a new run with same version and inputs
    // Navigate to new run detail
    const newRun = await createRun(
      workflowId ?? '',  // needs workflowId
      { inputs: data.inputs },
    );
    navigate(`/workflows/runs/${newRun.id}`, { state: { workflowId } });
  } catch (err) {
    // show error
  } finally {
    setRerunning(false);
  }
}

async function handleRerunWithChanges() {
  if (!runId) return;
  try {
    const data = await getRerunData(runId);
    setRerunData(data);
    setShowRerunInputs(true);
  } catch {
    // silently fail
  }
}
```

Add buttons in the header after the cancel button:

```tsx
{/* Rerun buttons */}
<div className="flex items-center gap-2">
  <button
    className="px-3 py-1.5 rounded text-sm font-medium bg-wr-accent text-wr-on-accent hover:bg-wr-accent-hover disabled:opacity-40 disabled:cursor-not-allowed"
    disabled={!isTerminal || rerunning}
    onClick={handleRerun}
  >
    {rerunning ? 'Rerunning...' : 'Rerun'}
  </button>
  <button
    className="px-3 py-1.5 rounded text-sm font-medium border border-wr-border bg-wr-surface text-wr-text hover:bg-wr-elevated disabled:opacity-40 disabled:cursor-not-allowed"
    disabled={!isTerminal}
    onClick={handleRerunWithChanges}
  >
    Rerun with changes
  </button>
  <button
    className="px-3 py-1.5 rounded text-sm font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-40 disabled:cursor-not-allowed"
    disabled={isTerminal || cancelling}
    onClick={handleCancel}
  >
    {cancelling ? 'Cancelling...' : 'Cancel'}
  </button>
</div>
```

Add the rerun inputs form modal at the bottom:

```tsx
{showRerunInputs && rerunData && (
  <InputsForm
    schema={{}}
    initialValues={rerunData.inputs}
    onSubmit={async (inputs, opts) => {
      if (!workflowId) return;
      const newRun = await createRun(workflowId, { inputs, idempotency_key: opts.idempotency_key });
      setShowRerunInputs(false);
      navigate(`/workflows/runs/${newRun.id}`, { state: { workflowId } });
    }}
    onCancel={() => setShowRerunInputs(false)}
  />
)}
```

**Step 2: Run existing RunDetailPage tests**

Run: `cd frontend && npx vitest run src/components/Workflows/Runs/__tests__/RunDetailPage.test.tsx`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/Workflows/Runs/RunDetailPage.tsx
git commit -m "feat(phase6): RunDetailPage — rerun + rerun-with-changes buttons"
```

---

## Task 13: Non-Impact Verification + Full Test Suite

**Files:**
- Test: `backend/tests/test_phase6_non_impact.py`

**Step 1: Write non-impact tests**

Create `backend/tests/test_phase6_non_impact.py`:

```python
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService
from src.contracts.registry import ContractRegistry


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "workflows.db")


@pytest_asyncio.fixture
async def repo(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    return r


@pytest_asyncio.fixture
async def svc(repo):
    return WorkflowService(repo, ContractRegistry())


@pytest.mark.asyncio
async def test_existing_create_workflow_unaffected(svc):
    wf = await svc.create_workflow(name="test", description="d", created_by=None)
    assert wf["id"]
    assert wf["name"] == "test"


@pytest.mark.asyncio
async def test_existing_list_workflows_returns_active(svc):
    await svc.create_workflow(name="wf1", description=None, created_by=None)
    wfs = await svc.list_workflows()
    assert len(wfs) == 1


@pytest.mark.asyncio
async def test_existing_get_workflow_returns_active(svc):
    wf = await svc.create_workflow(name="wf", description=None, created_by=None)
    result = await svc.get_workflow(wf["id"])
    assert result is not None


@pytest.mark.asyncio
async def test_deleted_workflow_not_in_list(svc):
    wf = await svc.create_workflow(name="wf", description=None, created_by=None)
    dag = {"inputs_schema": {}, "steps": []}
    await svc.create_version(wf["id"], dag)
    await svc.delete_workflow(wf["id"])
    wfs = await svc.list_workflows()
    assert len(wfs) == 0


@pytest.mark.asyncio
async def test_deleted_workflow_get_returns_none(svc):
    wf = await svc.create_workflow(name="wf", description=None, created_by=None)
    dag = {"inputs_schema": {}, "steps": []}
    await svc.create_version(wf["id"], dag)
    await svc.delete_workflow(wf["id"])
    result = await svc.get_workflow(wf["id"])
    assert result is None


@pytest.mark.asyncio
async def test_versions_survive_workflow_delete(svc, repo):
    """Run snapshot guarantee: versions remain after workflow is soft-deleted."""
    wf = await svc.create_workflow(name="wf", description=None, created_by=None)
    dag = {"inputs_schema": {}, "steps": []}
    v = await svc.create_version(wf["id"], dag)
    await svc.delete_workflow(wf["id"])

    # Version still exists
    version = await repo.get_version(wf["id"], 1)
    assert version is not None
    assert version["dag_json"]


@pytest.mark.asyncio
async def test_runs_survive_workflow_delete(svc, repo):
    """Run snapshot guarantee: runs and step_runs remain after workflow is soft-deleted."""
    wf = await svc.create_workflow(name="wf", description=None, created_by=None)
    dag = {"inputs_schema": {}, "steps": []}
    v = await svc.create_version(wf["id"], dag)
    run_id = await repo.create_run(
        workflow_version_id=v["version_id"], inputs_json="{}", idempotency_key=None
    )
    await repo.update_run_status(run_id, "succeeded")
    await svc.delete_workflow(wf["id"])

    # Run still accessible
    run = await svc.get_run(run_id)
    assert run is not None
    assert run["run"]["status"] == "succeeded"
```

**Step 2: Run non-impact tests**

Run: `cd backend && python3 -m pytest tests/test_phase6_non_impact.py -v`
Expected: ALL PASS

**Step 3: Run full backend test suite**

Run: `cd backend && python3 -m pytest tests/ -v --ignore=tests/test_investigation_integration.py`
Expected: ALL PASS

**Step 4: Run full frontend test suite**

Run: `cd frontend && npx vitest run`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/tests/test_phase6_non_impact.py
git commit -m "test(phase6): non-impact verification — run snapshot guarantee + regression suite"
```

---

## Task Dependency Map

```
Task 1 (Migration)
  ↓
Task 2 (Repository)
  ↓
Task 3 (Service)
  ↓
Task 4 (Routes)
  ↓
Task 5 (Frontend Types + Services)
  ↓
  ├── Task 6 (ConfirmDeleteDialog)
  ├── Task 7 (RunFilterBar)
  ├── Task 8 (VersionDiff)
  ↓
Task 9 (WorkflowListPage — needs 6)
Task 10 (WorkflowBuilderPage — needs 8)
Task 11 (WorkflowRunsPage — needs 7)
Task 12 (RunDetailPage)
  ↓
Task 13 (Non-Impact Verification)
```

**Parallelizable:** Tasks 6, 7, 8 can run in parallel. Tasks 9, 10, 11, 12 can run in parallel (after their component dependencies).
