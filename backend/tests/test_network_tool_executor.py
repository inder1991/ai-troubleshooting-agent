# backend/tests/test_network_tool_executor.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.network.tool_executor import NetworkToolExecutor


@pytest.fixture
def executor():
    return NetworkToolExecutor()


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, executor):
        result = await executor.execute("nonexistent_tool", {})
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_execute_get_top_talkers(self, executor):
        mock_data = [{"src": "10.0.0.1", "dst": "10.0.0.2", "bytes": 1000}]
        with patch.object(executor, "_call_flow_api", new_callable=AsyncMock, return_value=mock_data):
            result = await executor.execute("get_top_talkers", {"window": "5m", "limit": 10})
            parsed = json.loads(result)
            assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_execute_summarize_context(self, executor):
        result = await executor.execute("summarize_context", {})
        parsed = json.loads(result)
        assert "message" in parsed

    @pytest.mark.asyncio
    async def test_execute_start_investigation(self, executor):
        result = await executor.execute("start_investigation", {"reason": "cross-domain issue"})
        parsed = json.loads(result)
        assert parsed["action"] == "escalate"

    @pytest.mark.asyncio
    async def test_execution_error_returns_error_json(self, executor):
        with patch.object(executor, "_call_flow_api", new_callable=AsyncMock, side_effect=Exception("connection refused")):
            result = await executor.execute("get_top_talkers", {"window": "5m"})
            parsed = json.loads(result)
            assert "error" in parsed
