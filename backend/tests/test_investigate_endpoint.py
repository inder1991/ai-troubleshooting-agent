import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(autouse=True)
def _clear_sessions():
    from src.api.routes_v4 import sessions, supervisors, session_locks
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seeded_session(client):
    """Create a session to test against."""
    with patch("src.api.routes_v4.SupervisorAgent"):
        resp = client.post("/api/v4/session/start", json={
            "serviceName": "auth-service",
            "namespace": "payment-api",
            "capability": "troubleshoot_app",
        })
    assert resp.status_code == 200
    return resp.json()["session_id"]


class TestInvestigateEndpoint:
    def test_quick_action_returns_200(self, client, seeded_session):
        with patch("src.api.routes_v4._get_investigation_router") as mock_get:
            mock_router = AsyncMock()
            from src.tools.router_models import InvestigateResponse
            from src.models.schemas import EvidencePin
            from datetime import datetime, timezone

            mock_pin = EvidencePin(
                id="pin-001", claim="Pod ok", source_agent=None,
                source_tool="fetch_pod_logs", confidence=1.0,
                timestamp=datetime.now(timezone.utc), evidence_type="log",
                source="manual", domain="compute",
            )
            mock_router.route = AsyncMock(return_value=(
                InvestigateResponse(
                    pin_id="pin-001", intent="fetch_pod_logs",
                    params={"pod": "auth"}, path_used="fast", status="executing",
                ),
                mock_pin,
            ))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{seeded_session}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["pin_id"] == "pin-001"
        assert data["path_used"] == "fast"

    def test_invalid_session_returns_400(self, client):
        resp = client.post("/api/v4/session/not-a-uuid/investigate", json={
            "quick_action": {"intent": "test", "params": {}},
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 400

    def test_exactly_one_input_validation(self, client, seeded_session):
        resp = client.post(f"/api/v4/session/{seeded_session}/investigate", json={
            "command": "/logs pod=x",
            "query": "check logs",
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 422  # Pydantic validation error


class TestToolsEndpoint:
    def test_get_tools_returns_registry(self, client, seeded_session):
        resp = client.get(f"/api/v4/session/{seeded_session}/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) >= 6
        for tool in data["tools"]:
            assert "intent" in tool
            assert "label" in tool
            assert "slash_command" in tool
            assert "params_schema" in tool

    def test_get_tools_invalid_session(self, client):
        resp = client.get("/api/v4/session/not-a-uuid/tools")
        assert resp.status_code == 400
