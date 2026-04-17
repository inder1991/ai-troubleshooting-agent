"""Dispatcher — parallel agent fan-out with per-agent timeout.

Extracted from ``SupervisorAgent`` so the concern has a testable surface.
The dispatcher owns *how* agents run (parallel, timeout, error containment);
the planner owns *which* agents run; the reducer owns *what happens with
the results*. Keeping these separated makes each one a small amount of
code that actually fits in your head.

Parallelism contract:
  - All specs in a round start concurrently via ``asyncio.gather``.
  - Each spec has a hard per-agent timeout via ``asyncio.wait_for``.
  - Failures are contained: a timeout, exception, or cancellation is
    reported via ``StepResult(status=...)``; the other agents keep going.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional


StepStatus = Literal["ok", "timeout", "error"]


@dataclass(frozen=True)
class AgentSpec:
    """What to run."""

    agent: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StepResult:
    """What came back (or why nothing did)."""

    agent: str
    status: StepStatus
    value: Any = None
    error: Optional[str] = None
    started_at: float = 0.0
    elapsed_s: float = 0.0


# Executor is anything async that takes an AgentSpec and returns the agent's
# result. In production this is a bound method on SupervisorAgent; in tests
# it's a stub. Keeping the contract callable-shaped (not class-shaped) makes
# test injection trivial.
Executor = Callable[[AgentSpec], Awaitable[Any]]


class Dispatcher:
    """Runs an agent round concurrently with per-agent timeout containment."""

    def __init__(self, executor: Executor, *, timeout_per_agent_s: float = 60.0) -> None:
        self._executor = executor
        self._timeout_s = timeout_per_agent_s

    async def dispatch_round(self, specs: list[AgentSpec]) -> list[StepResult]:
        if not specs:
            return []
        return await asyncio.gather(*(self._run_one(s) for s in specs))

    async def _run_one(self, spec: AgentSpec) -> StepResult:
        started_at = time.monotonic()
        try:
            value = await asyncio.wait_for(
                self._executor(spec),
                timeout=self._timeout_s,
            )
            return StepResult(
                agent=spec.agent,
                status="ok",
                value=value,
                started_at=started_at,
                elapsed_s=time.monotonic() - started_at,
            )
        except asyncio.TimeoutError:
            return StepResult(
                agent=spec.agent,
                status="timeout",
                error=f"timed out after {self._timeout_s}s",
                started_at=started_at,
                elapsed_s=time.monotonic() - started_at,
            )
        except asyncio.CancelledError:
            # Propagate cancellation semantics: if the round itself is
            # cancelled (e.g. the investigation is cancelled by the user),
            # surface that cleanly — Task 4.25 will wire the propagation end-to-end.
            raise
        except Exception as exc:  # noqa: BLE001 — error containment is the point
            return StepResult(
                agent=spec.agent,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                started_at=started_at,
                elapsed_s=time.monotonic() - started_at,
            )
