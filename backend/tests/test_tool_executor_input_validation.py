"""Verify tool_executor validates input types."""
import json
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_input", [None, "string", 42, ["list"]])
async def test_bad_tool_input_returns_error(bad_input):
    """Non-dict tool_input must return a JSON error, not crash."""
    from src.agents.cluster.tool_executor import execute_tool_call
    result = await execute_tool_call("get_pods", bad_input, MagicMock(), 0)
    parsed = json.loads(result)
    assert "error" in parsed
