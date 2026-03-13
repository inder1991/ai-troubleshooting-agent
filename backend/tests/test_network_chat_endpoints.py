"""Tests for the NetworkChatGateway API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.network_chat_endpoints import network_chat_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(network_chat_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestNetworkChatEndpoints:
    def test_post_chat_message(self, client):
        """POST /api/v4/network/chat should forward to orchestrator and return response."""
        mock_result = {
            "response": "I see 3 active alerts.",
            "thread_id": "thread-123",
            "tool_calls": [],
        }
        with patch("src.api.network_chat_endpoints._get_orchestrator") as mock_get:
            mock_orch = AsyncMock()
            mock_orch.handle_message.return_value = mock_result
            mock_get.return_value = mock_orch

            resp = client.post(
                "/api/v4/network/chat",
                json={
                    "message": "Any alerts?",
                    "view": "observatory",
                    "visible_data_summary": {"alerts": 3},
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["response"] == "I see 3 active alerts."
            assert data["thread_id"] == "thread-123"
            assert data["tool_calls"] == []

            # Verify orchestrator was called with correct args
            mock_orch.handle_message.assert_called_once_with(
                user_id="default",
                view="observatory",
                message="Any alerts?",
                visible_data_summary={"alerts": 3},
                thread_id=None,
            )

    def test_post_chat_with_thread_id(self, client):
        """POST /api/v4/network/chat with an existing thread_id should pass it through."""
        mock_result = {
            "response": "Continuing conversation.",
            "thread_id": "thread-existing",
            "tool_calls": [],
        }
        with patch("src.api.network_chat_endpoints._get_orchestrator") as mock_get:
            mock_orch = AsyncMock()
            mock_orch.handle_message.return_value = mock_result
            mock_get.return_value = mock_orch

            resp = client.post(
                "/api/v4/network/chat",
                json={
                    "message": "What about now?",
                    "view": "topology",
                    "thread_id": "thread-existing",
                    "user_id": "user-42",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["thread_id"] == "thread-existing"

            mock_orch.handle_message.assert_called_once_with(
                user_id="user-42",
                view="topology",
                message="What about now?",
                visible_data_summary={},
                thread_id="thread-existing",
            )

    def test_post_chat_with_tool_calls(self, client):
        """Tool calls from orchestrator should be included in the response."""
        mock_result = {
            "response": "Found 2 devices.",
            "thread_id": "thread-456",
            "tool_calls": [
                {"name": "get_devices", "args": {}, "result": "[{...}]"},
            ],
        }
        with patch("src.api.network_chat_endpoints._get_orchestrator") as mock_get:
            mock_orch = AsyncMock()
            mock_orch.handle_message.return_value = mock_result
            mock_get.return_value = mock_orch

            resp = client.post(
                "/api/v4/network/chat",
                json={"message": "List devices", "view": "topology"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["tool_calls"]) == 1
            assert data["tool_calls"][0]["name"] == "get_devices"

    def test_post_chat_requires_message(self, client):
        """POST /api/v4/network/chat without 'message' field should return 422."""
        resp = client.post(
            "/api/v4/network/chat",
            json={"view": "observatory"},
        )
        assert resp.status_code == 422

    def test_post_chat_requires_view(self, client):
        """POST /api/v4/network/chat without 'view' field should return 422."""
        resp = client.post(
            "/api/v4/network/chat",
            json={"message": "hello"},
        )
        assert resp.status_code == 422

    def test_get_thread_messages(self, client):
        """GET /api/v4/network/chat/threads/{id}/messages should return messages from store."""
        with patch("src.api.network_chat_endpoints._get_store") as mock_get:
            mock_store = mock_get.return_value
            mock_store.list_messages.return_value = [
                {
                    "message_id": "m1",
                    "role": "user",
                    "content": "hello",
                    "timestamp": "2026-03-12T00:00:00Z",
                },
            ]

            resp = client.get("/api/v4/network/chat/threads/thread-123/messages")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["message_id"] == "m1"
            assert data[0]["role"] == "user"

            mock_store.list_messages.assert_called_once_with("thread-123", limit=50)

    def test_get_thread_messages_with_limit(self, client):
        """GET with ?limit=10 should pass limit to store."""
        with patch("src.api.network_chat_endpoints._get_store") as mock_get:
            mock_store = mock_get.return_value
            mock_store.list_messages.return_value = []

            resp = client.get(
                "/api/v4/network/chat/threads/thread-123/messages?limit=10"
            )
            assert resp.status_code == 200
            mock_store.list_messages.assert_called_once_with("thread-123", limit=10)

    def test_get_thread_messages_empty(self, client):
        """GET for a thread with no messages should return an empty list."""
        with patch("src.api.network_chat_endpoints._get_store") as mock_get:
            mock_store = mock_get.return_value
            mock_store.list_messages.return_value = []

            resp = client.get("/api/v4/network/chat/threads/thread-999/messages")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_post_chat_defaults(self, client):
        """Default values for optional fields should be applied correctly."""
        mock_result = {
            "response": "ok",
            "thread_id": "t-new",
            "tool_calls": [],
        }
        with patch("src.api.network_chat_endpoints._get_orchestrator") as mock_get:
            mock_orch = AsyncMock()
            mock_orch.handle_message.return_value = mock_result
            mock_get.return_value = mock_orch

            resp = client.post(
                "/api/v4/network/chat",
                json={"message": "hi", "view": "flows"},
            )
            assert resp.status_code == 200

            mock_orch.handle_message.assert_called_once_with(
                user_id="default",
                view="flows",
                message="hi",
                visible_data_summary={},
                thread_id=None,
            )
