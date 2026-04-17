# backend/tests/test_investigation_executor.py
import pytest
from dataclasses import dataclass
from typing import Any

from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec, StepResult, VirtualDag
from src.workflows.event_schema import StepStatus, StepMetadata, normalize_status

from backend.tests.workflows._fakes import FakeOutboxWriter


def _step_events(writer: FakeOutboxWriter) -> list[dict[str, Any]]:
    return [e for e in writer.events if e["kind"] == "step_update"]


def _run_events(writer: FakeOutboxWriter) -> list[dict[str, Any]]:
    return [e for e in writer.events if e["kind"] == "run_update"]


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
def writer():
    return FakeOutboxWriter()


@pytest.fixture
def executor(writer):
    return InvestigationExecutor(
        run_id="inv-123",
        writer=writer,
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
async def test_run_step_emits_running_then_final_status(executor, writer):
    """run_step should emit at least two outbox events: running and success/failed."""
    spec = _make_spec()
    await executor.run_step(spec)

    step_events = _step_events(writer)
    assert len(step_events) >= 2
    statuses = [e["payload"]["payload"]["status"] for e in step_events]
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
async def test_run_step_failure_marks_step_failed(writer):
    """If WorkflowExecutor raises, step should be marked failed."""
    executor = InvestigationExecutor(
        run_id="inv-fail-raise",
        writer=writer,
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
async def test_run_step_failure_via_agent_error(writer):
    """If the agent returns a FAILED status (not an exception), step should be marked failed."""
    executor = InvestigationExecutor(
        run_id="inv-fail-agent",
        writer=writer,
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
async def test_run_steps_sequential(executor, writer):
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
# Persistence (via OutboxWriter)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dag_persisted_via_writer(executor, writer):
    """After run_step, DAG snapshot should have been written through the writer."""
    spec = _make_spec()
    await executor.run_step(spec)

    # Two transitions per step ⇒ two update_dag calls; the last reflects SUCCESS.
    assert len(writer.dag_updates) == 2
    final_payload = writer.dag_updates[-1]["payload"]
    assert final_payload["run_id"] == "inv-123"
    assert len(final_payload["steps"]) == 1
    assert final_payload["steps"][0]["status"] == "success"


# ---------------------------------------------------------------------------
# Sequence numbers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sequence_numbers_monotonic(executor, writer):
    """Each event should have an incrementing sequence number."""
    specs = [
        _make_spec(step_id="round-1-log_agent", agent="log_agent"),
        _make_spec(step_id="round-2-metrics_agent", agent="metrics_agent"),
    ]
    await executor.run_steps(specs)

    step_events = _step_events(writer)
    seq_numbers = [e["seq"] for e in step_events]
    assert seq_numbers == sorted(seq_numbers)
    assert len(set(seq_numbers)) == len(seq_numbers)
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
    assert step.step_id == "round-3-code_navigator"
    parts = step.step_id.split("-", 2)
    assert parts[0] == "round"
    assert parts[1].isdigit()
    assert len(parts[2]) > 0


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_marks_running_step_cancelled(executor, writer):
    """cancel() should mark the investigation DAG as cancelled and emit a run_update."""
    spec = _make_spec()
    await executor.run_step(spec)

    await executor.cancel()
    dag = executor.get_dag()
    assert dag.status == "cancelled"

    run_events = _run_events(writer)
    assert len(run_events) == 1
    assert run_events[0]["payload"]["payload"]["status"] == "cancelled"

    final_dag_payload = writer.dag_updates[-1]["payload"]
    assert final_dag_payload["status"] == "cancelled"


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
    vstep.started_at = None
    vstep.ended_at = None
    with pytest.raises(AssertionError, match="invariant violated"):
        executor._step_result_from(vstep)


@pytest.mark.asyncio
async def test_duplicate_step_id_does_not_create_duplicate_dag_entry(writer):
    """Running a step with the same step_id + idempotency_key twice produces one DAG entry."""
    executor = InvestigationExecutor(
        run_id="inv-dedup",
        writer=writer,
        workflow_executor=FakeWorkflowExecutor(result_output={"v": "first"}),
    )
    spec = _make_spec(step_id="round-1-log_agent")
    await executor.run_step(spec)
    await executor.run_step(spec)

    dag = executor.get_dag()
    step_ids = [s.step_id for s in dag.steps]
    assert step_ids.count("round-1-log_agent") == 1
