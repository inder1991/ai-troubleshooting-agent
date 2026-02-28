"""Tests for ToolResult, EvidencePinFactory, and InvestigateRequest models.

Covers:
- ToolResult creation (success and failure)
- EvidencePinFactory.from_tool_result (manual, auto, failed)
- InvestigateRequest validation (exactly-one-input constraint)
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from src.tools.tool_result import ToolResult
from src.tools.router_models import (
    RouterContext,
    InvestigateRequest,
    QuickActionPayload,
)
from src.tools.evidence_pin_factory import EvidencePinFactory
from src.models.schemas import TimeWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_time_window() -> TimeWindow:
    return TimeWindow(start="2026-02-28T11:00:00Z", end="2026-02-28T12:00:00Z")


def _make_router_context(**overrides) -> RouterContext:
    defaults = dict(
        active_namespace="prod",
        active_service="payment-svc",
        active_pod="payment-svc-abc-123",
        time_window=_make_time_window(),
        session_id="sess-001",
        incident_id="inc-001",
        discovered_services=["payment-svc", "order-svc"],
        discovered_namespaces=["prod"],
        pod_names=["payment-svc-abc-123"],
    )
    defaults.update(overrides)
    return RouterContext(**defaults)


def _make_successful_tool_result(**overrides) -> ToolResult:
    defaults = dict(
        success=True,
        intent="get_pod_status",
        raw_output="NAME   READY   STATUS\npayment-svc-abc   0/1   CrashLoopBackOff",
        summary="Pod payment-svc-abc is crash-looping with OOMKilled",
        evidence_snippets=["OOMKilled exit code 137", "Last restart 2m ago"],
        evidence_type="k8s_resource",
        domain="compute",
        severity="critical",
        metadata={"pod": "payment-svc-abc-123"},
    )
    defaults.update(overrides)
    return ToolResult(**defaults)


def _make_failed_tool_result(**overrides) -> ToolResult:
    defaults = dict(
        success=False,
        intent="get_pod_logs",
        raw_output="",
        summary="Failed to fetch pod logs",
        evidence_snippets=[],
        evidence_type="log",
        domain="compute",
        error="ConnectionTimeout: Elasticsearch unreachable",
        metadata={},
    )
    defaults.update(overrides)
    return ToolResult(**defaults)


# ---------------------------------------------------------------------------
# TestToolResult
# ---------------------------------------------------------------------------

class TestToolResult:
    """Validate ToolResult model creation and field access."""

    def test_successful_result(self):
        """A successful ToolResult should populate all fields correctly."""
        result = _make_successful_tool_result()

        assert result.success is True
        assert result.intent == "get_pod_status"
        assert "CrashLoopBackOff" in result.raw_output
        assert result.summary == "Pod payment-svc-abc is crash-looping with OOMKilled"
        assert len(result.evidence_snippets) == 2
        assert result.evidence_type == "k8s_resource"
        assert result.domain == "compute"
        assert result.severity == "critical"
        assert result.error is None
        assert result.metadata == {"pod": "payment-svc-abc-123"}

    def test_failed_result(self):
        """A failed ToolResult should carry an error message and empty evidence."""
        result = _make_failed_tool_result()

        assert result.success is False
        assert result.intent == "get_pod_logs"
        assert result.raw_output == ""
        assert result.evidence_snippets == []
        assert result.error == "ConnectionTimeout: Elasticsearch unreachable"
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# TestEvidencePinFactory
# ---------------------------------------------------------------------------

class TestEvidencePinFactory:
    """Validate EvidencePinFactory.from_tool_result produces correct EvidencePins."""

    def test_manual_pin_from_successful_result(self):
        """Factory creates EvidencePin with source='manual', triggered_by='quick_action',
        domain='compute', validation_status='pending_critic', confidence=1.0,
        namespace from context."""
        result = _make_successful_tool_result()
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(
            result=result,
            triggered_by="quick_action",
            context=context,
        )

        assert pin.source == "manual"
        assert pin.triggered_by == "quick_action"
        assert pin.domain == "compute"
        assert pin.validation_status == "pending_critic"
        assert pin.confidence == 1.0
        assert pin.namespace == "prod"
        assert pin.service == "payment-svc"
        assert pin.resource_name == "payment-svc-abc-123"
        assert pin.source_tool == "get_pod_status"
        assert pin.source_agent is None
        assert pin.evidence_type == "k8s_resource"
        assert pin.claim == result.summary
        assert pin.raw_output == result.raw_output
        assert pin.severity == "critical"
        assert pin.causal_role is None
        assert pin.time_window is not None
        assert pin.time_window.start == "2026-02-28T11:00:00Z"
        # id should be a valid UUID
        import uuid
        uuid.UUID(pin.id)  # raises if invalid

    def test_auto_pin_from_pipeline(self):
        """Factory creates pin with source='auto' when triggered_by='automated_pipeline'."""
        result = _make_successful_tool_result()
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(
            result=result,
            triggered_by="automated_pipeline",
            context=context,
        )

        assert pin.source == "auto"
        assert pin.triggered_by == "automated_pipeline"

    def test_failed_result_gives_zero_confidence(self):
        """A failed ToolResult should produce an EvidencePin with confidence=0.0."""
        result = _make_failed_tool_result()
        context = _make_router_context()

        pin = EvidencePinFactory.from_tool_result(
            result=result,
            triggered_by="user_chat",
            context=context,
        )

        assert pin.confidence == 0.0
        assert pin.source == "manual"
        assert pin.claim == "Failed to fetch pod logs"


# ---------------------------------------------------------------------------
# TestInvestigateRequest
# ---------------------------------------------------------------------------

class TestInvestigateRequest:
    """Validate InvestigateRequest exactly-one-input constraint."""

    def test_exactly_one_input_required(self):
        """Providing both command and query should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InvestigateRequest(
                command="/analyze",
                query="Why is the pod crashing?",
                context=_make_router_context(),
            )
        assert "exactly one" in str(exc_info.value).lower()

    def test_no_input_rejected(self):
        """Providing no command, query, or quick_action should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            InvestigateRequest(
                context=_make_router_context(),
            )
        assert "exactly one" in str(exc_info.value).lower()

    def test_valid_quick_action(self):
        """A single quick_action should produce a valid request."""
        req = InvestigateRequest(
            quick_action=QuickActionPayload(
                intent="get_pod_status",
                params={"pod": "payment-svc-abc-123"},
            ),
            context=_make_router_context(),
        )

        assert req.quick_action is not None
        assert req.quick_action.intent == "get_pod_status"
        assert req.command is None
        assert req.query is None

    def test_valid_command(self):
        """A single command should produce a valid request."""
        req = InvestigateRequest(
            command="/analyze",
            context=_make_router_context(),
        )
        assert req.command == "/analyze"
        assert req.query is None
        assert req.quick_action is None

    def test_valid_query(self):
        """A single query should produce a valid request."""
        req = InvestigateRequest(
            query="Why is the pod crashing?",
            context=_make_router_context(),
        )
        assert req.query == "Why is the pod crashing?"
        assert req.command is None
        assert req.quick_action is None
