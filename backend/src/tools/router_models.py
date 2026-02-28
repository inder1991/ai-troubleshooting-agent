"""Request/response models for the investigation router.

RouterContext carries the UI viewport state with every investigation request.
InvestigateRequest enforces that exactly one input (command, query, or
quick_action) is provided.
"""

from pydantic import BaseModel, model_validator
from typing import Optional, Literal, Any

from src.models.schemas import TimeWindow


class RouterContext(BaseModel):
    """UI viewport state sent with every investigation request."""

    active_namespace: Optional[str] = None
    active_service: Optional[str] = None
    active_pod: Optional[str] = None
    time_window: TimeWindow
    session_id: str = ""
    incident_id: str = ""
    discovered_services: list[str] = []
    discovered_namespaces: list[str] = []
    pod_names: list[str] = []
    active_findings_summary: str = ""
    last_agent_phase: str = ""
    elk_index: Optional[str] = None


class QuickActionPayload(BaseModel):
    """Payload for a quick-action button press."""

    intent: str
    params: dict[str, Any]


class InvestigateRequest(BaseModel):
    """Top-level request to the investigation router.

    Exactly one of command, query, or quick_action must be provided.
    """

    command: Optional[str] = None
    query: Optional[str] = None
    quick_action: Optional[QuickActionPayload] = None
    context: RouterContext

    @model_validator(mode="after")
    def exactly_one_input(self) -> "InvestigateRequest":
        provided = sum(
            1 for v in [self.command, self.query, self.quick_action] if v is not None
        )
        if provided != 1:
            raise ValueError(
                "Exactly one of command, query, or quick_action must be provided"
            )
        return self


class InvestigateResponse(BaseModel):
    """Acknowledgement returned immediately after an investigation request."""

    pin_id: str
    intent: str
    params: dict[str, Any]
    path_used: Literal["fast", "smart"]
    status: Literal["executing", "error"]
    error: Optional[str] = None
