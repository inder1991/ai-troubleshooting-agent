from __future__ import annotations

from typing import Any

import pytest

from src.contracts.models import AgentContract
from src.contracts.registry import ContractRegistry
from src.workflows.compiler import compile_dag
from src.workflows.executor import WorkflowExecutor
from src.workflows.models import WorkflowDag
from src.workflows.runners.registry import AgentRunnerRegistry


def _contract(name: str) -> AgentContract:
    return AgentContract.model_validate(
        {
            "name": name,
            "version": 1,
            "deprecated_versions": [],
            "description": "t",
            "category": "t",
            "tags": [],
            "inputs": {"type": "object"},
            "outputs": {"type": "object", "properties": {"v": {"type": "string"}}},
            "trigger_examples": ["a", "b"],
            "retry_on": ["timeout"],
            "timeout_seconds": 30.0,
        }
    )


def _contracts(*names: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(n, 1): _contract(n) for n in names}
    return reg


class _Recording:
    def __init__(self, name: str, log: list[str], output: Any | None = None) -> None:
        self._name = name
        self._log = log
        self._output = output if output is not None else {"v": name}

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self._log.append(self._name)
        return self._output


def _runners(m: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, r in m.items():
        reg.register(name, 1, r)
    return reg


@pytest.mark.asyncio
async def test_when_true_executes():
    contracts = _contracts("a")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "when": {
                        "op": "eq",
                        "args": [
                            {"ref": {"from": "input", "path": "mode"}},
                            {"literal": "prod"},
                        ],
                    },
                }
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    runners = _runners({"a": _Recording("a", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={"mode": "prod"})
    assert result.status == "SUCCEEDED"
    assert result.node_states["a"].status == "SUCCESS"
    assert log == ["a"]


@pytest.mark.asyncio
async def test_when_false_marks_skipped_and_runner_not_called():
    contracts = _contracts("a")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "when": {
                        "op": "eq",
                        "args": [
                            {"ref": {"from": "input", "path": "mode"}},
                            {"literal": "prod"},
                        ],
                    },
                }
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    events: list[dict] = []

    async def emit(e: dict) -> None:
        events.append(e)

    runners = _runners({"a": _Recording("a", log)})
    executor = WorkflowExecutor(runners, event_emitter=emit)
    result = await executor.run(compiled, inputs={"mode": "dev"})
    assert result.status == "SUCCEEDED"
    assert result.node_states["a"].status == "SKIPPED"
    assert log == []
    assert any(e["type"] == "step.skipped" and e["node_id"] == "a" for e in events)


@pytest.mark.asyncio
async def test_downstream_of_skipped_node_fails_with_skipped_ref():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "when": {
                        "op": "eq",
                        "args": [
                            {"ref": {"from": "input", "path": "mode"}},
                            {"literal": "prod"},
                        ],
                    },
                },
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {
                        "x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}
                    },
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    runners = _runners({"a": _Recording("a", log), "b": _Recording("b", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={"mode": "dev"})
    assert result.node_states["a"].status == "SKIPPED"
    assert result.node_states["b"].status == "FAILED"
    assert result.node_states["b"].error is not None
    assert result.node_states["b"].error["type"] == "skipped_ref"
    assert "b" not in log
    assert result.status == "FAILED"


@pytest.mark.asyncio
async def test_branch_without_ref_to_skipped_proceeds():
    contracts = _contracts("a", "b", "c")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "when": {
                        "op": "eq",
                        "args": [
                            {"ref": {"from": "input", "path": "mode"}},
                            {"literal": "prod"},
                        ],
                    },
                },
                {"id": "b", "agent": "b", "agent_version": 1},
                {
                    "id": "c",
                    "agent": "c",
                    "agent_version": 1,
                    "inputs": {
                        "x": {"ref": {"from": "node", "node_id": "b", "path": "output.v"}}
                    },
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    runners = _runners(
        {"a": _Recording("a", log), "b": _Recording("b", log), "c": _Recording("c", log)}
    )
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={"mode": "dev"})
    assert result.status == "SUCCEEDED"
    assert result.node_states["a"].status == "SKIPPED"
    assert result.node_states["b"].status == "SUCCESS"
    assert result.node_states["c"].status == "SUCCESS"
