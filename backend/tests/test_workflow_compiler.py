from __future__ import annotations

import pytest

from src.contracts.models import AgentContract
from src.contracts.registry import ContractRegistry
from src.workflows.compiler import CompileError, compile_dag
from src.workflows.models import WorkflowDag


def _contract(
    name: str,
    version: int = 1,
    *,
    deprecated_versions: list[int] | None = None,
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    timeout_seconds: float = 30.0,
    retry_on: list[str] | None = None,
) -> AgentContract:
    return AgentContract.model_validate(
        {
            "name": name,
            "version": version,
            "deprecated_versions": deprecated_versions or [],
            "description": "test",
            "category": "test",
            "tags": [],
            "inputs": input_schema or {"type": "object", "properties": {}},
            "outputs": output_schema
            or {
                "type": "object",
                "properties": {"svc": {"type": "string"}},
            },
            "trigger_examples": ["a", "b"],
            "retry_on": retry_on or ["timeout", "transient"],
            "timeout_seconds": timeout_seconds,
        }
    )


def _registry(*contracts: AgentContract) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(c.name, c.version): c for c in contracts}
    return reg


def test_happy_path_linear_three_step():
    reg = _registry(
        _contract(
            "a",
            output_schema={"type": "object", "properties": {"svc": {"type": "string"}}},
        ),
        _contract(
            "b",
            output_schema={"type": "object", "properties": {"x": {"type": "string"}}},
        ),
        _contract("c"),
    )
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"svc": {"type": "string"}}},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.svc"}}},
                },
                {
                    "id": "c",
                    "agent": "c",
                    "agent_version": 1,
                    "inputs": {"y": {"ref": {"from": "node", "node_id": "b", "path": "output.x"}}},
                },
            ],
        }
    )
    cw = compile_dag(dag, reg)
    assert cw.topo_order == ["a", "b", "c"]


def test_cycle_rejected():
    reg = _registry(
        _contract("a", output_schema={"type": "object", "properties": {"x": {"type": "string"}}}),
        _contract("b", output_schema={"type": "object", "properties": {"x": {"type": "string"}}}),
    )
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "b", "path": "output.x"}}},
                },
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.x"}}},
                },
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "cycle" in str(exc.value)


def test_unknown_agent_rejected():
    reg = _registry(_contract("a"))
    dag = WorkflowDag.model_validate(
        {"steps": [{"id": "missing_step", "agent": "nonexistent"}]}
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "missing_step" in exc.value.path


def test_timeout_override_cannot_exceed_contract():
    reg = _registry(_contract("a", timeout_seconds=10.0))
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1, "timeout_seconds_override": 20.0}
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "timeout_seconds_override" in exc.value.path


def test_retry_on_override_must_be_subset():
    reg = _registry(_contract("a", retry_on=["timeout"]))
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "retry_on_override": ["timeout", "rate_limit"],
                }
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "retry_on_override" in exc.value.path


def test_ref_to_unknown_node_rejected():
    reg = _registry(_contract("a"))
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "ghost", "path": "output.x"}}},
                }
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "ghost" in str(exc.value)


def test_ref_path_missing_in_upstream_schema_rejected():
    reg = _registry(
        _contract(
            "a",
            output_schema={"type": "object", "properties": {"svc": {"type": "string"}}},
        ),
        _contract("b"),
    )
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.not_a_field"}}},
                },
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "not_a_field" in str(exc.value)


def test_latest_resolves_highest_non_deprecated():
    reg = _registry(
        _contract("a", version=1),
        _contract("a", version=2, deprecated_versions=[2]),
        _contract("a", version=3),
    )
    # active versions: 1, 3 — latest picks 3
    dag = WorkflowDag.model_validate(
        {"steps": [{"id": "a", "agent": "a", "agent_version": "latest"}]}
    )
    cw = compile_dag(dag, reg)
    assert cw.steps["a"].agent_version == 3


def test_latest_with_only_deprecated_rejected():
    reg = _registry(
        _contract("a", version=1, deprecated_versions=[1]),
    )
    dag = WorkflowDag.model_validate(
        {"steps": [{"id": "a", "agent": "a", "agent_version": "latest"}]}
    )
    with pytest.raises(CompileError):
        compile_dag(dag, reg)


def test_fallback_dep_subset_rule():
    # primary depends on a; fallback depends on a AND b — violates subset
    reg = _registry(
        _contract("a", output_schema={"type": "object", "properties": {"x": {"type": "string"}}}),
        _contract("b", output_schema={"type": "object", "properties": {"x": {"type": "string"}}}),
        _contract("fb"),
        _contract("primary"),
    )
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {"id": "b", "agent": "b", "agent_version": 1},
                {
                    "id": "fb",
                    "agent": "fb",
                    "agent_version": 1,
                    "inputs": {
                        "x": {"ref": {"from": "node", "node_id": "a", "path": "output.x"}},
                        "y": {"ref": {"from": "node", "node_id": "b", "path": "output.x"}},
                    },
                },
                {
                    "id": "primary",
                    "agent": "primary",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.x"}}},
                    "on_failure": "fallback",
                    "fallback_step_id": "fb",
                },
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "fallback_step_id" in exc.value.path


def test_fallback_target_must_exist():
    reg = _registry(_contract("a"))
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "on_failure": "fallback",
                    "fallback_step_id": "ghost",
                }
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "fallback_step_id" in exc.value.path


def test_max_total_steps_enforced(monkeypatch):
    monkeypatch.setenv("MAX_TOTAL_STEPS_PER_RUN", "2")
    reg = _registry(_contract("a"), _contract("b"), _contract("c"))
    dag = WorkflowDag.model_validate(
        {
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {"id": "b", "agent": "b", "agent_version": 1},
                {"id": "c", "agent": "c", "agent_version": 1},
            ]
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "MAX_TOTAL_STEPS_PER_RUN" in str(exc.value)


def test_ref_input_validated_against_inputs_schema():
    reg = _registry(_contract("a"))
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"svc": {"type": "string"}}},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "input", "path": "nonexistent"}}},
                }
            ],
        }
    )
    with pytest.raises(CompileError) as exc:
        compile_dag(dag, reg)
    assert "nonexistent" in str(exc.value)
