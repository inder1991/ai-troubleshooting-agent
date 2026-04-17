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
        idempotency_key="key-round-1-log-agent",
        depends_on=[],
        input_data={"service_name": "api-gateway"},
        metadata=StepMetadata(agent="log_agent", round=1, reason="initial triage"),
    )
    assert spec.step_id == "round-1-log-agent"
    assert spec.input_data["service_name"] == "api-gateway"
    assert spec.idempotency_key == "key-round-1-log-agent"
