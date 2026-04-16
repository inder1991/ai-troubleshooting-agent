"""Workflow save-path + run-path service.

Extends Task-8 save-path with Task 16-18 run lifecycle: create_run schedules
the executor, wires persistence via the emitter, exposes a per-run live
event queue (for SSE), and a per-run cancel event.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import jsonschema

from src.contracts.registry import ContractRegistry
from src.workflows.compiler import CompiledStep, CompiledWorkflow, compile_dag
from src.workflows.executor import WorkflowExecutor
from src.workflows.models import WorkflowDag
from src.workflows.repository import WorkflowRepository
from src.workflows.runners.registry import AgentRunnerRegistry


logger = logging.getLogger(__name__)


class InputsInvalid(ValueError):
    """Raised when run inputs violate the workflow version's inputs_schema."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rehydrate_compiled(compiled_dict: dict[str, Any]) -> CompiledWorkflow:
    steps_raw = compiled_dict["steps"]
    steps: dict[str, CompiledStep] = {}
    for sid, s in steps_raw.items():
        steps[sid] = CompiledStep(
            id=s["id"],
            agent=s["agent"],
            agent_version=s["agent_version"],
            inputs=s["inputs"],
            when=s.get("when"),
            on_failure=s.get("on_failure", "fail"),
            fallback_step_id=s.get("fallback_step_id"),
            parallel_group=s.get("parallel_group"),
            concurrency_group=s.get("concurrency_group"),
            timeout_seconds=float(s["timeout_seconds"]),
            retry_on=list(s.get("retry_on", [])),
            upstream_ids=list(s.get("upstream_ids", [])),
        )
    return CompiledWorkflow(
        topo_order=list(compiled_dict["topo_order"]),
        steps=steps,
        inputs_schema=compiled_dict.get("inputs_schema", {}),
    )


_TERMINAL = {"succeeded", "failed", "cancelled"}


