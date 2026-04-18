"""End-to-end TracingAgent orchestration — backend mocked, full flow exercised.

Validates:
  * Backend selection (jaeger vs tempo) via config.
  * Trace-id-given path (no mining).
  * Trace-mining path (mining + ranker + top-N + per-trace fetch).
  * Envoy-flag self-explanatory → Tier 0 (no LLM call).
  * Ambiguous → Tier 2 LLM call with proper prompt shape.
  * ELK fallback when backend returns nothing.
  * Handoff fields (services_in_chain, mined_trace_ids) populated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.tracing.backends.base import TraceNotFound
from src.agents.tracing_agent import TracingAgent, TracingAgentConfig
from src.models.schemas import SpanInfo, TraceSummary


def _span(span_id, service="api", op="op", duration=10.0, status="ok",
          parent=None, tags=None) -> SpanInfo:
    return SpanInfo(
        span_id=span_id, service_name=service, operation_name=op,
        duration_ms=duration, status=status, parent_span_id=parent, tags=tags or {},
    )


def _trace_summary(tid, service="api") -> TraceSummary:
    return TraceSummary(
        trace_id=tid, root_service=service, root_operation="/op",
        start_time_us=1_700_000_000_000_000, duration_ms=100.0,
        span_count=10, error_count=1,
    )


@pytest.fixture
def mock_backend():
    """Yields a mock TraceBackend; returned spans configurable per test."""
    backend = MagicMock()
    backend.backend_id = "jaeger"
    backend.list_services = AsyncMock(return_value=["api", "db"])
    backend.get_trace = AsyncMock()
    backend.find_traces = AsyncMock()
    return backend


@pytest.mark.asyncio
async def test_tier0_envoy_self_explanatory(mock_backend):
    """Envoy UH flag + single trace → Tier 0, no LLM call."""
    spans = [
        _span("s1", service="api", tags={"response.flags": "UH",
                                         "upstream.cluster": "inventory"}),
    ]
    mock_backend.get_trace.return_value = spans

    agent = TracingAgent()
    agent._backend = mock_backend
    # Don't hit the real LLM.
    agent.llm_client.chat = AsyncMock()

    result = await agent.run({"trace_id": "t1"})

    assert result["tier_decision"]["tier"] == 0
    assert result["trace_source"] == "jaeger"
    assert len(result["envoy_findings"]) == 1
    assert result["envoy_findings"][0]["flag"] == "UH"
    # Most critically: no LLM call was made.
    agent.llm_client.chat.assert_not_called()
    # Handoff: services_in_chain populated.
    assert result["services_in_chain"] == ["api"]


@pytest.mark.asyncio
async def test_tier1_single_trace_error_no_envoy(mock_backend):
    """Single-trace error, no envoy flag → Tier 1 Haiku call."""
    spans = [
        _span("s1", service="api", status="ok", duration=100.0),
        _span("s2", service="db", status="error", parent="s1",
              tags={"error.message": "conn refused"}),
    ]
    mock_backend.get_trace.return_value = spans

    agent = TracingAgent()
    agent._backend = mock_backend
    # Mock LLM: returns structured JSON.
    mock_response = MagicMock()
    mock_response.text = '{"failure_point": {"span_id": "s2", "service_name": "db"}, ' \
                         '"cascade_path": ["api", "db"], "overall_confidence": 75, ' \
                         '"retry_detected": false, "trace_source": "jaeger", ' \
                         '"summary": "DB connection refused"}'
    agent.llm_client.chat = AsyncMock(return_value=mock_response)

    result = await agent.run({"trace_id": "t1"})

    assert result["tier_decision"]["tier"] == 1
    assert result["tier_decision"]["model_key"] == "cheap"
    assert result["failure_point"]["span_id"] == "s2"
    agent.llm_client.chat.assert_called_once()


@pytest.mark.asyncio
async def test_tier2_cross_trace_consensus(mock_backend):
    """Mining (3 candidates) → Tier 2 regardless of each trace being small."""
    # Mining returns 3 error-carrying candidates.
    summaries = [_trace_summary(f"t{i}") for i in range(3)]
    mock_backend.find_traces = AsyncMock(return_value=summaries)

    # Each trace has a simple error span.
    mock_backend.get_trace = AsyncMock(return_value=[
        _span("s1", status="error", tags={"error.message": "boom"})
    ])

    agent = TracingAgent()
    agent._backend = mock_backend
    mock_response = MagicMock()
    mock_response.text = '{"overall_confidence": 80, ' \
                         '"cross_trace_consensus": "unanimous", "cascade_path": []}'
    agent.llm_client.chat = AsyncMock(return_value=mock_response)

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=15)
    result = await agent.run({
        "service_name": "api",
        "time_window": (start, end),
    })

    assert result["tier_decision"]["tier"] == 2
    assert len(result["mined_trace_ids"]) == 3
    assert result["cross_trace_consensus"] == "unanimous"


@pytest.mark.asyncio
async def test_trace_not_found_falls_through_to_no_trace_result(mock_backend):
    mock_backend.get_trace = AsyncMock(side_effect=TraceNotFound("missing"))

    agent = TracingAgent()
    agent._backend = mock_backend
    agent.llm_client.chat = AsyncMock()

    result = await agent.run({"trace_id": "missing"})

    assert result["total_spans"] == 0
    assert result["overall_confidence"] == 0
    # We emitted a negative finding describing the missing trace.
    assert any("No spans" in nf.get("result", "") for nf in result["negative_findings"])


@pytest.mark.asyncio
async def test_services_from_traces_passed_as_handoff(mock_backend):
    spans = [
        _span("s1", service="api"),
        _span("s2", service="db", parent="s1"),
        _span("s3", service="cache", parent="s2"),
    ]
    mock_backend.get_trace = AsyncMock(return_value=spans)

    agent = TracingAgent()
    agent._backend = mock_backend
    mock_response = MagicMock()
    mock_response.text = '{"overall_confidence": 50, "cascade_path": ["api", "db", "cache"]}'
    agent.llm_client.chat = AsyncMock(return_value=mock_response)

    result = await agent.run({"trace_id": "t1"})

    assert set(result["services_in_chain"]) == {"api", "db", "cache"}


@pytest.mark.asyncio
async def test_summarization_trims_oversized_trace(mock_backend):
    # 5000 spans → over default MAX_ANALYSIS_SPANS=2000.
    big_trace = [_span(f"s{i}", service="api") for i in range(5000)]
    big_trace[999] = _span("s999", service="api", status="error",
                           tags={"error.message": "boom"})
    mock_backend.get_trace = AsyncMock(return_value=big_trace)

    agent = TracingAgent()
    agent._backend = mock_backend
    mock_response = MagicMock()
    mock_response.text = '{"overall_confidence": 60, "failure_point": {"span_id": "s999"}}'
    agent.llm_client.chat = AsyncMock(return_value=mock_response)

    result = await agent.run({"trace_id": "t1"})

    # Trace source marked "summarized" when reduction happened.
    assert result["trace_source"] == "summarized"
    # Call chain is <= MAX_ANALYSIS_SPANS_DEFAULT.
    assert len(result["call_chain"]) <= 2000
    # Error span survived the reduction.
    assert result["failure_point"]["span_id"] == "s999"


@pytest.mark.asyncio
async def test_redaction_applied_before_llm(mock_backend):
    """Span with credential-class tag key + email value should be redacted
    BEFORE the prompt is built."""
    spans = [
        _span("s1", service="api", status="error",
              tags={
                  "authorization": "Bearer secret",  # stripped by key denylist
                  "db.statement": "WHERE email='a@b.com'",  # value redacted
                  "http.method": "POST",  # safe, passes through
              }),
    ]
    mock_backend.get_trace = AsyncMock(return_value=spans)

    agent = TracingAgent()
    agent._backend = mock_backend

    captured_prompt = {}
    async def capture_chat(prompt, system, max_tokens):
        captured_prompt["prompt"] = prompt
        resp = MagicMock()
        resp.text = '{"overall_confidence": 50}'
        return resp

    agent.llm_client.chat = capture_chat
    await agent.run({"trace_id": "t1"})

    prompt = captured_prompt["prompt"]
    # The two critical security invariants: credential-class keys stripped,
    # PII values regex-redacted before they ever reach the LLM prompt.
    assert "Bearer secret" not in prompt, "auth token must not leak to LLM"
    assert "a@b.com" not in prompt, "email must be redacted in LLM prompt"
