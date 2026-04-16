"""Virtual DAG model, step spec, and typed step result for investigations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.workflows.event_schema import StepStatus, StepMetadata, ErrorDetail


@dataclass
class InvestigationStepSpec:
    step_id: str
    agent: str
    depends_on: list[str] = field(default_factory=list)
    input_data: dict | None = None
    metadata: StepMetadata | None = None


@dataclass
class StepResult:
    step_id: str
    status: StepStatus
    output: dict | None
    error: ErrorDetail | None
    started_at: str
    ended_at: str
    duration_ms: int


@dataclass
class VirtualStep:
    step_id: str
    agent: str
    depends_on: list[str]
    status: StepStatus
    round: int
    group: str | None = None
    triggered_by: str | None = None
    reason: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    output: dict | None = None
    error: ErrorDetail | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "step_id": self.step_id,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "round": self.round,
        }
        for attr in ("group", "triggered_by", "reason", "started_at", "ended_at", "duration_ms", "output"):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        if self.error is not None:
            d["error"] = {"message": self.error.message, "type": self.error.type}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VirtualStep:
        error = None
        if "error" in d and d["error"] is not None:
            error = ErrorDetail(**d["error"])
        return cls(
            step_id=d["step_id"],
            agent=d["agent"],
            depends_on=d.get("depends_on", []),
            status=StepStatus(d["status"]),
            round=d["round"],
            group=d.get("group"),
            triggered_by=d.get("triggered_by"),
            reason=d.get("reason"),
            started_at=d.get("started_at"),
            ended_at=d.get("ended_at"),
            duration_ms=d.get("duration_ms"),
            output=d.get("output"),
            error=error,
        )


@dataclass
class VirtualDag:
    run_id: str
    steps: list[VirtualStep] = field(default_factory=list)
    last_sequence_number: int = 0
    current_round: int = 0
    status: str = "running"  # "running" | "completed" | "failed"

    def append_step(self, step: VirtualStep) -> None:
        self.steps.append(step)

    def next_sequence(self) -> int:
        self.last_sequence_number += 1
        return self.last_sequence_number

    def get_step(self, step_id: str) -> VirtualStep | None:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def update_step(self, step_id: str, **kwargs: Any) -> None:
        step = self.get_step(step_id)
        if step is None:
            return
        for k, v in kwargs.items():
            setattr(step, k, v)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "steps": [s.to_dict() for s in self.steps],
            "last_sequence_number": self.last_sequence_number,
            "current_round": self.current_round,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VirtualDag:
        dag = cls(
            run_id=d["run_id"],
            last_sequence_number=d.get("last_sequence_number", 0),
            current_round=d.get("current_round", 0),
            status=d.get("status", "running"),
        )
        for step_data in d.get("steps", []):
            dag.steps.append(VirtualStep.from_dict(step_data))
        return dag
