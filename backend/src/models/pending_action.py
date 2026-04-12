from __future__ import annotations

from dataclasses import dataclass, field
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
        return {
            "type": self.type,
            "blocking": self.blocking,
            "actions": self.actions,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "context": self.context,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PendingAction:
        expires_at = None
        if d.get("expires_at"):
            expires_at = datetime.fromisoformat(d["expires_at"])
        return cls(
            type=d["type"],
            blocking=d["blocking"],
            actions=d["actions"],
            expires_at=expires_at,
            context=d.get("context", {}),
            version=d.get("version", 1),
        )
