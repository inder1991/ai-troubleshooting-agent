from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from src.workflows.compiler import CompiledStep, CompiledWorkflow
from src.workflows.evaluator import MissingRefError, SkippedRefError, evaluate
from src.workflows.runners.registry import AgentRunnerRegistry

logger = logging.getLogger(__name__)


EventEmitter = Callable[[dict], Awaitable[None]]


@dataclass
class NodeState:
    status: str = "PENDING"
    output: Any = None
    error: dict | None = None
    started_at: str | None = None
    ended_at: str | None = None
    attempt: int = 0


@dataclass
class RunResult:
    status: str
    node_states: dict[str, NodeState]
    error: dict | None = None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(order=True)
class _QueueItem:
    readiness_time: float
    step_id: str = field(compare=True)


class WorkflowExecutor:
    def __init__(
        self,
        runners: AgentRunnerRegistry,
        max_concurrent_steps: int = 8,
        concurrency_group_caps: dict[str, int] | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._runners = runners
        self._max_concurrent = max_concurrent_steps
        self._group_caps = dict(concurrency_group_caps or {})
        self._emitter = event_emitter

    async def _emit(self, ev: dict) -> None:
        if self._emitter is None:
            return
        try:
            await self._emitter(ev)
        except Exception:
            logger.exception("event emitter raised; continuing")

    async def run(
        self,
        compiled: CompiledWorkflow,
        inputs: dict,
        env: dict | None = None,
    ) -> RunResult:
        env = env or {}
        node_states: dict[str, NodeState] = {
            sid: NodeState() for sid in compiled.topo_order
        }
        # Tracks nodes whose *resolved* output should be used when other nodes
        # reference them (for fallback replacement).
        output_for_ref: dict[str, str] = {sid: sid for sid in compiled.topo_order}

        remaining_upstream: dict[str, set[str]] = {
            sid: set(compiled.steps[sid].upstream_ids) for sid in compiled.topo_order
        }
        completed: set[str] = set()
        fail_fast_triggered = False
        run_error: dict | None = None

        global_sem = asyncio.Semaphore(self._max_concurrent)
        group_sems: dict[str, asyncio.Semaphore] = {
            g: asyncio.Semaphore(cap) for g, cap in self._group_caps.items()
        }

        scheduled: set[str] = set()  # already started (or skipped) — will not re-queue
        running: set[str] = set()
        queue: list[_QueueItem] = []

        await self._emit({"type": "run.started", "timestamp": _iso_now()})

        # Seed queue with nodes having no upstream deps
        monotonic = time.monotonic
        for sid in compiled.topo_order:
            if not remaining_upstream[sid]:
                queue.append(_QueueItem(monotonic(), sid))

        tasks: dict[str, asyncio.Task] = {}
        cond = asyncio.Condition()

        def _state_dict_for_eval() -> dict:
            nodes_view: dict[str, dict] = {}
            for sid, ns in node_states.items():
                if ns.status in ("SUCCESS", "SKIPPED", "FAILED"):
                    # Remap to output-source for fallback replacement
                    src_id = output_for_ref.get(sid, sid)
                    src_ns = node_states[src_id]
                    nodes_view[sid] = {
                        "status": src_ns.status,
                        "output": src_ns.output,
                    }
            return {"input": inputs, "env": env, "nodes": nodes_view}

        def _queue_ready(sid: str) -> None:
            if sid in scheduled or sid in running:
                return
            if remaining_upstream[sid]:
                return
            queue.append(_QueueItem(monotonic(), sid))

        def _sort_queue() -> None:
            queue.sort(key=lambda q: (q.readiness_time, q.step_id))

        async def _finalize_node(sid: str) -> None:
            """Propagate completion to downstream ready-set."""
            completed.add(sid)
            running.discard(sid)
            for nsid, ups in remaining_upstream.items():
                if sid in ups:
                    ups.discard(sid)
                    if not ups and nsid not in completed and nsid not in scheduled and nsid not in running:
                        queue.append(_QueueItem(monotonic(), nsid))
            async with cond:
                cond.notify_all()

        async def _run_step(step: CompiledStep) -> None:
            try:
                await _run_step_inner(step)
            finally:
                await _finalize_node(step.id)

        async def _run_step_inner(step: CompiledStep) -> None:
            """Execute a single step including predicate eval, input resolve,
            runner invocation, and bookkeeping. Respects fail_fast."""
            nonlocal fail_fast_triggered, run_error

            ns = node_states[step.id]

            if fail_fast_triggered:
                ns.status = "CANCELLED"
                ns.started_at = _iso_now()
                ns.ended_at = ns.started_at
                return

            # Predicate
            if step.when is not None:
                try:
                    truthy = bool(evaluate(step.when, _state_dict_for_eval()))
                except SkippedRefError as e:
                    ns.status = "FAILED"
                    ns.error = {"type": "skipped_ref", "message": str(e)}
                    ns.started_at = ns.ended_at = _iso_now()
                    await self._emit(
                        {
                            "type": "step.failed",
                            "node_id": step.id,
                            "attempt": 1,
                            "duration_ms": 0,
                            "error_class": "skipped_ref",
                            "error_message": str(e),
                            "timestamp": _iso_now(),
                        }
                    )
                    await _handle_failure(step)
                    return
                except MissingRefError as e:
                    ns.status = "FAILED"
                    ns.error = {"type": "missing_ref", "message": str(e)}
                    ns.started_at = ns.ended_at = _iso_now()
                    await _handle_failure(step)
                    return

                if not truthy:
                    ns.status = "SKIPPED"
                    ns.started_at = ns.ended_at = _iso_now()
                    await self._emit(
                        {
                            "type": "step.skipped",
                            "node_id": step.id,
                            "attempt": 0,
                            "duration_ms": 0,
                            "timestamp": _iso_now(),
                        }
                    )
                    return

            # Check upstream FAILED (for on_failure=continue path)
            upstream_failed: str | None = None
            for up in step.upstream_ids:
                up_src = output_for_ref.get(up, up)
                if node_states[up_src].status == "FAILED":
                    upstream_failed = up
                    break
            if upstream_failed is not None:
                ns.status = "FAILED"
                ns.error = {
                    "type": "upstream_failed",
                    "message": f"upstream {upstream_failed!r} failed",
                }
                ns.started_at = ns.ended_at = _iso_now()
                await self._emit(
                    {
                        "type": "step.failed",
                        "node_id": step.id,
                        "attempt": 1,
                        "duration_ms": 0,
                        "error_class": "upstream_failed",
                        "error_message": ns.error["message"],
                        "timestamp": _iso_now(),
                    }
                )
                await _handle_failure(step)
                return

            # Resolve inputs
            try:
                resolved_inputs = evaluate(step.inputs, _state_dict_for_eval())
            except SkippedRefError as e:
                ns.status = "FAILED"
                ns.error = {"type": "skipped_ref", "message": str(e)}
                ns.started_at = ns.ended_at = _iso_now()
                await self._emit(
                    {
                        "type": "step.failed",
                        "node_id": step.id,
                        "attempt": 1,
                        "duration_ms": 0,
                        "error_class": "skipped_ref",
                        "error_message": str(e),
                        "timestamp": _iso_now(),
                    }
                )
                await _handle_failure(step)
                return
            except MissingRefError as e:
                ns.status = "FAILED"
                ns.error = {"type": "missing_ref", "message": str(e)}
                ns.started_at = ns.ended_at = _iso_now()
                await _handle_failure(step)
                return

            # Acquire semaphores
            group = step.concurrency_group
            group_sem = group_sems.get(group) if group else None

            async with global_sem:
                if group_sem is not None:
                    await group_sem.acquire()
                try:
                    ns.status = "RUNNING"
                    ns.attempt = 1
                    ns.started_at = _iso_now()
                    t0 = monotonic()
                    await self._emit(
                        {
                            "type": "step.started",
                            "node_id": step.id,
                            "attempt": 1,
                            "duration_ms": None,
                            "timestamp": ns.started_at,
                        }
                    )
                    try:
                        runner = self._runners.get(step.agent, step.agent_version)
                        output = await runner.run(
                            resolved_inputs,
                            context={
                                "step_id": step.id,
                                "attempt": 1,
                            },
                        )
                    except Exception as e:
                        ns.status = "FAILED"
                        ns.ended_at = _iso_now()
                        duration_ms = (monotonic() - t0) * 1000.0
                        ns.error = {
                            "type": type(e).__name__,
                            "message": str(e),
                        }
                        await self._emit(
                            {
                                "type": "step.failed",
                                "node_id": step.id,
                                "attempt": 1,
                                "duration_ms": duration_ms,
                                "error_class": type(e).__name__,
                                "error_message": str(e),
                                "timestamp": ns.ended_at,
                            }
                        )
                        await _handle_failure(step)
                        return
                    ns.status = "SUCCESS"
                    ns.output = output
                    ns.ended_at = _iso_now()
                    duration_ms = (monotonic() - t0) * 1000.0
                    await self._emit(
                        {
                            "type": "step.completed",
                            "node_id": step.id,
                            "attempt": 1,
                            "duration_ms": duration_ms,
                            "timestamp": ns.ended_at,
                        }
                    )
                finally:
                    if group_sem is not None:
                        group_sem.release()

        async def _handle_failure(step: CompiledStep) -> None:
            """Apply on_failure policy. Called while the node is still 'running'
            in bookkeeping (caller will _finalize_node after)."""
            nonlocal fail_fast_triggered, run_error
            policy = step.on_failure
            if policy == "continue":
                # Run keeps going; downstream refs to this node will trigger
                # upstream_failed on those downstream steps.
                return
            if policy == "fallback" and step.fallback_step_id:
                fb_id = step.fallback_step_id
                fb_step = compiled.steps[fb_id]
                # Schedule the fallback synchronously here (already under the
                # primary's global semaphore slot). Re-use _execute_fallback.
                await _execute_fallback(step, fb_step)
                return
            # policy == "fail" (or missing fallback id — compiler should reject)
            if run_error is None:
                run_error = {
                    "type": "step_failed",
                    "node_id": step.id,
                    "message": node_states[step.id].error.get("message") if node_states[step.id].error else "",
                }
            fail_fast_triggered = True

        async def _execute_fallback(primary: CompiledStep, fb: CompiledStep) -> None:
            """Run a fallback step; its output replaces primary's for ref resolution."""
            nonlocal fail_fast_triggered, run_error
            fb_ns = node_states[fb.id]
            # Fallback shares the primary's already-acquired global slot but
            # still honors its own concurrency_group.
            group = fb.concurrency_group
            group_sem = group_sems.get(group) if group else None
            try:
                if group_sem is not None:
                    await group_sem.acquire()
                # Resolve fb inputs
                try:
                    resolved_inputs = evaluate(fb.inputs, _state_dict_for_eval())
                except (SkippedRefError, MissingRefError) as e:
                    fb_ns.status = "FAILED"
                    fb_ns.error = {"type": "missing_ref", "message": str(e)}
                    fb_ns.started_at = fb_ns.ended_at = _iso_now()
                    # Treat as primary-level fail
                    if run_error is None:
                        run_error = {
                            "type": "step_failed",
                            "node_id": primary.id,
                            "message": "fallback failed to resolve inputs",
                        }
                    fail_fast_triggered = True
                    return
                fb_ns.status = "RUNNING"
                fb_ns.attempt = 1
                fb_ns.started_at = _iso_now()
                t0 = monotonic()
                await self._emit(
                    {
                        "type": "step.started",
                        "node_id": fb.id,
                        "attempt": 1,
                        "duration_ms": None,
                        "timestamp": fb_ns.started_at,
                    }
                )
                try:
                    runner = self._runners.get(fb.agent, fb.agent_version)
                    output = await runner.run(
                        resolved_inputs,
                        context={"step_id": fb.id, "attempt": 1},
                    )
                except Exception as e:
                    fb_ns.status = "FAILED"
                    fb_ns.ended_at = _iso_now()
                    duration_ms = (monotonic() - t0) * 1000.0
                    fb_ns.error = {"type": type(e).__name__, "message": str(e)}
                    await self._emit(
                        {
                            "type": "step.failed",
                            "node_id": fb.id,
                            "attempt": 1,
                            "duration_ms": duration_ms,
                            "error_class": type(e).__name__,
                            "error_message": str(e),
                            "timestamp": fb_ns.ended_at,
                        }
                    )
                    if run_error is None:
                        run_error = {
                            "type": "step_failed",
                            "node_id": primary.id,
                            "message": f"fallback {fb.id} failed: {e}",
                        }
                    fail_fast_triggered = True
                    return
                fb_ns.status = "SUCCESS"
                fb_ns.output = output
                fb_ns.ended_at = _iso_now()
                duration_ms = (monotonic() - t0) * 1000.0
                await self._emit(
                    {
                        "type": "step.completed",
                        "node_id": fb.id,
                        "attempt": 1,
                        "duration_ms": duration_ms,
                        "timestamp": fb_ns.ended_at,
                    }
                )
                # Re-point primary's output source to fallback
                output_for_ref[primary.id] = fb.id
                # Also mark primary as "SUCCESS-alias" for downstream ref purposes
                # We keep node_states[primary].status = FAILED (authoritative),
                # but evaluator uses output_for_ref remapping.
                # Hack: override the nodes_view for primary to SUCCESS/output of fb.
                # Done by using output_for_ref above.
                # Mark primary as if scheduling already occurred so its FAILED
                # status won't cause downstream upstream_failed triggers:
                # we check output_for_ref remapped node's status.
            finally:
                if group_sem is not None:
                    group_sem.release()

        # Main scheduling loop
        async def _launcher() -> None:
            while True:
                # Clean up finished tasks
                done_ids = [sid for sid, t in tasks.items() if t.done()]
                for sid in done_ids:
                    t = tasks.pop(sid)
                    exc = t.exception()
                    if exc is not None:
                        logger.exception("task for %s crashed", sid, exc_info=exc)

                # Schedule more ready nodes
                _sort_queue()
                while queue:
                    item = queue.pop(0)
                    sid = item.step_id
                    if sid in scheduled or sid in running:
                        continue
                    step = compiled.steps[sid]
                    scheduled.add(sid)
                    running.add(sid)
                    tasks[sid] = asyncio.create_task(_run_step(step))

                if not tasks and not queue:
                    return

                # Wait for at least one task to complete
                if tasks:
                    await asyncio.wait(
                        tasks.values(), return_when=asyncio.FIRST_COMPLETED
                    )

        await _launcher()

        # Any node still PENDING becomes CANCELLED (fail-fast left them behind)
        for sid, ns in node_states.items():
            if ns.status == "PENDING":
                ns.status = "CANCELLED"

        if fail_fast_triggered or any(
            ns.status == "FAILED" and compiled.steps[sid].on_failure == "fail"
            for sid, ns in node_states.items()
        ):
            status = "FAILED"
        else:
            status = "SUCCEEDED"

        # But if all FAILED nodes were under on_failure=continue or replaced by
        # successful fallback (output_for_ref remapped), we're SUCCEEDED.
        if status == "FAILED" and run_error is None:
            # There's a FAILED node whose policy is 'fail' — but maybe it's the
            # primary of a successful fallback; in that case the fallback's
            # output is live and we shouldn't fail the run.
            failed_primary_no_fallback = False
            for sid, ns in node_states.items():
                if ns.status != "FAILED":
                    continue
                step = compiled.steps[sid]
                if step.on_failure == "continue":
                    continue
                if step.on_failure == "fallback":
                    fb_id = step.fallback_step_id
                    if fb_id and node_states[fb_id].status == "SUCCESS":
                        continue
                failed_primary_no_fallback = True
                break
            if not failed_primary_no_fallback:
                status = "SUCCEEDED"

        await self._emit(
            {
                "type": "run.completed" if status == "SUCCEEDED" else "run.failed",
                "status": status,
                "timestamp": _iso_now(),
            }
        )

        return RunResult(status=status, node_states=node_states, error=run_error)
