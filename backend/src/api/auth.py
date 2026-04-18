"""API key authentication middleware.

When the ``API_KEYS`` environment variable is set (comma-separated list of
valid keys), every request must carry a valid ``X-API-Key`` header.  A small
set of paths (health checks, docs, metrics) are always exempt.

When ``API_KEYS`` is **not** set the middleware is a no-op so that local
development stays frictionless.
"""
from __future__ import annotations

import os
from typing import Set

from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Paths that never require authentication
EXEMPT_PATHS: Set[str] = {
    "/health",
    "/health/ready",
    "/health/live",
    "/healthz",  # k8s-canonical liveness (see src/api/health.py)
    "/readyz",   # k8s-canonical readiness (see src/api/health.py)
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_valid_keys() -> set[str] | None:
    """Return the set of valid API keys or *None* if auth is disabled."""
    raw = os.environ.get("API_KEYS", "").strip()
    if not raw:
        return None
    return {k.strip() for k in raw.split(",") if k.strip()}


async def verify_api_key(request: Request, api_key: str | None = Depends(_api_key_header)):
    """FastAPI dependency that enforces API key auth when enabled."""
    valid_keys = _get_valid_keys()
    if valid_keys is None:
        # Auth disabled (dev mode)
        return

    # Exempt certain paths
    if request.url.path in EXEMPT_PATHS:
        return

    if not api_key or api_key not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware alternative for API key validation.

    This is used when ``API_KEYS`` is set so that *every* request is
    intercepted regardless of router structure.
    """

    async def dispatch(self, request: Request, call_next):
        valid_keys = _get_valid_keys()

        # Auth disabled — passthrough
        if valid_keys is None:
            return await call_next(request)

        # Exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key not in valid_keys:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
