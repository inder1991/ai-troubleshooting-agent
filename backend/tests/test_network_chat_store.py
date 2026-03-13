"""Tests for network chat thread & message storage."""
import os
import tempfile
import time

import pytest


@pytest.fixture
def store():
    from src.database.network_chat_store import NetworkChatStore

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = NetworkChatStore(db_path=path)
    yield s
    os.unlink(path)


class TestNetworkChatStore:
    # ── Thread ops ────────────────────────────────────────────

    def test_create_thread(self, store):
        thread = store.create_thread(user_id="u1", view="topology")
        assert thread["thread_id"]
        assert thread["user_id"] == "u1"
        assert thread["view"] == "topology"
        assert thread["created_at"]
        assert thread["last_message_at"]
        assert thread["investigation_session_id"] is None

    def test_get_thread(self, store):
        created = store.create_thread(user_id="u1", view="flows")
        fetched = store.get_thread(created["thread_id"])
        assert fetched is not None
        assert fetched["thread_id"] == created["thread_id"]
        assert fetched["user_id"] == "u1"
        assert fetched["view"] == "flows"

    def test_get_thread_not_found(self, store):
        assert store.get_thread("nonexistent-id") is None

    def test_get_active_thread_for_view(self, store):
        """Returns the most recent non-investigation thread for a user+view."""
        t1 = store.create_thread(user_id="u1", view="topology")
        time.sleep(0.01)  # ensure distinct timestamps
        t2 = store.create_thread(user_id="u1", view="topology")
        time.sleep(0.01)
        # escalated thread should be skipped
        t3 = store.create_thread(user_id="u1", view="topology")
        store.escalate_thread(t3["thread_id"], "inv-session-1")

        # different view — should not appear
        store.create_thread(user_id="u1", view="flows")

        active = store.get_active_thread(user_id="u1", view="topology")
        assert active is not None
        assert active["thread_id"] == t2["thread_id"]

    def test_escalate_thread(self, store):
        thread = store.create_thread(user_id="u1", view="topology")
        assert thread["investigation_session_id"] is None

        store.escalate_thread(thread["thread_id"], "inv-session-42")
        updated = store.get_thread(thread["thread_id"])
        assert updated["investigation_session_id"] == "inv-session-42"

    # ── Message ops ───────────────────────────────────────────

    def test_add_and_list_messages(self, store):
        thread = store.create_thread(user_id="u1", view="topology")
        tid = thread["thread_id"]

        m1 = store.add_message(tid, role="user", content="What is latency?")
        m2 = store.add_message(tid, role="assistant", content="Latency is ...")
        m3 = store.add_message(
            tid,
            role="tool",
            content="",
            tool_name="get_metrics",
            tool_args={"service": "api-gw"},
            tool_result={"p99": 120},
        )

        assert m1["message_id"]
        assert m1["role"] == "user"
        assert m3["tool_name"] == "get_metrics"
        assert m3["tool_args"] == {"service": "api-gw"}
        assert m3["tool_result"] == {"p99": 120}

        messages = store.list_messages(tid)
        assert len(messages) == 3
        # chronological order
        assert messages[0]["message_id"] == m1["message_id"]
        assert messages[1]["message_id"] == m2["message_id"]
        assert messages[2]["message_id"] == m3["message_id"]

    def test_list_messages_with_limit(self, store):
        thread = store.create_thread(user_id="u1", view="topology")
        tid = thread["thread_id"]

        for i in range(25):
            store.add_message(tid, role="user", content=f"msg-{i}")

        messages = store.list_messages(tid, limit=20)
        assert len(messages) == 20
        # should be the LAST 20 (most recent), ordered chronologically
        assert messages[0]["content"] == "msg-5"
        assert messages[-1]["content"] == "msg-24"

    def test_add_message_updates_thread_last_message_at(self, store):
        thread = store.create_thread(user_id="u1", view="topology")
        original_ts = thread["last_message_at"]

        time.sleep(0.01)  # ensure time advances
        store.add_message(thread["thread_id"], role="user", content="hello")

        updated = store.get_thread(thread["thread_id"])
        assert updated["last_message_at"] > original_ts
