from __future__ import annotations

import asyncio
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
            "retry_on": [],
            "timeout_seconds": 30.0,
        }
    )


def _contracts(*names: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(n, 1): _contract(n) for n in names}
    return reg


def _runners(m: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, r in m.items():
        reg.register(name, 1, r)
    return reg


class _Gate:
    """Runner that waits on an external event then returns."""

    def __init__(self, gate: asyncio.Event, name: str) -> None:
        self._gate = gate
        self._name = name

    async def run(self, inputs: dict, *, context: dict) -> dict:
        await self._gate.wait()
        return {"v": self._name}


class _Cooperative:
    """Runner that polls ``context['is_cancelled']`` and returns when set."""

    def __init__(self, name: str) -> None:
        self._name = name
        self.saw_cancel = False

    async def run(self, inputs: dict, *, context: dict) -> dict:
        is_cancelled = context["is_cancelled"]
        for _ in range(200):
            if is_cancelled():
                self.saw_cancel = True
                raise RuntimeError("cooperative cancel")
            await asyncio.sleep(0.01)
        return {"v": self._name}


class _Stubborn:
    """Runner that ignores the cancel flag and sleeps forever."""

    async def run(self, inputs: dict, *, context: dict) -> dict:
        await asyncio.sleep(60.0)
        return {"v": "never"}


class _Immediate:
    def __init__(self, name: str) -> None:
        self._name = name

    async def run(self, inputs: dict, *, context: dict) -> dict:
        return {"v": self._name}


@pytest.mark.asyncio
async def test_cancel_before_any_step_completes():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {"id": "b", "agent": "b", "agent_version": 1},
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    gate = asyncio.Event()
    runners = _runners({"a": _Gate(gate, "a"), "b": _Gate(gate, "b")})

    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    cancel = asyncio.Event()
    executor = WorkflowExecutor(
        runners,
        event_emitter=emit,
        cancel_grace_seconds=0.1,
    )

    async def _trigger_cancel() -> None:
        await asyncio.sleep(0.02)
        cancel.set()

    trigger = asyncio.create_task(_trigger_cancel())
    result = await executor.run(compiled, inputs={}, cancel_event=cancel)
    await trigger
    gate.set()

    assert result.status == "CANCELLED"
    assert all(ns.status == "CANCELLED" for ns in result.node_states.values())
    types = [e["type"] for e in events]
    assert "run.cancelling" in types
    assert "run.cancelled" in types


@pytest.mark.asyncio
async def test_cancel_mid_run_with_cooperative_inflight():
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
    coop = _Cooperative("b")
    runners = _runners(
        {"a": _Immediate("a"), "b": coop, "c": _Immediate("c")}
    )

    cancel = asyncio.Event()
    executor = WorkflowExecutor(runners, cancel_grace_seconds=2.0)

    async def _trigger_cancel() -> None:
        # Wait until b has started running.
        await asyncio.sleep(0.05)
        cancel.set()

    trigger = asyncio.create_task(_trigger_cancel())
    result = await executor.run(compiled, inputs={}, cancel_event=cancel)
    await trigger

    assert result.status == "CANCELLED"
    assert result.node_states["a"].status == "SUCCESS"
    assert result.node_states["b"].status == "CANCELLED"
    assert result.node_states["c"].status == "CANCELLED"
    assert coop.saw_cancel is True


@pytest.mark.asyncio
async def test_cancel_forces_noncooperative_after_grace():
    contracts = _contracts("a")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runners = _runners({"a": _Stubborn()})

    cancel = asyncio.Event()
    executor = WorkflowExecutor(runners, cancel_grace_seconds=0.1)

    async def _trigger_cancel() -> None:
        await asyncio.sleep(0.02)
        cancel.set()

    trigger = asyncio.create_task(_trigger_cancel())
    result = await executor.run(compiled, inputs={}, cancel_event=cancel)
    await trigger

    assert result.status == "CANCELLED"
    assert result.node_states["a"].status == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_after_completion_is_noop():
    contracts = _contracts("a")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runners = _runners({"a": _Immediate("a")})

    cancel = asyncio.Event()  # set AFTER run finishes
    executor = WorkflowExecutor(runners, cancel_grace_seconds=0.1)
    result = await executor.run(compiled, inputs={}, cancel_event=cancel)
    # Setting cancel after the fact should not retroactively change status.
    cancel.set()
    assert result.status == "SUCCEEDED"
    assert result.node_states["a"].status == "SUCCESS"
