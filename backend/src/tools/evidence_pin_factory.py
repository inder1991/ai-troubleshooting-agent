"""Factory that converts ToolResult into EvidencePin.

EvidencePinFactory.from_tool_result() is the single conversion point between
raw tool output and the governance-tracked EvidencePin model.
"""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal

from src.models.schemas import EvidencePin
from src.tools.tool_result import ToolResult
from src.tools.router_models import RouterContext


class EvidencePinFactory:
    """Converts ToolResult objects into EvidencePin instances."""

    @staticmethod
    def from_tool_result(
        result: ToolResult,
        triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"],
        context: RouterContext,
    ) -> EvidencePin:
        """Create an EvidencePin from a tool execution result.

        Args:
            result: The intermediate ToolResult from tool execution.
            triggered_by: How this investigation was triggered.
            context: The RouterContext carrying UI viewport state.

        Returns:
            A fully populated EvidencePin ready for the evidence graph.
        """
        source = (
            "manual"
            if triggered_by in ("user_chat", "quick_action")
            else "auto"
        )
        return EvidencePin(
            id=str(uuid4()),
            claim=result.summary,
            source=source,
            source_agent=None,
            source_tool=result.intent,
            triggered_by=triggered_by,
            evidence_type=result.evidence_type,
            supporting_evidence=result.evidence_snippets,
            raw_output=result.raw_output,
            confidence=1.0 if result.success else 0.0,
            severity=result.severity,
            causal_role=None,
            domain=result.domain,
            validation_status="pending_critic",
            namespace=context.active_namespace,
            service=context.active_service,
            resource_name=result.metadata.get("pod") or result.metadata.get("name"),
            timestamp=datetime.now(timezone.utc),
            time_window=context.time_window,
        )
