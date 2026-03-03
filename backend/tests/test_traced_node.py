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
    # Use an agent node name so domain_reports are injected on failure
    @traced_node(timeout_seconds=0.1)
    async def node_agent(state, config):
        await asyncio.sleep(10)
        return {}
    result = await node_agent({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "FAILED"
    assert result["_trace"][0]["failure_reason"] == "TIMEOUT"
    # Verify error report is included in domain_reports
    assert "domain_reports" in result
    assert result["domain_reports"][0]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_traced_node_exception():
    # Use an agent node name so domain_reports are injected on failure
    @traced_node(timeout_seconds=5)
    async def storage_agent(state, config):
        raise ValueError("something broke")
    result = await storage_agent({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "FAILED"
    assert result["_trace"][0]["failure_reason"] == "EXCEPTION"
    # Verify error report is included in domain_reports
    assert "domain_reports" in result
    assert result["domain_reports"][0]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_traced_node_non_agent_no_domain_reports():
    """Non-agent nodes should NOT inject domain_reports on failure."""
    @traced_node(timeout_seconds=5)
    async def synthesizer(state, config):
        raise ValueError("infra failure")
    result = await synthesizer({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert isinstance(result["_trace"], list)
    assert result["_trace"][0]["status"] == "FAILED"
    # Non-agent nodes should not have domain_reports
    assert "domain_reports" not in result


def test_node_execution_model():
    execution = NodeExecution(node_name="ctrl_plane_agent", duration_ms=2340, failure_reason=None, status="SUCCESS")
    assert execution.node_name == "ctrl_plane_agent"
    assert execution.duration_ms == 2340
