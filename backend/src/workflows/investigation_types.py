"""Virtual DAG model, step spec, and typed step result for investigations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.workflows._schema import _check_schema_version
from src.workflows.event_schema import StepStatus, StepMetadata, ErrorDetail


@dataclass
class InvestigationStepSpec:
    SCHEMA_VERSION = 2

    step_id: str
    agent: str
    idempotency_key: str
    depends_on: list[str] = field(default_factory=list)
    input_data: dict | None = None
    metadata: StepMetadata | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "step_id": self.step_id,
            "agent": self.agent,
            "idempotency_key": self.idempotency_key,
            "depends_on": list(self.depends_on),
        }
        if self.input_data is not None:
            d["input_data"] = self.input_data
        if self.metadata is not None:
            md = self.metadata
            md_dict: dict[str, Any] = {}
            for attr in ("agent", "round", "group", "hypothesis_id", "reason", "duration_ms"):
                val = getattr(md, attr)
                if val is not None:
                    md_dict[attr] = val
            if md.error is not None:
                md_dict["error"] = {"message": md.error.message, "type": md.error.type}
            d["metadata"] = md_dict
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InvestigationStepSpec:
        # v2 added a required ``idempotency_key``. v1 payloads predate the
        # field — synthesize a deterministic legacy key during the grace window.
        version = d.get("schema_version", cls.SCHEMA_VERSION)
        if version not in (1, cls.SCHEMA_VERSION):
            raise ValueError(
                f"unsupported schema_version for {cls.__name__}: got {version!r}, expected {cls.SCHEMA_VERSION}"
            )
        metadata = None
        if d.get("metadata") is not None:
            md = dict(d["metadata"])
            error = None
            if md.get("error") is not None:
                error = ErrorDetail(**md["error"])
            metadata = StepMetadata(
                agent=md.get("agent"),
                round=md.get("round"),
                group=md.get("group"),
                hypothesis_id=md.get("hypothesis_id"),
                reason=md.get("reason"),
                duration_ms=md.get("duration_ms"),
                error=error,
            )
        if version == cls.SCHEMA_VERSION:
            if "idempotency_key" not in d:
                raise ValueError(
                    f"{cls.__name__} v{cls.SCHEMA_VERSION} requires 'idempotency_key'"
                )
            idempotency_key = d["idempotency_key"]
        else:
            idempotency_key = d.get("idempotency_key") or f"legacy-{d['step_id']}"
        return cls(
            step_id=d["step_id"],
            agent=d["agent"],
            idempotency_key=idempotency_key,
            depends_on=d.get("depends_on", []),
            input_data=d.get("input_data"),
            metadata=metadata,
        )


@dataclass
class StepResult:
    SCHEMA_VERSION = 1

    step_id: str
    status: StepStatus
    output: dict | None
    error: ErrorDetail | None
    started_at: str
    ended_at: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "step_id": self.step_id,
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "output": self.output,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
        }
        if self.error is not None:
            d["error"] = {"message": self.error.message, "type": self.error.type}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StepResult:
        _check_schema_version(d, cls.SCHEMA_VERSION, cls.__name__)
        error = None
        if "error" in d and d["error"] is not None:
            error = ErrorDetail(**d["error"])
        return cls(
            step_id=d["step_id"],
            status=StepStatus(d["status"]) if not isinstance(d["status"], StepStatus) else d["status"],
            output=d.get("output"),
            error=error,
            started_at=d["started_at"],
            ended_at=d["ended_at"],
            duration_ms=d["duration_ms"],
        )


@dataclass
class VirtualStep:
    SCHEMA_VERSION = 1

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
    idempotency_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_version": self.SCHEMA_VERSION,
            "step_id": self.step_id,
            "agent": self.agent,
            "depends_on": self.depends_on,
            "status": self.status.value if isinstance(self.status, StepStatus) else self.status,
            "round": self.round,
        }
        for attr in ("group", "triggered_by", "reason", "started_at", "ended_at", "duration_ms", "output", "idempotency_key"):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        if self.error is not None:
            d["error"] = {"message": self.error.message, "type": self.error.type}
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VirtualStep:
        _check_schema_version(d, cls.SCHEMA_VERSION, cls.__name__)
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
            idempotency_key=d.get("idempotency_key"),
        )


@dataclass
class VirtualDag:
    SCHEMA_VERSION = 1

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
            "schema_version": self.SCHEMA_VERSION,
            "run_id": self.run_id,
            "steps": [s.to_dict() for s in self.steps],
            "last_sequence_number": self.last_sequence_number,
            "current_round": self.current_round,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VirtualDag:
        _check_schema_version(d, cls.SCHEMA_VERSION, cls.__name__)
        dag = cls(
            run_id=d["run_id"],
            last_sequence_number=d.get("last_sequence_number", 0),
            current_round=d.get("current_round", 0),
            status=d.get("status", "running"),
        )
        for step_data in d.get("steps", []):
            dag.steps.append(VirtualStep.from_dict(step_data))
        return dag
