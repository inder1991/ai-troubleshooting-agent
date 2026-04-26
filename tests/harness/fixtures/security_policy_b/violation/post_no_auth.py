"""Q13.B violation — POST handler without auth dependency.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/api/v4/incidents")
async def create_incident(payload: dict) -> dict:
    return {"ok": True}
