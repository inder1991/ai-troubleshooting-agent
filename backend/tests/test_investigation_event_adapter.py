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
