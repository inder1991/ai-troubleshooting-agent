"""Tests for /health, /health/ready, /health/live endpoints."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from starlette.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def client(tmp_path):
    """Build a TestClient pointing at a real (writable) SQLite DB."""
    db_path = str(tmp_path / "test_health.db")
    # Pre-create the DB so the health check can connect
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS _health_test (id INTEGER)")
    conn.close()

    with patch.dict(os.environ, {"DEBUGDUCK_DB_PATH": db_path}):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


@pytest.fixture
def client_bad_db():
    """Build a TestClient pointing at an invalid DB path."""
    with patch.dict(os.environ, {"DEBUGDUCK_DB_PATH": "/nonexistent/path/bad.db"}):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


# ═══════════════════════════════════════════════════════════════════
# 1. /health
# ═══════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    def test_healthy_response(self, client):
        """GET /health returns 200 with status=healthy and checks."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["checks"]["database"] == "ok"
        assert data["checks"]["event_bus"] == "ok"

    def test_unhealthy_database(self, client_bad_db):
        """GET /health returns 503 when the database is inaccessible."""
        resp = client_bad_db.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"] == "error"

    def test_health_contains_checks_dict(self, client):
        """The response includes a 'checks' dict with known keys."""
        resp = client.get("/health")
        data = resp.json()
        assert isinstance(data["checks"], dict)
        assert "database" in data["checks"]
        assert "event_bus" in data["checks"]


# ═══════════════════════════════════════════════════════════════════
# 2. /health/ready
# ═══════════════════════════════════════════════════════════════════


class TestReadinessEndpoint:
    def test_ready_when_db_accessible(self, client):
        """GET /health/ready returns 200 with ready=true."""
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    def test_not_ready_when_db_inaccessible(self, client_bad_db):
        """GET /health/ready returns 503 with ready=false when DB is down."""
        resp = client_bad_db.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False


# ═══════════════════════════════════════════════════════════════════
# 3. /health/live
# ═══════════════════════════════════════════════════════════════════


class TestLivenessEndpoint:
    def test_always_returns_alive(self, client):
        """GET /health/live always returns 200 with alive=true."""
        resp = client.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alive"] is True

    def test_liveness_independent_of_db(self, client_bad_db):
        """GET /health/live returns 200 even if the DB is inaccessible."""
        resp = client_bad_db.get("/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alive"] is True
