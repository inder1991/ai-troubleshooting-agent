"""Tests for /api/db/monitor, /api/db/alerts, /api/db/schema endpoints."""
import pytest
from fastapi.testclient import TestClient
import tempfile
import os


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DB_DIAGNOSTICS_DB_PATH"] = path

    import src.api.db_endpoints as mod
    mod._profile_store = None
    mod._run_store = None
    mod._db_monitor = None
    mod._metrics_store = None
    mod._alert_engine = None
    mod._db_adapter_registry = None
    mod._remediation_engine = None

    from src.api.db_endpoints import db_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(db_router)
    yield TestClient(app)
    os.unlink(path)


class TestMonitorEndpoints:
    def test_monitor_status(self, client):
        resp = client.get("/api/db/monitor/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data

    def test_monitor_metrics_no_influx(self, client):
        resp = client.get("/api/db/monitor/metrics/fake-profile/cache_hit_ratio?duration=1h&resolution=1m")
        assert resp.status_code == 200
        assert resp.json() == []


class TestAlertEndpoints:
    def test_list_alert_rules(self, client):
        resp = client.get("/api/db/alerts/rules")
        assert resp.status_code == 200
        rules = resp.json()
        assert isinstance(rules, list)
        assert len(rules) >= 5

    def test_active_alerts_empty(self, client):
        resp = client.get("/api/db/alerts/active")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSchemaEndpoints:
    def test_schema_missing_profile(self, client):
        resp = client.get("/api/db/schema/nonexistent")
        assert resp.status_code == 404

    def test_table_detail_missing_profile(self, client):
        resp = client.get("/api/db/schema/nonexistent/table/orders")
        assert resp.status_code == 404
