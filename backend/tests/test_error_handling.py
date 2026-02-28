"""Tests for B7 (LLM timeouts) and B8 (sanitized error messages).

Covers:
- test_prom_error_no_internal_details: Prometheus errors don't leak URLs/hostnames
- test_es_error_no_internal_details: Elasticsearch errors don't leak URLs/hostnames
- test_critic_timeout_returns_default: Critic validate() and validate_delta() handle timeouts
- test_smart_path_timeout_returns_error: Smart path LLM timeout returns error response
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult
from src.agents.critic_agent import CriticAgent
from src.tools.investigation_router import InvestigationRouter
from src.tools.router_models import (
    InvestigateRequest, RouterContext, InvestigateResponse,
)
from src.models.schemas import (
    EvidencePin, Finding, DiagnosticState, TimeWindow,
)
# ── Helpers ──────────────────────────────────────────────────────────


def _make_context(**overrides):
    defaults = dict(
        active_namespace="payment-api",
        active_service="auth-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        session_id="test-session",
        incident_id="INC-TEST",
    )
    defaults.update(overrides)
    return RouterContext(**defaults)


def _make_pin(**overrides) -> EvidencePin:
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


# ── B8: Sanitized Error Messages ─────────────────────────────────────


class TestPromErrorNoInternalDetails:
    """B8: Prometheus errors must not expose internal URLs, hostnames, or stack traces."""

    @pytest.mark.asyncio
    async def test_prom_connection_error_sanitized(self):
        """ConnectionError with internal URL must not appear in client-facing fields."""
        executor = ToolExecutor(connection_config={"prometheus_url": "http://prom.internal:9090"})

        # Inject a mock client that raises a connection error with internal details
        mock_prom = MagicMock()
        mock_prom.query_range.side_effect = ConnectionError(
            "HTTPConnectionPool(host='prom.internal', port=9090): "
            "Max retries exceeded with url: /api/v1/query_range"
        )
        executor._prom_client = mock_prom

        result = await executor.execute("query_prometheus", {
            "query": "rate(http_requests_total[5m])",
            "range_minutes": 60,
        })

        assert result.success is False
        assert result.error == "Prometheus query failed"
        assert result.summary == "Prometheus query failed"
        # Verify no internal details leak
        assert "prom.internal" not in result.error
        assert "9090" not in result.error
        assert "HTTPConnectionPool" not in result.error
        assert "prom.internal" not in result.summary
        assert "prom.internal" not in result.raw_output

    @pytest.mark.asyncio
    async def test_prom_auth_error_sanitized(self):
        """Auth errors with token details must not leak to client."""
        executor = ToolExecutor(connection_config={"prometheus_url": "http://prom.internal:9090"})

        mock_prom = MagicMock()
        mock_prom.query_range.side_effect = Exception(
            "401 Unauthorized: Bearer token eyJhbGciOiJSUzI1NiIsInR5c... is expired"
        )
        executor._prom_client = mock_prom

        result = await executor.execute("query_prometheus", {
            "query": "up",
            "range_minutes": 5,
        })

        assert result.success is False
        assert result.error == "Prometheus query failed"
        assert "Bearer" not in result.error
        assert "eyJhbGci" not in result.error
        assert "Unauthorized" not in result.summary


class TestESErrorNoInternalDetails:
    """B8: Elasticsearch errors must not expose internal URLs or connection details."""

    @pytest.mark.asyncio
    async def test_es_connection_error_sanitized(self):
        """ConnectionError with Elasticsearch URL must not appear in client-facing fields."""
        executor = ToolExecutor(connection_config={"elasticsearch_url": "http://es.internal:9200"})

        mock_es = MagicMock()
        mock_es.search.side_effect = ConnectionError(
            "ConnectionError(http://es.internal:9200): "
            "Connection refused [Errno 111]"
        )
        executor._es_client = mock_es

        result = await executor.execute("search_logs", {
            "query": "error AND auth-service",
            "index": "app-logs-*",
        })

        assert result.success is False
        assert result.error == "Log search failed"
        assert result.summary == "Log search failed"
        # Verify no internal details leak
        assert "es.internal" not in result.error
        assert "9200" not in result.error
        assert "Connection refused" not in result.error
        assert "es.internal" not in result.summary
        assert "es.internal" not in result.raw_output

    @pytest.mark.asyncio
    async def test_es_index_error_sanitized(self):
        """Index-not-found errors must not leak index patterns or cluster info."""
        executor = ToolExecutor(connection_config={"elasticsearch_url": "http://es.internal:9200"})

        mock_es = MagicMock()
        mock_es.search.side_effect = Exception(
            "index_not_found_exception: no such index [app-logs-2026.02.28] "
            "on node [node-abc123.es.internal]"
        )
        executor._es_client = mock_es

        result = await executor.execute("search_logs", {
            "query": "timeout",
        })

        assert result.success is False
        assert result.error == "Log search failed"
        assert "node-abc123" not in result.error
        assert "es.internal" not in result.summary


# ── B7: Critic Timeout Returns Default ───────────────────────────────


class TestCriticTimeoutReturnsDefault:
    """B7: Critic LLM calls must time out gracefully and return sensible defaults."""

    @pytest.mark.asyncio
    async def test_validate_timeout_returns_insufficient_data(self):
        """validate() returns insufficient_data verdict when LLM times out."""
        mock_llm = AsyncMock()

        # Simulate a slow LLM that never resolves within timeout
        async def slow_chat(**kwargs):
            await asyncio.sleep(60)  # Much longer than 30s timeout

        mock_llm.chat = slow_chat

        critic = CriticAgent(llm_client=mock_llm)

        finding = Finding(
            finding_id="finding-1",
            agent_name="log_agent",
            category="error",
            summary="Auth service returning 500 errors",
            severity="high",
            confidence_score=85,
            breadcrumbs=[],
            negative_findings=[],
        )

        # Use a minimal DiagnosticState
        state = MagicMock(spec=DiagnosticState)
        state.log_analysis = None
        state.metrics_analysis = None
        state.k8s_analysis = None
        state.trace_analysis = None
        state.all_negative_findings = []

        # Patch the timeout to be very short for testing
        original_wait_for = asyncio.wait_for

        async def short_timeout_wait_for(coro, timeout):
            return await original_wait_for(coro, timeout=0.1)

        with patch("src.agents.critic_agent.asyncio.wait_for", side_effect=short_timeout_wait_for):
            verdict = await critic.validate(finding, state)

        assert verdict.verdict == "insufficient_data"
        assert verdict.confidence_in_verdict == 0
        assert "timed out" in verdict.reasoning.lower()

    @pytest.mark.asyncio
    async def test_validate_delta_timeout_returns_default_with_timeout_status(self):
        """validate_delta() returns timeout validation_status when LLM times out."""
        mock_llm = AsyncMock()

        async def slow_chat(**kwargs):
            await asyncio.sleep(60)

        mock_llm.chat = slow_chat

        critic = CriticAgent(llm_client=mock_llm)
        new_pin = _make_pin()

        original_wait_for = asyncio.wait_for

        async def short_timeout_wait_for(coro, timeout):
            return await original_wait_for(coro, timeout=0.1)

        with patch("src.agents.critic_agent.asyncio.wait_for", side_effect=short_timeout_wait_for):
            result = await critic.validate_delta(new_pin, existing_pins=[], causal_chains=[])

        assert result["validation_status"] == "pending_critic"
        assert "timed out" in result["reasoning"].lower()
        assert result["causal_role"] == "informational"
        assert isinstance(result["confidence"], float)

    @pytest.mark.asyncio
    async def test_validate_timeout_direct_asyncio_timeout_error(self):
        """validate() handles asyncio.TimeoutError raised directly by wait_for."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=asyncio.TimeoutError())

        critic = CriticAgent(llm_client=mock_llm)

        finding = Finding(
            finding_id="finding-2",
            agent_name="metrics_agent",
            category="memory",
            summary="Memory spike detected",
            severity="critical",
            confidence_score=90,
            breadcrumbs=[],
            negative_findings=[],
        )

        state = MagicMock(spec=DiagnosticState)
        state.log_analysis = None
        state.metrics_analysis = None
        state.k8s_analysis = None
        state.trace_analysis = None
        state.all_negative_findings = []

        # When asyncio.wait_for raises TimeoutError, it should be caught
        with patch("src.agents.critic_agent.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            verdict = await critic.validate(finding, state)

        assert verdict.verdict == "insufficient_data"
        assert verdict.confidence_in_verdict == 0
        assert "timed out" in verdict.reasoning.lower()


# ── B7: Smart Path Timeout Returns Error ─────────────────────────────


class TestSmartPathTimeoutReturnsError:
    """B7: Smart path LLM call must time out gracefully and return error response."""

    @pytest.mark.asyncio
    async def test_smart_path_timeout_returns_error_response(self):
        """Smart path returns error when LLM times out after 15s."""
        mock_executor = AsyncMock()
        mock_llm = AsyncMock()

        async def slow_chat(**kwargs):
            await asyncio.sleep(60)

        mock_llm.chat = slow_chat

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=mock_llm)

        request = InvestigateRequest(
            query="check the auth pod logs",
            context=_make_context(),
        )

        original_wait_for = asyncio.wait_for

        async def short_timeout_wait_for(coro, timeout):
            return await original_wait_for(coro, timeout=0.1)

        with patch("src.tools.investigation_router.asyncio.wait_for", side_effect=short_timeout_wait_for):
            response, pin = await router.route(request)

        assert response.status == "error"
        assert response.path_used == "smart"
        assert "timed out" in response.error.lower()
        assert pin is None
        # Executor should NOT have been called
        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_smart_path_timeout_direct(self):
        """Smart path handles asyncio.TimeoutError raised directly."""
        mock_executor = AsyncMock()
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=asyncio.TimeoutError())

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=mock_llm)

        request = InvestigateRequest(
            query="show me the pod status",
            context=_make_context(),
        )

        with patch("src.tools.investigation_router.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            response, pin = await router.route(request)

        assert response.status == "error"
        assert "timed out" in response.error.lower()
        assert pin is None
