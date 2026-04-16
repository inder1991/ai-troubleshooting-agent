import pytest
from dataclasses import dataclass

from src.agents.supervisor import SupervisorAgent
from src.workflows.investigation_executor import InvestigationExecutor
from src.workflows.investigation_types import InvestigationStepSpec
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
    """When investigation_executor is provided, _dispatch_via_executor routes through it."""
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

    result = await supervisor._dispatch_via_executor(
        "log_agent", inv_executor, round_num=1, agent_input={"service_name": "api"},
    )
    assert result is not None

    dag = inv_executor.get_dag()
    assert len(dag.steps) == 1
    assert dag.steps[0].agent == "log_agent"


@pytest.mark.asyncio
async def test_supervisor_falls_back_without_executor():
    """When no investigation_executor, supervisor has None (existing behavior preserved)."""
    supervisor = SupervisorAgent(connection_config={})
    assert supervisor._investigation_executor is None
