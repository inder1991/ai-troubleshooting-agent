"""
Campaign data models for multi-repo remediation orchestration.

A RemediationCampaign coordinates fix generation across multiple repositories
when an incident spans several services.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class CampaignRepoStatus(str, Enum):
    PENDING = "pending"
    CLONING = "cloning"
    GENERATING = "generating"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PR_CREATED = "pr_created"
    ERROR = "error"


class CampaignRepoFix(BaseModel):
    repo_url: str
    service_name: str
    status: CampaignRepoStatus = CampaignRepoStatus.PENDING
    cloned_path: str = ""
    target_files: list[str] = Field(default_factory=list)
    fixed_files: list[dict] = Field(default_factory=list)  # [{file_path, diff, original_code, fixed_code}]
    diff: str = ""
    fix_explanation: str = ""
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    branch_name: str = ""
    error_message: str = ""
    causal_role: str = ""  # "root_cause", "cascading", "correlated"


class RemediationCampaign(BaseModel):
    campaign_id: str = ""
    session_id: str = ""
    repos: dict[str, CampaignRepoFix] = Field(default_factory=dict)  # repo_url → fix state
    overall_status: str = "not_started"  # not_started, in_progress, awaiting_approvals, completed, partial_failure
    approved_count: int = 0
    total_count: int = 0
