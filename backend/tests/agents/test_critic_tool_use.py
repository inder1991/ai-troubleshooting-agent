"""Task 1.9 — Critic agent uses Anthropic tool-use for structured verdicts.

Regex extraction from free-text LLM replies has an error rate we can't
accept for a component that gates whether a finding reaches the user.
Instead, the critic declares a ``submit_critic_verdict`` tool and
forces the model to call it (``tool_choice=submit_critic_verdict``).
The schema validates fields at the SDK layer; if the model does
return free text, we raise ``StructuredOutputRequired`` rather than
guess.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.models.schemas import Finding, DiagnosticState, DiagnosticPhase, TimeWindow


def _make_state() -> DiagnosticState:
    return DiagnosticState(
        session_id="s1",
        phase=DiagnosticPhase.VALIDATING,
        service_name="svc-a",
        time_window=TimeWindow(start="now-1h", end="now"),
    )


def _fake_tool_use_response(name: str, input_payload: dict):
    """Build a minimal stand-in for an Anthropic Messages.create response
    containing exactly one tool_use block, matching the SDK's content shape."""
    tool_block = SimpleNamespace(
        type="tool_use", name=name, input=input_payload, id="toolu_test"
    )
    return SimpleNamespace(
        content=[tool_block],
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        stop_reason="tool_use",
    )


def _fake_text_response(text: str):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        stop_reason="end_turn",
    )


def _make_finding() -> Finding:
    return Finding(
        finding_id="log_agent_1",
        agent_name="log_agent",
        category="database",
        summary="Database is down",
        confidence_score=70,
        severity="high",
        breadcrumbs=[],
        negative_findings=[],
    )


@pytest.mark.asyncio
async def test_critic_returns_structured_verdict_from_tool_use():
    from src.agents.critic_agent import CriticAgent

    payload = {
        "verdict": "challenged",
        "confidence": 55,
        "reasoning": "metrics contradict the finding",
        "contradictions": ["db_cpu metric healthy at 18%"],
    }

    llm = AsyncMock()
    llm.chat_with_tools = AsyncMock(
        return_value=_fake_tool_use_response("submit_critic_verdict", payload)
    )

    critic = CriticAgent(llm_client=llm)
    verdict = await critic.validate(_make_finding(), _make_state())

    assert verdict.verdict == "challenged"
    assert verdict.confidence_in_verdict == 55
    assert "metrics contradict" in verdict.reasoning
    # chat_with_tools was called with forced tool_choice.
    _, kwargs = llm.chat_with_tools.call_args
    tools = kwargs["tools"]
    assert any(t["name"] == "submit_critic_verdict" for t in tools)


@pytest.mark.asyncio
async def test_critic_raises_when_model_returns_free_text():
    """If the LLM returns free text instead of a tool_use block, the
    critic refuses to guess; it must raise so the caller can retry or
    log and move on rather than silently falling back to a default
    verdict."""
    from src.agents.critic_agent import CriticAgent, StructuredOutputRequired

    llm = AsyncMock()
    llm.chat_with_tools = AsyncMock(
        return_value=_fake_text_response("I think this is validated because ...")
    )

    critic = CriticAgent(llm_client=llm)
    with pytest.raises(StructuredOutputRequired):
        await critic.validate(_make_finding(), _make_state())


@pytest.mark.asyncio
async def test_critic_raises_when_tool_input_violates_schema():
    """If somehow the model returns a tool_use block with out-of-range
    or missing required fields, we should raise rather than silently
    sanitising to defaults."""
    from src.agents.critic_agent import CriticAgent, StructuredOutputRequired

    llm = AsyncMock()
    llm.chat_with_tools = AsyncMock(
        return_value=_fake_tool_use_response(
            "submit_critic_verdict",
            # verdict is invalid enum value
            {"verdict": "maybe", "confidence": 50, "reasoning": "x"},
        )
    )

    critic = CriticAgent(llm_client=llm)
    with pytest.raises(StructuredOutputRequired):
        await critic.validate(_make_finding(), _make_state())


@pytest.mark.asyncio
async def test_critic_timeout_still_returns_insufficient_data_verdict():
    """Timeout is an operational error path distinct from structured
    output failure — the critic reports an ``insufficient_data`` verdict
    with a reasoning string explaining the timeout rather than raising,
    so the investigation flow continues without this critic's input."""
    import asyncio

    from src.agents.critic_agent import CriticAgent

    llm = AsyncMock()
    llm.chat_with_tools = AsyncMock(side_effect=asyncio.TimeoutError())

    critic = CriticAgent(llm_client=llm)
    verdict = await critic.validate(_make_finding(), _make_state())
    assert verdict.verdict == "insufficient_data"
    assert "timed out" in verdict.reasoning.lower()
