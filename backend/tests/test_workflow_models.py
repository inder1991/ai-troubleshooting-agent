from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.workflows.models import (
    RefNode,
    RefInput,
    RefEnv,
    Transform,
    StepSpec,
    WorkflowDag,
    FROZEN_OPS,
)


def test_ref_input_valid():
    r = RefInput.model_validate({"from": "input", "path": "service"})
    assert r.path == "service"
    assert r.from_ == "input"


def test_ref_node_valid_and_requires_node_id():
    r = RefNode.model_validate({"from": "node", "node_id": "a", "path": "output.x"})
    assert r.node_id == "a"
    with pytest.raises(ValidationError):
        RefNode.model_validate({"from": "node", "path": "output.x"})


def test_ref_input_rejects_unknown_from():
    with pytest.raises(ValidationError):
        RefInput.model_validate({"from": "bogus", "path": "x"})


def test_ref_env_valid():
    r = RefEnv.model_validate({"from": "env", "path": "FOO"})
    assert r.path == "FOO"


def test_transform_accepts_all_frozen_ops():
    for op in FROZEN_OPS:
        t = Transform.model_validate({"op": op, "args": []})
        assert t.op == op


def test_transform_rejects_unknown_op():
    with pytest.raises(ValidationError):
        Transform.model_validate({"op": "custom_op", "args": []})


def test_step_spec_defaults_and_id_regex():
    s = StepSpec.model_validate({"id": "step_a", "agent": "log_agent"})
    assert s.on_failure == "fail"
    assert s.agent_version == "latest"
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"id": "Bad-Id", "agent": "x"})
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"id": "1_bad", "agent": "x"})


def test_step_spec_rejects_unknown_on_failure():
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"id": "a", "agent": "x", "on_failure": "retry_forever"})


def test_step_spec_fallback_requires_fallback_step_id():
    with pytest.raises(ValidationError):
        StepSpec.model_validate({"id": "a", "agent": "x", "on_failure": "fallback"})
    s = StepSpec.model_validate(
        {"id": "a", "agent": "x", "on_failure": "fallback", "fallback_step_id": "b"}
    )
    assert s.fallback_step_id == "b"


def test_workflow_dag_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        WorkflowDag.model_validate(
            {
                "steps": [
                    {"id": "a", "agent": "x"},
                    {"id": "a", "agent": "y"},
                ]
            }
        )


def test_workflow_dag_ok_with_unique_ids():
    d = WorkflowDag.model_validate(
        {
            "steps": [
                {"id": "a", "agent": "x"},
                {"id": "b", "agent": "y"},
            ]
        }
    )
    assert [s.id for s in d.steps] == ["a", "b"]
