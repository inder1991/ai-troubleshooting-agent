"""Tests for Agent Matrix API endpoints: GET /agents, GET /agents/{id}/executions."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture: patch health probes so they all return True (no real infra needed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_health_probes():
    """Mock all health probes to return True so agents appear 'active'."""
    with patch(
        "src.api.agent_endpoints.run_all_health_probes",
        new_callable=AsyncMock,
        return_value={
            "k8s_api": True,
            "prometheus": True,
            "elasticsearch": True,
            "github": True,
        },
    ):
        yield


@pytest.fixture
def client():
    """Create a TestClient for the FastAPI app."""
    # Patch _init_stores so startup doesn't need real DB
    with patch("src.api.main._init_stores"):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


# =========================================================================
# GET /api/v4/agents
# =========================================================================


class TestListAgents:
    """Test the GET /api/v4/agents endpoint."""

    def test_returns_200(self, client):
        resp = client.get("/api/v4/agents")
        assert resp.status_code == 200

    def test_returns_25_agents(self, client):
        data = client.get("/api/v4/agents").json()
        assert len(data["agents"]) >= 25

    def test_summary_counts(self, client):
        data = client.get("/api/v4/agents").json()
        summary = data["summary"]
        total = summary["total"]
        assert total >= 25
        # With all probes mocked to True, all agents should be active
        assert summary["active"] == total
        assert summary["degraded"] == 0
        assert summary["offline"] == 0

    def test_agent_has_status_field(self, client):
        data = client.get("/api/v4/agents").json()
        for agent in data["agents"]:
            assert "status" in agent
            assert agent["status"] in ("active", "degraded", "offline")

    def test_agent_has_degraded_tools_list(self, client):
        data = client.get("/api/v4/agents").json()
        for agent in data["agents"]:
            assert "degraded_tools" in agent
            assert isinstance(agent["degraded_tools"], list)

    def test_agent_has_recent_executions_list(self, client):
        data = client.get("/api/v4/agents").json()
        for agent in data["agents"]:
            assert "recent_executions" in agent
            assert isinstance(agent["recent_executions"], list)

    def test_agent_has_required_fields(self, client):
        data = client.get("/api/v4/agents").json()
        required_fields = {
            "id", "name", "workflow", "role", "description", "icon",
            "level", "llm_config", "timeout_s", "status",
            "degraded_tools", "tools", "architecture_stages",
            "recent_executions",
        }
        for agent in data["agents"]:
            missing = required_fields - set(agent.keys())
            assert not missing, f"Agent {agent['id']} missing fields: {missing}"

    def test_all_agents_active_when_probes_pass(self, client):
        data = client.get("/api/v4/agents").json()
        for agent in data["agents"]:
            assert agent["status"] == "active", (
                f"Agent {agent['id']} should be active but is {agent['status']}"
            )

    def test_degraded_when_probe_fails(self, client):
        """When one probe fails, agents depending on it should be degraded or offline."""
        with patch(
            "src.api.agent_endpoints.run_all_health_probes",
            new_callable=AsyncMock,
            return_value={
                "k8s_api": True,
                "prometheus": False,
                "elasticsearch": True,
                "github": True,
            },
        ):
            data = client.get("/api/v4/agents").json()
            # MetricsAgent depends only on prometheus -> should be offline
            metrics = next(a for a in data["agents"] if a["id"] == "metrics_agent")
            assert metrics["status"] == "offline"
            assert "prometheus" in metrics["degraded_tools"]

            # NodeAgent depends on k8s_api + prometheus -> degraded (one failing)
            node = next(a for a in data["agents"] if a["id"] == "node_agent")
            assert node["status"] == "degraded"
            assert "prometheus" in node["degraded_tools"]

    def test_summary_reflects_degraded_status(self, client):
        """Summary counts should reflect degraded/offline agents."""
        with patch(
            "src.api.agent_endpoints.run_all_health_probes",
            new_callable=AsyncMock,
            return_value={
                "k8s_api": False,
                "prometheus": False,
                "elasticsearch": False,
                "github": False,
            },
        ):
            data = client.get("/api/v4/agents").json()
            summary = data["summary"]
            assert summary["total"] >= 25
            # Agents with no health checks remain active
            assert summary["active"] > 0
            # Agents with all checks failing should be offline
            assert summary["offline"] > 0


# =========================================================================
# GET /api/v4/agents/{agent_id}/executions
# =========================================================================


class TestGetAgentExecutions:
    """Test the GET /api/v4/agents/{id}/executions endpoint."""

    def test_valid_agent_returns_200(self, client):
        resp = client.get("/api/v4/agents/node_agent/executions")
        assert resp.status_code == 200

    def test_invalid_agent_returns_404(self, client):
        resp = client.get("/api/v4/agents/nonexistent_agent/executions")
        assert resp.status_code == 404

    def test_response_has_agent_id(self, client):
        data = client.get("/api/v4/agents/supervisor_agent/executions").json()
        assert data["agent_id"] == "supervisor_agent"

    def test_response_has_executions_list(self, client):
        data = client.get("/api/v4/agents/supervisor_agent/executions").json()
        assert "executions" in data
        assert isinstance(data["executions"], list)

    def test_empty_executions_when_no_sessions(self, client):
        """When there are no sessions, executions should be an empty list."""
        data = client.get("/api/v4/agents/supervisor_agent/executions").json()
        assert data["executions"] == []

    def test_executions_with_session_data(self, client):
        """When sessions contain agent events, they should appear in executions."""
        from src.api.routes_v4 import sessions
        from src.utils.event_emitter import EventEmitter
        from src.models.schemas import TaskEvent

        # Create a fake emitter with events for node_agent
        emitter = MagicMock()
        now = datetime.now(timezone.utc)
        events = [
            TaskEvent(
                timestamp=now - timedelta(seconds=2),
                agent_name="node_agent",
                event_type="started",
                message="Starting node analysis",
                session_id="test-session-1",
            ),
            TaskEvent(
                timestamp=now,
                agent_name="node_agent",
                event_type="success",
                message="Node analysis complete",
                session_id="test-session-1",
            ),
        ]
        emitter.get_events_by_agent.return_value = events

        # Inject the fake session
        sessions["test-session-1"] = {
            "service_name": "test-service",
            "created_at": now.isoformat(),
            "emitter": emitter,
        }

        try:
            data = client.get("/api/v4/agents/node_agent/executions").json()
            assert len(data["executions"]) == 1
            execution = data["executions"][0]
            assert execution["session_id"] == "test-session-1"
            assert execution["status"] == "SUCCESS"
            assert execution["duration_ms"] == 2000
            assert "trace" in execution
        finally:
            # Clean up injected session
            sessions.pop("test-session-1", None)

    def test_executions_limited_to_5(self, client):
        """Executions should be limited to the last 5."""
        from src.api.routes_v4 import sessions
        from src.models.schemas import TaskEvent

        now = datetime.now(timezone.utc)
        injected_ids = []

        try:
            for i in range(7):
                sid = f"test-session-limit-{i}"
                injected_ids.append(sid)
                emitter = MagicMock()
                events = [
                    TaskEvent(
                        timestamp=now - timedelta(minutes=7 - i, seconds=1),
                        agent_name="supervisor_agent",
                        event_type="started",
                        message=f"Run {i}",
                        session_id=sid,
                    ),
                    TaskEvent(
                        timestamp=now - timedelta(minutes=7 - i),
                        agent_name="supervisor_agent",
                        event_type="success",
                        message=f"Done {i}",
                        session_id=sid,
                    ),
                ]
                emitter.get_events_by_agent.return_value = events
                sessions[sid] = {
                    "service_name": "test",
                    "created_at": now.isoformat(),
                    "emitter": emitter,
                }

            data = client.get("/api/v4/agents/supervisor_agent/executions").json()
            assert len(data["executions"]) == 5
        finally:
            for sid in injected_ids:
                sessions.pop(sid, None)
