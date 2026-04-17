"""Phase 2 end-to-end smoke test (Task 21).

Boots the *real* FastAPI app with ``WORKFLOWS_ENABLED=true`` and
``CATALOG_UI_ENABLED=true`` so the startup hook wires the workflow
subsystem end-to-end. Then exercises the full happy path:

  create workflow -> create version (2-step DAG) -> create run
  -> SSE stream -> get run (terminal SUCCESS) -> idempotent re-POST.

The ``log_agent`` runner is swapped for a deterministic stub after
startup so the test has zero LLM / network / log-backend coupling.
"""

from __future__ import annotations

import asyncio
import json
import time
from importlib import reload
from typing import Any

import pytest
from fastapi.testclient import TestClient


class _StubLogRunner:
    """Deterministic log_agent stub.

    Returns a fixed ``root_cause_hypothesis`` so step B's ``when``
    predicate (eq against a literal) evaluates to true.
    """

    async def run(self, inputs: dict, *, context: dict) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {
            "root_cause_hypothesis": "oom",
            "overall_confidence": 0.9,
            "patterns_found": 1,
            "raw_logs_count": 42,
        }


@pytest.fixture(autouse=True)
def _reset_sse_app_status():
    # sse-starlette stashes a module-scoped anyio.Event the first time it
    # serves a stream; that Event is bound to the loop that touched it,
    # which breaks subsequent tests that spin up a fresh loop. Reset it.
    from sse_starlette import sse as _sse

    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False
    yield
    _sse.AppStatus.should_exit_event = None
    _sse.AppStatus.should_exit = False


@pytest.fixture
def real_app_client(monkeypatch, tmp_path):
    """Boot src.api.main with workflows + catalog UI enabled, hermetic DB."""
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true")
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true")
    monkeypatch.setenv("WORKFLOWS_DB_PATH", str(tmp_path / "wf.db"))

    from src import config
    reload(config)
    from src.api import routes_workflows
    reload(routes_workflows)
    from src.api import main as app_main
    reload(app_main)

    with TestClient(app_main.app) as client:
        # Swap log_agent runner for the deterministic stub so the test
        # never touches Elasticsearch / the LLM.
        svc = routes_workflows.get_workflow_service()
        svc._runners.register("log_agent", 1, _StubLogRunner())  # type: ignore[attr-defined]
        yield client


def _two_step_dag() -> dict:
    """Two log_agent steps; B depends on A via a `when` predicate that
    references A's ``root_cause_hypothesis`` output, plus an input ref."""
    return {
        "inputs_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string"}},
            "required": ["service_name"],
        },
        "steps": [
            {
                "id": "a",
                "agent": "log_agent",
                "agent_version": 1,
                "inputs": {
                    "service_name": {
                        "ref": {"from": "input", "path": "service_name"}
                    }
                },
            },
            {
                "id": "b",
                "agent": "log_agent",
                "agent_version": 1,
                "when": {
                    "op": "eq",
                    "args": [
                        {"ref": {"from": "node", "node_id": "a", "path": "output.root_cause_hypothesis"}},
                        {"literal": "oom"},
                    ],
                },
                "inputs": {
                    "service_name": {
                        "ref": {"from": "input", "path": "service_name"}
                    }
                },
            },
        ],
    }


def _wait_terminal(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        r = client.get(f"/api/v4/runs/{run_id}")
        assert r.status_code == 200, r.text
        last = r.json()
        if last["run"]["status"] in ("success", "failed", "cancelled"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"run did not reach terminal in {timeout}s: {last}")


def _parse_sse(text: str) -> list[dict[str, str]]:
    """Parse an SSE response body into a list of {id,event,data} dicts."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line == "":
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith(":"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            if v.startswith(" "):
                v = v[1:]
            current[k.strip()] = current.get(k.strip(), "") + v
    if current:
        events.append(current)
    return events


def test_phase2_end_to_end_smoke(real_app_client):
    client = real_app_client

    # 1. Create workflow.
    r = client.post("/api/v4/workflows", json={"name": "e2e-wf"})
    assert r.status_code == 201, r.text
    wf_id = r.json()["id"]

    # 2. Create version with 2-step DAG.
    r = client.post(
        f"/api/v4/workflows/{wf_id}/versions", json=_two_step_dag()
    )
    assert r.status_code == 201, r.text

    # 3. Create a run.
    body = {"inputs": {"service_name": "checkout"}, "idempotency_key": "e2e-key"}
    r = client.post(f"/api/v4/workflows/{wf_id}/runs", json=body)
    assert r.status_code == 201, r.text
    run_id = r.json()["run"]["id"]

    # 4. Wait for terminal state via polling.
    final = _wait_terminal(client, run_id)
    assert final["run"]["status"] == "success", final
    step_runs = {sr["step_id"]: sr for sr in final["step_runs"]}
    assert set(step_runs) == {"a", "b"}, step_runs
    assert step_runs["a"]["status"] == "success"
    assert step_runs["b"]["status"] == "success"

    # 5. Fetch SSE stream (post-terminal replay).
    with client.stream("GET", f"/api/v4/runs/{run_id}/events") as resp:
        assert resp.status_code == 200
        sse_body = resp.read().decode()
    events = _parse_sse(sse_body)
    types = [e.get("event") for e in events]

    # Sanity: required event kinds in order.
    assert "run.started" in types
    assert types.count("step.started") >= 2
    assert types.count("step.completed") >= 2
    assert types[-1] == "run.completed"

    # run.started precedes step.started precedes step.completed precedes run.completed.
    idx_run_started = types.index("run.started")
    idx_step_started = types.index("step.started")
    idx_step_completed = types.index("step.completed")
    idx_run_completed = types.index("run.completed")
    assert idx_run_started < idx_step_started < idx_step_completed < idx_run_completed

    # Monotonic strictly-increasing sequence ids.
    seq_ids = [int(e["id"]) for e in events if e.get("id")]
    assert seq_ids, "expected at least one numbered event"
    assert seq_ids == sorted(seq_ids)
    assert len(seq_ids) == len(set(seq_ids)), "duplicate sequence ids"

    # Each step.completed payload carries a node_id matching one of our steps.
    completed_nodes = set()
    for e in events:
        if e.get("event") == "step.completed":
            payload = json.loads(e["data"])
            node_id = payload.get("node_id") or payload.get("step_id")
            if node_id:
                completed_nodes.add(node_id)
    assert {"a", "b"}.issubset(completed_nodes), completed_nodes

    # 6. Idempotent replay — same idempotency_key returns the same run_id,
    # no new executor task is scheduled.
    r2 = client.post(f"/api/v4/workflows/{wf_id}/runs", json=body)
    assert r2.status_code == 201, r2.text
    assert r2.json()["run"]["id"] == run_id
