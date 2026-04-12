from src.agents.intent_parser import IntentParser, UserIntent
from src.models.pending_action import PendingAction


def test_intent_routes_approve_to_attestation_when_pending():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("looks good to me", pending)
    assert intent.type == "approve_attestation"


def test_intent_routes_question_keeps_pending():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("can you show me finding 3?", pending)
    assert intent.type == "ask_question"


def test_low_confidence_returns_general():
    parser = IntentParser()
    pending = PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject"], expires_at=None,
        context={}, version=1,
    )
    intent = parser.parse("hmm not sure", pending)
    assert intent.confidence < 0.7
