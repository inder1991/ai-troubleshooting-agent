import pytest
from src.agents.workflow_state_machine import WorkflowStateMachine, InvalidTransitionError
from src.models.schemas import DiagnosticPhase


class FakeState:
    def __init__(self, phase, attestation_acknowledged=False, fix_decided=False):
        self.phase = phase
        self.attestation_acknowledged = attestation_acknowledged
        self.fix_decided = fix_decided


sm = WorkflowStateMachine()


def test_valid_transition_initial_to_collecting():
    state = FakeState(DiagnosticPhase.INITIAL)
    sm.transition(state, DiagnosticPhase.COLLECTING_CONTEXT)
    assert state.phase == DiagnosticPhase.COLLECTING_CONTEXT


def test_valid_transition_diagnosis_to_fix_with_attestation():
    state = FakeState(DiagnosticPhase.DIAGNOSIS_COMPLETE, attestation_acknowledged=True)
    sm.transition(state, DiagnosticPhase.FIX_IN_PROGRESS)
    assert state.phase == DiagnosticPhase.FIX_IN_PROGRESS


def test_invalid_transition_diagnosis_to_fix_without_attestation():
    state = FakeState(DiagnosticPhase.DIAGNOSIS_COMPLETE, attestation_acknowledged=False)
    with pytest.raises(InvalidTransitionError):
        sm.transition(state, DiagnosticPhase.FIX_IN_PROGRESS)


def test_invalid_transition_initial_to_complete():
    state = FakeState(DiagnosticPhase.INITIAL)
    with pytest.raises(InvalidTransitionError):
        sm.transition(state, DiagnosticPhase.COMPLETE)


def test_valid_transition_fix_to_complete():
    state = FakeState(DiagnosticPhase.FIX_IN_PROGRESS, fix_decided=True)
    sm.transition(state, DiagnosticPhase.COMPLETE)
    assert state.phase == DiagnosticPhase.COMPLETE


def test_any_phase_can_go_to_error():
    for phase in DiagnosticPhase:
        if phase == DiagnosticPhase.ERROR:
            continue
        state = FakeState(phase)
        sm.transition(state, DiagnosticPhase.ERROR)
        assert state.phase == DiagnosticPhase.ERROR
