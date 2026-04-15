"""Task 18: cooperative run cancellation endpoint."""

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


class _BlockingRunner:
    """Runner that waits on is_cancelled cooperatively and returns CANCELLED
    status shape on cancel. It polls the provided ``is_cancelled`` callback
    from context."""

    async def run(self, inputs, *, context):
        is_cancelled = context.get("is_cancelled")
        for _ in range(200):
            await asyncio.sleep(0.02)
            if is_cancelled and is_cancelled():
                # Raising here is the cooperative exit; executor will treat as
                # failure inside the grace window and the run-level CANCELLED
                # supersedes per-step status.
                raise asyncio.CancelledError()
        return {"summary": "finished", "errors": []}


class _FastRunner:
    async def run(self, inputs, *, context):
        await asyncio.sleep(0)
        return {"summary": "fast", "errors": []}


def _build_app(tmp_path, monkeypatch, *, enabled: bool, runner):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", enabled)
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(repo.init())
    runners = AgentRunnerRegistry()
    runners.register("log_agent", 1, runner)
    svc = WorkflowService(
        repo=repo,
        contracts=contracts,
        runners=runners,
        cancel_grace_seconds=0.2,
    )
    routes_workflows.set_workflow_service(svc)
    app = FastAPI()
    app.include_router(routes_workflows.router)
    return app


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    from sse_starlette import sse as _sse

    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False
    yield
    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False


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


def _setup_run(client: TestClient) -> str:
    wf = client.post("/api/v4/workflows", json={"name": "wf"}).json()
    client.post(f"/api/v4/workflows/{wf['id']}/versions", json=_min_dag())
    r = client.post(
        f"/api/v4/workflows/{wf['id']}/runs",
        json={"inputs": {"service_name": "svc"}},
    )
    assert r.status_code == 201, r.text
    return r.json()["run"]["id"]


def _wait_status(client: TestClient, run_id: str, wanted: set[str], timeout: float = 3.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v4/runs/{run_id}").json()
        if body["run"]["status"] in wanted:
            return body["run"]["status"]
        time.sleep(0.02)
    raise AssertionError(f"timeout; last={body}")


def test_flag_off_cancel_returns_404(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=False, runner=_FastRunner())
    with TestClient(app) as c:
        r = c.post("/api/v4/runs/whatever/cancel")
        assert r.status_code == 404


def test_cancel_unknown_run_returns_404(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=True, runner=_FastRunner())
    with TestClient(app) as c:
        r = c.post("/api/v4/runs/does-not-exist/cancel")
        assert r.status_code == 404


def test_cancel_terminal_returns_409(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=True, runner=_FastRunner())
    with TestClient(app) as c:
        run_id = _setup_run(c)
        _wait_status(c, run_id, {"succeeded", "failed"})
        r = c.post(f"/api/v4/runs/{run_id}/cancel")
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["type"] == "run_terminal"
        assert body["detail"]["status"] in ("succeeded", "failed")


def test_cancel_in_flight_transitions_to_cancelled(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=True, runner=_BlockingRunner())
    with TestClient(app) as c:
        run_id = _setup_run(c)
        # Let it enter running.
        _wait_status(c, run_id, {"running"}, timeout=2.0)

        r = c.post(f"/api/v4/runs/{run_id}/cancel")
        assert r.status_code == 202, r.text
        assert r.json()["run"]["status"] == "cancelling"

        final = _wait_status(c, run_id, {"cancelled"}, timeout=3.0)
        assert final == "cancelled"
