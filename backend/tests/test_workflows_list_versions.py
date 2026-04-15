"""Phase 3 Task 2: GET /api/v4/workflows/{workflow_id}/versions."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import config
from src.api import routes_workflows
from src.contracts.service import init_registry
from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService


def _build_app(tmp_path, monkeypatch, *, enabled: bool) -> FastAPI:
    monkeypatch.setattr(config.settings, "WORKFLOWS_ENABLED", enabled)
    contracts = init_registry()
    db_path = str(tmp_path / "wf.db")
    repo = WorkflowRepository(db_path)
    asyncio.new_event_loop().run_until_complete(repo.init())
    svc = WorkflowService(repo=repo, contracts=contracts)
    routes_workflows.set_workflow_service(svc)
    app = FastAPI()
    app.include_router(routes_workflows.router)
    return app


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


def test_flag_disabled_returns_404(client_disabled):
    resp = client_disabled.get("/api/v4/workflows/any-id/versions")
    assert resp.status_code == 404


def test_unknown_workflow_returns_404(client_enabled):
    resp = client_enabled.get("/api/v4/workflows/nonexistent-id/versions")
    assert resp.status_code == 404


def test_empty_when_no_versions(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    resp = client_enabled.get(f"/api/v4/workflows/{wf['id']}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"versions": []}


def test_returns_versions_descending(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    wf_id = wf["id"]

    # create three versions
    for _ in range(3):
        r = client_enabled.post(f"/api/v4/workflows/{wf_id}/versions", json=_min_dag())
        assert r.status_code == 201

    resp = client_enabled.get(f"/api/v4/workflows/{wf_id}/versions")
    assert resp.status_code == 200
    body = resp.json()
    assert "versions" in body
    versions = body["versions"]
    assert len(versions) == 3
    assert [v["version"] for v in versions] == [3, 2, 1]
    for v in versions:
        assert v["workflow_id"] == wf_id
        assert "version_id" in v and v["version_id"]
        assert "created_at" in v
