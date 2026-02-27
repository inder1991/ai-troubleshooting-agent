"""Tests for cluster diagnostics findings API endpoint."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Clear session stores between tests."""
    from src.api.routes_v4 import sessions, supervisors, session_locks
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()


class TestClusterFindings:
    def test_findings_404_for_unknown_session(self, client):
        """GET /findings returns 404 for unknown session."""
        resp = client.get("/api/v4/session/00000000-0000-4000-8000-000000000001/findings")
        assert resp.status_code == 404

    def test_findings_400_for_invalid_session_id(self, client):
        """GET /findings returns 400 for malformed session ID."""
        resp = client.get("/api/v4/session/not-a-uuid/findings")
        assert resp.status_code == 400

    def test_cluster_findings_pending_when_no_state(self, client):
        """Cluster session with no state yet returns PENDING."""
        from src.api.routes_v4 import sessions
        sessions["00000000-0000-4000-8000-000000000002"] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-001",
            "phase": "initial",
            "confidence": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "state": None,
            "capability": "cluster_diagnostics",
        }
        resp = client.get("/api/v4/session/00000000-0000-4000-8000-000000000002/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform_health"] == "PENDING"
        assert data["domain_reports"] == []

    def test_cluster_findings_returns_health_report(self, client):
        """Cluster session with completed state returns full health report."""
        from src.api.routes_v4 import sessions
        sessions["00000000-0000-4000-8000-000000000003"] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-002",
            "phase": "complete",
            "confidence": 75,
            "created_at": "2026-01-01T00:00:00Z",
            "capability": "cluster_diagnostics",
            "state": {
                "platform": "openshift",
                "platform_version": "4.14",
                "data_completeness": 0.75,
                "domain_reports": [
                    {"domain": "ctrl_plane", "status": "SUCCESS", "confidence": 80, "anomalies": []},
                ],
                "causal_chains": [],
                "uncorrelated_findings": [],
                "health_report": {
                    "platform_health": "DEGRADED",
                    "blast_radius": {"summary": "2 nodes affected", "affected_nodes": 2, "affected_pods": 5, "affected_namespaces": 1},
                    "remediation": {"immediate": [], "long_term": []},
                    "execution_metadata": {"re_dispatch_count": 0},
                },
            },
        }
        resp = client.get("/api/v4/session/00000000-0000-4000-8000-000000000003/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform_health"] == "DEGRADED"
        assert data["platform"] == "openshift"
        assert data["data_completeness"] == 0.75
        assert len(data["domain_reports"]) == 1
        assert data["blast_radius"]["affected_nodes"] == 2
