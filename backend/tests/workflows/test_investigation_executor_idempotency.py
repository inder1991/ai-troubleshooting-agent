"""Idempotency: same step_id + same idempotency_key returns cached result;
mismatched key for an existing step_id is a logic bug and raises."""
from dataclasses import dataclass
from typing import Any

import pytest

from src.workflows.event_schema import StepStatus
from src.workflows.investigation_executor import (
    InvestigationExecutor,
    StepAlreadyRunning,
    StepIdempotencyKeyMismatch,
)
from src.workflows.investigation_store import InvestigationStore
from src.workflows.investigation_types import InvestigationStepSpec, StepResult


class _FakeEmitter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, agent_name, event_type, message, details=None):
        self.events.append({"agent_name": agent_name, "event_type": event_type, "message": message, "details": details})


class _FakeWorkflowExecutor:
    def __init__(self, output: dict | None = None) -> None:
        self._output = output or {"findings": [{"msg": "ok"}]}
        self.run_count = 0

    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        self.run_count += 1
        step_id = compiled.topo_order[0]

        @dataclass
        class NodeState:
            status: str
            output: dict | None = None
            error: dict | None = None
            started_at: str | None = "2026-04-17T00:00:00Z"
            ended_at: str | None = "2026-04-17T00:00:01Z"
            attempt: int = 1

        @dataclass
        class RunResult:
            status: str
            node_states: dict
            error: dict | None = None

        return RunResult(
            status="COMPLETED",
            node_states={step_id: NodeState(status="COMPLETED", output=self._output)},
        )


@pytest.fixture
def emitter():
    return _FakeEmitter()


@pytest.fixture
def store():
    return InvestigationStore(redis_client=None)


@pytest.fixture
def workflow_executor():
    return _FakeWorkflowExecutor()


@pytest.fixture
def executor(emitter, store, workflow_executor):
    return InvestigationExecutor(
        run_id="inv-idem",
        emitter=emitter,
        store=store,
        workflow_executor=workflow_executor,
    )


@pytest.fixture
def spec_factory():
    def _make(step_id: str, idempotency_key: str, agent: str = "log_agent") -> InvestigationStepSpec:
        return InvestigationStepSpec(
            step_id=step_id,
            agent=agent,
            idempotency_key=idempotency_key,
        )

    return _make


@pytest.mark.asyncio
async def test_duplicate_step_id_is_rejected_not_duplicated(executor, spec_factory, workflow_executor):
    spec = spec_factory(step_id="metrics_run_1", idempotency_key="abc123")
    result1 = await executor.run_step(spec)

    result2 = await executor.run_step(spec)

    dag = executor.get_dag()
    assert len([s for s in dag.steps if s.step_id == "metrics_run_1"]) == 1
    assert result2.status == dag.get_step("metrics_run_1").status
    assert result2.status == result1.status
    assert isinstance(result2, StepResult)
    # Workflow only ran once; second submission returned cached result.
    assert workflow_executor.run_count == 1


@pytest.mark.asyncio
async def test_mismatched_idempotency_key_for_same_step_id_raises(executor, spec_factory):
    await executor.run_step(spec_factory(step_id="metrics_run_1", idempotency_key="abc123"))

    with pytest.raises(StepIdempotencyKeyMismatch):
        await executor.run_step(spec_factory(step_id="metrics_run_1", idempotency_key="different"))


@pytest.mark.asyncio
async def test_running_step_resubmission_raises_step_already_running(emitter, store, spec_factory):
    """If a step is currently RUNNING and the same idempotency_key is resubmitted,
    raise StepAlreadyRunning instead of starting a duplicate execution."""

    class _PausingExecutor:
        def __init__(self) -> None:
            self.entered = False

        async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
            self.entered = True
            raise AssertionError("workflow_executor.run must not be called for a RUNNING duplicate")

    executor = InvestigationExecutor(
        run_id="inv-running",
        emitter=emitter,
        store=store,
        workflow_executor=_PausingExecutor(),
    )

    # Manually seed a RUNNING step into the DAG to model an in-flight dispatch.
    spec = spec_factory(step_id="metrics_run_1", idempotency_key="abc123")
    from src.workflows.investigation_types import VirtualStep

    executor.get_dag().append_step(
        VirtualStep(
            step_id=spec.step_id,
            agent=spec.agent,
            depends_on=[],
            status=StepStatus.RUNNING,
            round=0,
            idempotency_key=spec.idempotency_key,
        )
    )

    with pytest.raises(StepAlreadyRunning):
        await executor.run_step(spec)
