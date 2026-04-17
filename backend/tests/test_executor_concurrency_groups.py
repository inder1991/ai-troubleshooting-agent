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
            "retry_on": ["timeout"],
            "timeout_seconds": 30.0,
        }
    )


def _contracts(*names: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(n, 1): _contract(n) for n in names}
    return reg


class _Tracker:
    def __init__(self) -> None:
        self.current: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.lock = asyncio.Lock()


class _GroupGatedRunner:
    def __init__(self, group: str, tracker: _Tracker, gate: asyncio.Event) -> None:
        self._group = group
        self._tracker = tracker
        self._gate = gate

    async def run(self, inputs: dict, *, context: dict) -> dict:
        async with self._tracker.lock:
            self._tracker.current[self._group] = self._tracker.current.get(self._group, 0) + 1
            self._tracker.peak[self._group] = max(
                self._tracker.peak.get(self._group, 0), self._tracker.current[self._group]
            )
        try:
            await self._gate.wait()
        finally:
            async with self._tracker.lock:
                self._tracker.current[self._group] -= 1
        return {"v": self._group}


def _runners(mapping: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, runner in mapping.items():
        reg.register(name, 1, runner)
    return reg


@pytest.mark.asyncio
async def test_group_cap_limits_concurrency_below_global():
    contracts = _contracts("a", "b", "c", "d")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {
                    "id": sid,
                    "agent": sid,
                    "agent_version": 1,
                    "concurrency_group": "logs_api",
                }
                for sid in ("a", "b", "c", "d")
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    tracker = _Tracker()
    gate = asyncio.Event()

    async def release_soon() -> None:
        await asyncio.sleep(0.02)
        gate.set()

    runners = _runners(
        {sid: _GroupGatedRunner("logs_api", tracker, gate) for sid in ("a", "b", "c", "d")}
    )
    executor = WorkflowExecutor(
        runners, max_concurrent_steps=8, concurrency_group_caps={"logs_api": 2}
    )
    _, result = await asyncio.gather(release_soon(), executor.run(compiled, inputs={}))
    assert result.status == "SUCCESS"
    assert tracker.peak.get("logs_api", 0) == 2


@pytest.mark.asyncio
async def test_no_group_only_global_cap_applies():
    contracts = _contracts("a", "b", "c", "d")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": sid, "agent": sid, "agent_version": 1}
                for sid in ("a", "b", "c", "d")
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    tracker = _Tracker()
    gate = asyncio.Event()

    async def release_soon() -> None:
        await asyncio.sleep(0.02)
        gate.set()

    runners = _runners(
        {sid: _GroupGatedRunner("none", tracker, gate) for sid in ("a", "b", "c", "d")}
    )
    executor = WorkflowExecutor(runners, max_concurrent_steps=4)
    _, result = await asyncio.gather(release_soon(), executor.run(compiled, inputs={}))
    assert result.status == "SUCCESS"
    assert tracker.peak.get("none", 0) == 4
