"""Task 3.2 — per-investigation ResultCache."""
from __future__ import annotations

import asyncio

import pytest

from src.tools.result_cache import ResultCache, _canonical_key


class TestBasicCache:
    @pytest.mark.asyncio
    async def test_identical_call_returns_cached_result(self):
        cache = ResultCache()
        calls = []

        async def tool(p):
            calls.append(p)
            return {"r": 1}

        out1 = await cache.get_or_compute("metrics.query", {"q": "foo"}, tool)
        out2 = await cache.get_or_compute("metrics.query", {"q": "foo"}, tool)
        assert out1 == out2 == {"r": 1}
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_different_params_miss(self):
        cache = ResultCache()
        calls = []

        async def tool(p):
            calls.append(p)
            return p["q"]

        await cache.get_or_compute("metrics.query", {"q": "a"}, tool)
        await cache.get_or_compute("metrics.query", {"q": "b"}, tool)
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_different_tool_name_miss(self):
        cache = ResultCache()
        calls = []

        async def tool(p):
            calls.append(p)
            return 1

        await cache.get_or_compute("a.query", {"q": "foo"}, tool)
        await cache.get_or_compute("b.query", {"q": "foo"}, tool)
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_key_canonicalises_dict_ordering(self):
        k1 = _canonical_key("t", {"a": 1, "b": 2})
        k2 = _canonical_key("t", {"b": 2, "a": 1})
        assert k1 == k2


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_same_key_computes_once(self):
        cache = ResultCache()
        call_count = 0

        async def slow_tool(p):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            return {"p": p}

        # Fire 10 concurrent calls with the same key; only 1 should actually
        # invoke the tool — the rest wait on the same lock and read the cache.
        results = await asyncio.gather(*(
            cache.get_or_compute("t", {"q": "same"}, slow_tool) for _ in range(10)
        ))
        assert all(r == {"p": {"q": "same"}} for r in results)
        assert call_count == 1
        assert cache.snapshot()["hits"] == 9
        assert cache.snapshot()["misses"] == 1

    @pytest.mark.asyncio
    async def test_different_keys_run_in_parallel(self):
        cache = ResultCache()
        started_at = {}

        async def tool(p):
            started_at[p["q"]] = asyncio.get_running_loop().time()
            await asyncio.sleep(0.05)
            return p["q"]

        await asyncio.gather(
            cache.get_or_compute("t", {"q": "a"}, tool),
            cache.get_or_compute("t", {"q": "b"}, tool),
            cache.get_or_compute("t", {"q": "c"}, tool),
        )
        times = list(started_at.values())
        # All three should have started within 20 ms → real parallelism
        assert max(times) - min(times) < 0.02


class TestBounds:
    @pytest.mark.asyncio
    async def test_lru_eviction_respects_max_entries(self):
        cache = ResultCache(max_entries=3)

        async def tool(p):
            return p["q"]

        for q in ("a", "b", "c", "d"):
            await cache.get_or_compute("t", {"q": q}, tool)

        # Should hold at most 3 entries, "a" evicted (LRU)
        snap = cache.snapshot()
        assert snap["entries"] == 3

    def test_non_positive_max_entries_rejected(self):
        with pytest.raises(ValueError):
            ResultCache(max_entries=0)


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_reports_hit_miss_counts(self):
        cache = ResultCache()

        async def tool(p):
            return 1

        await cache.get_or_compute("t", {"q": "x"}, tool)
        await cache.get_or_compute("t", {"q": "x"}, tool)
        await cache.get_or_compute("t", {"q": "y"}, tool)
        snap = cache.snapshot()
        assert snap["hits"] == 1
        assert snap["misses"] == 2
        assert snap["entries"] == 2
