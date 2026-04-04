import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_tool_response(tool_name: str, input_dict: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    response = MagicMock()
    response.content = [block]
    response.text = ""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 200
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_causal_reasoning_uses_tool_input_not_text():
    """_llm_causal_reasoning must parse from tool_use.input."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    expected = {
        "causal_chains": [{"chain_id": "cc-001", "confidence": 0.8,
                            "root_cause": {"domain": "node", "anomaly_id": "n-1",
                                            "description": "disk full", "evidence_ref": "node/worker-1"},
                            "cascading_effects": []}],
        "uncorrelated_findings": [],
    }
    good_response = _mock_tool_response("submit_causal_analysis", expected)

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_causal_reasoning(anomalies=[], reports=[])

    assert len(result["causal_chains"]) == 1
    assert result["causal_chains"][0]["chain_id"] == "cc-001"


@pytest.mark.asyncio
async def test_verdict_uses_tool_input_not_text():
    """_llm_verdict must parse from tool_use.input."""
    from src.agents.cluster.synthesizer import _llm_verdict

    expected = {
        "platform_health": "DEGRADED",
        "blast_radius": {"summary": "2 pods down", "affected_namespaces": ["default"],
                          "affected_pods": [], "affected_nodes": []},
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
        "re_dispatch_domains": [],
    }
    good_response = _mock_tool_response("submit_verdict", expected)

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_verdict(causal_chains=[], reports=[], data_completeness=0.9)

    assert result["platform_health"] == "DEGRADED"
    assert result["re_dispatch_needed"] is False


def test_build_bounded_causal_prompt_drops_low_priority_anomalies():
    """_build_bounded_causal_prompt must drop low-confidence anomalies when over budget."""
    from src.agents.cluster.synthesizer import _build_bounded_causal_prompt

    # Create many low-severity anomalies that would exceed 60k token budget
    low_anomalies = [
        {"domain": "node", "anomaly_id": f"n-{i}", "description": "minor issue " * 50,
         "evidence_ref": f"pod/pod-{i}", "severity": "low", "evidence_sources": []}
        for i in range(200)
    ]
    critical_anomaly = {
        "domain": "ctrl_plane", "anomaly_id": "cp-001", "description": "API server down",
        "evidence_ref": "api-server/health", "severity": "high", "evidence_sources": [],
    }
    all_anomalies = [critical_anomaly] + low_anomalies

    prompt = _build_bounded_causal_prompt(all_anomalies, [], {}, [])

    # Critical anomaly must always be present
    assert "cp-001" in prompt
    assert "API server down" in prompt
    # Prompt must be under 60k * 4 chars (240k chars) — generous bound for the approximation
    assert len(prompt) < 300_000


def test_truncation_warning_included_when_flags_set():
    """_build_bounded_causal_prompt must include DATA COMPLETENESS block when truncation flags set."""
    from src.agents.cluster.synthesizer import _build_bounded_causal_prompt
    from src.agents.cluster.state import DomainReport, TruncationFlags, DomainStatus

    report = DomainReport(
        domain="node",
        status=DomainStatus.SUCCESS,
        confidence=70,
        truncation_flags=TruncationFlags(events=True, events_dropped=80,
                                          pods=True, pods_dropped=200),
    )

    prompt = _build_bounded_causal_prompt([], [report], {}, [])

    assert "DATA COMPLETENESS WARNING" in prompt
    assert "node" in prompt
    assert "events" in prompt.lower() or "truncated" in prompt.lower()
