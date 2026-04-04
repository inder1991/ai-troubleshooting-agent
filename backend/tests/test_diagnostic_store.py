import asyncio
import os
import tempfile
import pytest

pytestmark = pytest.mark.asyncio


async def test_sqlite_append_and_get_events():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        seq1 = await store.append_event("sess-1", {"type": "task_event", "message": "hello"})
        seq2 = await store.append_event("sess-1", {"type": "task_event", "message": "world"})
        assert seq2 > seq1

        events = await store.get_events("sess-1", after_sequence=0)
        assert len(events) == 2
        assert events[0]["message"] == "hello"
        assert events[1]["message"] == "world"

        events_after = await store.get_events("sess-1", after_sequence=seq1)
        assert len(events_after) == 1
        assert events_after[0]["message"] == "world"
    finally:
        os.unlink(db_path)
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)
        import src.observability.store as store_module
        store_module._store = None


async def test_sqlite_log_and_get_llm_calls():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        import time
        await store.log_llm_call({
            "session_id": "sess-2",
            "agent_name": "ctrl_plane",
            "model": "claude-haiku-4-5-20251001",
            "call_type": "tool_calling",
            "input_tokens": 100,
            "output_tokens": 50,
            "latency_ms": 200,
            "success": True,
            "error": None,
            "fallback_used": False,
            "response_json": {"anomalies": []},
            "created_at": time.time(),
        })

        calls = await store.get_llm_calls("sess-2")
        assert len(calls) == 1
        assert calls[0]["agent_name"] == "ctrl_plane"
        assert calls[0]["success"] is True
    finally:
        os.unlink(db_path)
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)
        import src.observability.store as store_module
        store_module._store = None


async def test_sqlite_delete_session():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        await store.append_event("sess-del", {"message": "x"})
        await store.log_llm_call({"session_id": "sess-del", "agent_name": "a", "model": "m",
                                   "call_type": "t", "input_tokens": 1, "output_tokens": 1,
                                   "latency_ms": 1, "success": True, "error": None,
                                   "fallback_used": False, "response_json": {}, "created_at": 1.0})

        await store.delete_session("sess-del")

        events = await store.get_events("sess-del")
        calls = await store.get_llm_calls("sess-del")
        assert events == []
        assert calls == []
    finally:
        os.unlink(db_path)
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)
        import src.observability.store as store_module
        store_module._store = None


async def test_factory_returns_sqlite_by_default():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None
        from src.observability.store import get_store
        store = get_store()
        assert "SQLite" in type(store).__name__
    finally:
        os.unlink(db_path)
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)
        import src.observability.store as store_module
        store_module._store = None
