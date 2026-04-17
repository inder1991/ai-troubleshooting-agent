"""Singleton httpx.AsyncClient per external backend.

Before: each call to `jira.create_issue`/`elk.search`/etc. opened a fresh
``httpx.AsyncClient`` context manager. Under concurrent investigations that
meant dozens of independent connection pools, none reused, all competing
for the same TCP connections.

After: one client per backend, shared across investigations. Per-backend
limits are explicit and auditable. This is also the bulkhead — a flood of
github requests can't drain the elasticsearch pool because they live in
different clients.
"""
from __future__ import annotations

import asyncio
from typing import Final

import httpx


# (max_connections, max_keepalive_connections). Tuned from the plan's
# Task 3.3 table. Keep numbers small-and-explicit; raising them is a diff,
# not a config fishing expedition.
_LIMITS: Final[dict[str, tuple[int, int]]] = {
    "elasticsearch": (50, 20),
    "prometheus": (30, 10),
    "kubernetes": (50, 20),
    "github": (10, 5),
    "jira": (10, 5),
    "confluence": (10, 5),
    "remedy": (5, 2),
}

# Per-backend default timeouts. Individual callers can override via their
# own request kwargs when the endpoint is known-slow (search_after, etc).
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

_clients: dict[str, httpx.AsyncClient] = {}
_lock = asyncio.Lock()


async def _inject_traceparent_hook(request: httpx.Request) -> None:
    """httpx event_hook that stamps ``traceparent`` on every outbound
    request (Stage K.11). A caller-provided header wins; absent header,
    the current context is used or a fresh trace is started.
    """
    try:
        from src.observability.trace_context import (
            TRACEPARENT_HEADER,
            inject_traceparent,
        )
        if TRACEPARENT_HEADER in request.headers:
            return
        merged = inject_traceparent(dict(request.headers))
        if TRACEPARENT_HEADER in merged:
            request.headers[TRACEPARENT_HEADER] = merged[TRACEPARENT_HEADER]
    except Exception:
        # Header injection must never break an outbound call.
        pass


def _build_client(backend: str) -> httpx.AsyncClient:
    if backend not in _LIMITS:
        raise KeyError(
            f"Unknown backend {backend!r}. Add an entry to http_clients._LIMITS "
            f"before calling get_client()."
        )
    max_c, keep = _LIMITS[backend]
    # ``retries=0`` because we own retry policy at the application layer
    # (Task 3.17 — Retry-After handling). Transport-level retries would
    # interact badly with our rate-limit budget.
    transport = httpx.AsyncHTTPTransport(retries=0)
    return httpx.AsyncClient(
        limits=httpx.Limits(max_connections=max_c, max_keepalive_connections=keep),
        timeout=_DEFAULT_TIMEOUT,
        transport=transport,
        # Stage K.11 — stamp traceparent on every request.
        event_hooks={"request": [_inject_traceparent_hook]},
    )


def get_client(backend: str) -> httpx.AsyncClient:
    """Return (creating if necessary) the singleton client for ``backend``.

    Not async — the dict access is fast and the lock is only needed to
    prevent a rare double-init under concurrent first calls. We handle
    that with a double-checked pattern + a module-level asyncio.Lock that
    we don't actually enter here (init is cheap and idempotent; duplicate
    init just wastes an AsyncClient and loses nothing).
    """
    client = _clients.get(backend)
    if client is not None:
        return client
    # Double-check after lock — but we can't hold an asyncio lock from a
    # sync function. Instead: last write wins; if two coroutines race here
    # both build a client, one gets stored, the other is orphaned. That's
    # wasteful once at startup and harmless thereafter.
    new_client = _build_client(backend)
    existing = _clients.setdefault(backend, new_client)
    if existing is not new_client:
        # Another caller beat us to setdefault. Close the one we built to
        # avoid leaking its transport.
        asyncio.get_event_loop().create_task(new_client.aclose())
    return existing


def enumerate_backend_pools() -> dict[str, httpx.AsyncClient]:
    """Introspection helper for tests. Materialises all known backends."""
    for name in _LIMITS:
        get_client(name)
    return dict(_clients)


async def close_all() -> None:
    """Close every open client. Call from the FastAPI shutdown handler."""
    global _clients
    to_close = list(_clients.values())
    _clients = {}
    for c in to_close:
        try:
            await c.aclose()
        except Exception:
            # Closing a client during shutdown is best-effort; log and move on.
            pass


async def reset_for_tests() -> None:
    """Clear the singleton state. Test-only — production uses ``close_all``."""
    await close_all()


def limits_for(backend: str) -> tuple[int, int]:
    """Return (max_connections, max_keepalive_connections) for auditing."""
    return _LIMITS[backend]
