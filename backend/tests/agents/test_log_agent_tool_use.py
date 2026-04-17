"""Task 1.10 — log_agent uses Anthropic tool-use for structured JSON output.

Replaces the regex-extract-JSON-from-free-text path in
``LogAnalysisAgent._parse_llm_response``. The model now declares its
analysis by calling ``submit_log_analysis`` exactly once; missing or
malformed calls raise ``StructuredOutputRequired`` instead of silently
defaulting fields.
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


def test_parse_log_analysis_from_tool_use():
    from src.agents.log_agent import _parse_log_analysis_from_response

    payload = {
        "primary_pattern": {"exception_type": "OOMKilled", "frequency": 12},
        "secondary_patterns": [{"exception_type": "NullPointer", "frequency": 3}],
        "overall_confidence": 84,
        "root_cause_hypothesis": "memory leak in order-service",
        "flow_analysis": "caller → order-service → DB",
        "patient_zero": {"service": "order-service"},
        "inferred_dependencies": [{"source": "checkout", "target": "order"}],
        "reasoning_chain": [{"step": 1, "observation": "x", "inference": "y"}],
        "suggested_promql_queries": [
            {"metric": "mem", "query": "q", "rationale": "r"}
        ],
    }
    resp = _tool_use_response("submit_log_analysis", payload)
    analysis = _parse_log_analysis_from_response(resp)
    assert analysis["primary_pattern"]["exception_type"] == "OOMKilled"
    assert analysis["overall_confidence"] == 84
    assert len(analysis["secondary_patterns"]) == 1
    # secondary_patterns must be capped at 5 per the prior contract.
    big_payload = dict(payload)
    big_payload["secondary_patterns"] = [
        {"exception_type": f"E{i}", "frequency": i} for i in range(10)
    ]
    resp2 = _tool_use_response("submit_log_analysis", big_payload)
    assert len(_parse_log_analysis_from_response(resp2)["secondary_patterns"]) == 5


def test_parse_log_analysis_raises_on_free_text():
    from src.agents.log_agent import _parse_log_analysis_from_response
    from src.agents.critic_agent import StructuredOutputRequired

    with pytest.raises(StructuredOutputRequired):
        _parse_log_analysis_from_response(_text_response('{"primary_pattern":{}}'))


def test_parse_log_analysis_raises_on_wrong_tool_name():
    from src.agents.log_agent import _parse_log_analysis_from_response
    from src.agents.critic_agent import StructuredOutputRequired

    with pytest.raises(StructuredOutputRequired):
        _parse_log_analysis_from_response(
            _tool_use_response("some_other_tool", {"primary_pattern": {}})
        )


def test_parse_log_analysis_raises_on_missing_required_field():
    """overall_confidence is required by the tool schema — absence must
    surface loudly rather than default to 50."""
    from src.agents.log_agent import _parse_log_analysis_from_response
    from src.agents.critic_agent import StructuredOutputRequired

    bad = {"primary_pattern": {}, "secondary_patterns": []}  # no overall_confidence
    with pytest.raises(StructuredOutputRequired):
        _parse_log_analysis_from_response(_tool_use_response("submit_log_analysis", bad))


def test_log_analysis_tool_schema_is_exported_and_well_formed():
    from src.agents.log_agent import _LOG_ANALYSIS_TOOL_SCHEMA, _LOG_ANALYSIS_TOOL_NAME

    assert _LOG_ANALYSIS_TOOL_SCHEMA["name"] == _LOG_ANALYSIS_TOOL_NAME
    assert _LOG_ANALYSIS_TOOL_SCHEMA["input_schema"]["type"] == "object"
    required = set(_LOG_ANALYSIS_TOOL_SCHEMA["input_schema"]["required"])
    assert {"primary_pattern", "overall_confidence", "root_cause_hypothesis"} <= required
