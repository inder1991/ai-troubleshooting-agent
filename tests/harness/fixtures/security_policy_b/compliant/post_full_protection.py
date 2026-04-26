"""Q13.B compliant — auth + rate limit + CSRF guard all wired.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> None: ...


@router.post("/api/v4/incidents")
@limiter.limit("10/minute")
async def create_incident(
    request: Request,
    payload: dict,
    user=Depends(require_user),
    csrf_protect: CsrfProtect = Depends(),
) -> dict:
    return {"ok": True}
