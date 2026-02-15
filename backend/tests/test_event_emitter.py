import pytest
from unittest.mock import AsyncMock
from src.utils.event_emitter import EventEmitter


@pytest.mark.asyncio
async def test_emit_task_event():
    mock_ws = AsyncMock()
    emitter = EventEmitter(session_id="test-123", websocket_manager=mock_ws)
    event = await emitter.emit("log_agent", "started", "Querying Elasticsearch...")
    mock_ws.send_message.assert_called_once()
    call_args = mock_ws.send_message.call_args
    assert call_args[0][0] == "test-123"
    msg = call_args[0][1]
    assert msg["type"] == "task_event"
    assert msg["data"]["agent_name"] == "log_agent"
    assert msg["data"]["event_type"] == "started"
    assert msg["data"]["message"] == "Querying Elasticsearch..."


@pytest.mark.asyncio
async def test_emit_collects_events():
    mock_ws = AsyncMock()
    emitter = EventEmitter(session_id="test-123", websocket_manager=mock_ws)
    await emitter.emit("log_agent", "started", "Starting analysis")
    await emitter.emit("log_agent", "success", "Found 847 entries")
    assert len(emitter.get_all_events()) == 2


@pytest.mark.asyncio
async def test_emit_without_websocket():
    emitter = EventEmitter(session_id="test-123")  # no ws manager
    event = await emitter.emit("log_agent", "started", "Starting")
    assert event.agent_name == "log_agent"
    assert len(emitter.get_all_events()) == 1


@pytest.mark.asyncio
async def test_emit_with_details():
    mock_ws = AsyncMock()
    emitter = EventEmitter(session_id="test-123", websocket_manager=mock_ws)
    event = await emitter.emit("log_agent", "progress", "Found patterns", details={"count": 4})
    assert event.details == {"count": 4}


@pytest.mark.asyncio
async def test_get_events_by_agent():
    emitter = EventEmitter(session_id="test-123")
    await emitter.emit("log_agent", "started", "Log started")
    await emitter.emit("metrics_agent", "started", "Metrics started")
    await emitter.emit("log_agent", "success", "Log done")
    log_events = emitter.get_events_by_agent("log_agent")
    assert len(log_events) == 2
    metrics_events = emitter.get_events_by_agent("metrics_agent")
    assert len(metrics_events) == 1
