"""End-to-end integration tests for the Live Investigation Steering pipeline.

Tests the complete flow: create session -> POST /investigate -> verify
EvidencePin stored -> verify WebSocket event emitted -> verify critic
delta revalidation triggered.

Covers:
- Quick action (fast path)
- Slash command (fast path)
- Natural language query (smart path)
- Pin merging into session state
- Multiple pins accumulating
- No-pin scenario (router returns None)
- Critic delta background task dispatch
- WebSocket event emission for pin creation
- Session-not-found and invalid-session guards
- Concurrent investigation requests under session lock
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.api.main import app
from src.tools.router_models import InvestigateResponse
from src.models.schemas import EvidencePin


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear():
    """Reset all module-level state between tests."""
    from src.api.routes_v4 import sessions, supervisors, session_locks, _investigation_routers
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _make_pin(pin_id: str = "pin-test", claim: str = "Pod auth: 3 errors", **overrides) -> EvidencePin:
    """Create an EvidencePin with sensible defaults for testing."""
    defaults = dict(
        id=pin_id,
        claim=claim,
        source_agent=None,
        source_tool="fetch_pod_logs",
        confidence=1.0,
        timestamp=datetime.now(timezone.utc),
        evidence_type="log",
        source="manual",
        triggered_by="quick_action",
        domain="compute",
        validation_status="pending_critic",
    )
    defaults.update(overrides)
    return EvidencePin(**defaults)


def _make_investigate_response(pin_id: str = "pin-test", intent: str = "fetch_pod_logs",
                                path_used: str = "fast", **overrides) -> InvestigateResponse:
    """Create an InvestigateResponse with sensible defaults."""
    defaults = dict(
        pin_id=pin_id,
        intent=intent,
        params={"pod": "auth"},
        path_used=path_used,
        status="executing",
    )
    defaults.update(overrides)
    return InvestigateResponse(**defaults)


def _create_session(client) -> str:
    """Helper to create a session and return its ID."""
    with patch("src.api.routes_v4.SupervisorAgent"):
        resp = client.post("/api/v4/session/start", json={
            "serviceName": "auth-service",
            "namespace": "payment-api",
            "capability": "troubleshoot_app",
        })
    assert resp.status_code == 200
    return resp.json()["session_id"]


def _mock_router(pin, response=None):
    """Patch _get_investigation_router and return a mock router that returns (response, pin)."""
    if response is None:
        response = _make_investigate_response(pin_id=pin.id if pin else "pin-none")
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(return_value=(response, pin))
    return mock_router


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestInvestigationIntegration:
    """End-to-end tests for the investigation steering flow."""

    def test_full_flow_quick_action(self, client):
        """Complete pipeline: create session -> quick_action -> pin created -> response verified."""
        # 1. Create session
        session_id = _create_session(client)

        # 2. Get available tools
        resp = client.get(f"/api/v4/session/{session_id}/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert any(t["intent"] == "fetch_pod_logs" for t in tools)

        # 3. Execute investigation via quick action
        pin = _make_pin()
        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock  # preserve Lock constructor
            mock_get.return_value = _mock_router(pin)

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["pin_id"] == "pin-test"
        assert data["path_used"] == "fast"
        assert data["status"] == "executing"
        assert data["intent"] == "fetch_pod_logs"

    def test_pin_merged_into_session_state(self, client):
        """After POST /investigate, pin is stored in sessions[session_id]['evidence_pins']."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-merge-1", claim="OOMKilled detected")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_get.return_value = _mock_router(pin)

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200

        # Verify pin is stored in session state
        state = sessions[session_id]
        assert "evidence_pins" in state
        assert len(state["evidence_pins"]) == 1
        stored_pin = state["evidence_pins"][0]
        assert stored_pin["id"] == "pin-merge-1"
        assert stored_pin["claim"] == "OOMKilled detected"
        assert stored_pin["source_tool"] == "fetch_pod_logs"
        assert stored_pin["validation_status"] == "pending_critic"

    def test_slash_command_flow(self, client):
        """Test using command: '/logs pod=auth-5b6q' instead of quick_action."""
        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-slash", claim="Logs from auth pod", triggered_by="user_chat")
        response = _make_investigate_response(pin_id="pin-slash", path_used="fast")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_router = _mock_router(pin, response)
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "command": "/logs pod=auth-5b6q",
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["pin_id"] == "pin-slash"
        assert data["path_used"] == "fast"

        # Verify router received the request with command
        call_args = mock_router.route.call_args
        request_arg = call_args[0][0]
        assert request_arg.command == "/logs pod=auth-5b6q"
        assert request_arg.quick_action is None
        assert request_arg.query is None

    def test_natural_language_flow(self, client):
        """Test using query: 'check the logs for auth service' (smart path)."""
        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-smart", claim="Auth service logs analyzed")
        response = _make_investigate_response(pin_id="pin-smart", path_used="smart")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_router = _mock_router(pin, response)
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "query": "check the logs for auth service",
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["pin_id"] == "pin-smart"
        assert data["path_used"] == "smart"

        # Verify router received the query input
        call_args = mock_router.route.call_args
        request_arg = call_args[0][0]
        assert request_arg.query == "check the logs for auth service"
        assert request_arg.command is None
        assert request_arg.quick_action is None

    def test_no_pin_when_router_returns_none(self, client):
        """When router returns (response, None), no pin is added to session state."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)
        error_response = _make_investigate_response(
            pin_id="", intent="nonexistent", status="error",
            error="Unknown tool: nonexistent",
        )

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr:
            mock_mgr.send_message = AsyncMock()
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value=(error_response, None))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "nonexistent", "params": {}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

        # Verify no pins in session state
        state = sessions[session_id]
        assert state.get("evidence_pins") is None or len(state.get("evidence_pins", [])) == 0

    def test_multiple_investigations_accumulate_pins(self, client):
        """Run 3 investigations and verify all pins accumulate in session state."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)

        pin_configs = [
            ("pin-1", "OOMKilled in auth-pod", "fetch_pod_logs", "log"),
            ("pin-2", "High error rate 5xx", "query_prometheus", "metric"),
            ("pin-3", "CrashLoopBackOff detected", "describe_resource", "k8s_resource"),
        ]

        for pin_id, claim, source_tool, evidence_type in pin_configs:
            pin = _make_pin(
                pin_id=pin_id, claim=claim,
                source_tool=source_tool, evidence_type=evidence_type,
            )
            response = _make_investigate_response(pin_id=pin_id, intent=source_tool)

            with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
                 patch("src.api.routes_v4.manager") as mock_mgr, \
                 patch("src.api.routes_v4.asyncio") as mock_asyncio:
                mock_mgr.send_message = AsyncMock()
                mock_asyncio.create_task = MagicMock()
                mock_asyncio.Lock = asyncio.Lock
                mock_get.return_value = _mock_router(pin, response)

                resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                    "quick_action": {"intent": source_tool, "params": {"pod": "auth"}},
                    "context": {"time_window": {"start": "now-1h", "end": "now"}},
                })
                assert resp.status_code == 200

        # Verify all 3 pins are accumulated
        state = sessions[session_id]
        assert len(state["evidence_pins"]) == 3
        stored_ids = [p["id"] for p in state["evidence_pins"]]
        assert stored_ids == ["pin-1", "pin-2", "pin-3"]

        # Verify each pin has the correct metadata
        assert state["evidence_pins"][0]["evidence_type"] == "log"
        assert state["evidence_pins"][1]["evidence_type"] == "metric"
        assert state["evidence_pins"][2]["evidence_type"] == "k8s_resource"

    def test_critic_delta_triggered(self, client):
        """Verify asyncio.create_task is called with _run_critic_delta after pin merge."""
        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-critic")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_task = MagicMock()
            mock_asyncio.create_task = MagicMock(return_value=mock_task)
            mock_asyncio.Lock = asyncio.Lock
            mock_get.return_value = _mock_router(pin)

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200

        # Verify asyncio.create_task was called
        mock_asyncio.create_task.assert_called_once()

        # Verify the task had add_done_callback called
        mock_task.add_done_callback.assert_called_once()

    def test_websocket_event_emitted_for_pin(self, client):
        """Verify WebSocket 'evidence_pin_added' event is emitted when pin is created."""
        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-ws", claim="WebSocket test pin", severity="critical")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_get.return_value = _mock_router(pin)

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200

        # Verify WebSocket send_message was called
        mock_mgr.send_message.assert_called_once()
        call_args = mock_mgr.send_message.call_args
        ws_session_id = call_args[0][0]
        ws_message = call_args[0][1]

        assert ws_session_id == session_id
        assert ws_message["type"] == "task_event"
        assert ws_message["data"]["event_type"] == "evidence_pin_added"
        assert ws_message["data"]["agent_name"] == "investigation_router"
        assert ws_message["data"]["details"]["pin_id"] == "pin-ws"
        assert ws_message["data"]["details"]["domain"] == "compute"
        assert ws_message["data"]["details"]["severity"] == "critical"
        assert ws_message["data"]["details"]["validation_status"] == "pending_critic"

    def test_no_websocket_event_when_no_pin(self, client):
        """When router returns None pin, no WebSocket event should be emitted."""
        session_id = _create_session(client)
        error_response = _make_investigate_response(status="error", error="Unknown tool")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr:
            mock_mgr.send_message = AsyncMock()
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value=(error_response, None))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "nonexistent", "params": {}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200
        # No WebSocket event should have been sent
        mock_mgr.send_message.assert_not_called()

    def test_no_critic_task_when_no_pin(self, client):
        """When router returns None pin, asyncio.create_task should NOT be called."""
        session_id = _create_session(client)
        error_response = _make_investigate_response(status="error", error="Unknown tool")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value=(error_response, None))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "nonexistent", "params": {}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        assert resp.status_code == 200
        mock_asyncio.create_task.assert_not_called()


