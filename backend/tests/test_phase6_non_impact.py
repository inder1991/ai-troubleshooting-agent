"""Phase 6 – Non-impact verification tests.

Verify that soft-deleting a workflow does NOT cascade to its versions, runs,
or step runs, and that existing creation flows remain functional.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "workflows.db")


@pytest_asyncio.fixture
async def repo(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    return r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_workflow(repo, name="wf", desc="d", by="u"):
    return await repo.create_workflow(name=name, description=desc, created_by=by)


async def _make_version(repo, wf_id, version=1, dag='{"v":1}', compiled="{}"):
    return await repo.create_version(wf_id, version, dag, compiled)


async def _make_run(repo, v_id, key=None, inputs="{}"):
    return await repo.create_run(
        workflow_version_id=v_id, inputs_json=inputs, idempotency_key=key
    )


# ---------------------------------------------------------------------------
# 1. Soft-delete does NOT affect versions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_delete_does_not_affect_versions(repo):
    """Versions remain fully queryable after their parent workflow is soft-deleted."""
    wf_id = await _make_workflow(repo)
    v1_id = await _make_version(repo, wf_id, version=1, dag='{"v":1}')
    v2_id = await _make_version(repo, wf_id, version=2, dag='{"v":2}')

    await repo.soft_delete_workflow(wf_id)

    # list_versions still returns both versions
    versions = await repo.list_versions(wf_id)
    assert len(versions) == 2
    version_ids = {v["id"] for v in versions}
    assert v1_id in version_ids
    assert v2_id in version_ids

    # get_version still works for individual lookups
    ver1 = await repo.get_version(wf_id, 1)
    assert ver1 is not None
    assert ver1["dag_json"] == '{"v":1}'

    ver2 = await repo.get_version(wf_id, 2)
    assert ver2 is not None
    assert ver2["dag_json"] == '{"v":2}'

    # get_latest_version still works
    latest = await repo.get_latest_version(wf_id)
    assert latest is not None
    assert latest["version"] == 2


# ---------------------------------------------------------------------------
# 2. Soft-delete does NOT affect runs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soft_delete_does_not_affect_runs(repo):
    """Runs remain fully queryable after their parent workflow is soft-deleted."""
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run1_id = await _make_run(repo, v_id, key="r1")
    run2_id = await _make_run(repo, v_id, key="r2")

    # Move one run to a terminal state
    await repo.update_run_status(run1_id, "succeeded")
    await repo.update_run_status(run2_id, "succeeded")

    await repo.soft_delete_workflow(wf_id)

    # get_run still works for each run
    run1 = await repo.get_run(run1_id)
    assert run1 is not None
    assert run1["status"] == "succeeded"

    run2 = await repo.get_run(run2_id)
    assert run2 is not None

    # list_runs still returns runs when filtering by workflow_id
    rows, total = await repo.list_runs(workflow_id=wf_id)
    assert total == 2
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# 3. Full run snapshot guarantee
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_run_snapshot_guarantee(repo):
    """End-to-end: create workflow -> version -> run -> step runs -> soft-delete
    -> verify run still resolves its version and step runs still exist."""
    # Setup
    wf_id = await _make_workflow(repo, name="snapshot-wf")
    v_id = await _make_version(repo, wf_id, version=1, dag='{"steps":"a,b"}', compiled='{"c":1}')
    run_id = await _make_run(repo, v_id, key="snap", inputs='{"env":"prod"}')
    sr1_id = await repo.create_step_run(run_id, "step_a", attempt=1)
    sr2_id = await repo.create_step_run(run_id, "step_b", attempt=1)

    # Mark step runs and run as completed
    await repo.update_step_run(sr1_id, "succeeded", output_json='{"ok":true}')
    await repo.update_step_run(sr2_id, "succeeded", output_json='{"ok":true}')
    await repo.update_run_status(run_id, "succeeded")

    # Soft-delete the workflow
    await repo.soft_delete_workflow(wf_id)

    # Verify workflow IS soft-deleted
    wf = await repo.get_workflow(wf_id)
    assert wf is not None  # repo.get_workflow returns raw row including deleted
    assert wf["deleted_at"] is not None

    # Verify run still exists and is intact
    run = await repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "succeeded"
    assert run["workflow_version_id"] == v_id

    # Verify run's version still resolves
    version = await repo.get_version(wf_id, 1)
    assert version is not None
    assert version["id"] == v_id
    assert version["dag_json"] == '{"steps":"a,b"}'

    # Verify step runs still exist
    step_runs = await repo.list_step_runs(run_id)
    assert len(step_runs) == 2
    step_ids = {sr["step_id"] for sr in step_runs}
    assert step_ids == {"step_a", "step_b"}
    assert all(sr["status"] == "succeeded" for sr in step_runs)

    # Verify inputs are preserved
    parsed = json.loads(run["inputs_json"])
    assert parsed == {"env": "prod"}


# ---------------------------------------------------------------------------
# 4. Non-regression: existing creation flows still work
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_workflow_still_works(repo):
    """Basic workflow creation is unaffected by Phase 6 changes."""
    wf_id = await _make_workflow(repo, name="new-wf", desc="desc", by="admin")
    assert wf_id is not None
    wf = await repo.get_workflow(wf_id)
    assert wf["name"] == "new-wf"
    assert wf["description"] == "desc"
    assert wf["deleted_at"] is None


@pytest.mark.asyncio
async def test_create_version_still_works(repo):
    """Version creation is unaffected by Phase 6 changes."""
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id, version=1, dag='{"d":1}', compiled='{"c":1}')
    assert v_id is not None
    ver = await repo.get_version(wf_id, 1)
    assert ver is not None
    assert ver["dag_json"] == '{"d":1}'
    assert ver["compiled_json"] == '{"c":1}'


@pytest.mark.asyncio
async def test_create_run_still_works(repo):
    """Run creation is unaffected by Phase 6 changes."""
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await _make_run(repo, v_id, key="k1", inputs='{"x":1}')
    assert run_id is not None
    run = await repo.get_run(run_id)
    assert run is not None
    assert run["status"] == "pending"
    assert json.loads(run["inputs_json"]) == {"x": 1}


@pytest.mark.asyncio
async def test_create_step_run_still_works(repo):
    """Step run creation is unaffected by Phase 6 changes."""
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await _make_run(repo, v_id, key="k1")
    sr_id = await repo.create_step_run(run_id, "step_x", attempt=1)
    assert sr_id is not None
    steps = await repo.list_step_runs(run_id)
    assert len(steps) == 1
    assert steps[0]["step_id"] == "step_x"
    assert steps[0]["status"] == "running"


@pytest.mark.asyncio
async def test_list_workflows_still_returns_active(repo):
    """list_workflows returns non-deleted workflows correctly."""
    id1 = await _make_workflow(repo, name="active1")
    id2 = await _make_workflow(repo, name="active2")
    rows = await repo.list_workflows()
    ids = {r["id"] for r in rows}
    assert id1 in ids
    assert id2 in ids
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_service_get_workflow_hides_deleted(repo):
    """Service layer's get_workflow returns None for soft-deleted workflows,
    while repository layer still returns them."""
    # We only need the repo for the service; contracts/runners not needed
    # for this read-only path.
    svc = WorkflowService(repo, contracts=None, runners=None)

    wf_id = await _make_workflow(repo, name="svc-test")
    await _make_version(repo, wf_id, version=1)

    # Before deletion, service returns the workflow
    wf_via_svc = await svc.get_workflow(wf_id)
    assert wf_via_svc is not None

    # After deletion, service hides it
    await repo.soft_delete_workflow(wf_id)
    wf_via_svc = await svc.get_workflow(wf_id)
    assert wf_via_svc is None

    # But repository still returns it (with deleted_at set)
    wf_via_repo = await repo.get_workflow(wf_id)
    assert wf_via_repo is not None
    assert wf_via_repo["deleted_at"] is not None
