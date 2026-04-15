"""Task 17: SSE events endpoint with Last-Event-ID resume."""

from __future__ import annotations

import asyncio
import json
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
    async def run(self, inputs, *, context):
        await asyncio.sleep(0)
        return {"summary": "ok", "errors": []}


def _build_app(tmp_path, monkeypatch, *, enabled: bool):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", enabled)
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(repo.init())
    runners = AgentRunnerRegistry()
    runners.register("log_agent", 1, _StubLogRunner())
    svc = WorkflowService(repo=repo, contracts=contracts, runners=runners)
    routes_workflows.set_workflow_service(svc)
    app = FastAPI()
    app.include_router(routes_workflows.router)
    return app


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    # sse-starlette stashes an anyio.Event at module scope the first time it's
    # used; that Event is bound to whichever event loop touched it first, so
    # subsequent tests with fresh loops hit "bound to a different event loop".
    from sse_starlette import sse as _sse

    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False
    yield
    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False


@pytest.fixture
def client_enabled(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_disabled(tmp_path, monkeypatch):
    app = _build_app(tmp_path, monkeypatch, enabled=False)
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


def _create_and_run(client: TestClient) -> str:
    wf = client.post("/api/v4/workflows", json={"name": "wf"}).json()
    client.post(f"/api/v4/workflows/{wf['id']}/versions", json=_min_dag())
    r = client.post(
        f"/api/v4/workflows/{wf['id']}/runs",
        json={"inputs": {"service_name": "svc-a"}},
    )
    return r.json()["run"]["id"]


def _wait_terminal(client: TestClient, run_id: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v4/runs/{run_id}").json()
        if body["run"]["status"] in ("succeeded", "failed", "cancelled"):
            return
        time.sleep(0.02)
    raise AssertionError("timeout waiting for terminal")


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE response body into a list of {id,event,data} dicts."""
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line == "":
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):  # comment / keep-alive
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            if v.startswith(" "):
                v = v[1:]
            current[k.strip()] = current.get(k.strip(), "") + v
    if current:
        events.append(current)
    return events


def test_flag_disabled_events_returns_404(client_disabled):
    r = client_disabled.get("/api/v4/runs/nope/events")
    assert r.status_code == 404


def test_unknown_run_events_returns_404(client_enabled):
    r = client_enabled.get("/api/v4/runs/does-not-exist/events")
    assert r.status_code == 404


def test_replay_after_completion(client_enabled):
    run_id = _create_and_run(client_enabled)
    _wait_terminal(client_enabled, run_id)

    with client_enabled.stream("GET", f"/api/v4/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        body = resp.read().decode()
    events = _parse_sse(body)
    types = [e.get("event") for e in events]
    assert "run.started" in types
    # Exactly one terminal event.
    terminals = [t for t in types if t in ("run.completed", "run.failed", "run.cancelled")]
    assert len(terminals) == 1
    assert terminals[0] == "run.completed"
    # Sequence ids are strictly increasing ints.
    ids = [int(e["id"]) for e in events if e.get("id")]
    assert ids == sorted(ids)
    assert ids[0] >= 1


def test_last_event_id_resume_skips_events(client_enabled):
    run_id = _create_and_run(client_enabled)
    _wait_terminal(client_enabled, run_id)

    # Full stream first
    with client_enabled.stream("GET", f"/api/v4/runs/{run_id}/events") as resp:
        full = _parse_sse(resp.read().decode())
    assert len(full) >= 4

    skip_seq = int(full[2]["id"])
    with client_enabled.stream(
        "GET",
        f"/api/v4/runs/{run_id}/events",
        headers={"Last-Event-ID": str(skip_seq)},
    ) as resp:
        partial = _parse_sse(resp.read().decode())
    partial_ids = [int(e["id"]) for e in partial]
    assert all(i > skip_seq for i in partial_ids)
    assert len(partial) == len(full) - 3


def test_live_mode_stream_closes_on_terminal(client_enabled, monkeypatch):
    # Use a runner that gates on an event so we can open SSE mid-flight.
    gate = asyncio.Event()

    class _GatedRunner:
        async def run(self, inputs, *, context):
            # yield control; we don't actually block here since TestClient
            # runs the executor in the same loop. A small sleep is enough
            # to ensure SSE opens while run is still PENDING/RUNNING.
            await asyncio.sleep(0.05)
            return {"summary": "done", "errors": []}

    # Rebuild service with gated runner.
    svc = routes_workflows.get_workflow_service()
    svc._runners.register("log_agent", 1, _GatedRunner())  # type: ignore[attr-defined]

    run_id = _create_and_run(client_enabled)

    with client_enabled.stream("GET", f"/api/v4/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        body = resp.read().decode()
    events = _parse_sse(body)
    types = [e.get("event") for e in events]
    assert types[-1] in ("run.completed", "run.failed", "run.cancelled")
