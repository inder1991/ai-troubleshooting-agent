"""Synthetic backend API for generator tests."""
from fastapi import APIRouter, Depends, Request

router = APIRouter()


class limiter:
    @staticmethod
    def limit(spec): return lambda fn: fn


def require_user() -> None:
    return None


@router.get("/api/v4/incidents")
async def list_incidents() -> list[dict]:
    return []


@router.post("/api/v4/incidents")
@limiter.limit("10/minute")
async def create_incident(
    request: Request,
    payload: dict,
    user=Depends(require_user),
) -> dict:
    return {"ok": True}
