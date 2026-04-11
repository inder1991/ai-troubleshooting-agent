from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Minimal async TTL cache. Single-flight safety via per-key lock."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[K, tuple[float, V]] = {}
        self._locks: dict[K, asyncio.Lock] = {}

    async def get_or_set(self, key: K, loader: Callable[[], Awaitable[V]]) -> V:
        now = time.monotonic()
        entry = self._store.get(key)
        if entry is not None and (now - entry[0]) < self._ttl:
            return entry[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._store.get(key)
            now = time.monotonic()
            if entry is not None and (now - entry[0]) < self._ttl:
                return entry[1]
            value = await loader()
            self._store[key] = (time.monotonic(), value)
            return value
