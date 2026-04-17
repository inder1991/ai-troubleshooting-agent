"""Task 2.8 — Dispatcher runs agents in parallel with per-agent timeout."""
from __future__ import annotations

import asyncio
import time

import pytest

from src.agents.orchestration.dispatcher import (
    AgentSpec,
    Dispatcher,
    StepResult,
)


@pytest.mark.asyncio
async def test_dispatcher_runs_agents_in_parallel():
    started: list[tuple[str, float]] = []

    async def fake_executor(spec: AgentSpec):
        started.append((spec.agent, time.monotonic()))
        await asyncio.sleep(0.05)
        return {"agent": spec.agent}

    d = Dispatcher(executor=fake_executor, timeout_per_agent_s=2.0)
    results = await d.dispatch_round(
        [AgentSpec(agent="log_agent"), AgentSpec(agent="metrics_agent"), AgentSpec(agent="k8s_agent")]
    )

    # All three should have started within 50ms of each other → real parallelism
    times = [t for _, t in started]
    assert max(times) - min(times) < 0.05
    assert {r.agent for r in results} == {"log_agent", "metrics_agent", "k8s_agent"}
    assert all(r.status == "ok" for r in results)


@pytest.mark.asyncio
async def test_per_agent_timeout_is_enforced():
    async def fake_executor(spec: AgentSpec):
        # Simulate a stuck agent
        await asyncio.sleep(0.5)
        return {"agent": spec.agent}

    d = Dispatcher(executor=fake_executor, timeout_per_agent_s=0.1)
    results = await d.dispatch_round([AgentSpec(agent="log_agent")])
    assert results[0].status == "timeout"
    assert "timed out" in results[0].error


@pytest.mark.asyncio
async def test_one_agent_failure_does_not_block_others():
    async def fake_executor(spec: AgentSpec):
        if spec.agent == "bad":
            raise RuntimeError("boom")
        await asyncio.sleep(0.01)
        return {"agent": spec.agent}

    d = Dispatcher(executor=fake_executor, timeout_per_agent_s=1.0)
    results = await d.dispatch_round(
        [AgentSpec(agent="bad"), AgentSpec(agent="log_agent"), AgentSpec(agent="metrics_agent")]
    )
    by_agent = {r.agent: r for r in results}
    assert by_agent["bad"].status == "error"
    assert "RuntimeError" in by_agent["bad"].error
    assert by_agent["log_agent"].status == "ok"
    assert by_agent["metrics_agent"].status == "ok"


@pytest.mark.asyncio
async def test_empty_specs_returns_empty():
    async def fake_executor(spec):
        return None

    d = Dispatcher(executor=fake_executor, timeout_per_agent_s=1.0)
    results = await d.dispatch_round([])
    assert results == []


@pytest.mark.asyncio
async def test_cancellation_propagates():
    async def slow_executor(spec):
        await asyncio.sleep(10)

    d = Dispatcher(executor=slow_executor, timeout_per_agent_s=10.0)
    task = asyncio.create_task(
        d.dispatch_round([AgentSpec(agent="log_agent"), AgentSpec(agent="metrics_agent")])
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_result_carries_elapsed_time():
    async def fake_executor(spec):
        await asyncio.sleep(0.02)
        return spec.agent

    d = Dispatcher(executor=fake_executor, timeout_per_agent_s=1.0)
    results = await d.dispatch_round([AgentSpec(agent="log_agent")])
    assert results[0].elapsed_s >= 0.02
    assert results[0].started_at > 0
