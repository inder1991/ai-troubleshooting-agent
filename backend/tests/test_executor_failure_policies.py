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


class _Succeed:
    def __init__(self, name: str, log: list[str], output: Any | None = None) -> None:
        self._name = name
        self._log = log
        self._output = output if output is not None else {"v": name}

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self._log.append(self._name)
        return self._output


class _Fail:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self._log.append(self._name)
        raise RuntimeError(f"{self._name} boom")


def _runners(m: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, r in m.items():
        reg.register(name, 1, r)
    return reg


@pytest.mark.asyncio
async def test_default_failfast_cancels_unstarted_downstream():
    contracts = _contracts("a", "b", "c")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {
                        "x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}
                    },
                },
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
        {"a": _Fail("a", log), "b": _Succeed("b", log), "c": _Succeed("c", log)}
    )
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert result.status == "FAILED"
    assert result.node_states["a"].status == "FAILED"
    assert result.node_states["b"].status == "CANCELLED"
    assert result.node_states["c"].status == "CANCELLED"
    assert "b" not in log and "c" not in log


@pytest.mark.asyncio
async def test_continue_isolates_failure_on_independent_branch():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1, "on_failure": "continue"},
                {"id": "b", "agent": "b", "agent_version": 1},
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    runners = _runners({"a": _Fail("a", log), "b": _Succeed("b", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCESS"
    assert result.node_states["a"].status == "FAILED"
    assert result.node_states["b"].status == "SUCCESS"


@pytest.mark.asyncio
async def test_continue_downstream_refs_fail_with_upstream_failed():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1, "on_failure": "continue"},
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
    runners = _runners({"a": _Fail("a", log), "b": _Succeed("b", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert result.node_states["a"].status == "FAILED"
    assert result.node_states["b"].status == "FAILED"
    assert result.node_states["b"].error is not None
    assert result.node_states["b"].error["type"] == "upstream_failed"
    assert "b" not in log


@pytest.mark.asyncio
async def test_fallback_replaces_output_for_downstream_refs():
    contracts = _contracts("a", "a_fb", "c")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "on_failure": "fallback",
                    "fallback_step_id": "a_fb",
                },
                {"id": "a_fb", "agent": "a_fb", "agent_version": 1},
                {
                    "id": "c",
                    "agent": "c",
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
    captured: dict[str, Any] = {}

    class _Capture:
        def __init__(self, name: str) -> None:
            self._name = name

        async def run(self, inputs: dict, *, context: dict) -> dict:
            log.append(self._name)
            captured[self._name] = inputs
            return {"v": self._name}

    runners = _runners(
        {
            "a": _Fail("a", log),
            "a_fb": _Succeed("a_fb", log, output={"v": "fallback_value"}),
            "c": _Capture("c"),
        }
    )
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCESS"
    assert result.node_states["a"].status == "FAILED"
    assert result.node_states["a_fb"].status == "SUCCESS"
    assert result.node_states["c"].status == "SUCCESS"
    assert captured["c"] == {"x": "fallback_value"}


@pytest.mark.asyncio
async def test_fallback_itself_fails_causes_run_fail():
    contracts = _contracts("a", "a_fb")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "on_failure": "fallback",
                    "fallback_step_id": "a_fb",
                },
                {"id": "a_fb", "agent": "a_fb", "agent_version": 1},
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    log: list[str] = []
    runners = _runners({"a": _Fail("a", log), "a_fb": _Fail("a_fb", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert result.status == "FAILED"
    assert result.node_states["a"].status == "FAILED"
    assert result.node_states["a_fb"].status == "FAILED"
