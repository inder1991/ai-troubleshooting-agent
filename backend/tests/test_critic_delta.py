"""Tests for CriticAgent.validate_delta — delta revalidation of manual evidence pins."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.agents.critic_agent import CriticAgent
from src.models.schemas import EvidencePin
from src.utils.llm_client import LLMResponse


def _make_pin(**overrides) -> EvidencePin:
    """Helper to create an EvidencePin with sensible defaults."""
    defaults = dict(
        id="pin-new",
        claim="OOMKilled detected in auth-service pod",
        source_tool="fetch_pod_logs",
        confidence=0.85,
        timestamp=datetime.now(timezone.utc),
        evidence_type="log",
        source="manual",
        triggered_by="user_chat",
        severity="critical",
        domain="compute",
        validation_status="pending_critic",
        causal_role=None,
    )
    defaults.update(overrides)
    return EvidencePin(**defaults)


# ---------- validate_delta tests ----------


@pytest.mark.asyncio
async def test_validates_manual_pin():
    """LLM returns validated + cascading_symptom -> result dict reflects that."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "validation_status": "validated",
            "causal_role": "cascading_symptom",
            "confidence": 0.9,
            "reasoning": "Consistent with existing OOM evidence from k8s agent.",
            "contradictions": [],
        }),
        input_tokens=100,
        output_tokens=50,
    ))

    critic = CriticAgent(llm_client=mock_llm)

    new_pin = _make_pin()
    existing_pins = [
        _make_pin(id="pin-exist-1", claim="Memory usage at 95%", source_tool="query_prometheus"),
        _make_pin(id="pin-exist-2", claim="Pod restarted 3 times", source_tool="describe_resource"),
    ]

    result = await critic.validate_delta(new_pin, existing_pins, causal_chains=[])

    assert result["validation_status"] == "validated"
    assert result["causal_role"] == "cascading_symptom"
    assert result["confidence"] == 0.9
    assert result["reasoning"] == "Consistent with existing OOM evidence from k8s agent."
    assert result["contradictions"] == []

    # Verify LLM was called once
    mock_llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_handles_llm_parse_error():
    """LLM returns non-JSON -> graceful fallback with defaults."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=LLMResponse(
        text="I cannot parse this as JSON, here is some free text instead.",
        input_tokens=100,
        output_tokens=50,
    ))

    critic = CriticAgent(llm_client=mock_llm)

    new_pin = _make_pin()
    result = await critic.validate_delta(new_pin, existing_pins=[], causal_chains=[])

    # Should fallback gracefully
    assert result["validation_status"] == "validated"
    assert result["causal_role"] == "informational"
    assert isinstance(result["confidence"], float)
    assert isinstance(result["reasoning"], str)
    assert isinstance(result["contradictions"], list)


@pytest.mark.asyncio
async def test_handles_empty_existing_pins():
    """Empty existing_pins list -> still works, LLM is called."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "validation_status": "validated",
            "causal_role": "informational",
            "confidence": 0.7,
            "reasoning": "No existing evidence to compare against. Accepting as informational.",
            "contradictions": [],
        }),
        input_tokens=80,
        output_tokens=40,
    ))

    critic = CriticAgent(llm_client=mock_llm)
    new_pin = _make_pin()

    result = await critic.validate_delta(new_pin, existing_pins=[], causal_chains=[])

    assert result["validation_status"] == "validated"
    assert result["causal_role"] == "informational"
    mock_llm.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_handles_llm_exception():
    """LLM raises an exception -> graceful fallback."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(side_effect=Exception("API timeout"))

    critic = CriticAgent(llm_client=mock_llm)
    new_pin = _make_pin()

    result = await critic.validate_delta(new_pin, existing_pins=[], causal_chains=[])

    assert result["validation_status"] == "validated"
    assert result["causal_role"] == "informational"
    assert isinstance(result["reasoning"], str)


def test_backward_compatible_constructor():
    """CriticAgent() still works without llm_client arg (backward compat)."""
    critic = CriticAgent()
    assert critic.agent_name == "critic"
    assert critic.llm_client is not None


def test_injected_llm_client_used():
    """When llm_client is passed, it is used instead of creating AnthropicClient."""
    mock_llm = MagicMock()
    critic = CriticAgent(llm_client=mock_llm)
    assert critic.llm_client is mock_llm


@pytest.mark.asyncio
async def test_llm_returns_json_with_extra_text():
    """LLM wraps JSON in markdown code fence -> still parsed correctly."""
    mock_llm = AsyncMock()
    mock_llm.chat = AsyncMock(return_value=LLMResponse(
        text='Here is my analysis:\n```json\n{"validation_status": "rejected", "causal_role": "correlated", "confidence": 0.4, "reasoning": "Contradicts network timeline.", "contradictions": ["Timeline mismatch"]}\n```',
        input_tokens=100,
        output_tokens=60,
    ))

    critic = CriticAgent(llm_client=mock_llm)
    new_pin = _make_pin()

    result = await critic.validate_delta(new_pin, existing_pins=[], causal_chains=[])

    assert result["validation_status"] == "rejected"
    assert result["causal_role"] == "correlated"
    assert result["contradictions"] == ["Timeline mismatch"]
