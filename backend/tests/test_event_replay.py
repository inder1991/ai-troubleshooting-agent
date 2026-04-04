import asyncio
import os
import tempfile
import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_emitter_assigns_sequence_number_to_events():
    """After emit(), TaskEvent must have a sequence_number set."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        # Reset singleton
        import src.observability.store as store_module
        store_module._store = None

        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        from src.utils.event_emitter import EventEmitter
        emitter = EventEmitter(session_id="sess-replay", store=store)

        event1 = await emitter.emit("agent-a", "phase_change", "Starting")
        event2 = await emitter.emit("agent-a", "progress", "Working")

        assert event1.sequence_number is not None
        assert event2.sequence_number is not None
        assert event2.sequence_number > event1.sequence_number
    finally:
        os.unlink(db_path)
        import src.observability.store as store_module
        store_module._store = None
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)


@pytest.mark.asyncio
async def test_emitter_persists_events_to_store():
    """Events must be retrievable from the store after emit()."""
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

        from src.utils.event_emitter import EventEmitter
        emitter = EventEmitter(session_id="sess-persist", store=store)
        first_event = await emitter.emit("agent-x", "phase_change", "Event A")
        await emitter.emit("agent-x", "phase_change", "Event B")

        # Retrieve events after first (replay from sequence_number of Event A)
        events = await store.get_events("sess-persist", after_sequence=first_event.sequence_number - 1)
        assert any(e.get("message") == "Event B" for e in events)
    finally:
        os.unlink(db_path)
        import src.observability.store as store_module
        store_module._store = None
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ.pop("DIAGNOSTIC_DB_PATH", None)
