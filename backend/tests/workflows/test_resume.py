"""Task 4.26 — graceful drain + checkpoint resume."""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.workflows.resume import (
    DrainState,
    ResumableRun,
    resume_all_in_progress,
    select_orphaned_running,
    wait_for_drain,
)


_TEST_RUN_IDS = ("resume_r1", "resume_r2", "resume_r3")


@pytest_asyncio.fixture(autouse=True)
async def _isolate():
    await get_engine().dispose(close=False)
    await _purge()
    yield
    await _purge()
    await get_engine().dispose(close=False)


async def _purge():
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "DELETE FROM investigation_dag_snapshot WHERE run_id = ANY(:ids)"
                ),
                {"ids": list(_TEST_RUN_IDS)},
            )


async def _seed(run_id: str, *, payload: dict, stale_seconds: int):
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO investigation_dag_snapshot (run_id, payload, schema_version, updated_at) "
                    "VALUES (:run_id, CAST(:payload AS JSON), 1, NOW() - make_interval(secs => :stale))"
                ),
                {
                    "run_id": run_id,
                    "payload": json.dumps(payload),
                    "stale": stale_seconds,
                },
            )


class TestSelectOrphaned:
    @pytest.mark.asyncio
    async def test_stale_running_row_is_returned(self):
        await _seed(
            "resume_r1",
            payload={"schema_version": 1, "status": "running", "last_sequence_number": 3},
            stale_seconds=120,
        )
        rows = await select_orphaned_running()
        assert any(r.run_id == "resume_r1" for r in rows)

    @pytest.mark.asyncio
    async def test_completed_row_is_not_returned(self):
        await _seed(
            "resume_r2",
            payload={"schema_version": 1, "status": "completed"},
            stale_seconds=120,
        )
        rows = await select_orphaned_running()
        assert not any(r.run_id == "resume_r2" for r in rows)

    @pytest.mark.asyncio
    async def test_fresh_row_is_not_returned(self):
        # Fresh heartbeat — the owner is alive.
        await _seed(
            "resume_r3",
            payload={"schema_version": 1, "status": "running"},
            stale_seconds=0,
        )
        rows = await select_orphaned_running()
        assert not any(r.run_id == "resume_r3" for r in rows)


class TestResumeAllInProgress:
    @pytest.mark.asyncio
    async def test_in_progress_run_resumes_from_snapshot_after_restart(self):
        await _seed(
            "resume_r1",
            payload={"schema_version": 1, "status": "running", "last_sequence_number": 3},
            stale_seconds=120,
        )

        async def acquire_lock(run_id: str) -> bool:
            return True

        dispatched: list[str] = []

        async def dispatch(run: ResumableRun) -> None:
            dispatched.append(run.run_id)

        taken = await resume_all_in_progress(
            acquire_lock=acquire_lock,
            dispatch_resume=dispatch,
        )
        assert "resume_r1" in taken
        assert dispatched == taken

    @pytest.mark.asyncio
    async def test_failed_lock_acquisition_skips_run(self):
        await _seed(
            "resume_r1",
            payload={"schema_version": 1, "status": "running"},
            stale_seconds=120,
        )

        async def deny_lock(run_id: str) -> bool:
            return False

        dispatched: list[str] = []

        async def dispatch(run: ResumableRun) -> None:
            dispatched.append(run.run_id)

        taken = await resume_all_in_progress(
            acquire_lock=deny_lock,
            dispatch_resume=dispatch,
        )
        assert taken == []
        assert dispatched == []

    @pytest.mark.asyncio
    async def test_dispatch_failure_is_isolated_per_run(self):
        await _seed("resume_r1", payload={"status": "running"}, stale_seconds=120)
        await _seed("resume_r2", payload={"status": "running"}, stale_seconds=120)

        async def scoped_lock(run_id: str) -> bool:
            # Only lock the rows seeded by this test so we don't step on
            # other integration-test leftovers in the shared table.
            return run_id in _TEST_RUN_IDS

        async def flaky_dispatch(run: ResumableRun) -> None:
            if run.run_id == "resume_r1":
                raise RuntimeError("boom")

        taken = await resume_all_in_progress(
            acquire_lock=scoped_lock,
            dispatch_resume=flaky_dispatch,
        )
        # Only r2 should have succeeded; r1's failure must not stop the loop.
        assert "resume_r2" in taken
        assert "resume_r1" not in taken


class TestDrainState:
    def test_starts_not_draining(self):
        assert DrainState().is_draining() is False

    def test_start_drain_sets_flag(self):
        d = DrainState()
        d.start_drain()
        assert d.is_draining() is True


class TestWaitForDrain:
    @pytest.mark.asyncio
    async def test_returns_true_when_in_flight_drains(self):
        remaining = {"n": 3}

        def has_in_flight():
            if remaining["n"] > 0:
                remaining["n"] -= 1
                return remaining["n"] > 0
            return False

        ok = await wait_for_drain(has_in_flight=has_in_flight, grace_s=2, poll_s=0.01)
        assert ok is True

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        ok = await wait_for_drain(has_in_flight=lambda: True, grace_s=0, poll_s=0.01)
        assert ok is False
