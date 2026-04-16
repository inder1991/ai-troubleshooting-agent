"""Workflow save-path REST endpoints — flag-gated.

Phase 2 Task 8. All endpoints 404 when ``WORKFLOWS_ENABLED`` is false so
OFF-by-default deploys expose nothing.
"""

from __future__ import annotations

from typing import Any

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from sse_starlette.sse import EventSourceResponse

from src import config
from src.workflows.compiler import CompileError
from src.workflows.service import ActiveRunsError, InputsInvalid, RunTerminal, WorkflowService

router = APIRouter(prefix="/api/v4", tags=["workflows"])

_service: WorkflowService | None = None


def set_workflow_service(svc: WorkflowService) -> None:
    global _service
    _service = svc


def get_workflow_service() -> WorkflowService:
    if _service is None:
        raise RuntimeError("WorkflowService not initialized")
    return _service


def require_flag() -> None:
    if not config.settings.WORKFLOWS_ENABLED:
        raise HTTPException(status_code=404)


class CreateWorkflowBody(BaseModel):
    name: str
    description: str | None = None
    created_by: str | None = None


class UpdateWorkflowBody(BaseModel):
    name: str | None = None
    description: str | None = None


@router.post(
    "/workflows",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def create_workflow(
    body: CreateWorkflowBody,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    return await svc.create_workflow(
        name=body.name,
        description=body.description,
        created_by=body.created_by,
    )


@router.get("/workflows", dependencies=[Depends(require_flag)])
async def list_workflows(
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    return {"workflows": await svc.list_workflows()}


@router.get("/workflows/{workflow_id}", dependencies=[Depends(require_flag)])
async def get_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf


@router.post(
    "/workflows/{workflow_id}/versions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def create_version(
    workflow_id: str,
    request: Request,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    dag_dict = await request.json()
    try:
        return await svc.create_version(workflow_id, dag_dict)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"type": "dag_invalid", "errors": e.errors()},
        )
    except CompileError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "type": "compile_error",
                "message": str(e),
                "path": getattr(e, "path", None),
            },
        )


@router.get(
    "/workflows/{workflow_id}/versions",
    dependencies=[Depends(require_flag)],
)
async def list_versions(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"versions": await svc.list_versions(workflow_id)}


