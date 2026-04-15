"""Verify synthesizer LLM functions handle non-timeout exceptions."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_causal_reasoning_handles_generic_exception():
    """_llm_causal_reasoning must not crash on non-timeout LLM errors."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = RuntimeError("API connection reset")
        MockClient.return_value = mock_instance

        result = await _llm_causal_reasoning(anomalies=[], reports=reports)

    assert isinstance(result, dict)
    assert "causal_chains" in result
    assert result["causal_chains"] == []


@pytest.mark.asyncio
async def test_verdict_handles_generic_exception():
    """_llm_verdict must not crash on non-timeout LLM errors."""
    from src.agents.cluster.synthesizer import _llm_verdict
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.chat_with_tools.side_effect = RuntimeError("API connection reset")
        MockClient.return_value = mock_instance

        result = await _llm_verdict(causal_chains=[], reports=reports, data_completeness=1.0)

    assert isinstance(result, dict)
    assert result["platform_health"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_causal_reasoning_handles_none_usage():
    """_llm_causal_reasoning must not crash when response.usage is None."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning
    from src.agents.cluster.state import DomainReport, DomainStatus

    reports = [DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=80, anomalies=[], ruled_out=[], evidence_refs=[])]

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        mock_instance = AsyncMock()
        response = MagicMock()
        response.usage = None
        response.content = []
        mock_instance.chat_with_tools = AsyncMock(return_value=response)
        MockClient.return_value = mock_instance

        budget = MagicMock()
        budget.remaining_budget_pct.return_value = 0.8
        result = await _llm_causal_reasoning(anomalies=[], reports=reports, budget=budget)

    assert isinstance(result, dict)
