"""Kubernetes-canonical health endpoints — `/healthz` and `/readyz`.

Why these exist alongside the older `/health` family:

  - The legacy `/health`, `/health/ready`, `/health/live` endpoints in
    ``main.py`` still check the **SQLite** path that the codebase used pre-
    Phase-1. They no longer reflect the actual durable store (Postgres) or
    the event bus (Redis), so they always answer "healthy" even when those
    are down.
  - Rewriting them risks breaking external monitors that already poll the
    legacy paths, so this module ships parallel `/healthz` + `/readyz`
    endpoints with the conventional Kubernetes naming, and it's these the
    Helm chart's liveness/readiness probes target.

Semantics:

  - `/healthz` — **liveness**. Returns 200 if the process is alive enough
    to handle HTTP. Does NOT touch external dependencies — a transient
    Postgres blip should NOT trigger a pod restart loop.
  - `/readyz` — **readiness**. Pings Postgres + Redis with short timeouts.
    Returns 503 if either is unreachable, so the pod is removed from
    Service endpoints (load-shed) until the dependency recovers, but the
    pod itself isn't killed.

Both endpoints are exempt from API-key auth (see ``EXEMPT_PATHS`` in
``auth.py``).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Probe budgets — kept tight so a slow dep doesn't cascade into a slow probe
# loop. Kubernetes default probe timeoutSeconds is 1s; we leave headroom.
_PROBE_TIMEOUT_S = float(os.environ.get("HEALTH_PROBE_TIMEOUT_S", "0.8"))


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness — process is alive and serving HTTP. No external deps."""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    """Readiness — Postgres + Redis reachable.

    Returns 200 with per-check status when both pass, 503 when either fails.
    Each check is bounded by ``HEALTH_PROBE_TIMEOUT_S`` so a stalled
    dependency can't wedge the probe.
    """
    checks: dict[str, str] = {}

    checks["postgres"] = await _check(_check_postgres)
    checks["redis"] = await _check(_check_redis)

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"ready": all_ok, "checks": checks},
    )


# ─── Internal helpers ────────────────────────────────────────────────────────


async def _check(probe: Any) -> str:
    """Run a probe with a timeout; return 'ok' or 'error: <reason>'."""
    try:
        await asyncio.wait_for(probe(), timeout=_PROBE_TIMEOUT_S)
        return "ok"
    except asyncio.TimeoutError:
        return f"error: timeout after {_PROBE_TIMEOUT_S}s"
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"


async def _check_postgres() -> None:
    """`SELECT 1` against the configured async engine."""
    # Lazy import: keeps health.py importable in unit tests that don't
    # configure a database (the probe just fails with the expected error).
    from sqlalchemy import text

    from src.database.engine import get_session

    async with get_session() as session:
        await session.execute(text("SELECT 1"))


async def _check_redis() -> None:
    """`PING` against the configured Redis client."""
    import redis.asyncio as redis_async

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis_async.from_url(url, socket_timeout=_PROBE_TIMEOUT_S)
    try:
        pong = await client.ping()
        if not pong:
            raise RuntimeError("PING returned falsy")
    finally:
        await client.aclose()
