from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class AttestationDecision:
    finding_id: str
    decision: Literal["approved", "rejected", "skipped"]
    decided_by: str
    decided_at: datetime
    confidence_at_decision: float


@dataclass
class AttestationGate:
    findings: list[dict]
    decisions: dict[str, AttestationDecision] = field(default_factory=dict)
    status: Literal["pending", "partially_decided", "complete"] = "pending"
    auto_approved: bool = False
    expires_at: datetime | None = None

    def is_complete(self) -> bool:
        return len(self.decisions) == len(self.findings)

    def approved_finding_ids(self) -> list[str]:
        return [fid for fid, d in self.decisions.items() if d.decision == "approved"]
