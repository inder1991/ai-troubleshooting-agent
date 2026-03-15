"""REST endpoints for network auto-discovery."""

from __future__ import annotations
from fastapi import APIRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v4/discovery", tags=["discovery"])

_discovery_scheduler = None


def init_discovery(discovery_scheduler):
    global _discovery_scheduler
    _discovery_scheduler = discovery_scheduler


@router.get("/results")
async def get_discovery_results():
    if not _discovery_scheduler:
        return {"neighbors": {}, "total_links": 0}
    return _discovery_scheduler.get_results()


@router.get("/candidates")
async def get_discovery_candidates():
    if not _discovery_scheduler:
        return {"candidates": []}
    return {"candidates": _discovery_scheduler.get_candidates()}


@router.post("/run")
async def trigger_discovery():
    if not _discovery_scheduler:
        return {"status": "not_initialized"}
    import asyncio
    asyncio.create_task(_discovery_scheduler._run_discovery())
    return {"status": "discovery_started"}
