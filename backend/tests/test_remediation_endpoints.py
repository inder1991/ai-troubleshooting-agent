"""Tests for remediation API endpoints."""
import pytest
from fastapi.testclient import TestClient
import tempfile
import os


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DB_DIAGNOSTICS_DB_PATH"] = path

    # Reset singletons
    import src.api.db_endpoints as db_ep
    db_ep._profile_store = None
    db_ep._run_store = None
    db_ep._db_monitor = None
    db_ep._metrics_store = None
    db_ep._alert_engine = None
    db_ep._db_adapter_registry = None
    db_ep._remediation_engine = None

    from src.api.db_endpoints import db_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(db_router)
    yield TestClient(app)
    os.unlink(path)


class TestRemediationEndpoints:
    def test_list_plans_empty(self, client):
        resp = client.get("/api/db/remediation/plans?profile_id=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_plan(self, client):
        resp = client.post("/api/db/remediation/plan", json={
            "profile_id": "prof-1", "action": "vacuum",
            "params": {"table": "orders"},
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert "VACUUM" in resp.json()["sql_preview"]

    def test_get_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.get(f"/api/db/remediation/plans/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["plan_id"] == plan_id

    def test_approve_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.post(f"/api/db/remediation/approve/{plan_id}")
        assert resp.status_code == 200
        assert "approval_token" in resp.json()

    def test_reject_plan(self, client):
        create = client.post("/api/db/remediation/plan", json={
            "profile_id": "p1", "action": "vacuum", "params": {"table": "t"},
        })
        plan_id = create.json()["plan_id"]
        resp = client.post(f"/api/db/remediation/reject/{plan_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_audit_log_empty(self, client):
        resp = client.get("/api/db/remediation/log?profile_id=nonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_config_recommendations_missing_profile(self, client):
        resp = client.get("/api/db/config/nonexistent/recommendations")
        assert resp.status_code == 404
