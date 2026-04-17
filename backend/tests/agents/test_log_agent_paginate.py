"""K.7 — ElasticsearchClient.paginate_all adopts paginate_search."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.log_agent import ElasticsearchClient


class _FakeClient(ElasticsearchClient):
    """Override network calls with in-memory pagination state."""

    def __init__(self, total_hits: int):
        super().__init__(url="http://unused")
        self._total = total_hits
        self.open_pits = 0
        self._pit_counter = 0

    async def open_pit(self, *, index: str, keep_alive: str = "1m") -> dict:
        self._pit_counter += 1
        self.open_pits += 1
        return {"id": f"pit-{self._pit_counter}"}

    async def close_pit(self, *, pit_id: str) -> None:
        self.open_pits = max(0, self.open_pits - 1)

    async def search(self, index: str, body: dict, timeout: int = 30) -> dict:
        sa = body.get("search_after")
        start = (sa[0] + 1) if sa is not None else 0
        end = start + body["size"]
        hits = [
            {"_id": f"h-{i}", "sort": [i, i]}
            for i in range(start, min(end, self._total))
        ]
        return {"hits": {"hits": hits}, "pit_id": body["pit"]["id"]}


class TestPaginateAll:
    @pytest.mark.asyncio
    async def test_yields_every_hit_up_to_max_total(self):
        client = _FakeClient(total_hits=12_000)
        collected = []
        async for hit in client.paginate_all(
            {"match_all": {}}, index="logs-*", page_size=5000, max_total=12_000
        ):
            collected.append(hit)
        assert len(collected) == 12_000
        assert client.open_pits == 0  # PIT closed in finally

    @pytest.mark.asyncio
    async def test_max_total_caps_output(self):
        client = _FakeClient(total_hits=12_000)
        count = 0
        async for _ in client.paginate_all(
            {"match_all": {}}, page_size=5000, max_total=7500
        ):
            count += 1
        assert count == 7500
        assert client.open_pits == 0

    @pytest.mark.asyncio
    async def test_empty_dataset_opens_and_closes_pit_cleanly(self):
        client = _FakeClient(total_hits=0)
        collected = [h async for h in client.paginate_all({"match_all": {}})]
        assert collected == []
        assert client.open_pits == 0


class TestPitLifecycle:
    @pytest.mark.asyncio
    async def test_pit_cleaned_up_on_mid_pagination_error(self):
        client = _FakeClient(total_hits=1000)

        original = client.search
        call_count = {"n": 0}

        async def _flaky_search(index, body, timeout=30):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated mid-pagination failure")
            return await original(index, body, timeout)

        with patch.object(client, "search", _flaky_search):
            with pytest.raises(RuntimeError):
                async for _ in client.paginate_all(
                    {"match_all": {}}, page_size=100
                ):
                    pass

        assert client.open_pits == 0