class WorkflowService:
    def __init__(
        self,
        repo: WorkflowRepository,
        contracts: ContractRegistry,
        runners: AgentRunnerRegistry | None = None,
        *,
        cancel_grace_seconds: float = 30.0,
    ) -> None:
        self._repo = repo
        self._contracts = contracts
        self._runners = runners
        self._cancel_grace_seconds = cancel_grace_seconds
        # Per-run live event queues for SSE consumers (in-memory).
        self._run_subscribers: dict[str, list[asyncio.Queue]] = {}
        # Per-run cancel events.
        self._run_cancel_events: dict[str, asyncio.Event] = {}
        # Per-run executor tasks (so we can await completion in tests).
        self._run_tasks: dict[str, asyncio.Task] = {}

    # ---- workflow + version CRUD (Task 8) ----

    async def create_workflow(
        self,
        *,
        name: str,
        description: str | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        wf_id = await self._repo.create_workflow(
            name=name, description=description, created_by=created_by
        )
        row = await self._repo.get_workflow(wf_id)
        assert row is not None
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
        }

    async def list_workflows(self) -> list[dict[str, Any]]:
        rows = await self._repo.list_workflows()
        result: list[dict[str, Any]] = []
        for r in rows:
            wf: dict[str, Any] = {
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "created_at": r["created_at"],
            }
            latest_run = await self._repo.get_latest_run_for_workflow(r["id"])
            if latest_run is not None:
                wf["last_run_status"] = latest_run["status"]
                wf["last_run_at"] = latest_run.get("started_at") or latest_run.get("ended_at")
            result.append(wf)
        return result

    async def get_workflow(self, id: str) -> dict[str, Any] | None:
        row = await self._repo.get_workflow(id)
        if row is None or row.get("deleted_at"):
            return None
        latest = await self._repo.get_latest_version(id)
        latest_summary: dict[str, Any] | None = None
        if latest is not None:
            latest_summary = {
                "version": latest["version"],
                "created_at": latest["created_at"],
            }
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "latest_version": latest_summary,
        }

    async def create_version(
        self, workflow_id: str, dag_dict: dict[str, Any]
    ) -> dict[str, Any]:
        dag = WorkflowDag.model_validate(dag_dict)
        compiled = compile_dag(dag, self._contracts)

        latest = await self._repo.get_latest_version(workflow_id)
        next_version = (latest["version"] + 1) if latest else 1

        version_id = await self._repo.create_version(
            workflow_id,
            next_version,
            dag_json=json.dumps(dag_dict),
            compiled_json=json.dumps(asdict(compiled), default=str),
        )
        row = await self._repo.get_version(workflow_id, next_version)
        assert row is not None
        return {
            "version_id": version_id,
            "version": next_version,
            "created_at": row["created_at"],
            "workflow_id": workflow_id,
        }

    async def list_versions(self, workflow_id: str) -> list[dict[str, Any]]:
        rows = await self._repo.list_versions(workflow_id)
        return [
            {
                "version_id": r["id"],
                "workflow_id": r["workflow_id"],
                "version": r["version"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def get_version(
        self, workflow_id: str, version: int
    ) -> dict[str, Any] | None:
        row = await self._repo.get_version(workflow_id, version)
        if row is None:
            return None
        return {
            "workflow_id": row["workflow_id"],
            "version": row["version"],
            "dag": json.loads(row["dag_json"]),
            "compiled": json.loads(row["compiled_json"]),
            "created_at": row["created_at"],
        }

    # ---- delete / update / duplicate / rollback (Phase 6) ----

    async def delete_workflow(self, workflow_id: str) -> bool:
        wf = await self._repo.get_workflow(workflow_id)
        if wf is None:
            return False
        if wf.get("deleted_at"):
            return True  # already deleted, idempotent
        if await self._repo.has_active_runs(workflow_id):
            raise ActiveRunsError("workflow has active runs")
        await self._repo.soft_delete_workflow(workflow_id)
        return True

    async def update_workflow(
        self,
        workflow_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any] | None:
        wf = await self.get_workflow(workflow_id)
        if wf is None:
            return None
        await self._repo.update_workflow(workflow_id, name=name, description=description)
        return await self.get_workflow(workflow_id)

    async def duplicate_workflow(self, workflow_id: str) -> dict[str, Any]:
        wf = await self._repo.get_workflow(workflow_id)
        if wf is None:
            raise LookupError("workflow not found")
        base_name = wf["name"]
        new_name = f"{base_name} (copy)"
        existing = await self._repo.list_workflows()
        names = {w["name"] for w in existing}
        suffix = 1
        while new_name in names:
            suffix += 1
            new_name = f"{base_name} (copy {suffix})"
        new_id = await self._repo.duplicate_workflow(workflow_id, new_name)
        return await self.get_workflow(new_id)

    async def rollback_version(
        self, workflow_id: str, target_version: int
    ) -> dict[str, Any]:
        v_id, v_num = await self._repo.rollback_version(workflow_id, target_version)
        return {"version_id": v_id, "version": v_num, "workflow_id": workflow_id}

    # ---- run listing / rerun (Phase 6) ----

    async def list_runs(
        self,
        *,
        workflow_id: str | None = None,
        statuses: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        sort: str = "started_at",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows, total = await self._repo.list_runs(
            workflow_id=workflow_id,
            statuses=statuses,
            from_date=from_date,
            to_date=to_date,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
        return {
            "runs": [self._run_summary(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def rerun(self, run_id: str) -> dict[str, Any]:
        """Create a new run using the same version and inputs as an existing run."""
        row = await self._repo.get_run(run_id)
        if row is None:
            raise LookupError("run not found")
        workflow_version_id = row["workflow_version_id"]
        inputs_json = row["inputs_json"]
        new_run_id = await self._repo.create_run(
            workflow_version_id=workflow_version_id,
            inputs_json=inputs_json,
        )
        return {
            "run_id": new_run_id,
            "workflow_version_id": workflow_version_id,
            "inputs": json.loads(inputs_json),
        }

    async def get_rerun_data(self, run_id: str) -> dict[str, Any]:
        """Return rerun data for the 'rerun with changes' flow (pre-fill form)."""
        row = await self._repo.get_run(run_id)
        if row is None:
            raise LookupError("run not found")
        return {
            "workflow_version_id": row["workflow_version_id"],
            "inputs": json.loads(row["inputs_json"]),
        }

    # ---- run path (Task 16-18) ----

    def _run_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "id": row["id"],
            "workflow_version_id": row["workflow_version_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "idempotency_key": row.get("idempotency_key"),
            "run_mode": row.get("run_mode", "workflow"),
            "inputs": json.loads(row["inputs_json"]) if row.get("inputs_json") else None,
            "error": json.loads(row["error_json"]) if row.get("error_json") else None,
        }
        # Include workflow_id when available (joined from workflow_versions).
        if "workflow_id" in row:
            summary["workflow_id"] = row["workflow_id"]
        return summary

    def _step_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "step_id": row["step_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "attempt": row["attempt"],
            "duration_ms": row["duration_ms"],
            "output": json.loads(row["output_json"]) if row.get("output_json") else None,
            "error": json.loads(row["error_json"]) if row.get("error_json") else None,
        }

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = await self._repo.get_run(run_id)
        if row is None:
            return None
        step_rows = await self._repo.list_step_runs(run_id)
        return {
            "run": self._run_summary(row),
            "step_runs": [self._step_summary(s) for s in step_rows],
        }

    def get_live_queue(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._run_subscribers.setdefault(run_id, []).append(q)
        return q

    def drop_live_queue(self, run_id: str, q: asyncio.Queue) -> None:
        subs = self._run_subscribers.get(run_id)
        if not subs:
            return
        try:
            subs.remove(q)
        except ValueError:
            pass
        if not subs:
            self._run_subscribers.pop(run_id, None)

    def get_cancel_event(self, run_id: str) -> asyncio.Event | None:
        return self._run_cancel_events.get(run_id)

    async def cancel_run(self, run_id: str) -> dict[str, Any] | None:
        """Returns run summary after marking CANCELLING, or None if run not
        found. Raises ``RunTerminal`` if already terminal."""
        row = await self._repo.get_run(run_id)
        if row is None:
            return None
        status = row["status"]
        if status in _TERMINAL:
            raise RunTerminal(status)
        ev = self._run_cancel_events.get(run_id)
        if ev is not None:
            ev.set()
        await self._repo.update_run_status(run_id, "cancelling")
        row = await self._repo.get_run(run_id)
        assert row is not None
        return self._run_summary(row)

    async def create_run(
        self,
        workflow_id: str,
        inputs: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if self._runners is None:
            raise RuntimeError("WorkflowService: runners registry not configured")

        wf = await self._repo.get_workflow(workflow_id)
        if wf is None:
            raise LookupError("workflow not found")
        latest = await self._repo.get_latest_version(workflow_id)
        if latest is None:
            raise LookupError("no active version")

        compiled_dict = json.loads(latest["compiled_json"])
        inputs_schema = compiled_dict.get("inputs_schema") or {}
        try:
            jsonschema.validate(inputs, inputs_schema)
        except jsonschema.ValidationError as e:
            raise InputsInvalid(
                str(e.message),
                errors=[{"path": list(e.absolute_path), "message": e.message}],
            )

        # Repo enforces (workflow_version_id, idempotency_key) uniqueness.
        existing_id: str | None = None
        if idempotency_key is not None:
            existing = await self._find_run_by_key(
                workflow_version_id=latest["id"], key=idempotency_key
            )
            existing_id = existing["id"] if existing else None

        run_id = await self._repo.create_run(
            workflow_version_id=latest["id"],
            inputs_json=json.dumps(inputs),
            idempotency_key=idempotency_key,
        )

        if existing_id is not None and existing_id == run_id:
            # Idempotent replay — return existing without spawning executor.
            row = await self._repo.get_run(run_id)
            assert row is not None
            return self._run_summary(row)

        compiled = _rehydrate_compiled(compiled_dict)
        cancel_event = asyncio.Event()
        self._run_cancel_events[run_id] = cancel_event

        step_run_ids: dict[tuple[str, int], str] = {}

        async def emitter(ev: dict[str, Any]) -> None:
            etype = ev.get("type", "")
            node_id = ev.get("node_id")
            attempt = ev.get("attempt")
            duration_ms_raw = ev.get("duration_ms")
            duration_ms = (
                int(duration_ms_raw) if isinstance(duration_ms_raw, (int, float)) else None
            )
            error_class = ev.get("error_class")
            error_message = ev.get("error_message")
            payload = {k: v for k, v in ev.items() if k not in (
                "type", "node_id", "attempt", "duration_ms",
                "error_class", "error_message",
            )}
            try:
                _event_id, sequence = await self._repo.append_event(
                    run_id,
                    type=etype,
                    node_id=node_id,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error_class=error_class,
                    error_message=error_message,
                    payload_json=json.dumps(payload, default=str) if payload else None,
                )
            except Exception:
                logger.exception("append_event failed for %s %s", run_id, etype)
                sequence = None  # type: ignore[assignment]

            # Persist step_run lifecycle rows.
            try:
                if etype == "step.started" and node_id is not None and attempt is not None:
                    if (node_id, attempt) not in step_run_ids:
                        sr_id = await self._repo.create_step_run(run_id, node_id, attempt)
                        step_run_ids[(node_id, attempt)] = sr_id
                elif etype in ("step.completed", "step.failed") and node_id is not None:
                    key = (node_id, attempt if attempt is not None else 1)
                    sr_id = step_run_ids.get(key)
                    if sr_id is not None:
                        status = "success" if etype == "step.completed" else "failed"
                        err_json = None
                        if etype == "step.failed":
                            err_json = json.dumps(
                                {"type": error_class, "message": error_message}
                            )
                        await self._repo.update_step_run(
                            sr_id,
                            status=status,
                            ended_at=ev.get("timestamp") or _now(),
                            duration_ms=duration_ms,
                            error_json=err_json,
                        )
                elif etype == "step.skipped" and node_id is not None:
                    sr_id = await self._repo.create_step_run(run_id, node_id, 0)
                    await self._repo.update_step_run(
                        sr_id, status="skipped", ended_at=ev.get("timestamp") or _now()
                    )
                elif etype == "run.started":
                    await self._repo.update_run_status(run_id, "running")
            except Exception:
                logger.exception("step_run persistence failed for %s %s", run_id, etype)

            # Fan-out to live subscribers with sequence attached.
            live_ev = dict(ev)
            if sequence is not None:
                live_ev["sequence"] = sequence
            for q in list(self._run_subscribers.get(run_id, [])):
                try:
                    q.put_nowait(live_ev)
                except asyncio.QueueFull:
                    pass

        async def _driver() -> None:
            executor = WorkflowExecutor(
                runners=self._runners,
                event_emitter=emitter,
                cancel_grace_seconds=self._cancel_grace_seconds,
            )
            final_status = "failed"
            err_json: str | None = None
            try:
                result = await executor.run(
                    compiled,
                    inputs=inputs,
                    cancel_event=cancel_event,
                    contracts=self._contracts,
                )
                final_status = {
                    "SUCCEEDED": "succeeded",
                    "FAILED": "failed",
                    "CANCELLED": "cancelled",
                }.get(result.status, "failed")
                if result.error is not None:
                    err_json = json.dumps(result.error, default=str)
            except Exception as e:  # noqa: BLE001
                logger.exception("executor driver crashed for %s", run_id)
                err_json = json.dumps({"type": type(e).__name__, "message": str(e)})
                final_status = "failed"
            finally:
                try:
                    await self._repo.update_run_status(
                        run_id,
                        final_status,
                        ended_at=_now(),
                        error_json=err_json,
                    )
                except Exception:
                    logger.exception("final update_run_status failed for %s", run_id)
                # Signal terminal to any live subscribers then detach.
                sentinel = {"type": "__run_terminal__", "status": final_status}
                for q in list(self._run_subscribers.get(run_id, [])):
                    try:
                        q.put_nowait(sentinel)
                    except asyncio.QueueFull:
                        pass
                # Cleanup maps after a grace tick so last subscribers can drain.
                self._run_cancel_events.pop(run_id, None)

        task = asyncio.create_task(_driver())
        self._run_tasks[run_id] = task

        def _on_done(t: asyncio.Task) -> None:
            self._run_tasks.pop(run_id, None)

        task.add_done_callback(_on_done)

        row = await self._repo.get_run(run_id)
        assert row is not None
        return self._run_summary(row)

    async def _find_run_by_key(
        self, *, workflow_version_id: str, key: str
    ) -> dict[str, Any] | None:
        # No direct repo method; use connection via append pattern — simplest is
        # to use list via sqlite direct. We add a lightweight query here.
        import aiosqlite

        async with aiosqlite.connect(self._repo._db_path) as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM workflow_runs WHERE workflow_version_id = ? "
                "AND idempotency_key = ?",
                (workflow_version_id, key),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None


class ActiveRunsError(Exception):
    """Raised when trying to delete a workflow with active runs."""
    pass


class RunTerminal(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(f"run already terminal: {status}")
        self.status = status
