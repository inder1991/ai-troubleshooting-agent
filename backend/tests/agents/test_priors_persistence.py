"""Task 2.4 — per-agent priors persist across ConfidenceCalibrator instances."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.agents.confidence_calibrator import (
    DEFAULT_PRIOR,
    ConfidenceCalibrator,
)
from src.database.engine import get_engine, get_session


_TEST_AGENTS = ("test_log_agent", "test_metrics_agent", "test_k8s_agent")


@pytest_asyncio.fixture(autouse=True)
async def _isolate_priors():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge() -> None:
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM agent_priors WHERE agent_name = ANY(:names)"),
                {"names": list(_TEST_AGENTS)},
            )


@pytest.mark.asyncio
async def test_update_prior_persists_and_reloads():
    cal = ConfidenceCalibrator()
    await cal.update_prior("test_k8s_agent", was_correct=True)
    cal2 = ConfidenceCalibrator()  # fresh instance — must re-read from DB
    assert (await cal2.get_prior("test_k8s_agent")) > DEFAULT_PRIOR


@pytest.mark.asyncio
async def test_get_prior_returns_default_for_unknown_agent():
    cal = ConfidenceCalibrator()
    assert (await cal.get_prior("never_seen_agent_zzzzz")) == DEFAULT_PRIOR


@pytest.mark.asyncio
async def test_repeated_positive_updates_push_prior_up():
    cal = ConfidenceCalibrator()
    for _ in range(5):
        await cal.update_prior("test_log_agent", was_correct=True)
    assert (await cal.get_prior("test_log_agent")) > DEFAULT_PRIOR + 0.05


@pytest.mark.asyncio
async def test_repeated_negative_updates_push_prior_down():
    cal = ConfidenceCalibrator()
    for _ in range(5):
        await cal.update_prior("test_metrics_agent", was_correct=False)
    assert (await cal.get_prior("test_metrics_agent")) < DEFAULT_PRIOR - 0.05


@pytest.mark.asyncio
async def test_update_increments_sample_count():
    cal = ConfidenceCalibrator()
    await cal.update_prior("test_log_agent", was_correct=True)
    await cal.update_prior("test_log_agent", was_correct=False)
    async with get_session() as session:
        row = await session.execute(
            text(
                "SELECT sample_count FROM agent_priors WHERE agent_name = :n"
            ),
            {"n": "test_log_agent"},
        )
        count = row.scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_update_prior_bounds_stay_in_0_1():
    cal = ConfidenceCalibrator()
    for _ in range(100):
        await cal.update_prior("test_log_agent", was_correct=True)
    hi = await cal.get_prior("test_log_agent")
    assert 0.0 <= hi <= 1.0
    for _ in range(100):
        await cal.update_prior("test_metrics_agent", was_correct=False)
    lo = await cal.get_prior("test_metrics_agent")
    assert 0.0 <= lo <= 1.0
