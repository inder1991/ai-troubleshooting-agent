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
    serviceName: str
    elkIndex: str = "app-logs-*"
    timeframe: str = "1h"
    traceId: Optional[str] = None
    namespace: Optional[str] = None
    clusterUrl: Optional[str] = None
    repoUrl: Optional[str] = None


class StartSessionResponse(BaseModel):
    session_id: str
    status: str
    message: str


class SessionSummary(BaseModel):
    session_id: str
    service_name: str
    phase: str
    confidence: int
    created_at: str
