"""Schema-version invariant: every persisted dataclass tags itself and rejects
unknown versions on read."""
import pytest

from src.workflows.event_schema import (
    ErrorDetail,
    StepStatus,
    make_run_event,
    make_step_event,
)
from src.workflows.investigation_types import (
    InvestigationStepSpec,
    StepResult,
    VirtualDag,
    VirtualStep,
)


# ── VirtualDag ──────────────────────────────────────────────────────

def test_virtual_dag_serializes_schema_version():
    dag = VirtualDag(run_id="r1")
    assert dag.to_dict()["schema_version"] == 1


def test_virtual_dag_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        VirtualDag.from_dict({"run_id": "r1", "schema_version": 999, "steps": []})


def test_virtual_dag_accepts_unversioned_dict_as_v1():
    # Back-compat grace window: missing schema_version is treated as v1.
    dag = VirtualDag.from_dict({"run_id": "r1", "steps": []})
    assert dag.run_id == "r1"


# ── VirtualStep ─────────────────────────────────────────────────────

def test_virtual_step_serializes_schema_version():
    step = VirtualStep(
        step_id="s1",
        agent="log_agent",
        depends_on=[],
        status=StepStatus.PENDING,
        round=1,
    )
    assert step.to_dict()["schema_version"] == 1


def test_virtual_step_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        VirtualStep.from_dict({
            "step_id": "s1",
            "agent": "log_agent",
            "depends_on": [],
            "status": "pending",
            "round": 1,
            "schema_version": 999,
        })


# ── StepResult ──────────────────────────────────────────────────────

def test_step_result_serializes_schema_version():
    result = StepResult(
        step_id="s1",
        status=StepStatus.SUCCESS,
        output={"findings": []},
        error=None,
        started_at="2026-04-17T00:00:00Z",
        ended_at="2026-04-17T00:00:01Z",
        duration_ms=1000,
    )
    assert result.to_dict()["schema_version"] == 1


def test_step_result_roundtrip():
    result = StepResult(
        step_id="s1",
        status=StepStatus.FAILED,
        output=None,
        error=ErrorDetail(message="boom", type="RuntimeError"),
        started_at="2026-04-17T00:00:00Z",
        ended_at="2026-04-17T00:00:01Z",
        duration_ms=1000,
    )
    restored = StepResult.from_dict(result.to_dict())
    assert restored.step_id == "s1"
    assert restored.status == StepStatus.FAILED
    assert restored.error.message == "boom"


def test_step_result_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        StepResult.from_dict({
            "step_id": "s1",
            "status": "success",
            "output": None,
            "error": None,
            "started_at": "x",
            "ended_at": "y",
            "duration_ms": 0,
            "schema_version": 999,
        })


# ── InvestigationStepSpec ───────────────────────────────────────────

def test_investigation_step_spec_serializes_schema_version():
    spec = InvestigationStepSpec(step_id="s1", agent="log_agent")
    assert spec.to_dict()["schema_version"] == 1


def test_investigation_step_spec_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        InvestigationStepSpec.from_dict({
            "step_id": "s1",
            "agent": "log_agent",
            "schema_version": 999,
        })


# ── EventEnvelope (persisted as the wire payload) ───────────────────

def test_event_envelope_step_serializes_schema_version():
    env = make_step_event(
        run_id="r1",
        step_id="s1",
        parent_step_ids=[],
        status=StepStatus.RUNNING,
        sequence_number=1,
    )
    assert env.to_dict()["schema_version"] == 1


def test_event_envelope_run_serializes_schema_version():
    env = make_run_event(run_id="r1", status="running", sequence_number=1)
    assert env.to_dict()["schema_version"] == 1
