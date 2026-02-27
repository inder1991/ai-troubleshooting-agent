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
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_traced_node_timeout():
    @traced_node(timeout_seconds=0.1)
    async def slow_node(state, config):
        await asyncio.sleep(10)
        return {}
    result = await slow_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "FAILED"
    assert result["_trace"][0]["failure_reason"] == "TIMEOUT"
    # Verify error report is included in domain_reports
    assert "domain_reports" in result
    assert result["domain_reports"][0]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_traced_node_exception():
    @traced_node(timeout_seconds=5)
    async def bad_node(state, config):
        raise ValueError("something broke")
    result = await bad_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "FAILED"
    assert result["_trace"][0]["failure_reason"] == "EXCEPTION"
    # Verify error report is included in domain_reports
    assert "domain_reports" in result
    assert result["domain_reports"][0]["status"] == "FAILED"


def test_node_execution_model():
    execution = NodeExecution(node_name="ctrl_plane_agent", duration_ms=2340, failure_reason=None, status="SUCCESS")
    assert execution.node_name == "ctrl_plane_agent"
    assert execution.duration_ms == 2340
