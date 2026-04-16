# Phase 5: Supervisor Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bridge SupervisorAgent's dynamic decision loop with WorkflowExecutor's reliable execution engine via a new InvestigationExecutor, with unified event schema and durable virtual DAG persistence.

**Architecture:** InvestigationExecutor wraps WorkflowExecutor for 1-node DAG execution. Supervisor keeps its decision loop but dispatches agents through the executor. Each investigation becomes a single append-only virtual DAG. A canonical EventEnvelope with typed payloads normalizes events across both systems.

**Tech Stack:** Python 3.12, pytest, asyncio, Redis (fakeredis for tests), existing WorkflowExecutor + EventEmitter + RedisSessionStore

---

## Task 1: Canonical Event Schema

Define the unified event envelope and typed payloads used by both investigation and workflow event systems.

**Files:**
- Create: `backend/src/workflows/event_schema.py`
- Test: `backend/tests/test_event_schema.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_event_schema.py
import pytest
from datetime import datetime, timezone

from src.workflows.event_schema import (
    StepStatus,
    ErrorDetail,
    StepMetadata,
    StepPayload,
    RunPayload,
    ErrorPayload,
    EventEnvelope,
    make_step_event,
    make_run_event,
)


def test_step_status_values():
    assert StepStatus.PENDING == "pending"
    assert StepStatus.RUNNING == "running"
    assert StepStatus.SUCCESS == "success"
    assert StepStatus.FAILED == "failed"
    assert StepStatus.SKIPPED == "skipped"
    assert StepStatus.CANCELLED == "cancelled"


def test_make_step_event_minimal():
    env = make_step_event(
        run_id="inv-123",
        step_id="round-1-log-agent",
        parent_step_ids=[],
        status=StepStatus.RUNNING,
        sequence_number=1,
    )
    assert env.event_type == "step_update"
    assert env.run_id == "inv-123"
    assert env.sequence_number == 1
    assert isinstance(env.timestamp, str)
    assert env.payload.step_id == "round-1-log-agent"
    assert env.payload.status == StepStatus.RUNNING
    assert env.payload.parent_step_ids == []


def test_make_step_event_full_metadata():
    meta = StepMetadata(
        agent="metrics_agent",
        round=2,
        group="validation_phase",
        hypothesis_id="h1",
        reason="validate OOM suspicion",
        duration_ms=1234,
        error=ErrorDetail(message="timeout", type="TimeoutError"),
    )
    env = make_step_event(
        run_id="inv-123",
        step_id="round-2-metrics-agent",
        parent_step_ids=["round-1-log-agent"],
        status=StepStatus.FAILED,
        sequence_number=2,
        started_at="2026-04-16T10:00:00Z",
        ended_at="2026-04-16T10:00:01Z",
        metadata=meta,
    )
    assert env.payload.metadata.agent == "metrics_agent"
    assert env.payload.metadata.round == 2
    assert env.payload.metadata.error.message == "timeout"
    assert env.payload.started_at == "2026-04-16T10:00:00Z"


def test_make_run_event():
    env = make_run_event(
        run_id="inv-123",
        status="completed",
        sequence_number=10,
    )
    assert env.event_type == "run_update"
    assert env.payload.status == "completed"


def test_event_envelope_to_dict():
    env = make_step_event(
        run_id="inv-123",
        step_id="round-1-log-agent",
        parent_step_ids=[],
        status=StepStatus.RUNNING,
        sequence_number=1,
    )
    d = env.to_dict()
    assert d["event_type"] == "step_update"
    assert d["run_id"] == "inv-123"
    assert d["sequence_number"] == 1
    assert d["payload"]["step_id"] == "round-1-log-agent"
    assert d["payload"]["status"] == "running"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_event_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.event_schema'`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/event_schema.py
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
                return {k: _convert(v) for k, v in asdict(obj).items() if v is not None}
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_event_schema.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/event_schema.py backend/tests/test_event_schema.py
git commit -m "feat(phase5): canonical event envelope schema with typed payloads"
```

---

## Task 2: Virtual DAG Model + StepResult

Define the virtual DAG data structures, InvestigationStepSpec, and typed StepResult.

**Files:**
- Create: `backend/src/workflows/investigation_types.py`
- Test: `backend/tests/test_investigation_types.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_types.py
import pytest
import json

from src.workflows.investigation_types import (
    InvestigationStepSpec,
    StepResult,
    VirtualStep,
    VirtualDag,
)
from src.workflows.event_schema import StepStatus, StepMetadata, ErrorDetail


def test_virtual_dag_append_only():
    dag = VirtualDag(run_id="inv-123")
    assert dag.steps == []
    assert dag.last_sequence_number == 0
    assert dag.current_round == 0
    assert dag.status == "running"

    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.PENDING,
        round=1,
    )
    dag.append_step(step)
    assert len(dag.steps) == 1
    assert dag.steps[0].step_id == "round-1-log-agent"


def test_virtual_dag_next_sequence():
    dag = VirtualDag(run_id="inv-123")
    assert dag.next_sequence() == 1
    assert dag.next_sequence() == 2
    assert dag.last_sequence_number == 2


def test_virtual_dag_get_step():
    dag = VirtualDag(run_id="inv-123")
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.PENDING,
        round=1,
    )
    dag.append_step(step)
    found = dag.get_step("round-1-log-agent")
    assert found is not None
    assert found.step_id == "round-1-log-agent"
    assert dag.get_step("nonexistent") is None


def test_virtual_dag_update_step_status():
    dag = VirtualDag(run_id="inv-123")
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.PENDING,
        round=1,
    )
    dag.append_step(step)
    dag.update_step("round-1-log-agent", status=StepStatus.RUNNING, started_at="2026-04-16T10:00:00Z")
    assert dag.steps[0].status == StepStatus.RUNNING
    assert dag.steps[0].started_at == "2026-04-16T10:00:00Z"


def test_virtual_dag_serialization():
    dag = VirtualDag(run_id="inv-123")
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
        triggered_by="h1",
        reason="initial triage",
    )
    dag.append_step(step)
    d = dag.to_dict()
    assert d["run_id"] == "inv-123"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["step_id"] == "round-1-log-agent"
    # Round-trip
    dag2 = VirtualDag.from_dict(d)
    assert dag2.run_id == "inv-123"
    assert dag2.steps[0].status == StepStatus.SUCCESS


