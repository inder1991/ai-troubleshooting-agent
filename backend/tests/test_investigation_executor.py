# backend/tests/test_investigation_executor.py
import pytest
import asyncio
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

    assert isinstance(result, StepResult)
    assert result.status == StepStatus.SUCCESS
    assert result.output["findings"][0]["msg"] == "OOM"
    assert result.error is None
    assert result.duration_ms >= 0

    dag = executor.get_dag()
    assert len(dag.steps) == 1
    assert dag.steps[0].step_id == "round-1-log-agent"
    assert dag.steps[0].status == StepStatus.SUCCESS

    step_events = [e for e in emitter.events if e["event_type"] == "step_update"]
    assert len(step_events) == 2
    assert step_events[0]["details"]["payload"]["status"] == "running"
    assert step_events[1]["details"]["payload"]["status"] == "success"

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
    assert len(set(seq_numbers)) == len(seq_numbers)


@pytest.mark.asyncio
async def test_get_dag_returns_current_state(executor):
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
