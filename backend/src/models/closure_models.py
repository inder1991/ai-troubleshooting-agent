"""
Incident Closure models — tracks Jira, Remedy, and Confluence actions
performed after a diagnosis is complete.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


class ClosurePhase(str, Enum):
    NOT_STARTED = "not_started"
    REMEDIATION = "remediation"
    TRACKING = "tracking"
    KNOWLEDGE_CAPTURE = "knowledge"
    CLOSED = "closed"


class JiraActionResult(BaseModel):
    status: Literal["success", "failed", "skipped"] = "skipped"
    issue_key: str = ""
    issue_url: str = ""
    error: str = ""
    created_at: Optional[datetime] = None


class RemedyActionResult(BaseModel):
    status: Literal["success", "failed", "skipped"] = "skipped"
    incident_number: str = ""
    incident_url: str = ""
    error: str = ""
    created_at: Optional[datetime] = None


class ConfluenceActionResult(BaseModel):
    status: Literal["success", "failed", "skipped"] = "skipped"
    page_id: str = ""
    page_url: str = ""
    space_key: str = ""
    error: str = ""
    created_at: Optional[datetime] = None


class IntegrationAvailability(BaseModel):
    configured: bool = False
    status: str = "not_linked"
    has_credentials: bool = False


class IncidentClosureState(BaseModel):
    phase: ClosurePhase = ClosurePhase.NOT_STARTED
    jira_result: JiraActionResult = Field(default_factory=JiraActionResult)
    remedy_result: RemedyActionResult = Field(default_factory=RemedyActionResult)
    confluence_result: ConfluenceActionResult = Field(default_factory=ConfluenceActionResult)
    postmortem_preview: str = ""
    closed_at: Optional[datetime] = None


# ── Request/Response models ──────────────────────────────────────────────


class JiraCreateRequest(BaseModel):
    project_key: str
    summary: str = ""
    description: str = ""
    issue_type: str = "Bug"
    priority: str = ""


class JiraLinkRequest(BaseModel):
    issue_key: str


class RemedyCreateRequest(BaseModel):
    summary: str = ""
    urgency: str = ""
    assigned_group: str = ""
    service_ci: str = ""


class ConfluencePublishRequest(BaseModel):
    space_key: str
    title: str = ""
    parent_page_id: str = ""
    body_markdown: str = ""


class ClosureStatusResponse(BaseModel):
    closure_state: IncidentClosureState
    integrations: dict = Field(default_factory=dict)
    can_start_closure: bool = False
    pre_filled: dict = Field(default_factory=dict)
