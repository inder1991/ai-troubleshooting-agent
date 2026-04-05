"""Verify agent error handling for LLM and tool call failures."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", [
    "src.agents.cluster.ctrl_plane_agent",
    "src.agents.cluster.node_agent",
    "src.agents.cluster.network_agent",
    "src.agents.cluster.storage_agent",
    "src.agents.cluster.rbac_agent",
])
async def test_llm_analyze_returns_fallback_on_exception(module_path):
    """_llm_analyze must catch LLM exceptions and return empty findings."""
    import importlib
    mod = importlib.import_module(module_path)
    fn = mod._llm_analyze

    with patch(f"{module_path}.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = Exception("API connection error")
        MockClient.return_value = mock_instance

        result = await fn("system prompt", "user prompt", session_id="test-123")

    assert isinstance(result, dict)
    assert result.get("anomalies") == []
    assert result.get("confidence") == 0
