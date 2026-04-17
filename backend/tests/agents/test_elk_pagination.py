"""Task 3.5 — ELK / OpenSearch PIT-based pagination."""
from __future__ import annotations

import pytest

from src.agents.elk_pagination import paginate_search


class FakeES:
    """In-memory stand-in implementing the ESLike protocol."""

    def __init__(self, total_hits: int):
        self._seed(total_hits)
        self.open_pits: int = 0
        self._pit_counter = 0
        self.last_page_size: int | None = None
        self.should_fail_on_page: int | None = None
        self.pages_served: int = 0

    def _seed(self, total: int):
        self._hits = [
            {
                "_id": f"hit-{i}",
                "_source": {"msg": f"msg {i}"},
                "sort": [i, i],  # stable sort tiebreaker
            }
            for i in range(total)
        ]

    async def open_pit(self, *, index: str, keep_alive: str) -> dict:
        self._pit_counter += 1
        self.open_pits += 1
        return {"id": f"pit-{self._pit_counter}"}

    async def close_pit(self, *, pit_id: str) -> None:
        self.open_pits = max(0, self.open_pits - 1)

    async def search(self, *, body: dict) -> dict:
        self.pages_served += 1
        self.last_page_size = body["size"]
        if (
            self.should_fail_on_page is not None
            and self.pages_served == self.should_fail_on_page
        ):
            raise RuntimeError("simulated ES failure mid-pagination")

        sa = body.get("search_after")
        start = (sa[0] + 1) if sa is not None else 0
        end = start + body["size"]
        page = self._hits[start:end]
        return {"hits": {"hits": page}, "pit_id": body["pit"]["id"]}


class TestPagination:
    @pytest.mark.asyncio
    async def test_paginate_through_more_than_one_page(self):
        fake = FakeES(total_hits=12_000)
        out = []
        async for hit in paginate_search(fake, {"match_all": {}}, page_size=5000, max_total=12_000):
            out.append(hit)
        assert len(out) == 12_000

    @pytest.mark.asyncio
    async def test_max_total_enforced(self):
        fake = FakeES(total_hits=12_000)
        out = []
        async for hit in paginate_search(fake, {"match_all": {}}, page_size=5000, max_total=7000):
            out.append(hit)
        assert len(out) == 7000

    @pytest.mark.asyncio
    async def test_smaller_dataset_returns_all(self):
        fake = FakeES(total_hits=42)
        out = [h async for h in paginate_search(fake, {"match_all": {}}, page_size=5000)]
        assert len(out) == 42

    @pytest.mark.asyncio
    async def test_empty_dataset_returns_nothing(self):
        fake = FakeES(total_hits=0)
        out = [h async for h in paginate_search(fake, {"match_all": {}}, page_size=5000)]
        assert out == []


class TestPITLifecycle:
    @pytest.mark.asyncio
    async def test_pit_cleaned_up_on_success(self):
        fake = FakeES(total_hits=100)
        async for _ in paginate_search(fake, {"match_all": {}}, page_size=50):
            pass
        assert fake.open_pits == 0

    @pytest.mark.asyncio
    async def test_pit_cleaned_up_on_failure(self):
        fake = FakeES(total_hits=1000)
        fake.should_fail_on_page = 2
        with pytest.raises(RuntimeError):
            async for _ in paginate_search(fake, {"match_all": {}}, page_size=100):
                pass
        assert fake.open_pits == 0


class TestPageSizeShrink:
    @pytest.mark.asyncio
    async def test_last_page_uses_smaller_size_to_respect_max_total(self):
        fake = FakeES(total_hits=12_000)
        out = []
        async for hit in paginate_search(fake, {"match_all": {}}, page_size=5000, max_total=7500):
            out.append(hit)
        assert len(out) == 7500
        # Last page should have been 2500 (7500 - 5000)
        assert fake.last_page_size == 2500
