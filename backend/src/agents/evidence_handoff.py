"""Dual-representation evidence handoff: structured dicts for the system, formatted text for the LLM."""

from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class EvidenceHandoff:
    claim: str
    domain: str
    timestamp: datetime | None = None
    confidence: float = 0.0
    source_agent: str = ""
    finding_id: str = ""
    corroborating_domains: list[str] = field(default_factory=list)
    contradicting_domains: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


def serialize_handoffs(handoffs: list[EvidenceHandoff]) -> dict:
    return {
        "handoffs": [
            {
                **asdict(h),
                "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            }
            for h in handoffs
        ]
    }


def format_handoff_for_agent(handoffs: list[EvidenceHandoff], target_domain: str) -> str:
    if not handoffs:
        return ""
    lines = ["Prior evidence to validate or refute:"]
    for i, h in enumerate(handoffs, 1):
        ts = f" at {h.timestamp.isoformat()}" if h.timestamp else ""
        lines.append(f"  {i}. [{h.domain}, confidence={h.confidence:.2f}] {h.claim}{ts}")
        if h.corroborating_domains:
            lines.append(f"     Corroborated by: {', '.join(h.corroborating_domains)}")
        if h.contradicting_domains:
            lines.append(f"     Contradicted by: {', '.join(h.contradicting_domains)}")
        if h.open_questions:
            for q in h.open_questions:
                lines.append(f"     Open question: {q}")
    lines.append(f"\nYOUR TASK: Use {target_domain} data to confirm or deny these claims.")
    return "\n".join(lines)
