"""Task 2.9 — EvalGate done-ness rules."""
from src.agents.orchestration.eval_gate import EvalGate, EvalGateInputs


def _state(**kw) -> EvalGateInputs:
    base = dict(
        rounds=1,
        max_rounds=10,
        confidence=0.5,
        challenged_verdicts=0,
        coverage_ratio=0.5,
        rounds_since_new_signal=0,
    )
    base.update(kw)
    return EvalGateInputs(**base)


def test_done_when_confidence_high_and_no_challenges():
    decision = EvalGate().is_done(
        _state(confidence=0.78, challenged_verdicts=0, rounds=3, coverage_ratio=0.8)
    )
    assert decision.is_done is True
    assert decision.reason == "high_confidence_no_challenges"


def test_not_done_when_confidence_low_even_at_max_rounds_minus_one():
    decision = EvalGate().is_done(_state(confidence=0.40, rounds=8, max_rounds=10))
    assert decision.is_done is False


def test_done_at_max_rounds_with_inconclusive():
    decision = EvalGate().is_done(_state(confidence=0.30, rounds=10, max_rounds=10))
    assert decision.is_done is True
    assert decision.reason == "max_rounds_reached"


def test_challenged_verdicts_block_high_confidence_termination():
    decision = EvalGate().is_done(_state(confidence=0.90, challenged_verdicts=2))
    # High confidence alone isn't enough when critics are challenging
    assert decision.is_done is False


def test_coverage_saturation_plus_stall_trips_done():
    decision = EvalGate().is_done(
        _state(
            confidence=0.60,
            coverage_ratio=0.80,
            rounds_since_new_signal=2,
            rounds=4,
        )
    )
    assert decision.is_done is True
    assert decision.reason == "coverage_saturated_no_new_signal"


def test_continue_when_no_rule_fires():
    decision = EvalGate().is_done(_state(confidence=0.30, rounds=2))
    assert decision.is_done is False
    assert decision.reason == "continue"


def test_max_rounds_beats_all_other_rules():
    # Even with high confidence, max_rounds takes precedence so the reason
    # logged is the most-honest one.
    decision = EvalGate().is_done(
        _state(confidence=0.95, rounds=10, max_rounds=10)
    )
    assert decision.is_done is True
    assert decision.reason == "max_rounds_reached"
