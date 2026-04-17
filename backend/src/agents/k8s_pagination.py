"""K8s list pagination — continue-token loop.

The kubernetes Python client's list_* calls paginate via a ``_continue``
token returned in ``metadata.continue``. When we omit the loop we silently
truncate large clusters to ``limit`` items (500 by default).

``list_all`` wraps any list callable — sync or async — and drives the
continue-token loop until the server returns an empty token. No LLM,
just boilerplate.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable


def _extract_continue(result: Any) -> str | None:
    """Read the continue token from a kubernetes-client list response.

    The client returns typed objects with ``.metadata._continue`` or
    ``.metadata.continue_``. Dicts (from raw REST) use the JSON field
    name ``"continue"``. Accept both.
    """
    meta = getattr(result, "metadata", None)
    if meta is not None:
        return getattr(meta, "_continue", None) or getattr(meta, "continue_", None)
    if isinstance(result, dict):
        metadata = result.get("metadata") or {}
        return metadata.get("continue") or metadata.get("_continue")
    return None


def _extract_items(result: Any) -> list[Any]:
    # Dicts have `.items()` too, but it's a different shape — handle them
    # explicitly before the generic branch.
    if isinstance(result, dict):
        return list(result.get("items") or [])
    if hasattr(result, "items"):
        items = result.items
        if callable(items):
            items = items()
        return list(items or [])
    return []


async def list_all(list_fn: Callable[..., Any], *, limit: int = 500, **kwargs) -> list:
    """Invoke ``list_fn`` with ``limit`` + ``_continue`` until fully drained.

    ``list_fn`` may be either an async callable or a sync callable; sync
    calls are run on the default executor so the supervisor's event loop
    isn't blocked while the k8s client's `requests` session does IO.
    """
    out: list = []
    cont: str | None = None
    while True:
        call_kwargs = dict(kwargs)
        call_kwargs["limit"] = limit
        if cont:
            call_kwargs["_continue"] = cont
        result = list_fn(**call_kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        out.extend(_extract_items(result))
        cont = _extract_continue(result)
        if not cont:
            return out
