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


def _contract(
    name: str,
    *,
    timeout: float = 30.0,
    retry_on: list[str] | None = None,
) -> AgentContract:
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
            "retry_on": list(retry_on or []),
            "timeout_seconds": timeout,
        }
    )


def _registry(contracts: list[AgentContract]) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(c.name, c.version): c for c in contracts}
    return reg


def _runners(m: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, r in m.items():
        reg.register(name, 1, r)
    return reg


class _SlowRunner:
    async def run(self, inputs: dict, *, context: dict) -> dict:
        await asyncio.sleep(5.0)
        return {"v": "never"}


class _FlakyRunner:
    """Fails with ``exc`` the first ``fail_times`` attempts then succeeds."""

    def __init__(self, exc: Exception, fail_times: int) -> None:
        self._exc = exc
        self._fail_times = fail_times
        self.attempts = 0

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self.attempts += 1
        if self.attempts <= self._fail_times:
            raise self._exc
        return {"v": "ok"}


class _AlwaysFail:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.attempts = 0

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self.attempts += 1
        raise self._exc


@pytest.mark.asyncio
async def test_runner_timeout_marks_step_failed_timeout():
    contracts = _registry([_contract("a", timeout=0.05)])
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runners = _runners({"a": _SlowRunner()})
    sleeps: list[float] = []

    async def _fake_sleep(d: float) -> None:
        sleeps.append(d)

    executor = WorkflowExecutor(runners, sleep_fn=_fake_sleep)
    result = await executor.run(compiled, inputs={})
    assert result.status == "FAILED"
    ns = result.node_states["a"]
    assert ns.status == "FAILED"
    assert ns.error is not None
    assert ns.error["type"] == "timeout"


@pytest.mark.asyncio
async def test_retry_succeeds_on_third_attempt():
    contracts = _registry(
        [_contract("a", timeout=30.0, retry_on=["ValueError"])]
    )
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runner = _FlakyRunner(ValueError("flaky"), fail_times=2)
    runners = _runners({"a": runner})

    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    sleeps: list[float] = []

    async def _fake_sleep(d: float) -> None:
        sleeps.append(d)

    executor = WorkflowExecutor(runners, event_emitter=emit, sleep_fn=_fake_sleep)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCESS"
    ns = result.node_states["a"]
    assert ns.status == "SUCCESS"
    assert ns.attempt == 3
    assert runner.attempts == 3
    started = [e for e in events if e.get("type") == "step.started" and e.get("node_id") == "a"]
    assert len(started) == 3
    assert [e["attempt"] for e in started] == [1, 2, 3]
    completed = [
        e for e in events if e.get("type") == "step.completed" and e.get("node_id") == "a"
    ]
    assert len(completed) == 1
    assert completed[0]["attempt"] == 3


@pytest.mark.asyncio
async def test_non_retryable_exception_fails_after_one_attempt():
    contracts = _registry(
        [_contract("a", timeout=30.0, retry_on=["ValueError"])]
    )
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runner = _AlwaysFail(RuntimeError("boom"))
    runners = _runners({"a": runner})

    sleeps: list[float] = []

    async def _fake_sleep(d: float) -> None:
        sleeps.append(d)

    executor = WorkflowExecutor(runners, sleep_fn=_fake_sleep)
    result = await executor.run(compiled, inputs={})
    assert result.status == "FAILED"
    ns = result.node_states["a"]
    assert ns.status == "FAILED"
    assert ns.attempt == 1
    assert runner.attempts == 1
    assert sleeps == []


@pytest.mark.asyncio
async def test_step_override_narrows_retry_set():
    contracts = _registry(
        [_contract("a", timeout=30.0, retry_on=["TimeoutError", "ConnectionError"])]
    )
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {
                    "id": "a",
                    "agent": "a",
                    "agent_version": 1,
                    "retry_on_override": ["TimeoutError"],
                }
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    runner = _AlwaysFail(ConnectionError("nope"))
    runners = _runners({"a": runner})

    async def _fake_sleep(d: float) -> None:
        pass

    executor = WorkflowExecutor(runners, sleep_fn=_fake_sleep)
    result = await executor.run(compiled, inputs={})
    assert result.status == "FAILED"
    assert result.node_states["a"].attempt == 1
    assert runner.attempts == 1


@pytest.mark.asyncio
async def test_exponential_backoff_sleeps_01_02_for_three_attempts():
    contracts = _registry(
        [_contract("a", timeout=30.0, retry_on=["ValueError"])]
    )
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runner = _FlakyRunner(ValueError("flaky"), fail_times=2)
    runners = _runners({"a": runner})

    sleeps: list[float] = []

    async def _fake_sleep(d: float) -> None:
        sleeps.append(d)

    executor = WorkflowExecutor(runners, sleep_fn=_fake_sleep)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCESS"
    assert sleeps == [0.1, 0.2]
