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
    d = result.to_dict()
    assert d["schema_version"] == 1
    # None ``error`` is pruned for symmetry with VirtualStep.to_dict.
    assert "error" not in d


def test_step_result_to_dict_includes_error_when_present():
    result = StepResult(
        step_id="s1",
        status=StepStatus.FAILED,
        output=None,
        error=ErrorDetail(message="boom", type="RuntimeError"),
        started_at="2026-04-17T00:00:00Z",
        ended_at="2026-04-17T00:00:01Z",
        duration_ms=1000,
    )
    d = result.to_dict()
    assert d["error"] == {"message": "boom", "type": "RuntimeError"}


def test_step_result_from_dict_handles_missing_error_key():
    restored = StepResult.from_dict({
        "schema_version": 1,
        "step_id": "s1",
        "status": "success",
        "output": None,
        "started_at": "x",
        "ended_at": "y",
        "duration_ms": 0,
    })
    assert restored.error is None


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


# ── DriftError ──────────────────────────────────────────────────────

def test_drift_error_serializes_schema_version():
    from src.workflows.drift import DriftError
    e = DriftError(step_id="s1", reason="contract_missing", detail="x v1 not in registry")
    assert e.to_dict()["schema_version"] == 1


def test_drift_error_rejects_unknown_schema_version():
    from src.workflows.drift import DriftError
    with pytest.raises(ValueError, match="schema_version"):
        DriftError.from_dict({
            "step_id": "s1",
            "reason": "contract_missing",
            "detail": "x v1 not in registry",
            "schema_version": 999,
        })


def test_drift_error_accepts_unversioned_dict_as_v1():
    from src.workflows.drift import DriftError
    e = DriftError.from_dict({
        "step_id": "s1",
        "reason": "contract_missing",
        "detail": "x v1 not in registry",
    })
    assert e.step_id == "s1"
    assert e.reason == "contract_missing"


# ── CompiledStep ────────────────────────────────────────────────────

def _sample_compiled_step():
    from src.workflows.compiler import CompiledStep
    return CompiledStep(
        id="s1",
        agent="log_agent",
        agent_version=1,
        inputs={"foo": "bar"},
        when=None,
        on_failure="fail",
        fallback_step_id=None,
        parallel_group=None,
        concurrency_group=None,
        timeout_seconds=30.0,
        retry_on=["TimeoutError"],
        upstream_ids=[],
    )


def test_compiled_step_serializes_schema_version():
    assert _sample_compiled_step().to_dict()["schema_version"] == 1


def test_compiled_step_rejects_unknown_schema_version():
    from src.workflows.compiler import CompiledStep
    bad = _sample_compiled_step().to_dict()
    bad["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        CompiledStep.from_dict(bad)


def test_compiled_step_accepts_unversioned_dict_as_v1():
    from src.workflows.compiler import CompiledStep
    raw = _sample_compiled_step().to_dict()
    raw.pop("schema_version")
    cs = CompiledStep.from_dict(raw)
    assert cs.id == "s1"
    assert cs.agent == "log_agent"


# ── CompiledWorkflow ────────────────────────────────────────────────

def _sample_compiled_workflow():
    from src.workflows.compiler import CompiledWorkflow
    return CompiledWorkflow(
        topo_order=["s1"],
        steps={"s1": _sample_compiled_step()},
        inputs_schema={"type": "object"},
    )


def test_compiled_workflow_serializes_schema_version():
    cw = _sample_compiled_workflow()
    d = cw.to_dict()
    assert d["schema_version"] == 1
    assert d["steps"]["s1"]["schema_version"] == 1


def test_compiled_workflow_rejects_unknown_schema_version():
    from src.workflows.compiler import CompiledWorkflow
    bad = _sample_compiled_workflow().to_dict()
    bad["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        CompiledWorkflow.from_dict(bad)


def test_compiled_workflow_accepts_unversioned_dict_as_v1():
    from src.workflows.compiler import CompiledWorkflow
    raw = _sample_compiled_workflow().to_dict()
    raw.pop("schema_version")
    cw = CompiledWorkflow.from_dict(raw)
    assert cw.topo_order == ["s1"]
    assert "s1" in cw.steps


def test_compiled_workflow_roundtrip():
    from src.workflows.compiler import CompiledWorkflow
    cw = _sample_compiled_workflow()
    restored = CompiledWorkflow.from_dict(cw.to_dict())
    assert restored.topo_order == cw.topo_order
    assert restored.inputs_schema == cw.inputs_schema
    assert restored.steps.keys() == cw.steps.keys()
    s_orig = cw.steps["s1"]
    s_new = restored.steps["s1"]
    assert s_new == s_orig


# ── EventEnvelope.from_dict stub ────────────────────────────────────

def test_event_envelope_from_dict_rejects_unknown_schema_version():
    from src.workflows.event_schema import EventEnvelope
    with pytest.raises(ValueError, match="schema_version"):
        EventEnvelope.from_dict({
            "schema_version": 999,
            "event_type": "step_update",
            "run_id": "r1",
            "sequence_number": 1,
            "timestamp": "x",
            "payload": {},
        })


def test_event_envelope_from_dict_raises_not_implemented_when_version_ok():
    from src.workflows.event_schema import EventEnvelope
    with pytest.raises(NotImplementedError, match="wire-only"):
        EventEnvelope.from_dict({
            "schema_version": 1,
            "event_type": "step_update",
            "run_id": "r1",
            "sequence_number": 1,
            "timestamp": "x",
            "payload": {},
        })
