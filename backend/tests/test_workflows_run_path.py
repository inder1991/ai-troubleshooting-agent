"""Task 16: workflow run path — POST /runs, GET /runs/:id, idempotency."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import config
from src.api import routes_workflows
from src.contracts.service import init_registry
from src.workflows.repository import WorkflowRepository
from src.workflows.runners import AgentRunnerRegistry
from src.workflows.service import WorkflowService


class _StubLogRunner:
    """Deterministic stub log_agent runner — no LLM, no network."""

    async def run(self, inputs, *, context):
        await asyncio.sleep(0)
        return {
            "summary": f"stubbed for {inputs.get('service_name', '?')}",
            "errors": [],
        }


def _build_runners() -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    reg.register("log_agent", 1, _StubLogRunner())
    return reg


def _build_app(tmp_path, monkeypatch, *, enabled: bool):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", enabled)
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(repo.init())
    runners = _build_runners()
    svc = WorkflowService(repo=repo, contracts=contracts, runners=runners)
    routes_workflows.set_workflow_service(svc)
    app = FastAPI()
    app.include_router(routes_workflows.router)
    return app, svc


@pytest.fixture
def client_enabled(tmp_path, monkeypatch):
    app, svc = _build_app(tmp_path, monkeypatch, enabled=True)
    with TestClient(app) as c:
        c.svc = svc  # type: ignore[attr-defined]
        yield c


@pytest.fixture
def client_disabled(tmp_path, monkeypatch):
    app, _ = _build_app(tmp_path, monkeypatch, enabled=False)
    with TestClient(app) as c:
        yield c


def _min_dag() -> dict:
    return {
        "inputs_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string"}},
            "required": ["service_name"],
        },
        "steps": [
            {
                "id": "s1",
                "agent": "log_agent",
                "agent_version": 1,
                "inputs": {
                    "service_name": {
                        "ref": {"from": "input", "path": "service_name"}
                    }
                },
            }
        ],
    }


def _create_wf_and_version(client: TestClient) -> str:
    wf = client.post("/api/v4/workflows", json={"name": "wf"}).json()
    wf_id = wf["id"]
    r = client.post(f"/api/v4/workflows/{wf_id}/versions", json=_min_dag())
    assert r.status_code == 201, r.text
    return wf_id


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/v4/runs/{run_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["run"]["status"] in ("success", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"run did not reach terminal: {body}")


def test_flag_disabled_returns_404_for_run_endpoints(client_disabled):
    assert (
        client_disabled.post(
            "/api/v4/workflows/abc/runs", json={"inputs": {}}
        ).status_code
        == 404
    )
    assert client_disabled.get("/api/v4/runs/abc").status_code == 404


def test_create_run_happy_path(client_enabled):
    wf_id = _create_wf_and_version(client_enabled)
    r = client_enabled.post(
        f"/api/v4/workflows/{wf_id}/runs",
        json={"inputs": {"service_name": "svc-a"}},
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run"]["id"]

    final = _wait_for_terminal(client_enabled, run_id)
    assert final["run"]["status"] == "success"
    assert len(final["step_runs"]) == 1
    assert final["step_runs"][0]["step_id"] == "s1"
    assert final["step_runs"][0]["status"] == "success"


def test_create_run_invalid_inputs_returns_422(client_enabled):
    wf_id = _create_wf_and_version(client_enabled)
    r = client_enabled.post(
        f"/api/v4/workflows/{wf_id}/runs",
        json={"inputs": {}},  # missing required service_name
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["type"] == "inputs_invalid"


def test_idempotent_replay_returns_same_run(client_enabled):
    wf_id = _create_wf_and_version(client_enabled)
    body = {"inputs": {"service_name": "svc-a"}, "idempotency_key": "k1"}
    r1 = client_enabled.post(f"/api/v4/workflows/{wf_id}/runs", json=body)
    assert r1.status_code == 201
    rid1 = r1.json()["run"]["id"]
    # Let first finish to avoid flakiness.
    _wait_for_terminal(client_enabled, rid1)

    r2 = client_enabled.post(f"/api/v4/workflows/{wf_id}/runs", json=body)
    assert r2.status_code == 201
    rid2 = r2.json()["run"]["id"]
    assert rid1 == rid2


def test_unknown_workflow_returns_404(client_enabled):
    r = client_enabled.post(
        "/api/v4/workflows/does-not-exist/runs",
        json={"inputs": {"service_name": "x"}},
    )
    assert r.status_code == 404


def test_workflow_without_version_returns_404(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "empty"}).json()
    r = client_enabled.post(
        f"/api/v4/workflows/{wf['id']}/runs",
        json={"inputs": {"service_name": "x"}},
    )
    assert r.status_code == 404


def test_unknown_run_returns_404(client_enabled):
    r = client_enabled.get("/api/v4/runs/does-not-exist")
    assert r.status_code == 404