@router.get(
    "/workflows/{workflow_id}/versions/{version}",
    dependencies=[Depends(require_flag)],
)
async def get_version(
    workflow_id: str,
    version: int,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    row = await svc.get_version(workflow_id, version)
    if row is None:
        raise HTTPException(status_code=404, detail="version not found")
    return row


class CreateRunBody(BaseModel):
    inputs: dict[str, Any] = {}
    idempotency_key: str | None = None


@router.post(
    "/workflows/{workflow_id}/runs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def create_run(
    workflow_id: str,
    body: CreateRunBody,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        summary = await svc.create_run(
            workflow_id, body.inputs, body.idempotency_key
        )
    except InputsInvalid as e:
        raise HTTPException(
            status_code=422,
            detail={"type": "inputs_invalid", "errors": e.errors, "message": str(e)},
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run": summary}


@router.get("/runs/{run_id}", dependencies=[Depends(require_flag)])
async def get_run(
    run_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    data = await svc.get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="run not found")
    return data


_TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}


@router.get("/runs/{run_id}/events", dependencies=[Depends(require_flag)])
async def run_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    svc: WorkflowService = Depends(get_workflow_service),
):
    # Validate the run exists up-front so unknown-id returns a proper 404.
    run = await svc.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    try:
        after_seq = int(last_event_id) if last_event_id else 0
    except ValueError:
        after_seq = 0

    async def _stream():
        # Subscribe BEFORE replay so we don't drop events that land during replay.
        queue = svc.get_live_queue(run_id)
        terminal_seen = False
        try:
            # Replay persisted.
            replayed = await svc._repo.list_events(run_id, after_sequence=after_seq)
            max_seq = after_seq
            for ev in replayed:
                payload = {k: ev[k] for k in ev.keys()}
                data = json.dumps(payload, default=str)
                yield {
                    "id": str(ev["sequence"]),
                    "event": ev["type"],
                    "data": data,
                }
                max_seq = ev["sequence"]
                if ev["type"] in ("run.completed", "run.failed", "run.cancelled"):
                    terminal_seen = True

            # If replay already covered a terminal event, we're done.
            if terminal_seen:
                return

            # Check persisted run status — maybe it finished before we subscribed.
            current = await svc._repo.get_run(run_id)
            if current is not None and current["status"] in _TERMINAL_RUN_STATUSES:
                # Drain any late events above max_seq then exit.
                late = await svc._repo.list_events(run_id, after_sequence=max_seq)
                for ev in late:
                    data = json.dumps({k: ev[k] for k in ev.keys()}, default=str)
                    yield {
                        "id": str(ev["sequence"]),
                        "event": ev["type"],
                        "data": data,
                    }
                return

            # Live tail.
            while True:
                if await request.is_disconnected():
                    return
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if ev.get("type") == "__run_terminal__":
                    return
                seq = ev.get("sequence")
                if seq is not None and seq <= max_seq:
                    continue
                if seq is not None:
                    max_seq = seq
                data = json.dumps(ev, default=str)
                yield {
                    "id": str(seq) if seq is not None else "",
                    "event": ev.get("type", "message"),
                    "data": data,
                }
                if ev.get("type") in ("run.completed", "run.failed", "run.cancelled"):
                    return
        except asyncio.CancelledError:
            return
        finally:
            svc.drop_live_queue(run_id, queue)

    return EventSourceResponse(_stream())


@router.post(
    "/runs/{run_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_flag)],
)
async def cancel_run(
    run_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        summary = await svc.cancel_run(run_id)
    except RunTerminal as e:
        raise HTTPException(
            status_code=409,
            detail={"type": "run_terminal", "status": e.status},
        )
    if summary is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run": summary}


@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_flag)],
)
async def delete_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
):
    try:
        result = await svc.delete_workflow(workflow_id)
    except ActiveRunsError:
        raise HTTPException(status_code=409, detail={"type": "active_runs", "message": "workflow has active runs"})
    if not result:
        raise HTTPException(status_code=404, detail="workflow not found")
    return None


@router.patch("/workflows/{workflow_id}", dependencies=[Depends(require_flag)])
async def update_workflow(
    workflow_id: str,
    body: UpdateWorkflowBody,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    result = await svc.update_workflow(workflow_id, name=body.name, description=body.description)
    if result is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return result


@router.post(
    "/workflows/{workflow_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def duplicate_workflow(
    workflow_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.duplicate_workflow(workflow_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/workflows/{workflow_id}/versions/{version}/rollback",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_flag)],
)
async def rollback_version(
    workflow_id: str,
    version: int,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.rollback_version(workflow_id, version)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs", dependencies=[Depends(require_flag)])
async def list_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    workflow_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    statuses = status_filter.split(",") if status_filter else None
    return await svc.list_runs(
        workflow_id=workflow_id, statuses=statuses, from_date=from_date,
        to_date=to_date, sort=sort, order=order, limit=min(limit, 200), offset=offset,
    )


@router.get("/workflows/{workflow_id}/runs", dependencies=[Depends(require_flag)])
async def list_workflow_runs(
    workflow_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    from_date: str | None = None,
    to_date: str | None = None,
    sort: str = "started_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    wf = await svc.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    statuses = status_filter.split(",") if status_filter else None
    return await svc.list_runs(
        workflow_id=workflow_id, statuses=statuses, from_date=from_date,
        to_date=to_date, sort=sort, order=order, limit=min(limit, 200), offset=offset,
    )


@router.post("/runs/{run_id}/rerun", dependencies=[Depends(require_flag)])
async def rerun(
    run_id: str,
    svc: WorkflowService = Depends(get_workflow_service),
) -> dict[str, Any]:
    try:
        return await svc.get_rerun_data(run_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
