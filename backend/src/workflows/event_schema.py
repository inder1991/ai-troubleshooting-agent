"""Canonical event envelope and typed payloads for investigation + workflow events."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ErrorDetail:
    message: str
    type: str | None = None


@dataclass(frozen=True)
class StepMetadata:
    agent: str | None = None
    round: int | None = None
    group: str | None = None
    hypothesis_id: str | None = None
    reason: str | None = None
    duration_ms: int | None = None
    error: ErrorDetail | None = None


@dataclass(frozen=True)
class StepPayload:
    step_id: str
    parent_step_ids: list[str]
    status: StepStatus
    started_at: str | None = None
    ended_at: str | None = None
    metadata: StepMetadata | None = None


@dataclass(frozen=True)
class RunPayload:
    status: str  # "running" | "completed" | "failed"


@dataclass(frozen=True)
class ErrorPayload:
    message: str
    recoverable: bool = True


@dataclass(frozen=True)
class EventEnvelope:
    event_type: str  # "step_update" | "run_update" | "error"
    run_id: str
    sequence_number: int
    timestamp: str
    payload: StepPayload | RunPayload | ErrorPayload

    def to_dict(self) -> dict[str, Any]:
        def _convert(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {
                    k: _convert(v)
                    for k, v in asdict(obj).items()
                    if v is not None
                }
            if isinstance(obj, list):
                return [_convert(i) for i in obj]
            return obj

        return {
            "event_type": self.event_type,
            "run_id": self.run_id,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp,
            "payload": _convert(self.payload),
        }


def make_step_event(
    *,
    run_id: str,
    step_id: str,
    parent_step_ids: list[str],
    status: StepStatus,
    sequence_number: int,
    started_at: str | None = None,
    ended_at: str | None = None,
    metadata: StepMetadata | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type="step_update",
        run_id=run_id,
        sequence_number=sequence_number,
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload=StepPayload(
            step_id=step_id,
            parent_step_ids=parent_step_ids,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            metadata=metadata,
        ),
    )


def make_run_event(
    *,
    run_id: str,
    status: str,
    sequence_number: int,
) -> EventEnvelope:
    return EventEnvelope(
        event_type="run_update",
        run_id=run_id,
        sequence_number=sequence_number,
        timestamp=datetime.now(timezone.utc).isoformat(),
        payload=RunPayload(status=status),
    )
