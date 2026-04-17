"""Per-investigation result dedup cache.

An agent that asks the same tool the same question twice in the same
investigation should not pay for it twice. The cache is per-investigation
(lifetime == RunLock) so cross-run leakage is impossible, and bounded in
size so a misconfigured agent that varies one whitespace character can't
OOM the process.

Cache HITs don't count against the budget (``get_or_compute`` returns the
cached value without calling the supplied callable). MISSes call the
callable and store the result.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from typing import Any, Awaitable, Callable


def _canonical_key(tool_name: str, params: dict) -> str:
    """Stable hash of (tool_name, params) regardless of dict insertion order.

    ``sort_keys`` + default-stringifier produces one canonical form; sha256
    because the key length matters (OrderedDict memory) and collisions would
    merge unrelated results.
    """
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(f"{tool_name}|{payload}".encode()).hexdigest()


class ResultCache:
    """LRU-ish dedup cache for tool results within one investigation."""

    def __init__(self, *, max_entries: int = 1000) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._max = max_entries
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        # Per-key locks so two concurrent callers for the same key both
        # get the cached result and we don't run the tool twice just
        # because of a race — but different keys stay parallel.
        self._locks: dict[str, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._master_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def get_or_compute(
        self,
        tool_name: str,
        params: dict,
        compute: Callable[[dict], Awaitable[Any]],
    ) -> Any:
        key = _canonical_key(tool_name, params)
        lock = await self._lock_for(key)
        async with lock:
            if key in self._store:
                self._hits += 1
                self._store.move_to_end(key)
                return self._store[key]
            self._misses += 1
            value = await compute(params)
            self._store[key] = value
            self._store.move_to_end(key)
            if len(self._store) > self._max:
                # Evict the least-recently-used entry.
                evicted_key, _ = self._store.popitem(last=False)
                # Drop the per-key lock too so the dict doesn't grow forever.
                self._locks.pop(evicted_key, None)
            return value

    def snapshot(self) -> dict:
        return {
            "entries": len(self._store),
            "max_entries": self._max,
            "hits": self._hits,
            "misses": self._misses,
        }
