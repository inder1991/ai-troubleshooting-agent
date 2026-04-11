from __future__ import annotations

import asyncio
import pytest

from src.integrations.cicd.cache import TTLCache


@pytest.mark.asyncio
async def test_ttl_cache_returns_cached_value_within_ttl():
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    async def load():
        calls["n"] += 1
        return 42

    assert await cache.get_or_set("k", load) == 42
    assert await cache.get_or_set("k", load) == 42
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_ttl_cache_reloads_after_ttl_expires(monkeypatch):
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=1)
    now = {"t": 1000.0}
    monkeypatch.setattr("src.integrations.cicd.cache.time.monotonic",
                        lambda: now["t"])
    calls = {"n": 0}

    async def load():
        calls["n"] += 1
        return calls["n"]

    assert await cache.get_or_set("k", load) == 1
    now["t"] += 2.0
    assert await cache.get_or_set("k", load) == 2
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_ttl_cache_isolates_keys():
    cache: TTLCache[str, str] = TTLCache(ttl_seconds=60)

    async def load_a():
        return "A"

    async def load_b():
        return "B"

    assert await cache.get_or_set("a", load_a) == "A"
    assert await cache.get_or_set("b", load_b) == "B"
