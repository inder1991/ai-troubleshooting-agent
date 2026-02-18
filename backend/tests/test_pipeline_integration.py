"""End-to-end integration tests for the agent → supervisor → API pipeline.

Verifies that every field produced by log_agent and metrics_agent flows through
the supervisor's _update_state_with_result() into state, and is exposed by the
/findings API endpoint. No data should be silently dropped.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.agents.supervisor import SupervisorAgent
from src.models.schemas import (
    DiagnosticState, DiagnosticPhase, TimeWindow, TokenUsage,
    MetricAnomaly, MetricsAnalysisResult, LogAnalysisResult,
    ErrorPattern, CorrelatedSignalGroup, EventMarker,
)


def _make_state(**overrides) -> DiagnosticState:
    defaults = dict(
        session_id="int-test-001",
        phase=DiagnosticPhase.INITIAL,
        service_name="order-service",
        time_window=TimeWindow(start="now-1h", end="now"),
    )
    defaults.update(overrides)
    return DiagnosticState(**defaults)


# ---------------------------------------------------------------------------
# 1. Log Agent → Supervisor integration
# ---------------------------------------------------------------------------

class TestLogAgentPipeline:
    """Verify every field from log_agent's run() output is consumed by supervisor."""

    LOG_AGENT_RESULT = {
        "primary_pattern": {
            "pattern_id": "p1",
            "exception_type": "ConnectionTimeout",
            "error_message": "Timed out after 30s calling payment-service",
            "frequency": 47,
            "severity": "critical",
            "affected_components": ["checkout-service", "payment-service"],
            "confidence_score": 87,
            "priority_rank": 1,
            "priority_reasoning": "High frequency timeout in critical path",
        },
        "secondary_patterns": [
            {
                "pattern_id": "s1",
                "exception_type": "NullPointerException",
                "error_message": "Null ref at UserService.java:42",
                "frequency": 5,
                "severity": "medium",
                "affected_components": ["user-service"],
                "confidence_score": 60,
                "priority_rank": 2,
                "priority_reasoning": "Lower frequency, may be secondary",
            },
        ],
        "overall_confidence": 82,
        "breadcrumbs": [
            {
                "agent_name": "log_agent",
                "action": "searched_elasticsearch",
                "source_type": "log",
                "source_reference": "app-logs-2025.01",
                "raw_evidence": "Found 47 error logs",
                "timestamp": "2025-12-26T14:00:00Z",
            },
        ],
        "negative_findings": [
            {
                "agent_name": "log_agent",
                "what_was_checked": "Memory error patterns",
                "result": "No OOM or memory-related errors found",
                "implication": "Memory is likely not the issue",
                "source_reference": "app-logs-2025.01",
            },
        ],
        "tokens_used": {
            "agent_name": "log_agent",
            "input_tokens": 1500,
            "output_tokens": 800,
            "total_tokens": 2300,
        },
        "service_flow": [
            {"service": "api-gateway", "timestamp": "2025-12-26T14:00:01Z", "operation": "GET /checkout", "status": "ok", "status_detail": "200", "message": "", "is_new_service": True},
            {"service": "checkout-service", "timestamp": "2025-12-26T14:00:02Z", "operation": "processOrder", "status": "error", "status_detail": "ConnectionTimeout", "message": "Timed out", "is_new_service": True},
        ],
        "flow_source": "elasticsearch",
        "flow_confidence": 70,
        "evidence_pins": [],
        "raw_logs_count": 200,
        "patterns_found": 3,
    }

    @pytest.mark.asyncio
    async def test_log_analysis_populated(self):
        """state.log_analysis must be populated with primary and secondary patterns."""
        supervisor = SupervisorAgent()
        state = _make_state()

        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        assert state.log_analysis is not None, "state.log_analysis was not populated"
        assert isinstance(state.log_analysis, LogAnalysisResult)

    @pytest.mark.asyncio
    async def test_primary_pattern_fields(self):
        """Primary pattern must retain all fields from agent output."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        pp = state.log_analysis.primary_pattern
        assert pp.exception_type == "ConnectionTimeout"
        assert pp.error_message == "Timed out after 30s calling payment-service"
        assert pp.frequency == 47
        assert pp.severity == "critical"
        assert pp.confidence_score == 87
        assert "checkout-service" in pp.affected_components

    @pytest.mark.asyncio
    async def test_secondary_patterns_consumed(self):
        """Secondary patterns from log_agent must be stored on state.log_analysis."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        assert len(state.log_analysis.secondary_patterns) == 1
        sp = state.log_analysis.secondary_patterns[0]
        assert sp.exception_type == "NullPointerException"
        assert sp.frequency == 5

    @pytest.mark.asyncio
    async def test_service_flow_stored(self):
        """Service flow from log_agent must be stored on state."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        assert len(state.service_flow) == 2
        assert state.service_flow[0]["service"] == "api-gateway"
        assert state.service_flow[1]["status"] == "error"
        assert state.flow_source == "elasticsearch"
        assert state.flow_confidence == 70

    @pytest.mark.asyncio
    async def test_findings_created(self):
        """Critical patterns should be promoted to all_findings."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        log_findings = [f for f in state.all_findings if f.agent_name == "log_agent"]
        assert len(log_findings) >= 1
        assert log_findings[0].category == "ConnectionTimeout"
        assert log_findings[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_breadcrumbs_stored(self):
        """Breadcrumbs from log_agent must appear in state.all_breadcrumbs."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        log_crumbs = [b for b in state.all_breadcrumbs if b.agent_name == "log_agent"]
        assert len(log_crumbs) >= 1

    @pytest.mark.asyncio
    async def test_negative_findings_stored(self):
        """Negative findings from log_agent must appear in state.all_negative_findings."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        log_nf = [nf for nf in state.all_negative_findings if nf.agent_name == "log_agent"]
        assert len(log_nf) >= 1
        assert "Memory" in log_nf[0].what_was_checked

    @pytest.mark.asyncio
    async def test_confidence_updated(self):
        """Overall confidence should be set from log_agent result."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        assert state.overall_confidence == 82

    @pytest.mark.asyncio
    async def test_computed_fields_in_error_pattern(self):
        """ErrorPattern computed fields for frontend compatibility."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "log_agent", self.LOG_AGENT_RESULT)

        pp = state.log_analysis.primary_pattern
        dumped = pp.model_dump(mode="json")
        # Computed fields for frontend
        assert dumped["pattern"] == "ConnectionTimeout"
        assert dumped["count"] == 47
        assert dumped["sample_message"] == "Timed out after 30s calling payment-service"
        assert dumped["confidence"] == 87


# ---------------------------------------------------------------------------
# 2. Metrics Agent → Supervisor integration
# ---------------------------------------------------------------------------

class TestMetricsAgentPipeline:
    """Verify every field from metrics_agent's run() output is consumed by supervisor."""

    METRICS_AGENT_RESULT = {
        "anomalies": [
            {
                "metric_name": "container_memory_usage",
                "promql_query": 'container_memory_working_set_bytes{namespace="prod"}',
                "baseline_value": 200.0,
                "peak_value": 510.0,
                "spike_start": "2025-12-26T14:02:00Z",
                "spike_end": "2025-12-26T14:15:00Z",
                "severity": "critical",
                "correlation_to_incident": "Memory spike preceded first error by 2 minutes",
                "confidence_score": 90,
            },
            {
                "metric_name": "http_error_rate",
                "promql_query": 'rate(http_requests_total{code=~"5.."}[5m])',
                "baseline_value": 0.01,
                "peak_value": 0.12,
                "spike_start": "2025-12-26T14:04:00Z",
                "spike_end": "2025-12-26T14:14:00Z",
                "severity": "high",
                "correlation_to_incident": "Error rate jumped 12x during incident",
                "confidence_score": 85,
            },
        ],
        "correlated_signals": [
            {
                "group_name": "Saturation → Errors",
                "signal_type": "USE",
                "metrics": ["container_memory_usage", "http_error_rate"],
                "narrative": "Memory hit 95% before errors spiked",
            },
        ],
        "time_series_data": {
            "memory_query": [
                {"timestamp": "2025-12-26T14:00:00Z", "value": 200.0},
                {"timestamp": "2025-12-26T14:05:00Z", "value": 510.0},
            ],
        },
        "overall_confidence": 88,
        "breadcrumbs": [
            {
                "agent_name": "metrics_agent",
                "action": "queried_prometheus_range",
                "source_type": "metric",
                "source_reference": "Prometheus",
                "raw_evidence": "Retrieved 120 data points",
                "timestamp": "2025-12-26T14:00:00Z",
            },
        ],
        "negative_findings": [
            {
                "agent_name": "metrics_agent",
                "what_was_checked": "CPU throttling",
                "result": "No throttling detected",
                "implication": "CPU is not the bottleneck",
                "source_reference": "Prometheus",
            },
        ],
        "tokens_used": {
            "agent_name": "metrics_agent",
            "input_tokens": 2000,
            "output_tokens": 1000,
            "total_tokens": 3000,
        },
    }

    @pytest.mark.asyncio
    async def test_metrics_analysis_populated(self):
        """state.metrics_analysis must be populated from agent output."""
        supervisor = SupervisorAgent()
        state = _make_state()

        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        assert state.metrics_analysis is not None, "state.metrics_analysis was not populated"
        assert isinstance(state.metrics_analysis, MetricsAnalysisResult)

    @pytest.mark.asyncio
    async def test_anomalies_parsed(self):
        """All anomalies from agent output must be parsed into MetricAnomaly objects."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        assert len(state.metrics_analysis.anomalies) == 2
        mem = state.metrics_analysis.anomalies[0]
        assert mem.metric_name == "container_memory_usage"
        assert mem.peak_value == 510.0
        assert mem.baseline_value == 200.0
        assert mem.severity == "critical"
        assert mem.confidence_score == 90
        # Computed fields
        assert mem.current_value == 510.0
        assert mem.deviation_percent == 155.0
        assert mem.direction == "above"

    @pytest.mark.asyncio
    async def test_critical_anomalies_promoted_to_findings(self):
        """Critical and high severity anomalies must be promoted to all_findings."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        metric_findings = [f for f in state.all_findings if f.agent_name == "metrics_agent"]
        assert len(metric_findings) == 2  # critical + high
        categories = [f.category for f in metric_findings]
        assert "metric_anomaly" in categories

    @pytest.mark.asyncio
    async def test_correlated_signals_stored(self):
        """Correlated signal groups must be stored on state.metrics_analysis."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        assert len(state.metrics_analysis.correlated_signals) == 1
        cs = state.metrics_analysis.correlated_signals[0]
        assert cs.group_name == "Saturation → Errors"
        assert cs.signal_type == "USE"
        assert "container_memory_usage" in cs.metrics

    @pytest.mark.asyncio
    async def test_time_series_data_passed_through(self):
        """Time series data from agent must be stored (not discarded)."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        assert len(state.metrics_analysis.time_series_data) > 0, \
            "time_series_data was discarded — should be passed through from agent"
        assert "memory_query" in state.metrics_analysis.time_series_data

    @pytest.mark.asyncio
    async def test_tokens_used_not_dummy(self):
        """Token usage should come from agent result, not be all zeros."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        tu = state.metrics_analysis.tokens_used
        assert tu.total_tokens == 3000, f"Expected 3000, got {tu.total_tokens} — dummy zeros?"
        assert tu.input_tokens == 2000
        assert tu.output_tokens == 1000

    @pytest.mark.asyncio
    async def test_breadcrumbs_stored(self):
        """Breadcrumbs from metrics_agent must appear in state.all_breadcrumbs."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        metric_crumbs = [b for b in state.all_breadcrumbs if b.agent_name == "metrics_agent"]
        assert len(metric_crumbs) >= 1

    @pytest.mark.asyncio
    async def test_negative_findings_stored(self):
        """Negative findings from metrics_agent must appear in state.all_negative_findings."""
        supervisor = SupervisorAgent()
        state = _make_state()
        await supervisor._update_state_with_result(state, "metrics_agent", self.METRICS_AGENT_RESULT)

        metric_nf = [nf for nf in state.all_negative_findings if nf.agent_name == "metrics_agent"]
        assert len(metric_nf) >= 1


# ---------------------------------------------------------------------------
# 3. Log → Metrics cross-agent handoff
# ---------------------------------------------------------------------------

class TestLogToMetricsHandoff:
    """Verify that log_agent output enriches the metrics_agent context."""

    @pytest.mark.asyncio
    async def test_error_hints_extracted(self):
        """Error hints should be extracted from log analysis for metrics context."""
        supervisor = SupervisorAgent()
        state = _make_state()

        # First, populate log_analysis
        log_result = {
            "primary_pattern": {
                "pattern_id": "p1",
                "exception_type": "OutOfMemoryError",
                "error_message": "Java heap space OOM",
                "frequency": 10,
                "severity": "critical",
                "affected_components": ["svc"],
                "confidence_score": 90,
                "priority_rank": 1,
                "priority_reasoning": "OOM is root cause",
            },
            "secondary_patterns": [],
            "overall_confidence": 85,
            "breadcrumbs": [],
            "negative_findings": [],
            "tokens_used": {"agent_name": "log_agent", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "service_flow": [],
            "flow_source": "elasticsearch",
            "flow_confidence": 0,
        }
        await supervisor._update_state_with_result(state, "log_agent", log_result)

        # Now build context for metrics_agent
        context = supervisor._build_agent_context("metrics_agent", state)

        assert "error_hints" in context, "error_hints not in metrics context"
        assert "oom" in context["error_hints"], f"Expected 'oom' in {context['error_hints']}"

    @pytest.mark.asyncio
    async def test_error_patterns_passed_to_metrics(self):
        """Error patterns from log analysis should be passed to metrics_agent context."""
        supervisor = SupervisorAgent()
        state = _make_state()

        log_result = {
            "primary_pattern": {
                "pattern_id": "p1",
                "exception_type": "ConnectionTimeout",
                "error_message": "Timeout calling DB",
                "frequency": 20,
                "severity": "high",
                "affected_components": ["svc"],
                "confidence_score": 80,
                "priority_rank": 1,
                "priority_reasoning": "Timeout",
            },
            "secondary_patterns": [],
            "overall_confidence": 75,
            "breadcrumbs": [],
            "negative_findings": [],
            "tokens_used": {"agent_name": "log_agent", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "service_flow": [],
            "flow_source": "elasticsearch",
            "flow_confidence": 0,
        }
        await supervisor._update_state_with_result(state, "log_agent", log_result)

        context = supervisor._build_agent_context("metrics_agent", state)
        assert context.get("error_patterns") is not None, "error_patterns not passed to metrics_agent"
        assert context["error_patterns"]["exception_type"] == "ConnectionTimeout"

    @pytest.mark.asyncio
    async def test_event_markers_from_log_analysis(self):
        """Event markers on metrics should be built from log analysis data."""
        supervisor = SupervisorAgent()
        state = _make_state()

        log_result = {
            "primary_pattern": {
                "pattern_id": "p1",
                "exception_type": "ConnectionTimeout",
                "error_message": "Timeout",
                "frequency": 5,
                "severity": "high",
                "affected_components": ["svc"],
                "sample_logs": [
                    {
                        "log_id": "l1",
                        "index": "app-logs",
                        "timestamp": "2025-12-26T14:02:00Z",
                        "level": "ERROR",
                        "message": "ConnectionTimeout",
                        "service": "svc",
                        "raw_line": "ERROR ConnectionTimeout",
                    },
                ],
                "confidence_score": 80,
                "priority_rank": 1,
                "priority_reasoning": "Timeout",
            },
            "secondary_patterns": [],
            "overall_confidence": 70,
            "breadcrumbs": [],
            "negative_findings": [],
            "tokens_used": {"agent_name": "log_agent", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "service_flow": [],
            "flow_source": "elasticsearch",
            "flow_confidence": 0,
        }
        await supervisor._update_state_with_result(state, "log_agent", log_result)

        # Now run metrics agent result
        metrics_result = {
            "anomalies": [],
            "correlated_signals": [],
            "time_series_data": {},
            "overall_confidence": 50,
            "breadcrumbs": [],
            "negative_findings": [],
            "tokens_used": {"agent_name": "metrics_agent", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        await supervisor._update_state_with_result(state, "metrics_agent", metrics_result)

        # Event markers should have been built from log analysis
        assert len(state.metrics_analysis.event_markers) >= 1, \
            "Event markers should be built from log analysis sample_logs"
        assert state.metrics_analysis.event_markers[0].source == "log_agent"


# ---------------------------------------------------------------------------
# 4. API Integration — findings endpoint
# ---------------------------------------------------------------------------

class TestFindingsAPIIntegration:
    """Verify the /findings endpoint exposes all state fields."""

    @pytest.mark.asyncio
    async def test_findings_endpoint_returns_all_fields(self):
        """Simulate state after both agents and verify API response structure."""
        from starlette.testclient import TestClient
        from src.api.routes_v4 import router_v4, sessions
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router_v4)

        supervisor = SupervisorAgent()
        state = _make_state()

        # Run log agent result
        log_result = TestLogAgentPipeline.LOG_AGENT_RESULT
        await supervisor._update_state_with_result(state, "log_agent", log_result)

        # Run metrics agent result
        metrics_result = TestMetricsAgentPipeline.METRICS_AGENT_RESULT
        await supervisor._update_state_with_result(state, "metrics_agent", metrics_result)

        # Store state in session store
        sessions["test-api-001"] = {
            "service_name": "order-service",
            "phase": "metrics_analyzed",
            "confidence": state.overall_confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": state,
        }

        client = TestClient(app)
        resp = client.get("/api/v4/session/test-api-001/findings")
        assert resp.status_code == 200
        data = resp.json()

        # Verify all expected fields are present and non-empty
        assert len(data["findings"]) >= 3, f"Expected >=3 findings (1 log + 2 metric), got {len(data['findings'])}"
        assert len(data["error_patterns"]) >= 1, "error_patterns should be non-empty after log_agent"
        assert len(data["metric_anomalies"]) == 2, "metric_anomalies should have 2 entries"
        assert len(data["correlated_signals"]) == 1, "correlated_signals should have 1 entry"
        assert len(data["negative_findings"]) >= 2, "negative_findings from both agents"
        assert len(data["service_flow"]) == 2, "service_flow should have 2 steps"
        assert data["flow_source"] == "elasticsearch"
        assert data["flow_confidence"] == 70

        # Verify error_pattern computed fields for frontend compatibility
        ep = data["error_patterns"][0]
        assert "pattern" in ep, "ErrorPattern missing computed 'pattern' field"
        assert "count" in ep, "ErrorPattern missing computed 'count' field"
        assert "sample_message" in ep, "ErrorPattern missing computed 'sample_message' field"

        # Verify metric_anomaly computed fields
        ma = data["metric_anomalies"][0]
        assert "current_value" in ma, "MetricAnomaly missing computed 'current_value' field"
        assert "deviation_percent" in ma, "MetricAnomaly missing computed 'deviation_percent' field"
        assert "direction" in ma, "MetricAnomaly missing computed 'direction' field"

        # Verify correlated signals structure
        cs = data["correlated_signals"][0]
        assert cs["group_name"] == "Saturation → Errors"
        assert cs["signal_type"] == "USE"

        # Verify event markers are present
        assert "event_markers" in data

        # Cleanup
        sessions.pop("test-api-001", None)
