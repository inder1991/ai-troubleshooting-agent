"""
API Request/Response Models
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any

class ConversationRequest(BaseModel):
    message: str = Field(..., description="User's message")
    conversation_history: Optional[List[Dict[str, str]]] = Field(
        default=None, 
        description="Previous messages in conversation"
    )
 
class ConversationResponse(BaseModel):
    intent: str = Field(..., description="Detected intent: troubleshoot, general_chat, clarification_needed")
    response: str = Field(..., description="LLM-generated response")
    show_form: bool = Field(..., description="Whether to show troubleshooting form")
    confidence: float = Field(..., description="Confidence score 0-1")
    reasoning: Optional[str] = Field(None, description="Reasoning for intent classification")
    timestamp: str = Field(..., description="Response timestamp")
    
class TroubleshootRequest(BaseModel):
    elkIndex: str = Field(..., description="ELK index pattern")
    githubRepo: str = Field(..., description="GitHub repository")
    timeframe: str = Field(default="1h", description="Time range")
    errorMessage: Optional[str] = Field(None, description="Error filter")
    rawLogs: Optional[str] = Field(None, description="Raw logs if available")
    repoPath: Optional[str] = Field(None, description="Local repository path")


class TroubleshootResponse(BaseModel):
    session_id: str
    status: str
    message: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    current_step: Optional[str]
    progress: float
    results: Optional[Dict[str, Any]]


class ApprovalRequest(BaseModel):
    session_id: str
    approved: bool
    comments: Optional[str]


# ── v4 Models ──────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    phase: str
    confidence: int


class StartSessionRequest(BaseModel):
    model_config = {"populate_by_name": True}

    serviceName: str = Field(alias="service_name", default="unknown")
    elkIndex: str = Field(default="app-logs-*", alias="elk_index")
    timeframe: str = Field(default="1h", alias="time_window")
    traceId: Optional[str] = Field(default=None, alias="trace_id")
    namespace: Optional[str] = None
    clusterUrl: Optional[str] = Field(default=None, alias="cluster_url")
    repoUrl: Optional[str] = Field(default=None, alias="repo_url")
    profileId: Optional[str] = Field(default=None, alias="profile_id")
    capability: str = "troubleshoot_app"


class StartSessionResponse(BaseModel):
    session_id: str
    incident_id: str
    status: str
    message: str
    service_name: str = ""
    created_at: str = ""


class SessionSummary(BaseModel):
    session_id: str
    service_name: Optional[str] = None
    incident_id: Optional[str] = None
    phase: str
    confidence: int
    created_at: str


# ── Fix Pipeline Models ──────────────────────────────────────────────


class FixRequest(BaseModel):
    guidance: str = ""


class FixStatusFileEntry(BaseModel):
    file_path: str
    diff: str = ""


class FixStatusResponse(BaseModel):
    fix_status: str
    target_file: str = ""
    diff: str = ""
    fix_explanation: str = ""
    fixed_files: list[FixStatusFileEntry] = []
    verification_result: Optional[Dict[str, Any]] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    attempt_count: int = 0


class FixDecisionRequest(BaseModel):
    decision: str = Field(..., min_length=1, description="approve, reject, or feedback text")


# ── Campaign Models ──────────────────────────────────────────────────


class CampaignRepoStatusResponse(BaseModel):
    repo_url: str
    service_name: str
    status: str
    causal_role: str
    diff: str = ""
    fix_explanation: str = ""
    fixed_files: list[FixStatusFileEntry] = []
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    error_message: str = ""


class CampaignStatusResponse(BaseModel):
    campaign_id: str
    overall_status: str
    approved_count: int
    total_count: int
    repos: list[CampaignRepoStatusResponse]


class CampaignRepoDecisionRequest(BaseModel):
    decision: str  # "approve", "reject", or "revoke"


class CampaignExecuteResponse(BaseModel):
    status: str  # "executed", "partial_failure"
    merged_prs: list[dict] = []
    failed_repos: list[str] = []
