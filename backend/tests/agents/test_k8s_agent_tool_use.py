"""Task 1.10 — k8s_agent uses Anthropic tool-use for structured JSON output.

Mirrors the log_agent change: the model must call
``submit_k8s_analysis`` exactly once with the required structured
fields; free text or an off-schema call raises StructuredOutputRequired.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _tool_use_response(name: str, input_payload: dict):
    block = SimpleNamespace(type="tool_use", name=name, input=input_payload, id="toolu_x")
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=5, output_tokens=10),
        stop_reason="tool_use",
    )


def _text_response(text: str):
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=5, output_tokens=5),
        stop_reason="end_turn",
    )


def test_parse_k8s_analysis_from_tool_use():
    from src.agents.k8s_agent import _parse_k8s_analysis_from_response

    payload = {
        "pod_statuses": [{"pod": "order-abc", "status": "Running"}],
        "events": [{"type": "Warning", "reason": "BackOff"}],
        "is_crashloop": False,
        "total_restarts_last_hour": 3,
        "resource_mismatch": None,
        "overall_confidence": 72,
    }
    analysis = _parse_k8s_analysis_from_response(
        _tool_use_response("submit_k8s_analysis", payload)
    )
    assert analysis["is_crashloop"] is False
    assert analysis["total_restarts_last_hour"] == 3
    assert analysis["overall_confidence"] == 72


def test_parse_k8s_analysis_raises_on_free_text():
    from src.agents.k8s_agent import _parse_k8s_analysis_from_response
    from src.agents.critic_agent import StructuredOutputRequired

    with pytest.raises(StructuredOutputRequired):
        _parse_k8s_analysis_from_response(_text_response('{"is_crashloop":true}'))


def test_parse_k8s_analysis_raises_on_missing_required_field():
    from src.agents.k8s_agent import _parse_k8s_analysis_from_response
    from src.agents.critic_agent import StructuredOutputRequired

    # overall_confidence missing
    bad = {"pod_statuses": [], "events": [], "is_crashloop": False}
    with pytest.raises(StructuredOutputRequired):
        _parse_k8s_analysis_from_response(_tool_use_response("submit_k8s_analysis", bad))


def test_k8s_analysis_tool_schema_is_exported_and_well_formed():
    from src.agents.k8s_agent import _K8S_ANALYSIS_TOOL_SCHEMA, _K8S_ANALYSIS_TOOL_NAME

    assert _K8S_ANALYSIS_TOOL_SCHEMA["name"] == _K8S_ANALYSIS_TOOL_NAME
    required = set(_K8S_ANALYSIS_TOOL_SCHEMA["input_schema"]["required"])
    assert {"is_crashloop", "overall_confidence"} <= required
