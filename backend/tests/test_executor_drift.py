from __future__ import annotations

from typing import Any

import pytest

from src.contracts.models import AgentContract
from src.contracts.registry import ContractRegistry
from src.workflows.compiler import compile_dag
from src.workflows.executor import WorkflowExecutor
from src.workflows.models import WorkflowDag
from src.workflows.runners.registry import AgentRunnerRegistry


def _contract(
    name: str,
    *,
    version: int = 1,
    deprecated: list[int] | None = None,
    outputs: dict | None = None,
    timeout: float = 30.0,
    retry_on: list[str] | None = None,
) -> AgentContract:
    return AgentContract.model_validate(
        {
            "name": name,
            "version": version,
            "deprecated_versions": list(deprecated or []),
            "description": "t",
            "category": "t",
            "tags": [],
            "inputs": {"type": "object"},
            "outputs": outputs
            or {"type": "object", "properties": {"v": {"type": "string"}}},
            "trigger_examples": ["a", "b"],
            "retry_on": list(retry_on or []),
            "timeout_seconds": timeout,
        }
    )


def _registry(contracts: list[AgentContract]) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(c.name, c.version): c for c in contracts}
    return reg


class _Succeed:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self._log.append(self._name)
        return {"v": self._name}


def _runners(m: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, r in m.items():
        reg.register(name, 1, r)
    return reg


def _simple_dag() -> WorkflowDag:
    return WorkflowDag.model_validate(
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
            ],
        }
    )


@pytest.mark.asyncio
async def test_happy_path_no_drift():
    contracts = _registry([_contract("a"), _contract("b")])
    compiled = compile_dag(_simple_dag(), contracts)
    log: list[str] = []
    runners = _runners({"a": _Succeed("a", log), "b": _Succeed("b", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={}, contracts=contracts)
    assert result.status == "SUCCESS"
    assert log == ["a", "b"]


@pytest.mark.asyncio
async def test_drift_when_version_becomes_deprecated():
    contracts = _registry([_contract("a"), _contract("b")])
    compiled = compile_dag(_simple_dag(), contracts)
    log: list[str] = []
    runners = _runners({"a": _Succeed("a", log), "b": _Succeed("b", log)})

    # Mutate registry: deprecate b v1 after save.
    contracts._by_key[("b", 1)] = _contract("b", deprecated=[1])

    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    executor = WorkflowExecutor(runners, event_emitter=emit)
    result = await executor.run(compiled, inputs={}, contracts=contracts)
    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error["type"] == "drift_detected"
    drifts = result.error["drifts"]
    assert any(d["step_id"] == "b" for d in drifts)
    assert log == []
    types = [e["type"] for e in events]
    assert "run.started" in types
    assert "run.failed" in types


@pytest.mark.asyncio
async def test_drift_when_ref_path_disappears_from_output_schema():
    contracts = _registry([_contract("a"), _contract("b")])
    compiled = compile_dag(_simple_dag(), contracts)
    log: list[str] = []
    runners = _runners({"a": _Succeed("a", log), "b": _Succeed("b", log)})

    # Remove `v` from a's output schema.
    contracts._by_key[("a", 1)] = _contract(
        "a", outputs={"type": "object", "properties": {"other": {"type": "string"}}}
    )

    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={}, contracts=contracts)
    assert result.status == "FAILED"
    assert result.error["type"] == "drift_detected"
    assert any(
        d["step_id"] == "b" and "output.v" in d["detail"]
        for d in result.error["drifts"]
    )
    assert log == []


@pytest.mark.asyncio
async def test_drift_when_contract_timeout_tightens_below_override():
    base_a = _contract("a")
    base_b = _contract("b", timeout=30.0)
    contracts = _registry([base_a, base_b])
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "timeout_seconds_override": 20.0,
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)

    # Tighten contract b's timeout below the compiled override.
    contracts._by_key[("b", 1)] = _contract("b", timeout=5.0)

    log: list[str] = []
    runners = _runners({"a": _Succeed("a", log), "b": _Succeed("b", log)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={}, contracts=contracts)
    assert result.status == "FAILED"
    assert result.error["type"] == "drift_detected"
    assert any(d["step_id"] == "b" for d in result.error["drifts"])
    assert log == []
