"""Task 8: workflows save-path service + REST endpoints."""

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


def test_flag_disabled_returns_404_for_all(client_disabled):
    assert client_disabled.post("/api/v4/workflows", json={"name": "x"}).status_code == 404
    assert client_disabled.get("/api/v4/workflows").status_code == 404
    assert client_disabled.get("/api/v4/workflows/abc").status_code == 404
    assert (
        client_disabled.post("/api/v4/workflows/abc/versions", json=_min_dag()).status_code
        == 404
    )


def test_create_workflow_and_list_and_get(client_enabled):
    resp = client_enabled.post(
        "/api/v4/workflows",
        json={"name": "My WF", "description": "desc", "created_by": "tester"},
    )
    assert resp.status_code == 201
    wf = resp.json()
    assert wf["name"] == "My WF"
    assert wf["description"] == "desc"
    wf_id = wf["id"]
    assert isinstance(wf_id, str) and wf_id
    assert "created_at" in wf

    lst = client_enabled.get("/api/v4/workflows")
    assert lst.status_code == 200
    body = lst.json()
    assert "workflows" in body
    assert any(w["id"] == wf_id for w in body["workflows"])

    got = client_enabled.get(f"/api/v4/workflows/{wf_id}")
    assert got.status_code == 200
    detail = got.json()
    assert detail["id"] == wf_id
    assert detail["latest_version"] is None


def test_get_unknown_workflow_returns_404(client_enabled):
    resp = client_enabled.get("/api/v4/workflows/nonexistent-id")
    assert resp.status_code == 404


def test_create_version_happy_and_increments(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    wf_id = wf["id"]

    r1 = client_enabled.post(f"/api/v4/workflows/{wf_id}/versions", json=_min_dag())
    assert r1.status_code == 201, r1.text
    v1 = r1.json()
    assert v1["version"] == 1
    assert v1["workflow_id"] == wf_id
    assert "version_id" in v1

    r2 = client_enabled.post(f"/api/v4/workflows/{wf_id}/versions", json=_min_dag())
    assert r2.status_code == 201
    assert r2.json()["version"] == 2

    # detail now reports latest version
    det = client_enabled.get(f"/api/v4/workflows/{wf_id}").json()
    assert det["latest_version"]["version"] == 2


def test_create_version_malformed_dag_returns_422(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    resp = client_enabled.post(
        f"/api/v4/workflows/{wf['id']}/versions", json={"inputs_schema": {}}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["type"] == "dag_invalid"
    assert isinstance(body["detail"]["errors"], list)


def test_create_version_unknown_agent_returns_422_compile_error(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    bad = {
        "steps": [
            {"id": "s1", "agent": "does_not_exist_agent", "agent_version": 1}
        ]
    }
    resp = client_enabled.post(f"/api/v4/workflows/{wf['id']}/versions", json=bad)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["type"] == "compile_error"
    assert "does_not_exist_agent" in body["detail"]["message"]
    assert "path" in body["detail"]


def test_get_version_roundtrips_dag_and_compiled(client_enabled):
    wf = client_enabled.post("/api/v4/workflows", json={"name": "wf"}).json()
    wf_id = wf["id"]
    dag = _min_dag()
    client_enabled.post(f"/api/v4/workflows/{wf_id}/versions", json=dag)

    resp = client_enabled.get(f"/api/v4/workflows/{wf_id}/versions/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_id"] == wf_id
    assert body["version"] == 1
    assert body["dag"]["steps"][0]["id"] == "s1"
    assert "compiled" in body
    assert body["compiled"]["topo_order"] == ["s1"]

    # Unknown version
    assert (
        client_enabled.get(f"/api/v4/workflows/{wf_id}/versions/99").status_code == 404
    )