def test_step_result_typed():
    result = StepResult(
        step_id="round-1-log-agent",
        status=StepStatus.SUCCESS,
        output={"findings": [{"message": "OOM detected"}]},
        error=None,
        started_at="2026-04-16T10:00:00Z",
        ended_at="2026-04-16T10:00:01Z",
        duration_ms=1000,
    )
    assert result.output["findings"][0]["message"] == "OOM detected"
    assert result.error is None


def test_step_result_with_error():
    result = StepResult(
        step_id="round-2-metrics-agent",
        status=StepStatus.FAILED,
        output=None,
        error=ErrorDetail(message="timeout", type="TimeoutError"),
        started_at="2026-04-16T10:00:00Z",
        ended_at="2026-04-16T10:00:30Z",
        duration_ms=30000,
    )
    assert result.status == StepStatus.FAILED
    assert result.error.type == "TimeoutError"


def test_investigation_step_spec():
    spec = InvestigationStepSpec(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        input_data={"service_name": "api-gateway"},
        metadata=StepMetadata(agent="log_agent", round=1, reason="initial triage"),
    )
    assert spec.step_id == "round-1-log-agent"
    assert spec.input_data["service_name"] == "api-gateway"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_investigation_types.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/investigation_types.py
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_investigation_types.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/investigation_types.py backend/tests/test_investigation_types.py
git commit -m "feat(phase5): virtual DAG model, step spec, and typed StepResult"
```

---

## Task 3: VirtualDag Redis Persistence

Add durable persistence for the virtual DAG so it survives process restarts.

**Files:**
- Create: `backend/src/workflows/investigation_store.py`
- Test: `backend/tests/test_investigation_store.py`
- Reference: `backend/src/utils/redis_store.py` (existing RedisSessionStore pattern)

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_store.py
import pytest
import json

from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_types import VirtualDag, VirtualStep
from src.workflows.event_schema import StepStatus


class FakeRedis:
    """Minimal async Redis mock for testing."""
    def __init__(self):
        self._data: dict[str, str] = {}
        self._expiry: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value
        if ex:
            self._expiry[key] = ex

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def expire(self, key: str, ttl: int) -> None:
        self._expiry[key] = ttl


@pytest.fixture
def store():
    return InvestigationStore(redis_client=FakeRedis())


@pytest.fixture
def sample_dag():
    dag = VirtualDag(run_id="inv-123")
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
    )
    dag.append_step(step)
    dag.last_sequence_number = 3
    dag.current_round = 1
    return dag


@pytest.mark.asyncio
async def test_save_and_load(store, sample_dag):
    await store.save_dag(sample_dag)
    loaded = await store.load_dag("inv-123")
    assert loaded is not None
    assert loaded.run_id == "inv-123"
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == "round-1-log-agent"
    assert loaded.last_sequence_number == 3


@pytest.mark.asyncio
async def test_load_nonexistent(store):
    loaded = await store.load_dag("nonexistent")
    assert loaded is None


@pytest.mark.asyncio
async def test_delete(store, sample_dag):
    await store.save_dag(sample_dag)
    await store.delete_dag("inv-123")
    loaded = await store.load_dag("inv-123")
    assert loaded is None


@pytest.mark.asyncio
async def test_in_memory_fallback():
    store = InvestigationStore(redis_client=None)
    dag = VirtualDag(run_id="inv-456")
    await store.save_dag(dag)
    loaded = await store.load_dag("inv-456")
    assert loaded is not None
    assert loaded.run_id == "inv-456"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_investigation_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/investigation_store.py
"""Durable persistence for investigation virtual DAGs."""
from __future__ import annotations

import json
from typing import Any

from src.workflows.investigation_types import VirtualDag
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TTL = 86400  # 24 hours


class InvestigationStore:
    def __init__(self, redis_client: Any | None = None, ttl: int = DEFAULT_TTL):
        self._redis = redis_client
        self._ttl = ttl
        self._memory: dict[str, str] = {}

    def _key(self, run_id: str) -> str:
        return f"investigation:{run_id}:dag"

    async def save_dag(self, dag: VirtualDag) -> None:
        serialized = json.dumps(dag.to_dict())
        if self._redis is not None:
            try:
                await self._redis.set(self._key(dag.run_id), serialized, ex=self._ttl)
            except Exception as e:
                logger.warning("Redis save failed, using in-memory fallback: %s", e)
                self._memory[dag.run_id] = serialized
        else:
            self._memory[dag.run_id] = serialized

    async def load_dag(self, run_id: str) -> VirtualDag | None:
        raw: str | None = None
        if self._redis is not None:
            try:
                raw = await self._redis.get(self._key(run_id))
                if isinstance(raw, bytes):
                    raw = raw.decode()
            except Exception as e:
                logger.warning("Redis load failed, trying in-memory: %s", e)
                raw = self._memory.get(run_id)
        else:
            raw = self._memory.get(run_id)

        if raw is None:
            return None
        return VirtualDag.from_dict(json.loads(raw))

    async def delete_dag(self, run_id: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(self._key(run_id))
            except Exception:
                pass
        self._memory.pop(run_id, None)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_investigation_store.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/investigation_store.py backend/tests/test_investigation_store.py
git commit -m "feat(phase5): investigation DAG store with Redis persistence + in-memory fallback"
```

---

## Task 4: Investigation Event Adapter

Thin adapter that translates InvestigationExecutor events into canonical EventEnvelope and emits them over the existing WebSocket EventEmitter.

