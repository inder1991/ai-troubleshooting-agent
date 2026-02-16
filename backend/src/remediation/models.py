from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class RunbookMatch(BaseModel):
    runbook_id: str
    title: str
    match_score: float = Field(..., ge=0.0, le=1.0)
    matched_symptoms: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    success_rate: float = 0.0
    last_used: Optional[datetime] = None
    source: Literal["internal", "vendor", "ai_generated"] = "internal"


class RemediationDecision(BaseModel):
    proposed_action: str
    action_type: Literal["restart", "scale", "rollback", "config_change", "code_fix"]
    is_destructive: bool = False
    requires_double_confirmation: bool = False  # True if destructive
    dry_run_available: bool = True
    rollback_plan: str = ""
    estimated_impact: str = ""
    pre_checks: list[str] = Field(default_factory=list)
    post_checks: list[str] = Field(default_factory=list)


class RemediationResult(BaseModel):
    decision: RemediationDecision
    status: Literal["pending", "dry_run_complete", "executing", "success", "failed", "rolled_back"]
    dry_run_output: Optional[str] = None
    execution_output: Optional[str] = None
    rollback_output: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
