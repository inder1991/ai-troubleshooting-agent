"""Phase 6 routes — DELETE, PATCH, duplicate, rollback, list runs, rerun."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src import config
from src.api.routes_workflows import router, set_workflow_service
from src.contracts.registry import ContractRegistry
from src.contracts.service import init_registry
from src.workflows.repository import WorkflowRepository
from src.workflows.runners.registry import AgentRunnerRegistry
from src.workflows.service import WorkflowService


class _StubRunner:
    async def run(self, inputs, *, context):
        await asyncio.sleep(0)
        return {"summary": "stub", "errors": []}


def _build_runners() -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    reg.register("log_agent", 1, _StubRunner())
    return reg


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", True)


@pytest_asyncio.fixture
async def client(tmp_path):
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    await repo.init()
    runners = _build_runners()
    svc = WorkflowService(repo=repo, contracts=contracts, runners=runners)
    set_workflow_service(svc)
    app = FastAPI()
    app.include_router(router)
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


# ---- DELETE ----

@pytest.mark.asyncio
async def test_delete_workflow(client):
    wf = await _create_wf(client)
    resp = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_not_found(client):
    resp = await client.delete("/api/v4/workflows/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_idempotent(client):
    wf = await _create_wf(client)
    resp1 = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp1.status_code == 204
    resp2 = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp2.status_code == 204


# ---- PATCH ----

@pytest.mark.asyncio
async def test_patch_rename(client):
    wf = await _create_wf(client, name="orig")
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


# ---- DUPLICATE ----

@pytest.mark.asyncio
async def test_duplicate(client):
    wf = await _create_wf(client, name="orig")
    await _create_version(client, wf["id"])  # need at least one version
    resp = await client.post(f"/api/v4/workflows/{wf['id']}/duplicate")
    assert resp.status_code == 201
    assert resp.json()["name"] == "orig (copy)"


# ---- ROLLBACK ----

@pytest.mark.asyncio
async def test_rollback(client):
    wf = await _create_wf(client)
    await _create_version(client, wf["id"])  # v1
    await _create_version(client, wf["id"])  # v2
    resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/versions/1/rollback"
    )
    assert resp.status_code == 201
    assert resp.json()["version"] == 3


@pytest.mark.asyncio
async def test_rollback_not_found(client):
    resp = await client.post(
        "/api/v4/workflows/nonexistent/versions/1/rollback"
    )
    assert resp.status_code == 404


# ---- LIST RUNS ----

@pytest.mark.asyncio
async def test_list_runs(client):
    resp = await client.get("/api/v4/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


@pytest.mark.asyncio
async def test_list_runs_status_filter(client):
    resp = await client.get("/api/v4/runs", params={"status": "success"})
    assert resp.status_code == 200
    assert "runs" in resp.json()


# ---- WORKFLOW RUNS ----

@pytest.mark.asyncio
async def test_workflow_runs(client):
    wf = await _create_wf(client)
    resp = await client.get(f"/api/v4/workflows/{wf['id']}/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert "total" in data


# ---- RERUN ----

@pytest.mark.asyncio
async def test_rerun(client):
    wf = await _create_wf(client)
    ver = await _create_version(client, wf["id"])
    # Create a run first
    run_resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/runs",
        json={"inputs": {}},
    )
    assert run_resp.status_code == 201, run_resp.text
    run_id = run_resp.json()["run"]["id"]
    # Wait briefly for run to be persisted
    await asyncio.sleep(0.2)
    resp = await client.post(f"/api/v4/runs/{run_id}/rerun")
    assert resp.status_code == 201
    data = resp.json()
    assert "run_id" in data
    assert "workflow_version_id" in data
    assert "inputs" in data


# ---- DELETE 409 CONFLICT (active runs) ----

@pytest.mark.asyncio
async def test_delete_workflow_409_active_runs(client):
    wf = await _create_wf(client)
    ver = await _create_version(client, wf["id"])
    # Create a run (will go through executor quickly with stub runner)
    run_resp = await client.post(
        f"/api/v4/workflows/{wf['id']}/runs",
        json={"inputs": {}},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["run"]["id"]
    # Directly set status to 'running' in the DB via the service's repo
    from src.api.routes_workflows import _service
    async with _service._repo._conn() as db:
        await db.execute(
            "UPDATE workflow_runs SET status = 'running' WHERE id = ?",
            (run_id,),
        )
        await db.commit()
    # Attempt to delete should return 409
    resp = await client.delete(f"/api/v4/workflows/{wf['id']}")
    assert resp.status_code == 409
    assert resp.json()["detail"]["type"] == "active_runs"


# ---- LIST RUNS VALIDATION ----

@pytest.mark.asyncio
async def test_list_runs_invalid_status(client):
    resp = await client.get("/api/v4/runs", params={"status": "bogus"})
    assert resp.status_code == 400
    assert "invalid status values" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_runs_invalid_sort(client):
    resp = await client.get("/api/v4/runs", params={"sort": "nope"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_invalid_limit(client):
    resp = await client.get("/api/v4/runs", params={"limit": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_limit_over_max(client):
    resp = await client.get("/api/v4/runs", params={"limit": 201})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_negative_offset(client):
    resp = await client.get("/api/v4/runs", params={"offset": -1})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_runs_mixed_valid_invalid_status(client):
    resp = await client.get("/api/v4/runs", params={"status": "running,bogus"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_runs_valid_statuses(client):
    resp = await client.get("/api/v4/runs", params={"status": "running,failed"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_runs_invalid_order(client):
    resp = await client.get("/api/v4/runs", params={"order": "sideways"})
    assert resp.status_code == 422