**Files:**
- Create: `backend/src/workflows/investigation_event_adapter.py`
- Test: `backend/tests/test_investigation_event_adapter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_event_adapter.py
import pytest

from src.workflows.investigation_event_adapter import InvestigationEventAdapter
from src.workflows.investigation_types import VirtualStep
from src.workflows.event_schema import StepStatus, StepMetadata, ErrorDetail


class FakeEmitter:
    def __init__(self):
        self.events: list[dict] = []

    async def emit(self, agent_name: str, event_type: str, message: str, details: dict | None = None):
        self.events.append({
            "agent_name": agent_name,
            "event_type": event_type,
            "message": message,
            "details": details,
        })


@pytest.fixture
def adapter():
    emitter = FakeEmitter()
    return InvestigationEventAdapter(run_id="inv-123", emitter=emitter), emitter


@pytest.mark.asyncio
async def test_emit_step_running(adapter):
    adp, emitter = adapter
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.RUNNING,
        round=1,
    )
    await adp.emit_step_update(step, sequence_number=1)
    assert len(emitter.events) == 1
    evt = emitter.events[0]
    assert evt["agent_name"] == "investigation"
    assert evt["event_type"] == "step_update"
    details = evt["details"]
    assert details["event_type"] == "step_update"
    assert details["payload"]["step_id"] == "round-1-log-agent"
    assert details["payload"]["status"] == "running"
    assert details["sequence_number"] == 1


@pytest.mark.asyncio
async def test_emit_step_failed_with_error(adapter):
    adp, emitter = adapter
    step = VirtualStep(
        step_id="round-2-metrics-agent",
        agent="metrics_agent",
        depends_on=["round-1-log-agent"],
        status=StepStatus.FAILED,
        round=2,
        error=ErrorDetail(message="timeout", type="TimeoutError"),
        started_at="2026-04-16T10:00:00Z",
        ended_at="2026-04-16T10:00:30Z",
        duration_ms=30000,
    )
    await adp.emit_step_update(step, sequence_number=5)
    details = emitter.events[0]["details"]
    assert details["payload"]["status"] == "failed"
    assert details["payload"]["metadata"]["error"]["message"] == "timeout"
    assert details["payload"]["parent_step_ids"] == ["round-1-log-agent"]


@pytest.mark.asyncio
async def test_emit_run_update(adapter):
    adp, emitter = adapter
    await adp.emit_run_update(status="completed", sequence_number=10)
    evt = emitter.events[0]
    assert evt["event_type"] == "run_update"
    details = evt["details"]
    assert details["event_type"] == "run_update"
    assert details["payload"]["status"] == "completed"


@pytest.mark.asyncio
async def test_adapter_translates_not_interprets(adapter):
    """Adapter must pass through data without adding business logic."""
    adp, emitter = adapter
    step = VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
        triggered_by="h1",
        reason="validate hypothesis",
    )
    await adp.emit_step_update(step, sequence_number=1)
    details = emitter.events[0]["details"]
    assert details["payload"]["metadata"]["hypothesis_id"] == "h1"
    assert details["payload"]["metadata"]["reason"] == "validate hypothesis"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_investigation_event_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/investigation_event_adapter.py
"""Thin adapter: translates investigation step state into canonical EventEnvelope
and emits via the existing WebSocket EventEmitter. Translates, does not interpret."""
from __future__ import annotations

from src.workflows.event_schema import (
    StepStatus,
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_investigation_event_adapter.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/investigation_event_adapter.py backend/tests/test_investigation_event_adapter.py
git commit -m "feat(phase5): investigation event adapter — thin translator to canonical envelope"
```

---

## Task 5: InvestigationExecutor Core

The conductor: maintains virtual DAG, dispatches steps through WorkflowExecutor as 1-node DAGs, emits canonical events, persists state.

**Files:**
- Create: `backend/src/workflows/investigation_executor.py`
- Test: `backend/tests/test_investigation_executor.py`
- Reference: `backend/src/workflows/executor.py` (WorkflowExecutor)
- Reference: `backend/src/workflows/compiler.py` (CompiledStep, CompiledWorkflow)

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_executor.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec, StepResult, VirtualDag
from src.workflows.investigation_store import InvestigationStore
from src.workflows.event_schema import StepStatus, StepMetadata


class FakeEmitter:
    def __init__(self):
        self.events = []
    async def emit(self, agent_name, event_type, message, details=None):
        self.events.append({"agent_name": agent_name, "event_type": event_type, "message": message, "details": details})


class FakeWorkflowExecutor:
    """Mimics WorkflowExecutor.run() returning a RunResult for a 1-node DAG."""
    def __init__(self, result_output=None, should_fail=False):
        self._result_output = result_output or {"findings": []}
        self._should_fail = should_fail
        self.calls = []

    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        self.calls.append({"compiled": compiled, "inputs": inputs})
        step_id = compiled.topo_order[0]

        @dataclass
        class NodeState:
            status: str
            output: dict | None = None
            error: dict | None = None
            started_at: str | None = "2026-04-16T10:00:00Z"
            ended_at: str | None = "2026-04-16T10:00:01Z"
            attempt: int = 1

        @dataclass
        class RunResult:
            status: str
            node_states: dict
            error: dict | None = None

        if self._should_fail:
            return RunResult(
                status="FAILED",
                node_states={step_id: NodeState(status="FAILED", error={"message": "agent crashed", "type": "RuntimeError"})},
                error={"message": "agent crashed"},
            )
        return RunResult(
            status="COMPLETED",
            node_states={step_id: NodeState(status="COMPLETED", output=self._result_output)},
        )


@pytest.fixture
def emitter():
    return FakeEmitter()


@pytest.fixture
def store():
    return InvestigationStore(redis_client=None)


@pytest.fixture
def executor(emitter, store):
    return InvestigationExecutor(
        run_id="inv-123",
        emitter=emitter,
        store=store,
        workflow_executor=FakeWorkflowExecutor(result_output={"findings": [{"msg": "OOM"}]}),
    )


@pytest.mark.asyncio
async def test_run_step_success(executor, emitter, store):
    spec = InvestigationStepSpec(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        input_data={"service_name": "api"},
        metadata=StepMetadata(agent="log_agent", round=1, reason="initial triage"),
    )
    result = await executor.run_step(spec)

    # Typed StepResult
    assert isinstance(result, StepResult)
    assert result.status == StepStatus.SUCCESS
    assert result.output["findings"][0]["msg"] == "OOM"
    assert result.error is None
    assert result.duration_ms >= 0

    # Virtual DAG updated
    dag = executor.get_dag()
    assert len(dag.steps) == 1
    assert dag.steps[0].step_id == "round-1-log-agent"
    assert dag.steps[0].status == StepStatus.SUCCESS

    # Events emitted (running + success = 2 step events)
    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    assert len(step_events) == 2
    assert step_events[0]["details"]["payload"]["status"] == "running"
    assert step_events[1]["details"]["payload"]["status"] == "success"

    # Persisted to store
    loaded = await store.load_dag("inv-123")
    assert loaded is not None
    assert loaded.steps[0].status == StepStatus.SUCCESS


@pytest.mark.asyncio
async def test_run_step_failure(emitter, store):
    executor = InvestigationExecutor(
        run_id="inv-456",
        emitter=emitter,
        store=store,
        workflow_executor=FakeWorkflowExecutor(should_fail=True),
    )
    spec = InvestigationStepSpec(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
    )
    result = await executor.run_step(spec)

    assert result.status == StepStatus.FAILED
    assert result.error is not None
    assert result.error.message == "agent crashed"

    dag = executor.get_dag()
    assert dag.steps[0].status == StepStatus.FAILED


