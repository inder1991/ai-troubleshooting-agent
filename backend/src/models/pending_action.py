from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal


PENDING_ACTION_TYPES = Literal[
    "attestation_required",
    "fix_approval",
    "repo_confirm",
    "campaign_execute_confirm",
    "code_agent_question",
]


@dataclass
class AttestationContext:
    findings_count: int
    confidence: float
    proposed_action: str

    def to_dict(self) -> dict:
        return {"_ctx_type": "attestation", **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "AttestationContext":
        return cls(findings_count=d["findings_count"], confidence=d["confidence"], proposed_action=d["proposed_action"])


@dataclass
class FixApprovalContext:
    diff_summary: str
    fix_explanation: str
    fixed_files: list[str]
    attempt_number: int

    def to_dict(self) -> dict:
        return {"_ctx_type": "fix_approval", **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "FixApprovalContext":
        return cls(diff_summary=d["diff_summary"], fix_explanation=d["fix_explanation"], fixed_files=d["fixed_files"], attempt_number=d["attempt_number"])


@dataclass
class CampaignExecuteContext:
    repo_count: int
    repos: list[str]
    approved_count: int

    def to_dict(self) -> dict:
        return {"_ctx_type": "campaign_execute", **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignExecuteContext":
        return cls(repo_count=d["repo_count"], repos=d["repos"], approved_count=d["approved_count"])


@dataclass
class RepoConfirmContext:
    repo_url: str
    service_name: str

    def to_dict(self) -> dict:
        return {"_ctx_type": "repo_confirm", **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "RepoConfirmContext":
        return cls(repo_url=d["repo_url"], service_name=d["service_name"])


@dataclass
class CodeAgentQuestionContext:
    question: str
    agent_name: str

    def to_dict(self) -> dict:
        return {"_ctx_type": "code_agent_question", **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "CodeAgentQuestionContext":
        return cls(question=d["question"], agent_name=d["agent_name"])


_CONTEXT_REGISTRY: dict[str, type] = {
    "attestation": AttestationContext,
    "fix_approval": FixApprovalContext,
    "campaign_execute": CampaignExecuteContext,
    "repo_confirm": RepoConfirmContext,
    "code_agent_question": CodeAgentQuestionContext,
}


@dataclass
class PendingAction:
    type: PENDING_ACTION_TYPES
    blocking: bool
    actions: list[str]
    expires_at: datetime | None
    context: dict
    version: int = 1

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        ctx = self.context.to_dict() if hasattr(self.context, 'to_dict') else self.context
        return {
            "type": self.type,
            "blocking": self.blocking,
            "actions": self.actions,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "context": ctx,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingAction":
        expires_at = None
        if d.get("expires_at"):
            expires_at = datetime.fromisoformat(d["expires_at"])
        raw_ctx = d.get("context", {})
        ctx_type = raw_ctx.get("_ctx_type") if isinstance(raw_ctx, dict) else None
        if ctx_type and ctx_type in _CONTEXT_REGISTRY:
            context = _CONTEXT_REGISTRY[ctx_type].from_dict(raw_ctx)
        else:
            context = raw_ctx
        return cls(
            type=d["type"],
            blocking=d["blocking"],
            actions=d["actions"],
            expires_at=expires_at,
            context=context,
            version=d.get("version", 1),
        )
