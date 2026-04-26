"""Q13.B violation — POST handler with auth but no @limiter.limit.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends

router = APIRouter()


def require_user() -> None: ...


@router.post("/api/v4/incidents")
async def create_incident(payload: dict, user=Depends(require_user)) -> dict:
    return {"ok": True}
