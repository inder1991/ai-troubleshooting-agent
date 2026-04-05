"""Tests for synthesizer prompt construction."""
import inspect
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.cluster.synthesizer import (
    _build_bounded_causal_prompt,
    _llm_causal_reasoning,
    CAUSAL_RULES,
    CONSTRAINED_LINK_TYPES,
)


def test_causal_rules_included_in_system_prompt():
    """CAUSAL_RULES must appear in the synthesizer system prompt."""
    # Verify all 6 rules are present in the constant
    assert "TEMPORAL" in CAUSAL_RULES
    assert "MECHANISM" in CAUSAL_RULES
    assert "DOMAIN BOUNDARY" in CAUSAL_RULES
    assert "SINGLE ROOT" in CAUSAL_RULES
    assert "WEAKEST LINK" in CAUSAL_RULES
    assert "OBSERVABILITY CONFIRMATION" in CAUSAL_RULES
    assert len(CONSTRAINED_LINK_TYPES) > 5

    # Verify _llm_causal_reasoning actually references CAUSAL_RULES and CONSTRAINED_LINK_TYPES
    source = inspect.getsource(_llm_causal_reasoning)
    assert "CAUSAL_RULES" in source, "_llm_causal_reasoning must reference CAUSAL_RULES"
    assert "CONSTRAINED_LINK_TYPES" in source, "_llm_causal_reasoning must reference CONSTRAINED_LINK_TYPES"


@pytest.mark.asyncio
async def test_causal_rules_injected_into_llm_system_prompt():
    """Verify CAUSAL_RULES and CONSTRAINED_LINK_TYPES are sent to the LLM in the system prompt."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "submit_causal_analysis"
    tool_block.input = {
        "causal_chains": [],
        "uncorrelated_findings": [],
    }
    mock_response = MagicMock()
    mock_response.content = [tool_block]
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)

    mock_client = MagicMock()
    mock_client.chat_with_tools = AsyncMock(return_value=mock_response)

    anomalies = [MagicMock(
        model_dump=MagicMock(return_value={
            "domain": "node", "anomaly_id": "n-001",
            "description": "DiskPressure", "severity": "high",
        }),
    )]
    reports = []

    with patch("src.agents.cluster.synthesizer.AnthropicClient", return_value=mock_client):
        await _llm_causal_reasoning(anomalies, reports)

    mock_client.chat_with_tools.assert_called_once()
    system_arg = mock_client.chat_with_tools.call_args.kwargs.get(
        "system", mock_client.chat_with_tools.call_args[1].get("system", "")
    )
    # All 6 causal rules must be in the system prompt
    assert "TEMPORAL" in system_arg
    assert "MECHANISM" in system_arg
    assert "DOMAIN BOUNDARY" in system_arg
    assert "SINGLE ROOT" in system_arg
    assert "WEAKEST LINK" in system_arg
    assert "OBSERVABILITY CONFIRMATION" in system_arg
    # CONSTRAINED_LINK_TYPES entries must be present
    for lt in CONSTRAINED_LINK_TYPES:
        assert lt in system_arg, f"Link type '{lt}' missing from system prompt"


def test_bounded_prompt_includes_anomalies():
    anomalies = [{"domain": "node", "anomaly_id": "n-001", "description": "DiskPressure", "severity": "high"}]
    reports = []
    prompt = _build_bounded_causal_prompt(anomalies, reports, {}, [])
    assert "DiskPressure" in prompt
    assert "Anomalies Found" in prompt


def test_bounded_prompt_includes_ruled_out():
    """ruled_out from domain reports must be included in synthesizer prompt."""
    from unittest.mock import MagicMock
    report = MagicMock()
    report.domain = "node"
    report.status = MagicMock(value="SUCCESS")
    report.confidence = 85
    report.anomalies = []
    report.ruled_out = ["etcd healthy", "API server responsive"]
    report.truncation_flags = MagicMock(events=False, pods=False, nodes=False)

    anomalies = [{"domain": "node", "anomaly_id": "n-001", "description": "test", "severity": "high"}]
    prompt = _build_bounded_causal_prompt(anomalies, [report], {}, [])
    assert "etcd healthy" in prompt
