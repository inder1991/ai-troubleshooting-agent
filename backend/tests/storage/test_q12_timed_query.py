"""Sprint H.0b Story 5 — @timed_query decorator (Q12 hard gate on DB queries).

Note: separate from any future tests of the existing backend/src/database
ORM. The Q12 _timing.py decorator lives under backend/src/storage/ as the
new Q8 spine path.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_timed_query_passes_under_budget() -> None:
    from src.storage._timing import timed_query

    @timed_query(max_ms=100)
    async def fast_query() -> int:
        await asyncio.sleep(0.001)
        return 42

    assert await fast_query() == 42


@pytest.mark.asyncio
async def test_timed_query_raises_over_budget() -> None:
    from src.storage._timing import timed_query, QueryBudgetExceeded

    @timed_query(max_ms=10)
    async def slow_query() -> int:
        await asyncio.sleep(0.05)  # 50ms > 10ms budget
        return 42

    with pytest.raises(QueryBudgetExceeded):
        await slow_query()