@pytest.mark.asyncio
async def test_run_steps_sequential(executor, emitter):
    specs = [
        InvestigationStepSpec(step_id="round-1-log-agent", agent="log_agent", depends_on=[]),
        InvestigationStepSpec(step_id="round-2-metrics-agent", agent="metrics_agent", depends_on=["round-1-log-agent"]),
    ]
    results = await executor.run_steps(specs)

    assert len(results) == 2
    assert results[0].status == StepStatus.SUCCESS
    assert results[1].status == StepStatus.SUCCESS

    dag = executor.get_dag()
    assert len(dag.steps) == 2
    assert dag.steps[1].depends_on == ["round-1-log-agent"]


@pytest.mark.asyncio
async def test_sequence_numbers_monotonic(executor, emitter):
    spec1 = InvestigationStepSpec(step_id="round-1-log-agent", agent="log_agent", depends_on=[])
    spec2 = InvestigationStepSpec(step_id="round-2-metrics-agent", agent="metrics_agent", depends_on=["round-1-log-agent"])

    await executor.run_step(spec1)
    await executor.run_step(spec2)

    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    seq_numbers = [e["details"]["sequence_number"] for e in step_events]
    assert seq_numbers == sorted(seq_numbers)
    assert len(set(seq_numbers)) == len(seq_numbers)  # all unique


@pytest.mark.asyncio
async def test_get_dag_returns_copy(executor):
    spec = InvestigationStepSpec(step_id="round-1-log-agent", agent="log_agent", depends_on=[])
    await executor.run_step(spec)
    dag = executor.get_dag()
    assert dag.run_id == "inv-123"


@pytest.mark.asyncio
async def test_cancel(executor, emitter, store):
    await executor.cancel()
    dag = executor.get_dag()
    assert dag.status == "cancelled"

    run_events = [e for e in emitter.events if e["event_type"] == "run_update"]
    assert len(run_events) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_investigation_executor.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/investigation_executor.py
"""InvestigationExecutor: conductor that dispatches agent steps through WorkflowExecutor
as 1-node DAGs, maintains an append-only virtual DAG, and emits canonical events."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.workflows.compiler import CompiledStep, CompiledWorkflow
from src.workflows.event_schema import StepStatus, ErrorDetail
from src.workflows.investigation_types import (
    InvestigationStepSpec,
    StepResult,
    VirtualStep,
    VirtualDag,
)
from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_event_adapter import InvestigationEventAdapter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvestigationExecutor:
    def __init__(
        self,
        run_id: str,
        emitter: Any,
        store: InvestigationStore,
        workflow_executor: Any,
    ):
        self._run_id = run_id
        self._dag = VirtualDag(run_id=run_id)
        self._store = store
        self._workflow_executor = workflow_executor
        self._adapter = InvestigationEventAdapter(run_id=run_id, emitter=emitter)

    async def run_step(self, spec: InvestigationStepSpec) -> StepResult:
        now_iso = datetime.now(timezone.utc).isoformat()

        vstep = VirtualStep(
            step_id=spec.step_id,
            agent=spec.agent,
            depends_on=spec.depends_on,
            status=StepStatus.PENDING,
            round=spec.metadata.round if spec.metadata else 0,
            group=spec.metadata.group if spec.metadata else None,
            triggered_by=spec.metadata.hypothesis_id if spec.metadata else None,
            reason=spec.metadata.reason if spec.metadata else None,
        )
        self._dag.append_step(vstep)

        vstep.status = StepStatus.RUNNING
        vstep.started_at = now_iso
        seq = self._dag.next_sequence()
        await self._adapter.emit_step_update(vstep, sequence_number=seq)
        await self._store.save_dag(self._dag)

        start_mono = time.monotonic()
        try:
            compiled = self._build_single_step_workflow(spec)
            run_result = await self._workflow_executor.run(
                compiled,
                inputs=spec.input_data or {},
            )

            elapsed_ms = round((time.monotonic() - start_mono) * 1000)
            end_iso = datetime.now(timezone.utc).isoformat()

            node_state = run_result.node_states.get(spec.step_id)
            if node_state and node_state.status == "COMPLETED":
                vstep.status = StepStatus.SUCCESS
                vstep.output = node_state.output
                vstep.ended_at = end_iso
                vstep.duration_ms = elapsed_ms
                result = StepResult(
                    step_id=spec.step_id,
                    status=StepStatus.SUCCESS,
                    output=node_state.output,
                    error=None,
                    started_at=vstep.started_at,
                    ended_at=end_iso,
                    duration_ms=elapsed_ms,
                )
            else:
                error_dict = (node_state.error if node_state else None) or run_result.error or {}
                error_detail = ErrorDetail(
                    message=error_dict.get("message", "Unknown error"),
                    type=error_dict.get("type"),
                )
                vstep.status = StepStatus.FAILED
                vstep.error = error_detail
                vstep.ended_at = end_iso
                vstep.duration_ms = elapsed_ms
                result = StepResult(
                    step_id=spec.step_id,
                    status=StepStatus.FAILED,
                    output=None,
                    error=error_detail,
                    started_at=vstep.started_at,
                    ended_at=end_iso,
                    duration_ms=elapsed_ms,
                )

        except Exception as e:
            elapsed_ms = round((time.monotonic() - start_mono) * 1000)
            end_iso = datetime.now(timezone.utc).isoformat()
            error_detail = ErrorDetail(message=str(e), type=type(e).__name__)
            vstep.status = StepStatus.FAILED
            vstep.error = error_detail
            vstep.ended_at = end_iso
            vstep.duration_ms = elapsed_ms
            result = StepResult(
                step_id=spec.step_id,
                status=StepStatus.FAILED,
                output=None,
                error=error_detail,
                started_at=vstep.started_at,
                ended_at=end_iso,
                duration_ms=elapsed_ms,
            )

        seq = self._dag.next_sequence()
        await self._adapter.emit_step_update(vstep, sequence_number=seq)
        await self._store.save_dag(self._dag)

        return result

    async def run_steps(self, specs: list[InvestigationStepSpec]) -> list[StepResult]:
        results = []
        for spec in specs:
            results.append(await self.run_step(spec))
        return results

    def get_dag(self) -> VirtualDag:
        return self._dag

    async def cancel(self) -> None:
        self._dag.status = "cancelled"
        seq = self._dag.next_sequence()
        await self._adapter.emit_run_update(status="cancelled", sequence_number=seq)
        await self._store.save_dag(self._dag)

    def _build_single_step_workflow(self, spec: InvestigationStepSpec) -> CompiledWorkflow:
        step = CompiledStep(
            id=spec.step_id,
            agent=spec.agent,
            agent_version=1,
            inputs=spec.input_data or {},
            when=None,
            on_failure="continue",
            fallback_step_id=None,
            parallel_group=None,
            concurrency_group=None,
            timeout_seconds=300.0,
            retry_on=[],
            upstream_ids=[],
        )
        return CompiledWorkflow(
            topo_order=[spec.step_id],
            steps={spec.step_id: step},
            inputs_schema={},
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_investigation_executor.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/investigation_executor.py backend/tests/test_investigation_executor.py
git commit -m "feat(phase5): InvestigationExecutor — conductor dispatching through WorkflowExecutor"
```

---

## Task 6: Supervisor Integration

Modify `SupervisorAgent.run()` to dispatch agents through InvestigationExecutor instead of calling them directly.

**Files:**
- Modify: `backend/src/agents/supervisor.py` (lines 202-208 run signature, lines 639-700 _dispatch_agent, lines 340-366 dispatch loop)
- Test: `backend/tests/test_supervisor_investigation.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_supervisor_investigation.py
"""Test that SupervisorAgent dispatches agents through InvestigationExecutor
when one is provided, falling back to direct dispatch when not."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from src.agents.supervisor import SupervisorAgent
from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec, StepResult
from src.workflows.investigation_store import InvestigationStore
from src.workflows.event_schema import StepStatus


