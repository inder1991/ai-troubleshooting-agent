import pytest
from unittest.mock import AsyncMock
from src.agents.cluster.graph_event_bridge import GraphEventBridge

@pytest.fixture
def mock_emitter():
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter

@pytest.mark.asyncio
async def test_bridge_agent_started(mock_emitter):
    bridge = GraphEventBridge(diagnostic_id="D-1", emitter=mock_emitter)
    await bridge.handle_event({"event": "on_chain_start", "name": "ctrl_plane_agent", "tags": [], "metadata": {}})
    mock_emitter.emit.assert_called_once()
    call_args = mock_emitter.emit.call_args
    assert call_args.kwargs.get("event_type") == "agent_started"

@pytest.mark.asyncio
async def test_bridge_drops_internal_events(mock_emitter):
    bridge = GraphEventBridge(diagnostic_id="D-1", emitter=mock_emitter)
    await bridge.handle_event({"event": "on_chain_start", "name": "RunnableSequence", "tags": [], "metadata": {}})
    mock_emitter.emit.assert_not_called()

@pytest.mark.asyncio
async def test_bridge_tool_events(mock_emitter):
    bridge = GraphEventBridge(diagnostic_id="D-1", emitter=mock_emitter)
    await bridge.handle_event({"event": "on_tool_start", "name": "list_nodes", "data": {"input": {"namespace": "default"}}, "tags": ["ctrl_plane"], "metadata": {}})
    mock_emitter.emit.assert_called_once()
    call_args = mock_emitter.emit.call_args
    assert call_args.kwargs.get("event_type") == "tool_call"
