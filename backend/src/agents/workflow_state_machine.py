from __future__ import annotations
from typing import Any, Callable
from src.models.schemas import DiagnosticPhase


class InvalidTransitionError(Exception):
    pass


class WorkflowStateMachine:
    """Enforces valid diagnostic phase transitions with guard conditions.

    Every DiagnosticPhase value must appear as a key. The ERROR phase is
    handled specially: any phase can transition to ERROR unconditionally.
    """

    VALID_TRANSITIONS: dict[DiagnosticPhase, list[tuple[DiagnosticPhase, Callable]]] = {
        DiagnosticPhase.INITIAL: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
        ],
        DiagnosticPhase.COLLECTING_CONTEXT: [
            (DiagnosticPhase.LOGS_ANALYZED, lambda s: True),
            (DiagnosticPhase.METRICS_ANALYZED, lambda s: True),
            (DiagnosticPhase.K8S_ANALYZED, lambda s: True),
            (DiagnosticPhase.TRACING_ANALYZED, lambda s: True),
            (DiagnosticPhase.CODE_ANALYZED, lambda s: True),
        ],
        DiagnosticPhase.LOGS_ANALYZED: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.METRICS_ANALYZED, lambda s: True),
            (DiagnosticPhase.K8S_ANALYZED, lambda s: True),
            (DiagnosticPhase.TRACING_ANALYZED, lambda s: True),
            (DiagnosticPhase.CODE_ANALYZED, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.METRICS_ANALYZED: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.LOGS_ANALYZED, lambda s: True),
            (DiagnosticPhase.K8S_ANALYZED, lambda s: True),
            (DiagnosticPhase.TRACING_ANALYZED, lambda s: True),
            (DiagnosticPhase.CODE_ANALYZED, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.K8S_ANALYZED: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.LOGS_ANALYZED, lambda s: True),
            (DiagnosticPhase.METRICS_ANALYZED, lambda s: True),
            (DiagnosticPhase.TRACING_ANALYZED, lambda s: True),
            (DiagnosticPhase.CODE_ANALYZED, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.TRACING_ANALYZED: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.LOGS_ANALYZED, lambda s: True),
            (DiagnosticPhase.METRICS_ANALYZED, lambda s: True),
            (DiagnosticPhase.K8S_ANALYZED, lambda s: True),
            (DiagnosticPhase.CODE_ANALYZED, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.CODE_ANALYZED: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.LOGS_ANALYZED, lambda s: True),
            (DiagnosticPhase.METRICS_ANALYZED, lambda s: True),
            (DiagnosticPhase.K8S_ANALYZED, lambda s: True),
            (DiagnosticPhase.TRACING_ANALYZED, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.VALIDATING: [
            (DiagnosticPhase.DIAGNOSIS_COMPLETE, lambda s: True),
            (DiagnosticPhase.RE_INVESTIGATING, lambda s: True),
        ],
        DiagnosticPhase.RE_INVESTIGATING: [
            (DiagnosticPhase.COLLECTING_CONTEXT, lambda s: True),
            (DiagnosticPhase.VALIDATING, lambda s: True),
        ],
        DiagnosticPhase.DIAGNOSIS_COMPLETE: [
            (DiagnosticPhase.FIX_IN_PROGRESS, lambda s: getattr(s, 'attestation_acknowledged', False)),
            (DiagnosticPhase.RE_INVESTIGATING, lambda s: True),
        ],
        DiagnosticPhase.FIX_IN_PROGRESS: [
            (DiagnosticPhase.COMPLETE, lambda s: getattr(s, 'fix_decided', False)),
            (DiagnosticPhase.DIAGNOSIS_COMPLETE, lambda s: True),
        ],
        DiagnosticPhase.COMPLETE: [],
        DiagnosticPhase.ERROR: [
            # Allow recovery from error back to initial
            (DiagnosticPhase.INITIAL, lambda s: True),
        ],
    }

    def transition(self, state: Any, target: DiagnosticPhase) -> None:
        """Transition state to target phase if allowed, otherwise raise InvalidTransitionError."""
        # Any phase can transition to ERROR unconditionally
        if target == DiagnosticPhase.ERROR:
            state.phase = target
            return

        allowed = self.VALID_TRANSITIONS.get(state.phase, [])
        for target_phase, guard in allowed:
            if target_phase == target and guard(state):
                state.phase = target
                return

        raise InvalidTransitionError(
            f"Cannot transition from {state.phase.value} to {target.value}"
        )