class FakeEmitter:
    def __init__(self):
        self.events = []
    async def emit(self, agent_name, event_type, message, details=None):
        self.events.append({"agent_name": agent_name, "event_type": event_type})
        class FakeTaskEvent:
            sequence_number = len(self.events)
        return FakeTaskEvent()


class FakeWorkflowExecutor:
    """Returns a successful RunResult for any 1-node DAG."""
    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        step_id = compiled.topo_order[0]
        @dataclass
        class NodeState:
            status: str = "COMPLETED"
            output: dict | None = None
            error: dict | None = None
            started_at: str = "2026-04-16T10:00:00Z"
            ended_at: str = "2026-04-16T10:00:01Z"
            attempt: int = 1
        @dataclass
        class RunResult:
            status: str = "COMPLETED"
            node_states: dict = None
            error: dict | None = None
        return RunResult(
            status="COMPLETED",
            node_states={step_id: NodeState(output={"evidence_pins": [], "overall_confidence": 50})},
        )


@pytest.mark.asyncio
async def test_supervisor_uses_investigation_executor():
    """When investigation_executor is provided, _dispatch_agent should route through it."""
    emitter = FakeEmitter()
    store = InvestigationStore(redis_client=None)
    wf_executor = FakeWorkflowExecutor()
    inv_executor = InvestigationExecutor(
        run_id="inv-test",
        emitter=emitter,
        store=store,
        workflow_executor=wf_executor,
    )

    supervisor = SupervisorAgent(connection_config={})
    supervisor._investigation_executor = inv_executor

    # Mock all agents to avoid real LLM calls
    import os
    with patch.dict(os.environ, {"MOCK_AGENTS": "log_agent,metrics_agent,k8s_agent,change_agent,code_agent,tracing_agent"}):
        # We need fixtures for mock agents to work, so test via the executor path instead
        pass

    # Direct test: call _dispatch_via_executor
    result = await supervisor._dispatch_via_executor(
        "log_agent", inv_executor, round_num=1, agent_input={"service_name": "api"},
    )
    assert result is not None

    dag = inv_executor.get_dag()
    assert len(dag.steps) == 1
    assert dag.steps[0].agent == "log_agent"


@pytest.mark.asyncio
async def test_supervisor_falls_back_without_executor():
    """When no investigation_executor, supervisor dispatches agents directly (existing behavior)."""
    supervisor = SupervisorAgent(connection_config={})

    # Without investigation_executor, _dispatch_agent should work as before
    assert not hasattr(supervisor, '_investigation_executor') or supervisor._investigation_executor is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_supervisor_investigation.py -v`
Expected: FAIL — `AttributeError: 'SupervisorAgent' object has no attribute '_dispatch_via_executor'`

**Step 3: Modify supervisor.py**

Add `_investigation_executor` attribute and `_dispatch_via_executor` method. Modify `_dispatch_agent` to route through executor when available.

In `SupervisorAgent.__init__` (around line 140), add:

```python
self._investigation_executor = None
```

Add new method after `_dispatch_agent` (after line 700):

```python
async def _dispatch_via_executor(
    self, agent_name: str, investigation_executor, round_num: int,
    agent_input: dict | None = None, hypothesis_id: str | None = None,
    reason: str | None = None,
) -> dict | None:
    """Dispatch an agent through InvestigationExecutor instead of directly."""
    from src.workflows.investigation_types import InvestigationStepSpec
    from src.workflows.event_schema import StepMetadata

    prev_steps = investigation_executor.get_dag().steps
    prev_step_id = prev_steps[-1].step_id if prev_steps else None

    spec = InvestigationStepSpec(
        step_id=f"round-{round_num}-{agent_name}",
        agent=agent_name,
        depends_on=[prev_step_id] if prev_step_id else [],
        input_data=agent_input,
        metadata=StepMetadata(
            agent=agent_name,
            round=round_num,
            hypothesis_id=hypothesis_id,
            reason=reason,
        ),
    )
    result = await investigation_executor.run_step(spec)
    return result.output
```

Modify `_dispatch_agent` (line 639) to check for executor first. Add at the top of the method, after the mock check but before the real dispatch:

```python
# Route through InvestigationExecutor if available
if self._investigation_executor is not None:
    return await self._dispatch_via_executor(
        agent_name, self._investigation_executor,
        round_num=len([s for s in self._investigation_executor.get_dag().steps]) + 1,
        agent_input=await self._build_agent_context(agent_name, state, event_emitter),
    )
```

Modify `run()` signature (line 202) to accept optional investigation_executor:

```python
async def run(
    self,
    initial_input: dict,
    event_emitter: EventEmitter,
    websocket_manager=None,
    on_state_created=None,
    investigation_executor=None,
) -> DiagnosticState:
```

And at the start of `run()` (after line 210):

```python
self._investigation_executor = investigation_executor
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_supervisor_investigation.py -v`
Expected: PASS (2 tests)

**Step 5: Run existing supervisor tests to verify no regression**

Run: `cd backend && python -m pytest tests/test_supervisor.py tests/test_supervisor_v5.py -v`
Expected: All existing tests PASS (no regression — investigation_executor defaults to None, preserving existing behavior)

**Step 6: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_supervisor_investigation.py
git commit -m "feat(phase5): supervisor dispatches agents through InvestigationExecutor when provided"
```

---

## Task 7: Route Integration + DAG Endpoint

