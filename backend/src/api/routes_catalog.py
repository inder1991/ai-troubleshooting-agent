"""Agent catalog REST endpoints — read-only, flag-gated.

Phase 1 Task 8. All endpoints 404 unless ``CATALOG_UI_ENABLED`` is true,
so OFF-by-default deploys expose nothing to probers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from typing import Any

from backend.src import config
from backend.src.contracts.models import AgentContract, CostHint
from backend.src.contracts.service import get_registry

router = APIRouter(prefix="/api/v4/catalog", tags=["catalog"])


def require_flag() -> None:
    # Re-read settings on every request so env-driven flips (tests,
    # hot-reload) take effect without restarting.
    if not config.settings.CATALOG_UI_ENABLED:
        raise HTTPException(status_code=404)


class AgentSummary(BaseModel):
    name: str
    version: int
    description: str
    category: str
    tags: list[str]
    cost_hint: CostHint | None = None


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]


class AgentDetail(AgentSummary):
    deprecated_versions: list[int]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    trigger_examples: list[str]
    timeout_seconds: float
    retry_on: list[str]


def _to_summary(c: AgentContract) -> AgentSummary:
    return AgentSummary(
        name=c.name,
        version=c.version,
        description=c.description,
        category=c.category,
        tags=c.tags,
        cost_hint=c.cost_hint,
    )


def _to_detail(c: AgentContract) -> AgentDetail:
    return AgentDetail(
        name=c.name,
        version=c.version,
        description=c.description,
        category=c.category,
        tags=c.tags,
        cost_hint=c.cost_hint,
        deprecated_versions=c.deprecated_versions,
        input_schema=c.input_schema,
        output_schema=c.output_schema,
        trigger_examples=c.trigger_examples,
        timeout_seconds=c.timeout_seconds,
        retry_on=c.retry_on,
    )


@router.get(
    "/agents",
    response_model=AgentListResponse,
    dependencies=[Depends(require_flag)],
)
def list_agents() -> AgentListResponse:
    reg = get_registry()
    return AgentListResponse(agents=[_to_summary(c) for c in reg.list()])


@router.get(
    "/agents/{name}",
    response_model=AgentDetail,
    dependencies=[Depends(require_flag)],
)
def get_agent_latest(name: str) -> AgentDetail:
    reg = get_registry()
    # Latest version for name.
    candidates = [c for c in reg.list_all_versions() if c.name == name]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"agent '{name}' not found")
    latest = max(candidates, key=lambda c: c.version)
    return _to_detail(latest)


@router.get(
    "/agents/{name}/v/{version}",
    response_model=AgentDetail,
    dependencies=[Depends(require_flag)],
)
def get_agent_version(name: str, version: int) -> AgentDetail:
    reg = get_registry()
    try:
        c = reg.get(name, version=version)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"agent '{name}' v{version} not found"
        )
    return _to_detail(c)
