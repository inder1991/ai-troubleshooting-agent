# backend/tests/test_investigation_executor.py
import pytest
import asyncio
from dataclasses import dataclass
from typing import Any

from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec, StepResult, VirtualDag
from src.workflows.investigation_store import InvestigationStore
from src.workflows.event_schema import StepStatus, StepMetadata, normalize_status


class FakeEmitter:
    def __init__(self):
        self.events: list[dict[str, Any]] = []

    async def emit(self, agent_name, event_type, message, details=None):
        self.events.append({"agent_name": agent_name, "event_type": event_type, "message": message, "details": details})


class FakeWorkflowExecutor:
    """Mimics WorkflowExecutor.run() returning a RunResult for a 1-node DAG."""

    def __init__(self, result_output=None, should_fail=False, should_raise=False):
        self._result_output = result_output or {"findings": []}
        self._should_fail = should_fail
        self._should_raise = should_raise
        self.calls: list[dict] = []

    async def run(self, compiled, inputs, env=None, cancel_event=None, contracts=None):
        self.calls.append({"compiled": compiled, "inputs": inputs})
        step_id = compiled.topo_order[0]

        if self._should_raise:
            raise RuntimeError("executor exploded")

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


def _make_spec(step_id="round-1-log_agent", agent="log_agent", depends_on=None, input_data=None, metadata=None, idempotency_key=None):
    return InvestigationStepSpec(
        step_id=step_id,
        agent=agent,
        idempotency_key=idempotency_key or f"key-{step_id}",
        depends_on=depends_on or [],
        input_data=input_data,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Core run_step behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_step_appends_to_dag(executor):
    """run_step should add the step to the virtual DAG."""
    spec = _make_spec()
    await executor.run_step(spec)

    dag = executor.get_dag()
    assert len(dag.steps) == 1
    assert dag.steps[0].step_id == spec.step_id


@pytest.mark.asyncio
async def test_run_step_emits_running_then_final_status(executor, emitter):
    """run_step should emit at least two events: running and success/failed."""
    spec = _make_spec()
    await executor.run_step(spec)

    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    assert len(step_events) >= 2
    statuses = [e["details"]["payload"]["status"] for e in step_events]
    assert statuses[0] == "running"
    assert statuses[-1] in ("success", "failed")


@pytest.mark.asyncio
async def test_run_step_returns_typed_step_result(executor):
    """StepResult should have step_id, status, output, duration_ms etc."""
    spec = _make_spec(
        metadata=StepMetadata(agent="log_agent", round=1, reason="initial triage"),
    )
    result = await executor.run_step(spec)

    assert isinstance(result, StepResult)
    assert result.step_id == spec.step_id
    assert result.status == StepStatus.SUCCESS
    assert result.output is not None
    assert result.error is None
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0
    assert result.started_at is not None
    assert result.ended_at is not None


@pytest.mark.asyncio
async def test_run_step_failure_marks_step_failed(emitter, store):
    """If WorkflowExecutor raises, step should be marked failed."""
    executor = InvestigationExecutor(
        run_id="inv-fail-raise",
        emitter=emitter,
        store=store,
        workflow_executor=FakeWorkflowExecutor(should_raise=True),
    )
    spec = _make_spec()
    result = await executor.run_step(spec)

    assert result.status == StepStatus.FAILED
    assert result.error is not None
    assert "executor exploded" in result.error.message

    dag = executor.get_dag()
    assert dag.steps[0].status == StepStatus.FAILED


@pytest.mark.asyncio
async def test_run_step_failure_via_agent_error(emitter, store):
    """If the agent returns a FAILED status (not an exception), step should be marked failed."""
    executor = InvestigationExecutor(
        run_id="inv-fail-agent",
        emitter=emitter,
        store=store,
        workflow_executor=FakeWorkflowExecutor(should_fail=True),
    )
    spec = _make_spec()
    result = await executor.run_step(spec)

    assert result.status == StepStatus.FAILED
    assert result.error is not None
    assert result.error.message == "agent crashed"

    dag = executor.get_dag()
    assert dag.steps[0].status == StepStatus.FAILED


# ---------------------------------------------------------------------------
# Sequential execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_steps_sequential(executor, emitter):
    """run_steps should execute steps sequentially and return all results."""
    specs = [
        _make_spec(step_id="round-1-log_agent", agent="log_agent"),
        _make_spec(step_id="round-2-metrics_agent", agent="metrics_agent", depends_on=["round-1-log_agent"]),
    ]
    results = await executor.run_steps(specs)

    assert len(results) == 2
    assert results[0].status == StepStatus.SUCCESS
    assert results[1].status == StepStatus.SUCCESS

    dag = executor.get_dag()
    assert len(dag.steps) == 2
    assert dag.steps[1].depends_on == ["round-1-log_agent"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dag_persisted_to_store(executor, store):
    """After run_step, DAG should be saved to the store."""
    spec = _make_spec()
    await executor.run_step(spec)

    loaded = await store.load_dag("inv-123")
    assert loaded is not None
    assert len(loaded.steps) == 1
    assert loaded.steps[0].step_id == spec.step_id
    assert loaded.steps[0].status == StepStatus.SUCCESS


# ---------------------------------------------------------------------------
# Sequence numbers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequence_numbers_monotonic(executor, emitter):
    """Each event should have an incrementing sequence number."""
    specs = [
        _make_spec(step_id="round-1-log_agent", agent="log_agent"),
        _make_spec(step_id="round-2-metrics_agent", agent="metrics_agent"),
    ]
    await executor.run_steps(specs)

    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    seq_numbers = [e["details"]["sequence_number"] for e in step_events]
    # Strictly monotonically increasing
    assert seq_numbers == sorted(seq_numbers)
    assert len(set(seq_numbers)) == len(seq_numbers)
    # Should start at 1
    assert seq_numbers[0] == 1


# ---------------------------------------------------------------------------
# Step ID convention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_id_convention(executor):
    """Step IDs should follow round-{N}-{agent_name} convention."""
    spec = _make_spec(step_id="round-3-code_navigator")
    await executor.run_step(spec)

    dag = executor.get_dag()
    step = dag.steps[0]
    # Verify the step_id is stored as-is and follows the convention
    assert step.step_id == "round-3-code_navigator"
    parts = step.step_id.split("-", 2)
    assert parts[0] == "round"
    assert parts[1].isdigit()
    assert len(parts[2]) > 0


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_marks_running_step_cancelled(executor, emitter, store):
    """cancel() should mark the investigation DAG as cancelled."""
    # Run a step first so we have some state
    spec = _make_spec()
    await executor.run_step(spec)

    await executor.cancel()
    dag = executor.get_dag()
    assert dag.status == "cancelled"

    run_events = [e for e in emitter.events if e["event_type"] == "run_update"]
    assert len(run_events) == 1

    # Verify persisted
    loaded = await store.load_dag("inv-123")
    assert loaded is not None
    assert loaded.status == "cancelled"


# ---------------------------------------------------------------------------
# normalize_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_status_completed_maps_to_success():
    """COMPLETED from WorkflowExecutor should map to Status.SUCCESS."""
    assert normalize_status("COMPLETED") == StepStatus.SUCCESS
    assert normalize_status("completed") == StepStatus.SUCCESS
    assert normalize_status("SUCCEEDED") == StepStatus.SUCCESS
    assert normalize_status("SUCCESS") == StepStatus.SUCCESS
    # Also check the non-alias path
    assert normalize_status("running") == StepStatus.RUNNING
    assert normalize_status("pending") == StepStatus.PENDING
    assert normalize_status("FAILED") == StepStatus.FAILED


# ---------------------------------------------------------------------------
# Idempotency / duplicate step IDs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_result_from_asserts_completed_step_has_timestamps(executor):
    """_step_result_from is only valid for SUCCESS/FAILED steps; missing
    timestamps on a completed step indicates an invariant violation."""
    spec = _make_spec(step_id="round-1-log_agent")
    await executor.run_step(spec)

    dag = executor.get_dag()
    vstep = dag.steps[0]
    # Mutate to violate the invariant — completed step with no timestamps.
    vstep.started_at = None
    vstep.ended_at = None
    with pytest.raises(AssertionError, match="invariant violated"):
        executor._step_result_from(vstep)


@pytest.mark.asyncio
async def test_duplicate_step_id_does_not_create_duplicate_dag_entry(emitter, store):
    """Running a step with the same step_id + idempotency_key twice produces one DAG entry."""
    executor = InvestigationExecutor(
        run_id="inv-dedup",
        emitter=emitter,
        store=store,
        workflow_executor=FakeWorkflowExecutor(result_output={"v": "first"}),
    )
    spec = _make_spec(step_id="round-1-log_agent")
    await executor.run_step(spec)
    await executor.run_step(spec)

    dag = executor.get_dag()
    step_ids = [s.step_id for s in dag.steps]
    assert step_ids.count("round-1-log_agent") == 1
    loaded = await store.load_dag("inv-dedup")
    assert loaded is not None
