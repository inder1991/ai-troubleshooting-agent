"""Tests for cluster diagnostics session routing, /status endpoint, and cluster chat."""

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


class TestChatHistory:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_has_chat_history(self, mock_build, mock_run, client):
        """Cluster session should be created with empty chat_history."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert session["chat_history"] == []

    @patch("src.api.routes_v4.run_diagnosis", new_callable=AsyncMock)
    def test_app_session_has_chat_history(self, mock_run, client):
        """App session should be created with empty chat_history."""
        resp = client.post("/api/v4/session/start", json={
            "service_name": "my-app",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert session["chat_history"] == []


class TestClusterChat:
    def _make_cluster_session(self, sid, state=None):
        """Helper to insert a cluster session with optional state."""
        from src.api.routes_v4 import sessions
        sessions[sid] = {
            "service_name": "Cluster Diagnostics",
            "incident_id": "INC-100",
            "phase": "complete" if state else "initial",
            "confidence": 80 if state else 0,
            "created_at": "2026-01-01T00:00:00Z",
            "capability": "cluster_diagnostics",
            "state": state,
            "chat_history": [],
        }

    def test_cluster_chat_no_state(self, client):
        """Chat returns canned message when diagnostics haven't started."""
        sid = "00000000-0000-4000-8000-000000000020"
        self._make_cluster_session(sid, state=None)
        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "What's wrong?"})
        assert resp.status_code == 200
        data = resp.json()
        assert "still starting" in data["response"].lower()

    @patch("src.api.routes_v4.AnthropicClient")
    def test_cluster_chat_with_state(self, MockClient, client):
        """Chat returns LLM response grounded in cluster findings."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="The control plane has high latency."))
        MockClient.return_value = mock_llm

        sid = "00000000-0000-4000-8000-000000000021"
        state = {
            "domain_reports": [{"domain": "ctrl_plane", "status": "DEGRADED", "confidence": 0.7}],
            "causal_chains": [{"chain": "etcd slow -> apiserver timeout"}],
            "health_report": {"overall_status": "DEGRADED"},
        }
        self._make_cluster_session(sid, state=state)
        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "Why is the cluster slow?"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["response"]) > 0
        assert data["phase"] == "complete"

    @patch("src.api.routes_v4.AnthropicClient")
    def test_cluster_chat_stores_history(self, MockClient, client):
        """Chat appends user and assistant messages to chat_history."""
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Here is the answer."))
        MockClient.return_value = mock_llm

        sid = "00000000-0000-4000-8000-000000000022"
        state = {"domain_reports": [], "health_report": {"overall_status": "OK"}}
        self._make_cluster_session(sid, state=state)

        client.post(f"/api/v4/session/{sid}/chat", json={"message": "Hello"})

        from src.api.routes_v4 import sessions
        history = sessions[sid]["chat_history"]
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Here is the answer."

    @patch("src.api.routes_v4.AnthropicClient")
    def test_cluster_chat_history_cap(self, MockClient, client):
        """Chat history is capped at 20 messages."""
        sid = "00000000-0000-4000-8000-000000000023"
        state = {"domain_reports": []}
        self._make_cluster_session(sid, state=state)

        from src.api.routes_v4 import sessions
        # Pre-fill with 20 messages
        sessions[sid]["chat_history"] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
            for i in range(20)
        ]

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(text="Reply"))
        MockClient.return_value = mock_llm

        client.post(f"/api/v4/session/{sid}/chat", json={"message": "New question"})

        history = sessions[sid]["chat_history"]
        assert len(history) <= 20
