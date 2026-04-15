"""Workflow save-path REST endpoints — flag-gated.

Phase 2 Task 8. All endpoints 404 when ``WORKFLOWS_ENABLED`` is false so
OFF-by-default deploys expose nothing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from src import config
from src.workflows.compiler import CompileError
from src.workflows.service import WorkflowService

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
