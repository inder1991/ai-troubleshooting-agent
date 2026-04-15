"""Agent catalog REST endpoints — read-only, flag-gated.

Phase 1 Task 8. All endpoints 404 unless ``CATALOG_UI_ENABLED`` is true,
so OFF-by-default deploys expose nothing to probers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.src import config
from backend.src.contracts.models import CostHint
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


@router.get(
    "/agents",
    response_model=AgentListResponse,
    dependencies=[Depends(require_flag)],
)
def list_agents() -> AgentListResponse:
    reg = get_registry()
    return AgentListResponse(
        agents=[
            AgentSummary(
                name=c.name,
                version=c.version,
                description=c.description,
                category=c.category,
                tags=c.tags,
                cost_hint=c.cost_hint,
            )
            for c in reg.list()
        ]
    )
