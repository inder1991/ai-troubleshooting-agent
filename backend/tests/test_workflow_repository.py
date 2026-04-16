from __future__ import annotations

import asyncio
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


@pytest.mark.asyncio
async def test_init_is_idempotent(db_path):
    r = WorkflowRepository(db_path)
    await r.init()
    await r.init()
    wf_id = await r.create_workflow(name="wf", description="d", created_by="u")
    assert wf_id
    await r.init()
    wf = await r.get_workflow(wf_id)
    assert wf is not None
    assert wf["name"] == "wf"


@pytest.mark.asyncio
async def test_create_and_get_workflow(repo):
    wf_id = await repo.create_workflow(
        name="my-wf", description="desc", created_by="alice"
    )
    wf = await repo.get_workflow(wf_id)
    assert wf["id"] == wf_id
    assert wf["name"] == "my-wf"
    assert wf["description"] == "desc"
    assert wf["created_by"] == "alice"
    assert wf["created_at"]


@pytest.mark.asyncio
async def test_list_workflows(repo):
    id1 = await repo.create_workflow(name="a", description=None, created_by=None)
    id2 = await repo.create_workflow(name="b", description=None, created_by=None)
    rows = await repo.list_workflows()
    ids = {r["id"] for r in rows}
    assert {id1, id2}.issubset(ids)


@pytest.mark.asyncio
async def test_version_unique_constraint(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    await repo.create_version(wf_id, 1, "{}", "{}")
    with pytest.raises(Exception):
        await repo.create_version(wf_id, 1, "{}", "{}")


@pytest.mark.asyncio
async def test_get_version_and_latest(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v1 = await repo.create_version(wf_id, 1, '{"v":1}', "{}")
    v2 = await repo.create_version(wf_id, 2, '{"v":2}', "{}")
    assert v1 != v2
    got = await repo.get_version(wf_id, 1)
    assert got["id"] == v1
    assert got["version"] == 1
    latest = await repo.get_latest_version(wf_id)
    assert latest["id"] == v2
    assert latest["version"] == 2


@pytest.mark.asyncio
async def test_run_idempotency(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id_1 = await repo.create_run(
        workflow_version_id=v_id,
        inputs_json="{}",
        idempotency_key="key-1",
    )
    run_id_2 = await repo.create_run(
        workflow_version_id=v_id,
        inputs_json="{}",
        idempotency_key="key-1",
    )
    assert run_id_1 == run_id_2
    run_id_3 = await repo.create_run(
        workflow_version_id=v_id,
        inputs_json="{}",
        idempotency_key="key-2",
    )
    assert run_id_3 != run_id_1


@pytest.mark.asyncio
async def test_get_and_update_run_status(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id = await repo.create_run(
        workflow_version_id=v_id, inputs_json="{}", idempotency_key="k"
    )
    run = await repo.get_run(run_id)
    assert run["status"] in ("pending", "queued", "created")
    await repo.update_run_status(
        run_id, "success", ended_at="2026-04-15T00:00:00+00:00"
    )
    run2 = await repo.get_run(run_id)
    assert run2["status"] == "success"
    assert run2["ended_at"] == "2026-04-15T00:00:00+00:00"


@pytest.mark.asyncio
async def test_step_run_create_update_list(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id = await repo.create_run(
        workflow_version_id=v_id, inputs_json="{}", idempotency_key="k"
    )
    sr_id = await repo.create_step_run(run_id, "node-a", attempt=1)
    await repo.update_step_run(
        sr_id,
        status="success",
        output_json='{"x":1}',
        ended_at="2026-04-15T00:00:00+00:00",
        duration_ms=42,
    )
    rows = await repo.list_step_runs(run_id)
    assert len(rows) == 1
    assert rows[0]["step_id"] == "node-a"
    assert rows[0]["status"] == "success"
    assert rows[0]["duration_ms"] == 42
    assert rows[0]["output_json"] == '{"x":1}'


@pytest.mark.asyncio
async def test_append_event_monotonic_sequence(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id = await repo.create_run(
        workflow_version_id=v_id, inputs_json="{}", idempotency_key="k"
    )
    _, s1 = await repo.append_event(run_id, type="run.started")
    _, s2 = await repo.append_event(run_id, type="node.started", node_id="a")
    _, s3 = await repo.append_event(run_id, type="node.succeeded", node_id="a")
    assert s1 == 1
    assert s2 == 2
    assert s3 == 3


@pytest.mark.asyncio
async def test_append_event_concurrent_monotonic(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id = await repo.create_run(
        workflow_version_id=v_id, inputs_json="{}", idempotency_key="k"
    )

    async def one(i):
        _, seq = await repo.append_event(
            run_id, type="tick", payload_json=json.dumps({"i": i})
        )
        return seq

    results = await asyncio.gather(*[one(i) for i in range(20)])
    assert sorted(results) == list(range(1, 21))
    assert len(set(results)) == 20


@pytest.mark.asyncio
async def test_list_events_filters_by_sequence(repo):
    wf_id = await repo.create_workflow(name="wf", description=None, created_by=None)
    v_id = await repo.create_version(wf_id, 1, "{}", "{}")
    run_id = await repo.create_run(
        workflow_version_id=v_id, inputs_json="{}", idempotency_key="k"
    )
    for i in range(5):
        await repo.append_event(run_id, type="tick", payload_json=f'{{"i":{i}}}')

    all_events = await repo.list_events(run_id)
    assert [e["sequence"] for e in all_events] == [1, 2, 3, 4, 5]

    after = await repo.list_events(run_id, after_sequence=3)
    assert [e["sequence"] for e in after] == [4, 5]

    none_after = await repo.list_events(run_id, after_sequence=5)
    assert none_after == []
