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


def _contract(name: str, version: int = 1) -> AgentContract:
    return AgentContract.model_validate(
        {
            "name": name,
            "version": version,
            "deprecated_versions": [],
            "description": "t",
            "category": "t",
            "tags": [],
            "inputs": {"type": "object"},
            "outputs": {
                "type": "object",
                "properties": {"v": {"type": "string"}},
            },
            "trigger_examples": ["a", "b"],
            "retry_on": ["timeout"],
            "timeout_seconds": 30.0,
        }
    )


def _contracts(*names: str) -> ContractRegistry:
    reg = ContractRegistry()
    reg._by_key = {(n, 1): _contract(n) for n in names}
    return reg


class _RecordingRunner:
    """Simple runner that records call order and returns canned output."""

    def __init__(self, name: str, order: list[str], output: Any | None = None) -> None:
        self._name = name
        self._order = order
        self._output = output if output is not None else {"v": name}

    async def run(self, inputs: dict, *, context: dict) -> dict:
        self._order.append(self._name)
        return self._output


class _ConcurrencyTracker:
    def __init__(self) -> None:
        self.current = 0
        self.peak = 0
        self.lock = asyncio.Lock()


class _GatedRunner:
    """Runner that increments a concurrency counter, waits for an event,
    then decrements. Used to force deterministic concurrency snapshots."""

    def __init__(self, name: str, tracker: _ConcurrencyTracker, gate: asyncio.Event) -> None:
        self._name = name
        self._tracker = tracker
        self._gate = gate

    async def run(self, inputs: dict, *, context: dict) -> dict:
        async with self._tracker.lock:
            self._tracker.current += 1
            if self._tracker.current > self._tracker.peak:
                self._tracker.peak = self._tracker.current
        try:
            await self._gate.wait()
        finally:
            async with self._tracker.lock:
                self._tracker.current -= 1
        return {"v": self._name}


def _runners(mapping: dict[str, Any]) -> AgentRunnerRegistry:
    reg = AgentRunnerRegistry()
    for name, runner in mapping.items():
        reg.register(name, 1, runner)
    return reg


@pytest.mark.asyncio
async def test_linear_two_step_runs_in_order():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}},
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    order: list[str] = []
    runners = _runners({"a": _RecordingRunner("a", order), "b": _RecordingRunner("b", order)})
    executor = WorkflowExecutor(runners)
    result = await executor.run(compiled, inputs={})
    assert order == ["a", "b"]
    assert result.status == "SUCCEEDED"
    assert result.node_states["a"].status == "SUCCESS"
    assert result.node_states["b"].status == "SUCCESS"
    assert result.node_states["a"].output == {"v": "a"}


@pytest.mark.asyncio
async def test_parallel_fanout_respects_global_cap():
    contracts = _contracts("a", "b", "c", "d")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}},
                },
                {
                    "id": "c",
                    "agent": "c",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}},
                },
                {
                    "id": "d",
                    "agent": "d",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}},
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    tracker = _ConcurrencyTracker()
    gate = asyncio.Event()

    async def release_soon() -> None:
        # Give time for scheduler to launch as many as cap allows.
        await asyncio.sleep(0.02)
        gate.set()

    order: list[str] = []
    runners = _runners(
        {
            "a": _RecordingRunner("a", order),
            "b": _GatedRunner("b", tracker, gate),
            "c": _GatedRunner("c", tracker, gate),
            "d": _GatedRunner("d", tracker, gate),
        }
    )
    executor = WorkflowExecutor(runners, max_concurrent_steps=2)
    _, result = await asyncio.gather(release_soon(), executor.run(compiled, inputs={}))
    assert result.status == "SUCCEEDED"
    assert tracker.peak == 2


@pytest.mark.asyncio
async def test_fifo_tiebreak_by_step_id_lex_order():
    # Three steps with same readiness time (all root); global cap 1 forces
    # sequential execution, where ordering MUST be lex by id.
    contracts = _contracts("x_beta", "x_alpha", "x_gamma")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "x_beta", "agent": "x_beta", "agent_version": 1},
                {"id": "x_alpha", "agent": "x_alpha", "agent_version": 1},
                {"id": "x_gamma", "agent": "x_gamma", "agent_version": 1},
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    order: list[str] = []
    runners = _runners(
        {
            "x_beta": _RecordingRunner("x_beta", order),
            "x_alpha": _RecordingRunner("x_alpha", order),
            "x_gamma": _RecordingRunner("x_gamma", order),
        }
    )
    executor = WorkflowExecutor(runners, max_concurrent_steps=1)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCEEDED"
    assert order == ["x_alpha", "x_beta", "x_gamma"]


@pytest.mark.asyncio
async def test_emits_run_and_step_events_in_order():
    contracts = _contracts("a", "b")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [
                {"id": "a", "agent": "a", "agent_version": 1},
                {
                    "id": "b",
                    "agent": "b",
                    "agent_version": 1,
                    "inputs": {"x": {"ref": {"from": "node", "node_id": "a", "path": "output.v"}}},
                },
            ],
        }
    )
    compiled = compile_dag(dag, contracts)
    order: list[str] = []
    runners = _runners({"a": _RecordingRunner("a", order), "b": _RecordingRunner("b", order)})
    events: list[dict] = []

    async def emit(ev: dict) -> None:
        events.append(ev)

    executor = WorkflowExecutor(runners, event_emitter=emit)
    await executor.run(compiled, inputs={})
    types = [e["type"] for e in events]
    assert types[0] == "run.started"
    assert types[-1] == "run.completed"
    # Ensure step.started + step.completed present for each of a, b in order
    a_started = types.index("step.started")
    assert events[a_started]["node_id"] == "a"
    # The step.completed for 'a' must come before step.started for 'b'
    step_events = [
        (i, e) for i, e in enumerate(events) if e["type"].startswith("step.")
    ]
    seq = [(e["type"], e["node_id"]) for _, e in step_events]
    assert seq == [
        ("step.started", "a"),
        ("step.completed", "a"),
        ("step.started", "b"),
        ("step.completed", "b"),
    ]
    # step.completed events must carry duration_ms
    for _, e in step_events:
        if e["type"] == "step.completed":
            assert isinstance(e.get("duration_ms"), (int, float))
            assert e.get("attempt") == 1


@pytest.mark.asyncio
async def test_emitter_exception_does_not_fail_run():
    contracts = _contracts("a")
    dag = WorkflowDag.model_validate(
        {
            "inputs_schema": {"type": "object"},
            "steps": [{"id": "a", "agent": "a", "agent_version": 1}],
        }
    )
    compiled = compile_dag(dag, contracts)
    runners = _runners({"a": _RecordingRunner("a", [])})

    async def emit(ev: dict) -> None:
        raise RuntimeError("emitter boom")

    executor = WorkflowExecutor(runners, event_emitter=emit)
    result = await executor.run(compiled, inputs={})
    assert result.status == "SUCCEEDED"
