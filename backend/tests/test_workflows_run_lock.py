"""Task 1.6 wiring test — WorkflowService + RunLock integration via HTTP.

Covers:
- Happy path: run completes, lock key is absent afterward (released in driver
  finally).
- 409 path: when another replica already owns the run_id's lock key, the API
  caller sees 409 ``run_locked`` and the just-created run is marked failed so
  no ghost rows leak.

Uses a live Redis (skipped when unreachable) — same pattern as
``test_outbox_relay.py``.
"""
from __future__ import annotations

import asyncio
import os
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    import redis.asyncio as aredis
    import redis as _redis_sync
    _REDIS_IMPORT_OK = True
except Exception:  # pragma: no cover
    _REDIS_IMPORT_OK = False

from src import config
from src.api import routes_workflows
from src.contracts.service import init_registry
from src.workflows.repository import WorkflowRepository
from src.workflows.runners import AgentRunnerRegistry
from src.workflows.service import WorkflowService


def _redis_reachable() -> bool:
    if not _REDIS_IMPORT_OK:
        return False
    try:
        c = _redis_sync.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            socket_connect_timeout=1,
        )
        c.ping()
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis unreachable; run-lock wiring tests require live Redis",
)


class _StubLogRunner:
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


def _build_app(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", True)
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(repo.init())
    runners = _build_runners()
    redis_client = aredis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
    )
    svc = WorkflowService(
        repo=repo,
        contracts=contracts,
        runners=runners,
        redis_client=redis_client,
        lock_ttl_s=5,
        lock_heartbeat_s=1.0,
    )
    routes_workflows.set_workflow_service(svc)
    app = FastAPI()
    app.include_router(routes_workflows.router)
    return app, svc, redis_client


@pytest.fixture
def app_svc_redis(tmp_path, monkeypatch):
    app, svc, redis_client = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as c:
        c.svc = svc  # type: ignore[attr-defined]
        c.redis = redis_client  # type: ignore[attr-defined]
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
    wf = client.post("/api/v4/workflows", json={"name": f"wf-{uuid4().hex}"}).json()
    wf_id = wf["id"]
    r = client.post(f"/api/v4/workflows/{wf_id}/versions", json=_min_dag())
    assert r.status_code == 201, r.text
    return wf_id


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    body = None
    while time.monotonic() < deadline:
        r = client.get(f"/api/v4/runs/{run_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["run"]["status"] in ("success", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"run did not reach terminal: {body}")


def _sync_redis() -> "_redis_sync.Redis":
    return _redis_sync.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
    )


def test_happy_path_releases_lock_after_run(app_svc_redis):
    client = app_svc_redis
    wf_id = _create_wf_and_version(client)
    r = client.post(
        f"/api/v4/workflows/{wf_id}/runs",
        json={"inputs": {"service_name": "svc-a"}},
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run"]["id"]
    final = _wait_for_terminal(client, run_id)
    assert final["run"]["status"] == "success"

    # Lock key is gone after the driver finishes (use a sync redis client so
    # we don't cross event loops with TestClient's anyio portal).
    sync_r = _sync_redis()
    try:
        val = sync_r.get(f"investigation:{run_id}:lock")
        assert val is None, f"lock key still present after run terminal: {val!r}"
    finally:
        sync_r.close()


def test_conflicting_lock_returns_409_and_marks_run_failed(app_svc_redis):
    """Simulate a peer replica owning the lock: monkey-patch repo.create_run
    to return a deterministic run_id, pre-plant the lock key, then POST.
    API must return 409; the run row must end up 'failed'."""
    client = app_svc_redis
    svc = client.svc  # type: ignore[attr-defined]
    redis_client = client.redis  # type: ignore[attr-defined]
    wf_id = _create_wf_and_version(client)

    forced_run_id = f"locked-{uuid4().hex}"

    # Pre-plant the lock as though another replica owned it (sync client so
    # we don't cross event loops with TestClient's anyio portal).
    sync_r = _sync_redis()
    try:
        ok = sync_r.set(
            f"investigation:{forced_run_id}:lock",
            "peer-replica-token",
            ex=10,
            nx=True,
        )
        assert ok
    finally:
        sync_r.close()

    # Force svc.create_run to reuse our chosen run_id.
    orig_create = svc._repo.create_run

    async def _patched_create_run(*args, **kwargs):
        real_id = await orig_create(*args, **kwargs)
        # Rename the row so the lock key collision fires.
        import aiosqlite  # type: ignore
        async with aiosqlite.connect(svc._repo._db_path) as db:
            await db.execute(
                "UPDATE workflow_runs SET id = ? WHERE id = ?",
                (forced_run_id, real_id),
            )
            await db.commit()
        return forced_run_id

    svc._repo.create_run = _patched_create_run  # type: ignore[assignment]
    try:
        r = client.post(
            f"/api/v4/workflows/{wf_id}/runs",
            json={"inputs": {"service_name": "svc-a"}},
        )
        assert r.status_code == 409, r.text
        body = r.json()
        assert body["detail"]["type"] == "run_locked"
    finally:
        svc._repo.create_run = orig_create  # type: ignore[assignment]

    # Run row is marked failed with a RunLocked error.
    fetch = client.get(f"/api/v4/runs/{forced_run_id}")
    assert fetch.status_code == 200
    row = fetch.json()
    assert row["run"]["status"] == "failed"
    assert row["run"]["error"]["type"] == "RunLocked"

    # Cleanup the planted lock.
    sync_r = _sync_redis()
    try:
        sync_r.delete(f"investigation:{forced_run_id}:lock")
    finally:
        sync_r.close()
