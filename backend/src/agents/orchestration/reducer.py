"""Reducer — deterministic merge of agent results into state updates.

Takes a list of ``StepResult`` (from the Dispatcher) and produces a
structured update payload that the supervisor applies to its state. The
reducer is deliberately dumb: no LLM, no heuristics, just:
  - collect successful agents into ``agents_completed``
  - collect evidence pins from each result's payload
  - collect failures into ``failed_agents`` (the planner uses this to not
    retry them within the same run)

Keeping this a pure function makes it trivial to test and trivial to
replace when a more sophisticated merge policy is needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.agents.orchestration.dispatcher import StepResult


@dataclass(frozen=True)
class ReducedRound:
    agents_completed: list[str]
    failed_agents: list[str]
    evidence_pins: list[Any]
    new_signal: bool


class Reducer:
    """Merges a round's StepResults into a structured update payload."""

    def reduce(self, results: list[StepResult]) -> ReducedRound:
        completed: list[str] = []
        failed: list[str] = []
        pins: list[Any] = []
        seen_any_new_pin = False

        for r in results:
            if r.status == "ok":
                completed.append(r.agent)
                payload_pins = self._extract_pins(r.value)
                if payload_pins:
                    seen_any_new_pin = True
                pins.extend(payload_pins)
            else:
                failed.append(r.agent)

        return ReducedRound(
            agents_completed=completed,
            failed_agents=failed,
            evidence_pins=pins,
            new_signal=seen_any_new_pin,
        )

    @staticmethod
    def _extract_pins(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            pins = value.get("evidence_pins") or []
            return list(pins) if isinstance(pins, list) else []
        return []
