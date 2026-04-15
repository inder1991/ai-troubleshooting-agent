from __future__ import annotations

from dataclasses import dataclass, field
from src.models.pending_action import PendingAction


# Single-token exact matches
APPROVE_EXACT = {"approve", "yes", "y", "ok", "lgtm", "confirm", "proceed"}
REJECT_EXACT = {"reject", "no", "n", "cancel", "stop", "discard", "abort"}

# Multi-word phrases matched via containment (check longer first)
APPROVE_PHRASES = ["go ahead", "looks good", "create pr", "ship it", "yes please", "sounds good", "do it"]
REJECT_PHRASES = ["no thanks", "not now", "hold off", "don't proceed"]

# Guard against false positives: "no problem" contains "no" but isn't rejection
FALSE_POSITIVE_GUARDS = {"no problem", "no worries", "no issue", "no doubt"}


@dataclass
class UserIntent:
    type: str
    confidence: float
    entities: dict = field(default_factory=dict)


# Maps pending_action.type → (approve_intent, reject_intent, feedback_intent)
_INTENT_MAP: dict[str, tuple[str, str, str | None]] = {
    "attestation_required": ("approve_attestation", "reject_attestation", None),
    "fix_approval": ("approve_fix", "reject_fix", "fix_feedback"),
    "repo_confirm": ("approve_repo", "reject_repo", None),
    "campaign_execute_confirm": ("confirm_execute", "cancel_execute", None),
    "code_agent_question": ("general_chat", "general_chat", None),
}

# Valid intents per pending action type — security gate
ALLOWED_INTENTS: dict[str, set[str]] = {
    "attestation_required": {"approve_attestation", "reject_attestation", "ask_question", "general_chat"},
    "fix_approval": {"approve_fix", "reject_fix", "fix_feedback", "ask_question", "general_chat"},
    "repo_confirm": {"approve_repo", "reject_repo", "ask_question", "general_chat"},
    "campaign_execute_confirm": {"confirm_execute", "cancel_execute", "ask_question", "general_chat"},
    "code_agent_question": {"general_chat", "ask_question"},
}


def allowed_intents_for_pending(pending_type: str) -> set[str]:
    return ALLOWED_INTENTS.get(pending_type, {"general_chat", "ask_question"})


class IntentParser:
    def parse(self, message: str, pending_action: PendingAction | None) -> UserIntent:
        text = message.strip()

        # Layer 1: exact intent prefix from chip clicks
        if text.startswith("__intent:"):
            intent_type = text[len("__intent:"):]
            return UserIntent(type=intent_type, confidence=1.0)

        lower = text.lower().strip()

        # No pending action → everything is general chat
        if pending_action is None:
            return UserIntent(type="general_chat", confidence=1.0)

        intents = _INTENT_MAP.get(pending_action.type)
        if not intents:
            return UserIntent(type="general_chat", confidence=0.5)

        approve_intent, reject_intent, feedback_intent = intents

        # Layer 2: rule-based matching (exact tokens + phrase containment)

        # Guard against false positives first
        if any(fp in lower for fp in FALSE_POSITIVE_GUARDS):
            return UserIntent(type="general_chat", confidence=0.8)

        # Exact single-token match
        if lower in APPROVE_EXACT:
            return UserIntent(type=approve_intent, confidence=0.95)

        if lower in REJECT_EXACT:
            return UserIntent(type=reject_intent, confidence=0.95)

        # Phrase containment (longer phrases first to avoid partial matches)
        if any(phrase in lower for phrase in APPROVE_PHRASES):
            return UserIntent(type=approve_intent, confidence=0.9)

        if any(phrase in lower for phrase in REJECT_PHRASES):
            return UserIntent(type=reject_intent, confidence=0.9)

        # Questions → ask_question (keep pending action alive)
        if lower.endswith("?"):
            return UserIntent(type="ask_question", confidence=0.9)

        # For fix_approval: non-matching text is feedback
        if feedback_intent and pending_action.type == "fix_approval":
            return UserIntent(
                type=feedback_intent,
                confidence=0.85,
                entities={"feedback": text},
            )

        # Fallback: general chat (low confidence — caller may re-prompt)
        return UserIntent(type="general_chat", confidence=0.6)