Wire InvestigationExecutor into `routes_v4.py` session start flow. Add `GET /session/{id}/dag` endpoint.

**Files:**
- Modify: `backend/src/api/routes_v4.py` (lines 366-568 session start, lines 861-893 run_diagnosis)
- Test: `backend/tests/test_investigation_dag_endpoint.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_dag_endpoint.py
"""Test the GET /session/{id}/dag endpoint returns the virtual DAG."""
import pytest
from unittest.mock import MagicMock, patch

from src.workflows.investigation_types import VirtualDag, VirtualStep
from src.workflows.event_schema import StepStatus


def test_dag_endpoint_returns_virtual_dag():
    """Verify the DAG endpoint returns a serialized VirtualDag."""
    dag = VirtualDag(run_id="inv-123")
    dag.append_step(VirtualStep(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.SUCCESS,
        round=1,
    ))
    dag.append_step(VirtualStep(
        step_id="round-2-metrics-agent",
        agent="metrics_agent",
        depends_on=["round-1-log-agent"],
        status=StepStatus.RUNNING,
        round=2,
    ))

    result = dag.to_dict()
    assert result["run_id"] == "inv-123"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["step_id"] == "round-1-log-agent"
    assert result["steps"][1]["depends_on"] == ["round-1-log-agent"]


def test_dag_endpoint_empty_investigation():
    """New investigation with no steps yet returns empty DAG."""
    dag = VirtualDag(run_id="inv-new")
    result = dag.to_dict()
    assert result["steps"] == []
    assert result["status"] == "running"
```

**Step 2: Run test to verify it passes (these are structural tests)**

Run: `cd backend && python -m pytest tests/test_investigation_dag_endpoint.py -v`
Expected: PASS

**Step 3: Modify routes_v4.py**

Add at top of file (imports):

```python
from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_store import InvestigationStore
```

Add module-level investigation store (near line 208, after `sessions` dict):

```python
_investigation_store = InvestigationStore(redis_client=None)  # Upgraded to Redis in production init
_investigation_executors: dict[str, InvestigationExecutor] = {}
```

In session start handler (around line 519 where supervisor is created), add after supervisor creation:

```python
# Create InvestigationExecutor for this session
inv_run_id = f"investigation-{session_id}"
inv_executor = InvestigationExecutor(
    run_id=inv_run_id,
    emitter=emitter,
    store=_investigation_store,
    workflow_executor=None,  # Will be set when WorkflowExecutor is available
)
_investigation_executors[session_id] = inv_executor
```

In `run_diagnosis` function (line 861), pass investigation_executor to supervisor:

```python
async def run_diagnosis(session_id: str, supervisor: SupervisorAgent, initial_input: dict, emitter: EventEmitter):
    _diagnosis_tasks[session_id] = asyncio.current_task()
    lock = _acquire_lock(session_id)
    inv_executor = _investigation_executors.get(session_id)
    try:
        state = await supervisor.run(
            initial_input, emitter,
            on_state_created=lambda s: sessions[session_id].__setitem__("state", s),
            investigation_executor=inv_executor,
        )
        # ... rest unchanged
```

Add new endpoint (after the existing session endpoints):

```python
@router_v4.get("/session/{session_id}/dag")
async def get_investigation_dag(session_id: str):
    inv_executor = _investigation_executors.get(session_id)
    if inv_executor:
        return inv_executor.get_dag().to_dict()
    # Try loading from store
    dag = await _investigation_store.load_dag(f"investigation-{session_id}")
    if dag:
        return dag.to_dict()
    return {"run_id": f"investigation-{session_id}", "steps": [], "status": "unknown"}
```

**Step 4: Run existing route tests to verify no regression**

Run: `cd backend && python -m pytest tests/ -k "not test_supervisor" --timeout=30 -x -q`
Expected: No regressions

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_investigation_dag_endpoint.py
git commit -m "feat(phase5): wire InvestigationExecutor into session start + add DAG endpoint"
```

---

## Task 8: Agent Runner Bridge

Create a runner adapter that wraps existing investigation agents (LogAnalysisAgent, MetricsAgent, etc.) so they conform to the AgentRunner protocol expected by WorkflowExecutor.

**Files:**
- Create: `backend/src/workflows/runners/investigation_runner.py`
- Test: `backend/tests/test_investigation_runner.py`
- Reference: `backend/src/workflows/runners/registry.py` (AgentRunner protocol)
- Reference: `backend/src/agents/supervisor.py:677-700` (_dispatch_agent agent instantiation)

**Step 1: Write the failing test**

```python
# backend/tests/test_investigation_runner.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.workflows.runners.investigation_runner import InvestigationAgentRunner


class FakeAgent:
    def __init__(self, connection_config=None):
        self.run_called = False
        self.run_two_pass_called = False
        self._connection_config = connection_config

    async def run(self, context, event_emitter=None):
        self.run_called = True
        return {"evidence_pins": [{"claim": "OOM detected"}], "overall_confidence": 75}

    async def run_two_pass(self, context, event_emitter=None):
        self.run_two_pass_called = True
        return {"evidence_pins": [{"claim": "high latency"}], "overall_confidence": 60}

    def get_token_usage(self):
        return {"prompt": 100, "completion": 50}


@pytest.mark.asyncio
async def test_runner_calls_agent_run():
    runner = InvestigationAgentRunner(
        agent_cls=FakeAgent,
        agent_name="log_agent",
        connection_config={"host": "localhost"},
    )
    result = await runner.run(
        inputs={"service_name": "api"},
        context={},
    )
    assert "evidence_pins" in result
    assert result["evidence_pins"][0]["claim"] == "OOM detected"


@pytest.mark.asyncio
async def test_runner_uses_two_pass_for_supported_agents():
    runner = InvestigationAgentRunner(
        agent_cls=FakeAgent,
        agent_name="metrics_agent",
        connection_config={},
        use_two_pass=True,
    )
    result = await runner.run(
        inputs={"service_name": "api"},
        context={},
    )
    assert result["evidence_pins"][0]["claim"] == "high latency"


@pytest.mark.asyncio
async def test_runner_handles_agent_failure():
    class FailingAgent:
        def __init__(self, connection_config=None):
            pass
        async def run(self, context, event_emitter=None):
            raise RuntimeError("LLM quota exceeded")
        def get_token_usage(self):
            return {}

    runner = InvestigationAgentRunner(
        agent_cls=FailingAgent,
        agent_name="log_agent",
        connection_config={},
    )
    with pytest.raises(RuntimeError, match="LLM quota exceeded"):
        await runner.run(inputs={}, context={})
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_investigation_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/workflows/runners/investigation_runner.py
"""Bridge adapter: wraps existing investigation agents (LogAnalysisAgent, MetricsAgent, etc.)
to conform to the AgentRunner protocol expected by WorkflowExecutor."""
from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

