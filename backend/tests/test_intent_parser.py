from src.agents.intent_parser import IntentParser, UserIntent
from src.models.pending_action import PendingAction


def make_attestation_pending() -> PendingAction:
    return PendingAction(
        type="attestation_required", blocking=True,
        actions=["approve", "reject", "details"],
        expires_at=None, context={}, version=1,
    )


def make_fix_pending() -> PendingAction:
    return PendingAction(
        type="fix_approval", blocking=True,
        actions=["approve", "reject", "feedback"],
        expires_at=None, context={}, version=1,
    )


parser = IntentParser()


def test_exact_intent_prefix():
    result = parser.parse("__intent:approve_attestation", make_attestation_pending())
    assert result.type == "approve_attestation"
    assert result.confidence == 1.0


def test_approve_synonyms_with_attestation_pending():
    for word in ["yes", "lgtm", "go ahead", "looks good", "approve", "ok",
                 "yes please go ahead", "sounds good to me", "ship it"]:
        result = parser.parse(word, make_attestation_pending())
        assert result.type == "approve_attestation", f"Failed for: {word}"
        assert result.confidence >= 0.9


def test_reject_synonyms_with_attestation_pending():
    for word in ["reject", "no", "cancel", "stop", "hold off on this", "no thanks"]:
        result = parser.parse(word, make_attestation_pending())
        assert result.type == "reject_attestation", f"Failed for: {word}"
        assert result.confidence >= 0.9


def test_false_positive_guards():
    for phrase in ["no problem", "no worries", "no issue"]:
        result = parser.parse(phrase, make_attestation_pending())
        assert result.type != "reject_attestation", f"False positive for: {phrase}"


def test_approve_synonyms_with_fix_pending():
    for word in ["approve", "yes", "create pr", "lgtm"]:
        result = parser.parse(word, make_fix_pending())
        assert result.type == "approve_fix", f"Failed for: {word}"


def test_reject_synonyms_with_fix_pending():
    for word in ["reject", "no", "discard"]:
        result = parser.parse(word, make_fix_pending())
        assert result.type == "reject_fix", f"Failed for: {word}"


def test_feedback_with_fix_pending():
    result = parser.parse("handle the null case differently", make_fix_pending())
    assert result.type == "fix_feedback"
    assert result.entities.get("feedback") == "handle the null case differently"


def test_question_preserves_pending():
    result = parser.parse("what does finding 2 mean?", make_attestation_pending())
    assert result.type == "ask_question"


def test_no_pending_general_chat():
    result = parser.parse("what is the memory usage?", None)
    assert result.type == "general_chat"


def test_no_pending_approve_is_general():
    result = parser.parse("approve", None)
    assert result.type == "general_chat"
