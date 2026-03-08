"""Tests for /api/db/* endpoints."""
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
    import src.api.db_endpoints as mod
    mod._profile_store = None
    mod._run_store = None

    from src.api.db_endpoints import db_router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(db_router)
    yield TestClient(app)
    os.unlink(path)


class TestProfileEndpoints:
    def test_create_profile(self, client):
        resp = client.post("/api/db/profiles", json={
            "name": "test-pg", "engine": "postgresql",
            "host": "localhost", "port": 5432, "database": "testdb",
            "username": "admin", "password": "secret",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-pg"
        assert "password" not in data

    def test_list_profiles(self, client):
        client.post("/api/db/profiles", json={
            "name": "a", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        resp = client.get("/api/db/profiles")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_profile(self, client):
        create = client.post("/api/db/profiles", json={
            "name": "b", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        pid = create.json()["id"]
        resp = client.get(f"/api/db/profiles/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "b"

    def test_delete_profile(self, client):
        create = client.post("/api/db/profiles", json={
            "name": "del", "engine": "postgresql", "host": "h",
            "port": 5432, "database": "d", "username": "u", "password": "p",
        })
        pid = create.json()["id"]
        resp = client.delete(f"/api/db/profiles/{pid}")
        assert resp.status_code == 200
        assert client.get(f"/api/db/profiles/{pid}").status_code == 404

    def test_get_missing_profile(self, client):
        resp = client.get("/api/db/profiles/nonexistent")
        assert resp.status_code == 404


class TestDiagnosticEndpoints:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/db/diagnostics/history?profile_id=p1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_start_diagnostic_missing_profile(self, client):
        resp = client.post("/api/db/diagnostics/start", json={"profile_id": "nope"})
        assert resp.status_code == 404
