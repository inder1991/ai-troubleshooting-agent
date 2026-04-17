"""
API Request/Response Models
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Annotated

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

    # Aliases must use Annotated[] for Optional/Union-typed fields — see
    # https://docs.pydantic.dev/latest/concepts/alias/ — otherwise Pydantic v2
    # silently drops the alias with UnsupportedFieldAttributeWarning.
    serviceName: Annotated[str, Field(alias="service_name")] = "unknown"
    elkIndex: Annotated[Optional[str], Field(alias="elk_index")] = None
    timeframe: Annotated[str, Field(alias="time_window")] = "1h"
    traceId: Annotated[Optional[str], Field(alias="trace_id")] = None
    namespace: Optional[str] = None
    clusterUrl: Annotated[Optional[str], Field(alias="cluster_url")] = None
    repoUrl: Annotated[Optional[str], Field(alias="repo_url")] = None
    profileId: Annotated[Optional[str], Field(alias="profile_id")] = None
    capability: str = "troubleshoot_app"
    authToken: Annotated[Optional[str], Field(alias="auth_token")] = None
    authMethod: Annotated[Optional[str], Field(alias="auth_method")] = None
    kubeconfig_content: Optional[str] = None
    role: Optional[str] = None
    scan_mode: Annotated[str, Field(alias="scanMode")] = "diagnostic"
    scope: Optional[dict] = None       # DiagnosticScope dict from frontend
    resource_type: Optional[str] = None
    symptoms: Optional[str] = None
    target_host: Annotated[Optional[str], Field(alias="targetHost")] = None
    port_num: Annotated[Optional[int], Field(alias="portNum")] = None
    net_protocol: Annotated[Optional[str], Field(alias="netProtocol")] = None
    extra: Optional[dict] = None  # Additional capability-specific config
    # Phase-4 Task 4.5 opt-in: run the supervisor N times with shuffled
    # agent dispatch orders and vote on the winner. N>1 triples LLM cost
    # so this is off by default.
    self_consistency_runs: Annotated[
        int, Field(alias="selfConsistencyRuns", ge=1, le=5)
    ] = 1


class StartSessionResponse(BaseModel):
    session_id: str
    incident_id: str
    status: str
    message: str
    service_name: str = ""
    created_at: str = ""
    capability: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    service_name: Optional[str] = None
    incident_id: Optional[str] = None
    phase: str
    confidence: int
    created_at: str
    capability: Optional[str] = None
    investigation_mode: Optional[str] = None
    related_sessions: list[str] = []
    findings_count: int = 0
    critical_count: int = 0


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
