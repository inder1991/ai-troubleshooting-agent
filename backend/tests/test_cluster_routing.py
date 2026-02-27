"""Tests for cluster diagnostics session routing and /status endpoint."""

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


class TestClusterRouting:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_start_cluster_session(self, mock_build, mock_run, client):
        """POST /session/start with capability=cluster_diagnostics creates cluster session."""
        mock_build.return_value = MagicMock()

        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "session_id" in data
        assert data["service_name"] == "Cluster Diagnostics"

        # Verify session was stored with cluster capability
        from src.api.routes_v4 import sessions
        session = sessions[data["session_id"]]
        assert session["capability"] == "cluster_diagnostics"

    def test_cluster_status_no_crash(self, client):
        """GET /status for cluster session doesn't crash (was AttributeError before fix)."""
        from src.api.routes_v4 import sessions
        sid = "00000000-0000-4000-8000-000000000010"
        sessions[sid] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-010",
            "phase": "complete",
            "confidence": 80,
            "created_at": "2026-01-01T00:00:00Z",
            "capability": "cluster_diagnostics",
            "state": {
                "domain_reports": [{"domain": "ctrl_plane"}, {"domain": "node"}],
                "data_completeness": 0.5,
            },
        }
        resp = client.get(f"/api/v4/session/{sid}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["findings_count"] == 2
        assert data["data_completeness"] == 0.5

    def test_cluster_status_no_state(self, client):
        """GET /status for cluster session with no state yet returns defaults."""
        from src.api.routes_v4 import sessions
        sid = "00000000-0000-4000-8000-000000000011"
        sessions[sid] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-011",
            "phase": "initial",
            "confidence": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "capability": "cluster_diagnostics",
            "state": None,
        }
        resp = client.get(f"/api/v4/session/{sid}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["findings_count"] == 0
        assert data["phase"] == "initial"

    def test_app_session_findings_empty_when_no_state(self, client):
        """App session with no state returns empty findings structure."""
        from src.api.routes_v4 import sessions
        sid = "00000000-0000-4000-8000-000000000012"
        sessions[sid] = {
            "service_name": "my-app",
            "incident_id": "INC-012",
            "phase": "initial",
            "confidence": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "state": None,
        }
        resp = client.get(f"/api/v4/session/{sid}/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["findings"] == []
        assert data["message"] == "Analysis not yet complete"
