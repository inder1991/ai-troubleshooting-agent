"""Thin adapter: translates investigation step state into canonical EventEnvelope
and emits via the existing WebSocket EventEmitter. Translates, does not interpret."""
from __future__ import annotations

from src.workflows.event_schema import (
    StepMetadata,
    make_step_event,
    make_run_event,
)
from src.workflows.investigation_types import VirtualStep
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvestigationEventAdapter:
    def __init__(self, run_id: str, emitter):
        self._run_id = run_id
        self._emitter = emitter

    async def emit_step_update(self, step: VirtualStep, sequence_number: int) -> None:
        metadata = StepMetadata(
            agent=step.agent,
            round=step.round,
            group=step.group,
            hypothesis_id=step.triggered_by,
            reason=step.reason,
            duration_ms=step.duration_ms,
            error=step.error,
        )
        envelope = make_step_event(
            run_id=self._run_id,
            step_id=step.step_id,
            parent_step_ids=step.depends_on,
            status=step.status,
            sequence_number=sequence_number,
            started_at=step.started_at,
            ended_at=step.ended_at,
            metadata=metadata,
        )
        await self._emitter.emit(
            "investigation",
            "step_update",
            f"Step {step.step_id}: {step.status.value}",
            details=envelope.to_dict(),
        )

    async def emit_run_update(self, status: str, sequence_number: int) -> None:
        envelope = make_run_event(
            run_id=self._run_id,
            status=status,
            sequence_number=sequence_number,
        )
        await self._emitter.emit(
            "investigation",
            "run_update",
            f"Investigation {self._run_id}: {status}",
            details=envelope.to_dict(),
        )
