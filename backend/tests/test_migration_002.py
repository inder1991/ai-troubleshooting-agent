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
