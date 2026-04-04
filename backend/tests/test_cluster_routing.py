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


class TestStartSessionAuthFields:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_accepts_auth_fields(self, mock_build, mock_run, client):
        """POST /session/start accepts authToken and authMethod for cluster sessions."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
            "auth_token": "eyJhbGciOi...",
            "auth_method": "token",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"


class TestClusterConnectionConfig:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_stores_connection_config(self, mock_build, mock_run, client):
        """Cluster session stores connection_config in session dict."""
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
            "auth_token": "test-token-123",
            "auth_method": "token",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert "connection_config" in session

    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_cluster_session_with_profile_has_connection_config(self, mock_build, mock_run, client):
        """Cluster session with profile_id resolves connection_config from profile store."""
        mock_build.return_value = MagicMock()
        # connection_config comes from resolve_active_profile which is called earlier in start_session
        resp = client.post("/api/v4/session/start", json={
            "service_name": "Cluster Diagnostics",
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.cluster.example.com",
            "profile_id": "some-profile-id",
        })
        assert resp.status_code == 200
        from src.api.routes_v4 import sessions
        session = sessions[resp.json()["session_id"]]
        assert "connection_config" in session


class TestProfileRole:
    def test_create_profile_with_role(self, client):
        resp = client.post("/api/v5/profiles/", json={
            "name": "test-cluster-role",
            "cluster_url": "https://api.example.com:6443",
            "cluster_type": "openshift",
            "role": "cluster-admin",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "cluster-admin"

    def test_update_profile_role(self, client):
        # First create a profile
        create_resp = client.post("/api/v5/profiles/", json={
            "name": "test-update-role",
            "cluster_url": "https://api.example.com:6443",
            "cluster_type": "openshift",
        })
        assert create_resp.status_code == 200
        profile_id = create_resp.json()["id"]
        # Then update with role
        resp = client.put(f"/api/v5/profiles/{profile_id}", json={"role": "view"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "view"


class TestResolvedConnectionConfig:
    def test_has_auth_method_field(self):
        from src.integrations.connection_config import ResolvedConnectionConfig
        cfg = ResolvedConnectionConfig(
            cluster_url="https://x.com",
            cluster_token="tok",
            auth_method="token",
        )
        assert cfg.auth_method == "token"
        assert cfg.kubeconfig_content == ""
        assert cfg.role == ""

    def test_kubeconfig_content_field(self):
        from src.integrations.connection_config import ResolvedConnectionConfig
        cfg = ResolvedConnectionConfig(
            auth_method="kubeconfig",
            kubeconfig_content="apiVersion: v1\nkind: Config\n",
        )
        assert cfg.auth_method == "kubeconfig"
        assert cfg.kubeconfig_content == "apiVersion: v1\nkind: Config\n"

    def test_role_field_default_empty(self):
        from src.integrations.connection_config import ResolvedConnectionConfig
        cfg = ResolvedConnectionConfig()
        assert cfg.role == ""

    def test_config_from_env_reads_auth_method(self, monkeypatch):
        monkeypatch.setenv("K8S_AUTH_METHOD", "kubeconfig")
        monkeypatch.setenv("KUBECONFIG_CONTENT", "apiVersion: v1")
        from src.integrations import connection_config
        import importlib
        importlib.reload(connection_config)
        cfg = connection_config._config_from_env()
        assert cfg.auth_method == "kubeconfig"
        assert cfg.kubeconfig_content == "apiVersion: v1"


class TestCreateClusterClient:
    def test_returns_tuple(self, monkeypatch):
        """create_cluster_client always returns (client, temp_path_or_None)."""
        from src.api.routes_v4 import create_cluster_client
        from src.integrations.connection_config import ResolvedConnectionConfig

        # Patch KubernetesClient to avoid real network calls
        monkeypatch.setattr(
            "src.api.routes_v4.KubernetesClient",
            lambda **kwargs: object()
        )
        cfg = ResolvedConnectionConfig(cluster_url="https://api.example.com:6443", cluster_token="tok")
        result = create_cluster_client(cfg)
        assert isinstance(result, tuple)
        assert len(result) == 2
        client, temp_path = result
        assert client is not None
        assert temp_path is None  # no temp file for bearer token auth

    def test_kubeconfig_content_creates_temp_file(self, monkeypatch, tmp_path):
        """When auth_method=kubeconfig and kubeconfig_content set, a temp file is created."""
        import os
        from src.api.routes_v4 import create_cluster_client
        from src.integrations.connection_config import ResolvedConnectionConfig

        monkeypatch.setattr(
            "src.api.routes_v4.KubernetesClient",
            lambda **kwargs: type("C", (), {"kubeconfig_path": kwargs.get("kubeconfig_path")})()
        )
        cfg = ResolvedConnectionConfig(
            auth_method="kubeconfig",
            kubeconfig_content="apiVersion: v1\nkind: Config\n",
        )
        client, temp_path = create_cluster_client(cfg)
        assert temp_path is not None
        assert os.path.exists(temp_path)
        assert open(temp_path).read() == "apiVersion: v1\nkind: Config\n"
        # Cleanup
        os.unlink(temp_path)


class TestAppChatFindings:
    """Verify app chat includes actual findings in the LLM prompt."""

    def test_app_chat_routes_through_supervisor(self, client):
        """App chat routes through supervisor.handle_user_message()."""
        from src.api.routes_v4 import sessions, supervisors
        sid = "00000000-0000-4000-8000-000000000030"
        mock_supervisor = MagicMock()
        mock_supervisor.handle_user_message = AsyncMock(return_value="Findings-based answer")

        sessions[sid] = {
            "service_name": "my-app",
            "incident_id": "INC-030",
            "phase": "diagnosis_complete",
            "confidence": 85,
            "created_at": "2026-01-01T00:00:00Z",
            "state": MagicMock(),
            "chat_history": [],
        }
        supervisors[sid] = mock_supervisor

        resp = client.post(f"/api/v4/session/{sid}/chat", json={"message": "Why is memory spiking?"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "Findings-based answer"
        mock_supervisor.handle_user_message.assert_called_once()


class TestStartSessionNewFields:
    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_start_session_accepts_kubeconfig_content(self, mock_build, mock_run, client):
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.example.com:6443",
            "auth_method": "kubeconfig",
            "kubeconfig_content": "apiVersion: v1\nkind: Config\n",
        })
        # Session should be created (200 or 201)
        assert resp.status_code in (200, 201)
        sid = resp.json().get("session_id")
        assert sid

    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_start_session_accepts_role(self, mock_build, mock_run, client):
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.example.com:6443",
            "auth_token": "mytoken",
            "role": "cluster-admin",
        })
        assert resp.status_code in (200, 201)

    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_start_session_stores_elk_index(self, mock_build, mock_run, client):
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.example.com:6443",
            "auth_token": "tok",
            "elk_index": "cluster-logs-*",
        })
        assert resp.status_code in (200, 201)
        sid = resp.json()["session_id"]
        from src.api.routes_v4 import sessions
        assert sessions.get(sid, {}).get("elk_index") == "cluster-logs-*"

    @patch("src.api.routes_v4.run_cluster_diagnosis", new_callable=AsyncMock)
    @patch("src.api.routes_v4.build_cluster_diagnostic_graph")
    def test_elk_index_defaults_to_empty_for_cluster_diagnostics(self, mock_build, mock_run, client):
        mock_build.return_value = MagicMock()
        resp = client.post("/api/v4/session/start", json={
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.example.com:6443",
            "auth_token": "tok",
        })
        assert resp.status_code in (200, 201)
        sid = resp.json()["session_id"]
        from src.api.routes_v4 import sessions
        # elk_index should be "" not "app-logs-*"
        assert sessions.get(sid, {}).get("elk_index", "") == ""


class TestTestConnectionEndpoint:
    def test_returns_connected_status(self, client, monkeypatch):
        """POST /api/v5/profiles/test-connection returns status=connected on success."""
        from unittest.mock import AsyncMock, MagicMock

        mock_client_instance = MagicMock()
        mock_client_instance.detect_platform = AsyncMock(
            return_value={"platform": "openshift", "version": "4.14.0"}
        )
        mock_client_instance.close = AsyncMock()

        def mock_k8s_constructor(**kwargs):
            return mock_client_instance

        monkeypatch.setattr(
            "src.api.routes_profiles.KubernetesClient",
            mock_k8s_constructor
        )

        resp = client.post("/api/v5/profiles/test-connection", json={
            "cluster_url": "https://api.example.com:6443",
            "auth_method": "token",
            "credential": "mytoken",
            "verify_ssl": False,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "connected"
        assert body["platform"] == "openshift"
        assert body["version"] == "4.14.0"
        assert body["latency_ms"] >= 0
        assert body.get("error") is None

    def test_returns_auth_failed_on_401(self, client, monkeypatch):
        """POST /api/v5/profiles/test-connection returns status=auth_failed on 401 error."""
        from unittest.mock import AsyncMock, MagicMock

        def mock_k8s_constructor(**kwargs):
            instance = MagicMock()
            instance.detect_platform = AsyncMock(side_effect=Exception("401 Unauthorized"))
            instance.close = AsyncMock()
            return instance

        monkeypatch.setattr("src.api.routes_profiles.KubernetesClient", mock_k8s_constructor)

        resp = client.post("/api/v5/profiles/test-connection", json={
            "cluster_url": "https://api.example.com:6443",
            "auth_method": "token",
            "credential": "badtoken",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "auth_failed"

    def test_kubeconfig_auth_method(self, client, monkeypatch, tmp_path):
        """Kubeconfig auth method writes temp file and passes path to KubernetesClient."""
        from unittest.mock import AsyncMock, MagicMock

        received_kwargs = {}

        def mock_k8s_constructor(**kwargs):
            received_kwargs.update(kwargs)
            instance = MagicMock()
            instance.detect_platform = AsyncMock(return_value={"platform": "kubernetes", "version": "1.28"})
            instance.close = AsyncMock()
            return instance

        monkeypatch.setattr("src.api.routes_profiles.KubernetesClient", mock_k8s_constructor)

        resp = client.post("/api/v5/profiles/test-connection", json={
            "cluster_url": "https://api.example.com:6443",
            "auth_method": "kubeconfig",
            "credential": "apiVersion: v1\nkind: Config\n",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"
        # KubernetesClient was called with kubeconfig_path (not api_url + token)
        assert "kubeconfig_path" in received_kwargs


class TestClusterClientLifecycle:
    def test_cluster_client_stored_in_session(self, client, monkeypatch):
        """After start_session, cluster_client should be stored in the session dict."""
        from unittest.mock import MagicMock, AsyncMock
        import asyncio

        mock_k8s = MagicMock()
        mock_k8s.detect_platform = AsyncMock(return_value={"platform": "openshift", "version": "4.14"})
        mock_k8s.list_namespaces = AsyncMock(return_value=MagicMock(data=["default"]))
        mock_k8s.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
        mock_k8s.close = AsyncMock()

        monkeypatch.setattr(
            "src.api.routes_v4.KubernetesClient",
            lambda **kwargs: mock_k8s
        )

        # Patch graph.ainvoke to avoid running actual LangGraph
        from src.agents.cluster.graph import build_cluster_diagnostic_graph
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"phase": "complete", "data_completeness": 0.8,
                                                      "domain_reports": [], "health_report": None})
        monkeypatch.setattr("src.api.routes_v4.build_cluster_diagnostic_graph", lambda: mock_graph)

        resp = client.post("/api/v4/session/start", json={
            "capability": "cluster_diagnostics",
            "cluster_url": "https://api.example.com:6443",
            "auth_token": "mytoken",
        })
        assert resp.status_code in (200, 201)
        sid = resp.json()["session_id"]

        # Wait for background task to store client
        import time
        for _ in range(20):
            from src.api.routes_v4 import sessions
            if sessions.get(sid, {}).get("cluster_client") is not None:
                break
            time.sleep(0.1)

        from src.api.routes_v4 import sessions
        assert sessions.get(sid, {}).get("cluster_client") is not None

    def test_get_or_create_cluster_client_returns_cached(self, client, monkeypatch):
        """get_or_create_cluster_client returns the cached client if already in session."""
        import asyncio
        from src.api.routes_v4 import get_or_create_cluster_client, sessions

        mock_client = object()
        sid = "test-cached-session"
        sessions[sid] = {"cluster_client": mock_client, "connection_config": None}

        result = asyncio.run(get_or_create_cluster_client(sid))
        assert result is mock_client
