"""Cache-on-first-read per diagnostic run."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from src.agents.cluster_client.base import QueryResult


class DiagnosticCache:
    """Per-diagnostic in-memory cache. Retried nodes see identical data."""

    def __init__(self, diagnostic_id: str):
        self.diagnostic_id = diagnostic_id
        self._cache: dict[str, QueryResult] = {}

    def _make_key(self, method: str, params: dict) -> str:
        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return f"{method}:{params_hash}"

    async def get_or_fetch(
        self,
        method: str,
        params: dict,
        fetcher: Callable[[], Awaitable[QueryResult]],
        force_fresh: bool = False,
    ) -> QueryResult:
        key = self._make_key(method, params)
        if not force_fresh and key in self._cache:
            return self._cache[key]
        result = await fetcher()
        self._cache[key] = result
        return result

    def clear(self) -> None:
        self._cache.clear()