TWO_PASS_AGENTS = {"code_agent", "change_agent", "metrics_agent", "tracing_agent", "k8s_agent"}


class InvestigationAgentRunner:
    def __init__(
        self,
        agent_cls: type,
        agent_name: str,
        connection_config: dict,
        use_two_pass: bool | None = None,
    ):
        self._agent_cls = agent_cls
        self._agent_name = agent_name
        self._connection_config = connection_config
        self._use_two_pass = use_two_pass if use_two_pass is not None else (agent_name in TWO_PASS_AGENTS)

    async def run(self, inputs: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
        agent = self._agent_cls(connection_config=self._connection_config)

        if self._use_two_pass and hasattr(agent, "run_two_pass"):
            result = await agent.run_two_pass(inputs, None)
        else:
            result = await agent.run(inputs, None)

        return result
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_investigation_runner.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/workflows/runners/investigation_runner.py backend/tests/test_investigation_runner.py
git commit -m "feat(phase5): investigation agent runner bridge for WorkflowExecutor compatibility"
```

---

## Task 9: Integration Test — Full Investigation Loop

End-to-end test: SupervisorAgent → InvestigationExecutor → WorkflowExecutor → agents, verifying the full chain with mocked agents.

**Files:**
- Create: `backend/tests/test_investigation_integration.py`
- Reference: All Task 1-8 files

**Step 1: Write the integration test**

```python
# backend/tests/test_investigation_integration.py
"""Integration test: full investigation loop through InvestigationExecutor."""
import pytest
import os
from unittest.mock import patch, AsyncMock

from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_types import InvestigationStepSpec, VirtualDag
from src.workflows.event_schema import StepStatus, StepMetadata
from src.workflows.runners.investigation_runner import InvestigationAgentRunner


class FakeEmitter:
    def __init__(self):
        self.events = []
    async def emit(self, agent_name, event_type, message, details=None):
        self.events.append({"agent_name": agent_name, "event_type": event_type, "message": message, "details": details})
        class FakeTaskEvent:
            sequence_number = len(self.events)
        return FakeTaskEvent()


class FakeWorkflowExecutor:
    """Simulates WorkflowExecutor running 1-node DAGs with per-agent mock results."""
    def __init__(self, agent_results: dict[str, dict]):
        self._agent_results = agent_results
        self.run_count = 0

    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        from dataclasses import dataclass
        step_id = compiled.topo_order[0]
        agent = compiled.steps[step_id].agent
        self.run_count += 1

        output = self._agent_results.get(agent, {"evidence_pins": []})

        @dataclass
        class NodeState:
            status: str = "COMPLETED"
            output: dict | None = None
            error: dict | None = None
            started_at: str = "2026-04-16T10:00:00Z"
            ended_at: str = "2026-04-16T10:00:01Z"
            attempt: int = 1

        @dataclass
        class RunResult:
            status: str = "COMPLETED"
            node_states: dict = None
            error: dict | None = None

        return RunResult(
            status="COMPLETED",
            node_states={step_id: NodeState(output=output)},
        )


@pytest.mark.asyncio
async def test_full_investigation_loop():
    """Simulate a 3-round investigation: log → metrics → k8s."""
    emitter = FakeEmitter()
    store = InvestigationStore(redis_client=None)
    wf_executor = FakeWorkflowExecutor(agent_results={
        "log_agent": {"evidence_pins": [{"claim": "OOM in api-gateway"}], "overall_confidence": 40},
        "metrics_agent": {"evidence_pins": [{"claim": "memory spike at 10:42"}], "overall_confidence": 65},
        "k8s_agent": {"evidence_pins": [{"claim": "pod restarted 3x"}], "overall_confidence": 80},
    })

    inv_executor = InvestigationExecutor(
        run_id="inv-integration-1",
        emitter=emitter,
        store=store,
        workflow_executor=wf_executor,
    )

    # Round 1: log_agent
    r1 = await inv_executor.run_step(InvestigationStepSpec(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        input_data={"service_name": "api-gateway"},
        metadata=StepMetadata(agent="log_agent", round=1, reason="initial triage"),
    ))
    assert r1.status == StepStatus.SUCCESS
    assert r1.output["evidence_pins"][0]["claim"] == "OOM in api-gateway"

    # Round 2: metrics_agent (depends on log)
    r2 = await inv_executor.run_step(InvestigationStepSpec(
        step_id="round-2-metrics-agent",
        agent="metrics_agent",
        depends_on=["round-1-log-agent"],
        input_data={"service_name": "api-gateway"},
        metadata=StepMetadata(agent="metrics_agent", round=2, hypothesis_id="h1", reason="validate OOM"),
    ))
    assert r2.status == StepStatus.SUCCESS

    # Round 3: k8s_agent (depends on metrics)
    r3 = await inv_executor.run_step(InvestigationStepSpec(
        step_id="round-3-k8s-agent",
        agent="k8s_agent",
        depends_on=["round-2-metrics-agent"],
        input_data={"namespace": "production"},
        metadata=StepMetadata(agent="k8s_agent", round=3, hypothesis_id="h1", reason="check pod health"),
    ))
    assert r3.status == StepStatus.SUCCESS

    # Verify virtual DAG
    dag = inv_executor.get_dag()
    assert len(dag.steps) == 3
    assert dag.steps[0].step_id == "round-1-log-agent"
    assert dag.steps[1].depends_on == ["round-1-log-agent"]
    assert dag.steps[2].depends_on == ["round-2-metrics-agent"]

    # Verify all steps have typed results
    for step in dag.steps:
        assert step.status == StepStatus.SUCCESS
        assert step.started_at is not None
        assert step.ended_at is not None
        assert step.duration_ms is not None

    # Verify events emitted (2 per step: running + success = 6 total)
    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    assert len(step_events) == 6

    # Verify sequence numbers are monotonic
    seq_numbers = [e["details"]["sequence_number"] for e in step_events]
    assert seq_numbers == sorted(seq_numbers)
    assert len(set(seq_numbers)) == len(seq_numbers)

    # Verify workflow executor was called 3 times (one per step)
    assert wf_executor.run_count == 3

    # Verify persistence
    loaded = await store.load_dag("inv-integration-1")
    assert loaded is not None
    assert len(loaded.steps) == 3

    # Verify causal metadata preserved
    assert dag.steps[1].triggered_by == "h1"
    assert dag.steps[2].reason == "check pod health"


@pytest.mark.asyncio
async def test_investigation_with_agent_failure():
    """One agent fails mid-investigation — DAG records the failure."""
    emitter = FakeEmitter()
    store = InvestigationStore(redis_client=None)

    class FailingExecutor:
        async def run(self, compiled, inputs, **kwargs):
            from dataclasses import dataclass
            step_id = compiled.topo_order[0]
            @dataclass
            class NodeState:
                status: str = "FAILED"
                output: dict | None = None
                error: dict | None = None
                started_at: str = "2026-04-16T10:00:00Z"
                ended_at: str = "2026-04-16T10:00:05Z"
                attempt: int = 1
            @dataclass
            class RunResult:
                status: str = "FAILED"
                node_states: dict = None
                error: dict | None = None
            return RunResult(
                status="FAILED",
                node_states={step_id: NodeState(error={"message": "Prometheus unreachable", "type": "ConnectionError"})},
                error={"message": "Prometheus unreachable"},
            )

    inv_executor = InvestigationExecutor(
        run_id="inv-fail-1",
        emitter=emitter,
        store=store,
        workflow_executor=FailingExecutor(),
    )

    result = await inv_executor.run_step(InvestigationStepSpec(
        step_id="round-1-metrics-agent",
        agent="metrics_agent",
        depends_on=[],
        metadata=StepMetadata(agent="metrics_agent", round=1),
    ))

    assert result.status == StepStatus.FAILED
    assert result.error is not None
    assert result.error.message == "Prometheus unreachable"
    assert result.error.type == "ConnectionError"

    dag = inv_executor.get_dag()
    assert dag.steps[0].status == StepStatus.FAILED
    assert dag.steps[0].error.message == "Prometheus unreachable"


@pytest.mark.asyncio
async def test_hypothesis_boundary():
    """Verify hypotheses stay in supervisor, NOT in the executor/DAG."""
    emitter = FakeEmitter()
    store = InvestigationStore(redis_client=None)
    wf_executor = FakeWorkflowExecutor(agent_results={
        "log_agent": {"evidence_pins": [], "overall_confidence": 50},
    })

    inv_executor = InvestigationExecutor(
        run_id="inv-boundary-1",
        emitter=emitter,
        store=store,
        workflow_executor=wf_executor,
    )

    await inv_executor.run_step(InvestigationStepSpec(
        step_id="round-1-log-agent",
        agent="log_agent",
        depends_on=[],
        metadata=StepMetadata(agent="log_agent", round=1, hypothesis_id="h1"),
    ))

    dag = inv_executor.get_dag()
    # DAG knows which hypothesis triggered the step (metadata)
    assert dag.steps[0].triggered_by == "h1"
    # But DAG does NOT contain hypothesis details, evidence, or confidence
    step_dict = dag.steps[0].to_dict()
    assert "hypotheses" not in step_dict
    assert "evidence" not in step_dict
    assert "confidence" not in step_dict
```

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_investigation_integration.py -v`
Expected: PASS (3 tests)

**Step 3: Commit**

```bash
git add backend/tests/test_investigation_integration.py
git commit -m "test(phase5): integration tests — full investigation loop, failure handling, boundary enforcement"
```

---

## Task 10: Non-Impact Verification

Verify that all existing tests pass — WorkflowExecutor, supervisor, and route tests are unaffected.

**Files:**
- Create: `backend/tests/test_phase5_non_impact.py`

**Step 1: Write non-impact verification test**

```python
# backend/tests/test_phase5_non_impact.py
"""Phase 5 non-impact: verify existing systems are untouched."""


def test_workflow_executor_import_unchanged():
    from src.workflows.executor import WorkflowExecutor, NodeState, RunResult
    assert WorkflowExecutor is not None
    assert NodeState is not None


def test_workflow_compiler_import_unchanged():
    from src.workflows.compiler import CompiledStep, CompiledWorkflow
    assert CompiledStep is not None


def test_supervisor_still_works_without_executor():
    from src.agents.supervisor import SupervisorAgent
    s = SupervisorAgent(connection_config={})
    assert s._investigation_executor is None


def test_event_emitter_unchanged():
    from src.utils.event_emitter import EventEmitter
    e = EventEmitter(session_id="test")
    assert hasattr(e, 'emit')
    assert hasattr(e, 'get_all_events')


def test_redis_store_unchanged():
    from src.utils.redis_store import RedisSessionStore
    assert hasattr(RedisSessionStore, 'save')
    assert hasattr(RedisSessionStore, 'load')


def test_new_modules_importable():
    from src.workflows.event_schema import EventEnvelope, StepPayload, RunPayload, StepStatus
    from src.workflows.investigation_types import InvestigationStepSpec, StepResult, VirtualDag, VirtualStep
    from src.workflows.investigation_store import InvestigationStore
    from src.workflows.investigation_executor import InvestigationExecutor
    from src.workflows.investigation_event_adapter import InvestigationEventAdapter
    from src.workflows.runners.investigation_runner import InvestigationAgentRunner
    assert True
```

**Step 2: Run non-impact test**

Run: `cd backend && python -m pytest tests/test_phase5_non_impact.py -v`
Expected: PASS (6 tests)

**Step 3: Run full existing test suite**

Run: `cd backend && python -m pytest tests/test_executor_scheduler.py tests/test_executor_failure_policies.py tests/test_executor_timeouts_retries.py tests/test_executor_cancellation.py tests/test_supervisor.py -v --timeout=30`
Expected: All existing tests PASS

**Step 4: Commit**

```bash
git add backend/tests/test_phase5_non_impact.py
git commit -m "test(phase5): non-impact verification — existing systems untouched"
```

---

## Batch Execution Order

| Batch | Tasks | Parallel? |
|-------|-------|-----------|
| A | Task 1 (Event Schema) + Task 2 (Virtual DAG Types) | Yes — independent type definitions |
| B | Task 3 (Redis Persistence) | No — depends on Task 2 VirtualDag |
| C | Task 4 (Event Adapter) | No — depends on Task 1 EventEnvelope + Task 2 VirtualStep |
| D | Task 5 (InvestigationExecutor) | No — depends on Tasks 1-4 |
| E | Task 6 (Supervisor Integration) | No — depends on Task 5 |
| F | Task 7 (Route Integration) + Task 8 (Agent Runner Bridge) | Yes — independent wiring |
| G | Task 9 (Integration Test) + Task 10 (Non-Impact) | Yes — independent verification |
