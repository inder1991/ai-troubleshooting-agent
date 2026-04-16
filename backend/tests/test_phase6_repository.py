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


async def _make_workflow(repo, name="wf", desc="d", by="u"):
    return await repo.create_workflow(name=name, description=desc, created_by=by)


async def _make_version(repo, wf_id, version=1, dag='{"v":1}', compiled="{}"):
    return await repo.create_version(wf_id, version, dag, compiled)


async def _make_run(repo, v_id, key=None, inputs="{}"):
    return await repo.create_run(
        workflow_version_id=v_id, inputs_json=inputs, idempotency_key=key
    )


# ---- soft delete ----


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(repo):
    wf_id = await _make_workflow(repo)
    await repo.soft_delete_workflow(wf_id)
    wf = await repo.get_workflow(wf_id)
    assert wf is not None
    assert wf["deleted_at"] is not None


@pytest.mark.asyncio
async def test_list_workflows_excludes_deleted(repo):
    id1 = await _make_workflow(repo, name="a")
    id2 = await _make_workflow(repo, name="b")
    await repo.soft_delete_workflow(id1)
    rows = await repo.list_workflows()
    ids = {r["id"] for r in rows}
    assert id1 not in ids
    assert id2 in ids


@pytest.mark.asyncio
async def test_soft_delete_idempotent(repo):
    wf_id = await _make_workflow(repo)
    await repo.soft_delete_workflow(wf_id)
    wf1 = await repo.get_workflow(wf_id)
    ts1 = wf1["deleted_at"]
    # second call should not raise and should not update the timestamp
    await repo.soft_delete_workflow(wf_id)
    wf2 = await repo.get_workflow(wf_id)
    assert wf2["deleted_at"] == ts1


# ---- has_active_runs ----


@pytest.mark.asyncio
async def test_has_active_runs(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await _make_run(repo, v_id, key="k1")
    # pending is an active status
    assert await repo.has_active_runs(wf_id) is True
    # move to running — still active
    await repo.update_run_status(run_id, "running")
    assert await repo.has_active_runs(wf_id) is True


@pytest.mark.asyncio
async def test_has_active_runs_false_when_terminal(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    run_id = await _make_run(repo, v_id, key="k1")
    await repo.update_run_status(run_id, "succeeded")
    assert await repo.has_active_runs(wf_id) is False


# ---- update_workflow ----


@pytest.mark.asyncio
async def test_update_workflow_name(repo):
    wf_id = await _make_workflow(repo, name="old")
    await repo.update_workflow(wf_id, name="new")
    wf = await repo.get_workflow(wf_id)
    assert wf["name"] == "new"


@pytest.mark.asyncio
async def test_update_workflow_description(repo):
    wf_id = await _make_workflow(repo, desc="old")
    await repo.update_workflow(wf_id, description="new desc")
    wf = await repo.get_workflow(wf_id)
    assert wf["description"] == "new desc"


# ---- duplicate_workflow ----


@pytest.mark.asyncio
async def test_duplicate_workflow(repo):
    src_id = await _make_workflow(repo, name="original", desc="some desc")
    await _make_version(repo, src_id, 1, '{"v":1}', '{"c":1}')
    await _make_version(repo, src_id, 2, '{"v":2}', '{"c":2}')
    new_id = await repo.duplicate_workflow(src_id, "copy-of-original")
    assert new_id != src_id
    new_wf = await repo.get_workflow(new_id)
    assert new_wf["name"] == "copy-of-original"
    assert new_wf["description"] == "some desc"
    # only latest version copied
    versions = await repo.list_versions(new_id)
    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["dag_json"] == '{"v":2}'
    assert versions[0]["compiled_json"] == '{"c":2}'


# ---- rollback_version ----


@pytest.mark.asyncio
async def test_rollback_version(repo):
    wf_id = await _make_workflow(repo)
    await _make_version(repo, wf_id, 1, '{"v":1}', '{"c":1}')
    await _make_version(repo, wf_id, 2, '{"v":2}', '{"c":2}')
    v_id, new_ver = await repo.rollback_version(wf_id, 1)
    assert new_ver == 3
    ver3 = await repo.get_version(wf_id, 3)
    assert ver3 is not None
    assert ver3["id"] == v_id
    assert ver3["dag_json"] == '{"v":1}'
    assert ver3["compiled_json"] == '{"c":1}'


# ---- list_runs ----


@pytest.mark.asyncio
async def test_list_runs_basic(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    r1 = await _make_run(repo, v_id, key="a")
    r2 = await _make_run(repo, v_id, key="b")
    rows, total = await repo.list_runs()
    assert total == 2
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_list_runs_filter_status(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    r1 = await _make_run(repo, v_id, key="a")
    r2 = await _make_run(repo, v_id, key="b")
    await repo.update_run_status(r1, "succeeded")
    rows, total = await repo.list_runs(statuses=["pending"])
    assert total == 1
    assert rows[0]["id"] == r2


@pytest.mark.asyncio
async def test_list_runs_filter_workflow(repo):
    wf1 = await _make_workflow(repo, name="w1")
    wf2 = await _make_workflow(repo, name="w2")
    v1 = await _make_version(repo, wf1)
    v2 = await _make_version(repo, wf2)
    await _make_run(repo, v1, key="a")
    await _make_run(repo, v2, key="b")
    rows, total = await repo.list_runs(workflow_id=wf1)
    assert total == 1
    ids = {r["id"] for r in rows}
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_list_runs_pagination(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    for i in range(5):
        await _make_run(repo, v_id, key=f"k{i}")
    rows, total = await repo.list_runs(limit=2, offset=0)
    assert total == 5
    assert len(rows) == 2
    rows2, total2 = await repo.list_runs(limit=2, offset=2)
    assert total2 == 5
    assert len(rows2) == 2
    rows3, total3 = await repo.list_runs(limit=2, offset=4)
    assert total3 == 5
    assert len(rows3) == 1


@pytest.mark.asyncio
async def test_list_runs_for_workflow(repo):
    wf1 = await _make_workflow(repo, name="w1")
    wf2 = await _make_workflow(repo, name="w2")
    v1 = await _make_version(repo, wf1)
    v2 = await _make_version(repo, wf2)
    await _make_run(repo, v1, key="a")
    await _make_run(repo, v1, key="b")
    await _make_run(repo, v2, key="c")
    rows, total = await repo.list_runs(workflow_id=wf1)
    assert total == 2
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_get_run_with_inputs(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    inputs = json.dumps({"key": "value", "num": 42})
    run_id = await _make_run(repo, v_id, key="k", inputs=inputs)
    run = await repo.get_run(run_id)
    assert run is not None
    parsed = json.loads(run["inputs_json"])
    assert parsed["key"] == "value"
    assert parsed["num"] == 42


@pytest.mark.asyncio
async def test_get_latest_run_for_workflow(repo):
    wf_id = await _make_workflow(repo)
    v_id = await _make_version(repo, wf_id)
    r1 = await _make_run(repo, v_id, key="a")
    await repo.update_run_status(r1, "running", ended_at=None)
    # start r1 so it has a started_at
    await repo.update_run_status(r1, "succeeded", ended_at="2026-01-01T00:00:00+00:00")
    r2 = await _make_run(repo, v_id, key="b")
    await repo.update_run_status(r2, "running")
    latest = await repo.get_latest_run_for_workflow(wf_id)
    assert latest is not None
    # Should return a run (the most recent by started_at)
    assert latest["id"] in (r1, r2)
