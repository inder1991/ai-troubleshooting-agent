import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_tool_use_response(tool_name: str, input_dict: dict):
    """Simulate Anthropic response with a tool_use block."""
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    tool_use.name = tool_name
    tool_use.input = input_dict
    tool_use.id = "tu-123"

    response = MagicMock()
    response.content = [tool_use]
    response.text = ""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    response.usage = usage
    return response


def _make_text_response(text: str):
    """Simulate Anthropic response with text only (no tool use)."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.content = [text_block]
    response.text = text
    usage = MagicMock()
    usage.input_tokens = 50
    usage.output_tokens = 20
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_llm_analyze_parses_from_tool_input_not_text():
    """_llm_analyze must extract findings from tool_use.input, not response text."""
    from src.agents.cluster.ctrl_plane_agent import _llm_analyze

    expected_findings = {
        "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001",
                        "description": "DNS degraded", "evidence_ref": "op/dns",
                        "severity": "high"}],
        "ruled_out": ["etcd healthy"],
        "confidence": 75,
    }
    good_response = _make_tool_use_response("submit_domain_findings", expected_findings)

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_analyze("system", "prompt")

    assert result["confidence"] == 75
    assert result["anomalies"][0]["anomaly_id"] == "cp-001"
    # Verify it did NOT attempt string parsing (no text was in response)
    assert result != {"anomalies": [], "ruled_out": [], "confidence": 0}


@pytest.mark.asyncio
async def test_llm_analyze_falls_back_to_empty_when_tool_not_called():
    """_llm_analyze returns empty findings (not an exception) when LLM skips the tool."""
    from src.agents.cluster.ctrl_plane_agent import _llm_analyze

    text_only_response = _make_text_response("The cluster looks fine.")

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=text_only_response)
        result = await _llm_analyze("system", "prompt")

    assert result == {"anomalies": [], "ruled_out": [], "confidence": 0}


@pytest.mark.asyncio
async def test_tool_calling_loop_uses_submit_domain_findings_schema():
    """_tool_calling_loop must include SUBMIT_DOMAIN_FINDINGS_TOOL in the tools list."""
    from src.agents.cluster.ctrl_plane_agent import _tool_calling_loop
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL

    findings = {"anomalies": [], "ruled_out": ["all healthy"], "confidence": 90}
    submit_response = _make_tool_use_response("submit_domain_findings", findings)

    mock_client_instance = MagicMock()
    mock_cluster = MagicMock()

    captured_tools = []

    async def capture_chat_with_tools(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        return submit_response

    mock_client_instance.chat_with_tools = capture_chat_with_tools

    import os
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient", return_value=mock_client_instance):
        await _tool_calling_loop("system", "context", mock_cluster)

    tool_names = [t["name"] for t in captured_tools if isinstance(t, dict)]
    assert "submit_domain_findings" in tool_names, \
        f"Expected submit_domain_findings in tools list, got: {tool_names}"