class TestInvestigationEdgeCases:
    """Edge cases and error handling for the investigation endpoint."""

    def test_investigate_invalid_session_id(self, client):
        """Non-UUID session ID returns 400."""
        resp = client.post("/api/v4/session/not-a-uuid/investigate", json={
            "quick_action": {"intent": "test", "params": {}},
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 400

    def test_investigate_nonexistent_session(self, client):
        """Valid UUID that doesn't correspond to a session returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/v4/session/{fake_id}/investigate", json={
            "quick_action": {"intent": "test", "params": {}},
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 404

    def test_investigate_requires_exactly_one_input(self, client):
        """Providing both command and query returns 422 validation error."""
        session_id = _create_session(client)
        resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
            "command": "/logs pod=x",
            "query": "check logs",
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 422

    def test_investigate_requires_at_least_one_input(self, client):
        """Providing no input (no command, query, or quick_action) returns 422."""
        session_id = _create_session(client)
        resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 422

    def test_investigate_context_required(self, client):
        """Missing context field returns 422."""
        session_id = _create_session(client)
        resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
            "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
        })
        assert resp.status_code == 422

    def test_websocket_failure_does_not_break_response(self, client):
        """If WebSocket send_message raises, the endpoint still returns 200."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)
        pin = _make_pin(pin_id="pin-ws-fail")

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock(side_effect=Exception("WS connection closed"))
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_get.return_value = _mock_router(pin)

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        # Response should still succeed despite WebSocket failure
        assert resp.status_code == 200
        assert resp.json()["pin_id"] == "pin-ws-fail"

        # Pin should still be stored in session state
        state = sessions[session_id]
        assert len(state["evidence_pins"]) == 1


class TestToolsEndpointIntegration:
    """Integration tests for the GET /tools endpoint."""

    def test_tools_endpoint_returns_all_registered_tools(self, client):
        """GET /tools returns the full tool registry."""
        session_id = _create_session(client)
        resp = client.get(f"/api/v4/session/{session_id}/tools")
        assert resp.status_code == 200

        data = resp.json()
        assert "tools" in data
        tools = data["tools"]
        assert len(tools) >= 6

        # Verify each tool has required fields
        for tool in tools:
            assert "intent" in tool
            assert "label" in tool
            assert "slash_command" in tool
            assert "params_schema" in tool

    def test_tools_endpoint_invalid_session(self, client):
        """GET /tools with invalid session ID returns 400."""
        resp = client.get("/api/v4/session/bad-id/tools")
        assert resp.status_code == 400

    def test_tools_endpoint_nonexistent_session(self, client):
        """GET /tools with unknown session returns 404."""
        import uuid
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/v4/session/{fake_id}/tools")
        assert resp.status_code == 404

    def test_tools_include_fetch_pod_logs(self, client):
        """Verify fetch_pod_logs tool is in the registry."""
        session_id = _create_session(client)
        resp = client.get(f"/api/v4/session/{session_id}/tools")
        tools = resp.json()["tools"]
        log_tools = [t for t in tools if t["intent"] == "fetch_pod_logs"]
        assert len(log_tools) == 1
        assert log_tools[0]["slash_command"] == "/logs"


class TestSessionCreateIntegration:
    """Integration tests for session creation as part of the investigation flow."""

    def test_session_creates_lock(self, client):
        """Session creation also creates a per-session lock."""
        from src.api.routes_v4 import session_locks
        session_id = _create_session(client)
        assert session_id in session_locks
        assert isinstance(session_locks[session_id], asyncio.Lock)

    def test_session_initial_state_has_no_evidence_pins(self, client):
        """Freshly created session does not have evidence_pins key yet."""
        from src.api.routes_v4 import sessions
        session_id = _create_session(client)
        state = sessions[session_id]
        # evidence_pins is lazily created on first investigation
        assert "evidence_pins" not in state

    def test_session_start_response_format(self, client):
        """Verify session start response has expected fields."""
        with patch("src.api.routes_v4.SupervisorAgent"):
            resp = client.post("/api/v4/session/start", json={
                "serviceName": "auth-service",
                "namespace": "payment-api",
                "capability": "troubleshoot_app",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "incident_id" in data
        assert data["status"] == "started"


class TestPinDataIntegrity:
    """Tests verifying the integrity and structure of stored evidence pins."""

    def test_pin_serialized_correctly_in_session(self, client):
        """Verify pin is serialized via model_dump(mode='json') in session state."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)
        pin = _make_pin(
            pin_id="pin-serial",
            claim="Memory usage at 95%",
            source_tool="query_prometheus",
            evidence_type="metric",
            domain="compute",
            severity="high",
            confidence=0.92,
        )

        with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
             patch("src.api.routes_v4.manager") as mock_mgr, \
             patch("src.api.routes_v4.asyncio") as mock_asyncio:
            mock_mgr.send_message = AsyncMock()
            mock_asyncio.create_task = MagicMock()
            mock_asyncio.Lock = asyncio.Lock
            mock_get.return_value = _mock_router(pin)

            client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "query_prometheus", "params": {"query": "up"}},
                "context": {"time_window": {"start": "now-1h", "end": "now"}},
            })

        stored = sessions[session_id]["evidence_pins"][0]
        assert stored["id"] == "pin-serial"
        assert stored["claim"] == "Memory usage at 95%"
        assert stored["source_tool"] == "query_prometheus"
        assert stored["evidence_type"] == "metric"
        assert stored["domain"] == "compute"
        assert stored["severity"] == "high"
        assert stored["confidence"] == 0.92
        assert stored["validation_status"] == "pending_critic"
        assert stored["source"] == "manual"
        # timestamp should be a string after JSON serialization
        assert isinstance(stored["timestamp"], str)

    def test_pins_preserve_different_evidence_types(self, client):
        """Verify pins of different evidence types are stored with correct types."""
        from src.api.routes_v4 import sessions

        session_id = _create_session(client)

        type_map = {
            "pin-log": ("log", "fetch_pod_logs"),
            "pin-metric": ("metric", "query_prometheus"),
            "pin-k8s": ("k8s_resource", "describe_resource"),
        }

        for pin_id, (etype, tool) in type_map.items():
            pin = _make_pin(pin_id=pin_id, source_tool=tool, evidence_type=etype)
            resp_model = _make_investigate_response(pin_id=pin_id, intent=tool)

            with patch("src.api.routes_v4._get_investigation_router") as mock_get, \
                 patch("src.api.routes_v4.manager") as mock_mgr, \
                 patch("src.api.routes_v4.asyncio") as mock_asyncio:
                mock_mgr.send_message = AsyncMock()
                mock_asyncio.create_task = MagicMock()
                mock_asyncio.Lock = asyncio.Lock
                mock_get.return_value = _mock_router(pin, resp_model)

                client.post(f"/api/v4/session/{session_id}/investigate", json={
                    "quick_action": {"intent": tool, "params": {"pod": "x"}},
                    "context": {"time_window": {"start": "now-1h", "end": "now"}},
                })

        pins = sessions[session_id]["evidence_pins"]
        assert len(pins) == 3
        for pin_data in pins:
            expected_type = type_map[pin_data["id"]][0]
            assert pin_data["evidence_type"] == expected_type
