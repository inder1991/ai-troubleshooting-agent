"""EvalGate — explicit done-ness rules for an investigation.

The supervisor's loop termination used to be implicit ("break when
`_decide_next_agents` returns []"). That worked in the happy path but made
"why did we stop?" untraceable when confidence was low or when a round
produced no new signal.

This module replaces that with an explicit, auditable predicate. Rules are
ordered; the first matching rule decides. Each returned tuple is
``(is_done, reason)`` so the UI can show which condition tripped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvalGateInputs:
    """Minimum state needed to decide done-ness.

    Intentionally flat and tiny — the gate must not have to reach into the
    full DiagnosticState to reason about stopping.
    """

    rounds: int
    max_rounds: int
    confidence: float
    challenged_verdicts: int = 0
    coverage_ratio: float = 1.0
    rounds_since_new_signal: int = 0


@dataclass(frozen=True)
class GateDecision:
    is_done: bool
    reason: str


class EvalGate:
    """Deterministic stopping rules. No LLM, no randomness, no surprises."""

    # Thresholds pulled from the plan's Task 2.9 Step 2. Kept as class-level
    # constants so a future tune is a single diff with a git-blame reason.
    _HIGH_CONFIDENCE: float = 0.75
    _SUFFICIENT_CONFIDENCE: float = 0.50
    _SUFFICIENT_COVERAGE: float = 0.75
    _STALL_ROUNDS: int = 2

    def is_done(self, s: EvalGateInputs) -> GateDecision:
        if s.rounds >= s.max_rounds:
            return GateDecision(True, "max_rounds_reached")
        if s.confidence > self._HIGH_CONFIDENCE and s.challenged_verdicts == 0:
            return GateDecision(True, "high_confidence_no_challenges")
        if (
            s.confidence > self._SUFFICIENT_CONFIDENCE
            and s.coverage_ratio > self._SUFFICIENT_COVERAGE
            and s.rounds_since_new_signal >= self._STALL_ROUNDS
        ):
            return GateDecision(True, "coverage_saturated_no_new_signal")
        return GateDecision(False, "continue")
