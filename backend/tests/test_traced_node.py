import asyncio
import pytest
from src.agents.cluster.traced_node import traced_node, NodeExecution
from src.agents.cluster.state import FailureReason


@pytest.mark.asyncio
async def test_traced_node_success():
    @traced_node(timeout_seconds=5)
    async def my_node(state, config):
        return {"domain_reports": [{"domain": "test", "status": "SUCCESS"}]}
    result = await my_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert "domain_reports" in result
    assert result["_trace"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_traced_node_timeout():
    @traced_node(timeout_seconds=0.1)
    async def slow_node(state, config):
        await asyncio.sleep(10)
        return {}
    result = await slow_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert result["_trace"]["status"] == "FAILED"
    assert result["_trace"]["failure_reason"] == "TIMEOUT"


@pytest.mark.asyncio
async def test_traced_node_exception():
    @traced_node(timeout_seconds=5)
    async def bad_node(state, config):
        raise ValueError("something broke")
    result = await bad_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert result["_trace"]["status"] == "FAILED"
    assert result["_trace"]["failure_reason"] == "EXCEPTION"


def test_node_execution_model():
    execution = NodeExecution(node_name="ctrl_plane_agent", duration_ms=2340, failure_reason=None, status="SUCCESS")
    assert execution.node_name == "ctrl_plane_agent"
    assert execution.duration_ms == 2340
