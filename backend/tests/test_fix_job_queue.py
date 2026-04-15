"""Tests for the FixJobQueue module."""

import asyncio
import uuid

import pytest
import pytest_asyncio

from src.utils.fix_job_queue import (
    FixJob,
    FixJobQueue,
    FixJobStatus,
    RetryableFixError,
)


def _make_queue(max_workers: int = 2, max_queue_size: int = 10) -> FixJobQueue:
    """Create a fresh (non-singleton) queue instance for isolated testing."""
    q = FixJobQueue.__new__(FixJobQueue)
    q._MAX_WORKERS = max_workers
    q._MAX_QUEUE_SIZE = max_queue_size
    q._queue = asyncio.Queue(maxsize=max_queue_size)
    q._jobs: dict[str, FixJob] = {}
    q._temp_dirs: set[str] = set()
    q._workers: list[asyncio.Task] = []
    q._started = False
    q._shutdown = False
    return q


# ── Submit ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_returns_job_id():
    q = _make_queue()

    async def noop():
        pass

    job = await q.submit(session_id="sess-1", executor=noop)
    assert isinstance(job, FixJob)
    assert job.status == FixJobStatus.QUEUED
    assert job.session_id == "sess-1"
    assert job.id is not None


@pytest.mark.asyncio
async def test_submit_rejects_duplicate_session():
    q = _make_queue()

    async def noop():
        pass

    await q.submit(session_id="sess-dup", executor=noop)
    with pytest.raises(ValueError, match="already has an active"):
        await q.submit(session_id="sess-dup", executor=noop)


@pytest.mark.asyncio
async def test_submit_rejects_when_full():
    q = _make_queue(max_queue_size=2)

    async def noop():
        pass

    await q.submit(session_id="s1", executor=noop)
    await q.submit(session_id="s2", executor=noop)
    with pytest.raises(RuntimeError, match="queue is full"):
        await q.submit(session_id="s3", executor=noop)


# ── Cancel ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_sets_status():
    q = _make_queue()

    async def noop():
        pass

    job = await q.submit(session_id="sess-c", executor=noop)
    result = await q.cancel(job.id)
    assert result is True
    assert job.status == FixJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_unknown_job():
    q = _make_queue()
    result = await q.cancel(str(uuid.uuid4()))
    assert result is False


# ── Status ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_status():
    q = _make_queue()

    async def noop():
        pass

    job = await q.submit(session_id="sess-st", executor=noop)
    status = q.get_status(job.id)
    assert status is not None
    assert status["id"] == job.id
    assert status["session_id"] == "sess-st"
    assert status["status"] == FixJobStatus.QUEUED.value


# ── Active job lookup ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_job_for_session():
    q = _make_queue()

    async def noop():
        pass

    job = await q.submit(session_id="sess-a", executor=noop)
    found = q.get_active_job("sess-a")
    assert found is not None
    assert found.id == job.id


@pytest.mark.asyncio
async def test_get_active_job_returns_none():
    q = _make_queue()
    assert q.get_active_job("nonexistent") is None


# ── Temp dir tracking ────────────────────────────────────────────────

def test_track_temp_dir():
    q = _make_queue()
    q.track_temp_dir("/tmp/fix_abc123")
    assert "/tmp/fix_abc123" in q._temp_dirs
    q.untrack_temp_dir("/tmp/fix_abc123")
    assert "/tmp/fix_abc123" not in q._temp_dirs


# ── Worker / process_one ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_worker_executes_job():
    q = _make_queue()
    executed = asyncio.Event()

    async def work():
        executed.set()

    await q.submit(session_id="sess-w", executor=work)
    await q._process_one()
    assert executed.is_set()
    job = list(q._jobs.values())[0]
    assert job.status == FixJobStatus.COMPLETED
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_worker_retries_on_retryable_error():
    q = _make_queue()
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RetryableFixError("transient", stage="build", suggestion="retry")

    job = await q.submit(session_id="sess-r", executor=flaky, max_attempts=3)
    job._backoff_base = 0.0  # no sleep in tests
    # First attempt — should re-enqueue due to retryable error
    await q._process_one()
    assert job.status == FixJobStatus.RETRYING
    assert job.attempt == 1

    # Second attempt — should succeed
    await q._process_one()
    assert job.status == FixJobStatus.COMPLETED
    assert call_count == 2


@pytest.mark.asyncio
async def test_worker_fails_on_fatal_error():
    q = _make_queue()

    async def boom():
        raise RuntimeError("fatal crash")

    job = await q.submit(session_id="sess-f", executor=boom, max_attempts=3)
    await q._process_one()
    assert job.status == FixJobStatus.FAILED
    assert "fatal crash" in (job.error_message or "")


@pytest.mark.asyncio
async def test_worker_fails_after_max_retries():
    q = _make_queue()

    async def always_fail():
        raise RetryableFixError("still broken", stage="test", suggestion="check logs")

    job = await q.submit(session_id="sess-mr", executor=always_fail, max_attempts=2)
    job._backoff_base = 0.0  # no sleep in tests

    # attempt 1 → retry
    await q._process_one()
    assert job.status == FixJobStatus.RETRYING

    # attempt 2 → exhausted, should fail
    await q._process_one()
    assert job.status == FixJobStatus.FAILED
    assert "still broken" in (job.error_message or "")
