"""Integration test: fix job queue processes mock fix generation."""
import asyncio
import os
import tempfile
import pytest
from unittest.mock import AsyncMock

from src.utils.fix_job_queue import FixJobQueue, FixJobStatus, RetryableFixError


@pytest.fixture
def fresh_queue():
    """Fresh queue instance (not singleton)."""
    FixJobQueue.reset_instance()
    q = FixJobQueue()
    yield q
    # Cleanup
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(q.shutdown())
    except Exception:
        pass


@pytest.mark.asyncio
async def test_end_to_end_fix_job(fresh_queue):
    """Submit a job, process it, verify completion."""
    results = {}

    async def mock_executor():
        await asyncio.sleep(0.05)
        results["executed"] = True

    job = await fresh_queue.submit(session_id="test-sess", executor=mock_executor)
    assert job.status == FixJobStatus.QUEUED

    await fresh_queue._process_one()

    assert job.status == FixJobStatus.COMPLETED
    assert results.get("executed") is True


@pytest.mark.asyncio
async def test_retry_then_success(fresh_queue):
    """Job retries on RetryableFixError, eventually succeeds."""
    attempt_count = 0

    async def flaky_executor():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise RetryableFixError("timeout", stage="cloning")

    job = await fresh_queue.submit(session_id="test-sess", executor=flaky_executor)
    job._backoff_base = 0.01

    await fresh_queue._process_one()  # fails, re-enqueues
    assert job.status == FixJobStatus.RETRYING
    await fresh_queue._process_one()  # succeeds
    assert job.status == FixJobStatus.COMPLETED
    assert attempt_count == 2


@pytest.mark.asyncio
async def test_cancel_during_execution(fresh_queue):
    """Cancelling a job sets status to CANCELLED."""
    job = await fresh_queue.submit(
        session_id="test-sess",
        executor=AsyncMock(side_effect=lambda: asyncio.sleep(10)),
    )
    cancelled = await fresh_queue.cancel(job.id)
    assert cancelled is True
    assert job.status == FixJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_duplicate_session_rejected(fresh_queue):
    """Second submit for same session raises ValueError."""
    await fresh_queue.submit(session_id="test-sess", executor=AsyncMock())
    with pytest.raises(ValueError, match="already has an active"):
        await fresh_queue.submit(session_id="test-sess", executor=AsyncMock())


@pytest.mark.asyncio
async def test_orphan_cleanup(fresh_queue):
    """Orphan /tmp/fix_* dirs are purged on init."""
    d1 = tempfile.mkdtemp(prefix="fix_", dir="/tmp")
    d2 = tempfile.mkdtemp(prefix="fix_", dir="/tmp")
    assert os.path.exists(d1)
    assert os.path.exists(d2)

    fresh_queue._purge_orphan_temp_dirs()

    assert not os.path.exists(d1)
    assert not os.path.exists(d2)
