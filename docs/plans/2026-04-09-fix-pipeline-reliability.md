# Fix Pipeline Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fragile background-task fix generation with a production-grade asyncio job queue providing bounded concurrency, automatic retry, resource management, and structured error reporting.

**Architecture:** New `FixJobQueue` singleton with bounded worker pool (max 2 concurrent jobs), retry with exponential backoff, tracked temp directories with orphan cleanup. Supervisor delegates execution to the queue; routes use queue as single source of truth for concurrency. Frontend shows retry progress and stage-specific errors.

**Tech Stack:** Python 3.14, asyncio, FastAPI, React 18, TypeScript

---

### Task 1: Create FixJobQueue core module

**Files:**
- Create: `backend/src/utils/fix_job_queue.py`
- Create: `backend/tests/test_fix_job_queue.py`

**Step 1: Write tests for FixJobQueue**

```python
# backend/tests/test_fix_job_queue.py
"""Tests for FixJobQueue — bounded asyncio worker pool for fix generation."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.utils.fix_job_queue import FixJobQueue, FixJob, FixJobStatus


@pytest.fixture
def queue():
    """Fresh queue per test (not singleton)."""
    q = FixJobQueue.__new__(FixJobQueue)
    q._queue = asyncio.Queue(maxsize=10)
    q._jobs = {}
    q._temp_dirs = set()
    q._workers = []
    q._max_workers = 2
    q._started = False
    q._shutdown = False
    return q


@pytest.mark.asyncio
async def test_submit_returns_job_id(queue):
    """submit() should return a FixJob with queued status."""
    job = queue.submit(
        session_id="sess-1",
        executor=AsyncMock(),
    )
    assert job.status == FixJobStatus.QUEUED
    assert job.session_id == "sess-1"
    assert job.id is not None


@pytest.mark.asyncio
async def test_submit_rejects_duplicate_session(queue):
    """submit() should reject if session already has an active job."""
    queue.submit(session_id="sess-1", executor=AsyncMock())
    with pytest.raises(ValueError, match="already has an active"):
        queue.submit(session_id="sess-1", executor=AsyncMock())


@pytest.mark.asyncio
async def test_submit_rejects_when_full(queue):
    """submit() should raise when queue is full."""
    queue._queue = asyncio.Queue(maxsize=2)
    queue.submit(session_id="sess-1", executor=AsyncMock())
    queue.submit(session_id="sess-2", executor=AsyncMock())
    with pytest.raises(RuntimeError, match="full"):
        queue.submit(session_id="sess-3", executor=AsyncMock())


@pytest.mark.asyncio
async def test_cancel_sets_status(queue):
    """cancel() should set job status to cancelled."""
    job = queue.submit(session_id="sess-1", executor=AsyncMock())
    cancelled = queue.cancel(job.id)
    assert cancelled is True
    assert job.status == FixJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_unknown_job(queue):
    """cancel() should return False for unknown job."""
    assert queue.cancel("nonexistent") is False


@pytest.mark.asyncio
async def test_get_status(queue):
    """get_status() should return job state dict."""
    job = queue.submit(session_id="sess-1", executor=AsyncMock())
    status = queue.get_status(job.id)
    assert status["status"] == "queued"
    assert status["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_get_active_job_for_session(queue):
    """get_active_job() should find active job by session_id."""
    job = queue.submit(session_id="sess-1", executor=AsyncMock())
    found = queue.get_active_job("sess-1")
    assert found is not None
    assert found.id == job.id


@pytest.mark.asyncio
async def test_get_active_job_returns_none(queue):
    """get_active_job() returns None when no active job."""
    assert queue.get_active_job("sess-1") is None


@pytest.mark.asyncio
async def test_track_temp_dir(queue):
    """track_temp_dir and cleanup_temp_dir manage the set."""
    queue.track_temp_dir("/tmp/fix_abc")
    assert "/tmp/fix_abc" in queue._temp_dirs
    queue.untrack_temp_dir("/tmp/fix_abc")
    assert "/tmp/fix_abc" not in queue._temp_dirs


@pytest.mark.asyncio
async def test_worker_executes_job(queue):
    """Worker should pick up a job and execute it."""
    executor = AsyncMock(return_value=None)
    job = queue.submit(session_id="sess-1", executor=executor)

    # Run one worker cycle
    await queue._process_one()

    assert job.status == FixJobStatus.COMPLETED
    executor.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_retries_on_retryable_error(queue):
    """Worker should retry on RetryableFixError."""
    from src.utils.fix_job_queue import RetryableFixError

    call_count = 0
    async def flaky_executor(job):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryableFixError("clone timeout", stage="cloning")
        return None

    job = queue.submit(session_id="sess-1", executor=flaky_executor)
    job._backoff_base = 0.01  # fast retry for tests

    # Process until completed or max attempts
    for _ in range(5):
        if job.status in (FixJobStatus.COMPLETED, FixJobStatus.FAILED):
            break
        # Re-enqueue for retry
        await queue._process_one()

    assert job.status == FixJobStatus.COMPLETED
    assert call_count == 3


@pytest.mark.asyncio
async def test_worker_fails_on_fatal_error(queue):
    """Worker should not retry on non-retryable errors."""
    executor = AsyncMock(side_effect=ValueError("no repo url"))
    job = queue.submit(session_id="sess-1", executor=executor)

    await queue._process_one()

    assert job.status == FixJobStatus.FAILED
    assert "no repo url" in job.error_message


@pytest.mark.asyncio
async def test_worker_fails_after_max_retries(queue):
    """Worker should fail after exhausting retries."""
    from src.utils.fix_job_queue import RetryableFixError

    executor = AsyncMock(side_effect=RetryableFixError("timeout", stage="cloning"))
    job = queue.submit(session_id="sess-1", executor=executor)
    job.max_attempts = 2
    job._backoff_base = 0.01

    for _ in range(5):
        if job.status == FixJobStatus.FAILED:
            break
        await queue._process_one()

    assert job.status == FixJobStatus.FAILED
    assert job.attempt >= 2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_fix_job_queue.py -v 2>&1 | tail -20`
Expected: FAIL — module `src.utils.fix_job_queue` does not exist.

**Step 3: Implement FixJobQueue**

```python
# backend/src/utils/fix_job_queue.py
"""
Asyncio job queue for fix generation with bounded concurrency,
automatic retry, and temp directory lifecycle management.
"""
import asyncio
import glob
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional, Set

from src.utils.logger import get_logger

logger = get_logger(__name__)


class FixJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetryableFixError(Exception):
    """Raised for transient failures that should be retried."""

    def __init__(self, message: str, stage: str = "unknown", suggestion: str = ""):
        super().__init__(message)
        self.stage = stage
        self.suggestion = suggestion


@dataclass
class FixJob:
    """Tracks a single fix generation job lifecycle."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    status: FixJobStatus = FixJobStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempt: int = 0
    max_attempts: int = 3
    error_message: str = ""
    current_stage: str = ""
    executor: Optional[Callable[["FixJob"], Coroutine[Any, Any, None]]] = field(
        default=None, repr=False
    )
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _backoff_base: float = field(default=2.0, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.id,
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "error_message": self.error_message,
            "current_stage": self.current_stage,
        }


_MAX_WORKERS = 2
_MAX_QUEUE_SIZE = 10
_TEMP_DIR_PREFIX = "fix_"


class FixJobQueue:
    """Bounded asyncio worker pool for fix generation jobs.

    - Max 2 concurrent jobs (caps file descriptor usage)
    - Automatic retry with exponential backoff for transient failures
    - Temp directory tracking with cleanup
    - Orphan purge on startup
    """

    _instance: Optional["FixJobQueue"] = None

    def __init__(self) -> None:
        self._queue: asyncio.Queue[FixJob] = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
        self._jobs: Dict[str, FixJob] = {}
        self._temp_dirs: Set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._max_workers = _MAX_WORKERS
        self._started = False
        self._shutdown = False

    @classmethod
    def get_instance(cls) -> "FixJobQueue":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Start worker tasks. Call once at app startup."""
        if self._started:
            return
        self._started = True
        self._shutdown = False
        self._purge_orphan_temp_dirs()
        for i in range(self._max_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info(
            "FixJobQueue started",
            extra={"extra": {"workers": self._max_workers, "max_queue": _MAX_QUEUE_SIZE}},
        )

    async def shutdown(self) -> None:
        """Cancel all workers and running jobs, clean up temp dirs."""
        self._shutdown = True
        # Cancel all running jobs
        for job in self._jobs.values():
            if job.status in (FixJobStatus.RUNNING, FixJobStatus.RETRYING):
                if job._task and not job._task.done():
                    job._task.cancel()
                job.status = FixJobStatus.CANCELLED
        # Cancel workers
        for w in self._workers:
            w.cancel()
        self._workers.clear()
        # Clean up all temp dirs
        for d in list(self._temp_dirs):
            self._cleanup_dir(d)
        self._temp_dirs.clear()
        self._started = False
        logger.info("FixJobQueue shut down")

    # ── Public API ─────────────────────────────────────────────────────

    def submit(
        self,
        session_id: str,
        executor: Callable[["FixJob"], Coroutine[Any, Any, None]],
        max_attempts: int = 3,
    ) -> FixJob:
        """Submit a fix generation job. Returns FixJob immediately.

        Raises:
            ValueError: if session already has an active job
            RuntimeError: if queue is full
        """
        # Check for existing active job for this session
        existing = self.get_active_job(session_id)
        if existing:
            raise ValueError(
                f"Session {session_id} already has an active fix job "
                f"(id={existing.id}, status={existing.status.value})"
            )

        job = FixJob(session_id=session_id, executor=executor, max_attempts=max_attempts)
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            raise RuntimeError(
                f"Fix job queue is full ({_MAX_QUEUE_SIZE} pending). Try again later."
            )

        self._jobs[job.id] = job
        logger.info(
            "Fix job submitted",
            extra={"extra": {"job_id": job.id, "session_id": session_id}},
        )
        return job

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued or running job. Returns True if found."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status in (FixJobStatus.COMPLETED, FixJobStatus.FAILED, FixJobStatus.CANCELLED):
            return False
        if job._task and not job._task.done():
            job._task.cancel()
        job.status = FixJobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        logger.info("Fix job cancelled", extra={"extra": {"job_id": job_id}})
        return True

    def cancel_for_session(self, session_id: str) -> bool:
        """Cancel any active job for a session. Returns True if found."""
        job = self.get_active_job(session_id)
        if job:
            return self.cancel(job.id)
        return False

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status as dict."""
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def get_active_job(self, session_id: str) -> Optional[FixJob]:
        """Find an active (queued/running/retrying) job for a session."""
        active_statuses = (FixJobStatus.QUEUED, FixJobStatus.RUNNING, FixJobStatus.RETRYING)
        for job in self._jobs.values():
            if job.session_id == session_id and job.status in active_statuses:
                return job
        return None

    # ── Temp Dir Management ────────────────────────────────────────────

    def track_temp_dir(self, path: str) -> None:
        self._temp_dirs.add(path)

    def untrack_temp_dir(self, path: str) -> None:
        self._temp_dirs.discard(path)

    def _cleanup_dir(self, path: str) -> None:
        """Remove a temp directory, tolerating errors."""
        try:
            shutil.rmtree(path, ignore_errors=True)
            self._temp_dirs.discard(path)
        except Exception as e:
            logger.warning("Temp dir cleanup failed: %s — %s", path, e)

    def _purge_orphan_temp_dirs(self) -> None:
        """Remove leftover /tmp/fix_* dirs from previous crashes."""
        import tempfile
        import os

        tmp_root = tempfile.gettempdir()
        pattern = os.path.join(tmp_root, f"{_TEMP_DIR_PREFIX}*")
        orphans = glob.glob(pattern)
        for d in orphans:
            if os.path.isdir(d):
                logger.info("Purging orphan temp dir: %s", d)
                shutil.rmtree(d, ignore_errors=True)

    # ── Workers ────────────────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        """Worker that pulls jobs from the queue and executes them."""
        while not self._shutdown:
            try:
                await self._process_one()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker %d unexpected error: %s", worker_id, e, exc_info=True)
                await asyncio.sleep(1)

    async def _process_one(self) -> None:
        """Pull and process a single job from the queue."""
        try:
            job = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            await asyncio.sleep(0.1)
            return

        if job.status == FixJobStatus.CANCELLED:
            return

        job.status = FixJobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempt += 1

        try:
            job._task = asyncio.current_task()
            await job.executor(job)
            job.status = FixJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
        except RetryableFixError as e:
            job.error_message = str(e)
            job.current_stage = e.stage
            if job.attempt < job.max_attempts:
                backoff = job._backoff_base ** job.attempt
                logger.warning(
                    "Fix job retrying (attempt %d/%d, stage=%s): %s — backoff %.1fs",
                    job.attempt, job.max_attempts, e.stage, e, backoff,
                )
                job.status = FixJobStatus.RETRYING
                await asyncio.sleep(backoff)
                # Re-enqueue for retry
                if job.status == FixJobStatus.RETRYING:  # not cancelled during sleep
                    job.status = FixJobStatus.QUEUED
                    try:
                        self._queue.put_nowait(job)
                    except asyncio.QueueFull:
                        job.status = FixJobStatus.FAILED
                        job.error_message = f"Retry failed — queue full after {e}"
                        job.completed_at = datetime.now(timezone.utc)
            else:
                logger.error(
                    "Fix job failed after %d attempts (stage=%s): %s",
                    job.attempt, e.stage, e,
                )
                job.status = FixJobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
        except asyncio.CancelledError:
            job.status = FixJobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.error("Fix job fatal error: %s", e, exc_info=True)
            job.status = FixJobStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
        finally:
            job._task = None
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_fix_job_queue.py -v 2>&1 | tail -25`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add backend/src/utils/fix_job_queue.py backend/tests/test_fix_job_queue.py
git commit -m "feat(fix-pipeline): add FixJobQueue with bounded concurrency and retry"
```

---

### Task 2: Add sparse checkout to RepoManager

**Files:**
- Modify: `backend/src/utils/repo_manager.py`
- Create: `backend/tests/test_repo_manager_sparse.py`

**Step 1: Write test**

```python
# backend/tests/test_repo_manager_sparse.py
"""Tests for RepoManager sparse checkout support."""
import os
import tempfile
import subprocess
import pytest
from pathlib import Path

from src.utils.repo_manager import RepoManager


@pytest.fixture
def fake_repo():
    """Create a local bare repo with a few files for testing."""
    tmp = tempfile.mkdtemp(prefix="test_repo_")
    repo_dir = os.path.join(tmp, "repo")
    os.makedirs(repo_dir)
    subprocess.run(["git", "init", repo_dir], capture_output=True, check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", repo_dir, "config", "user.name", "Test"], capture_output=True, check=True)
    # Create files
    for f in ["src/app.py", "src/utils.py", "tests/test_app.py", "README.md", "docs/guide.md"]:
        fp = os.path.join(repo_dir, f)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        Path(fp).write_text(f"# {f}\n")
    subprocess.run(["git", "-C", repo_dir, "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", repo_dir, "commit", "-m", "init"], capture_output=True, check=True)
    yield repo_dir
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def test_clone_shallow(fake_repo):
    """Shallow clone should work."""
    target = tempfile.mkdtemp(prefix="test_clone_")
    try:
        result = RepoManager.clone_local(fake_repo, target)
        assert result["success"]
        assert os.path.exists(os.path.join(target, "src", "app.py"))
    finally:
        import shutil
        shutil.rmtree(target, ignore_errors=True)


def test_sparse_checkout(fake_repo):
    """Sparse checkout should only have target files."""
    target = tempfile.mkdtemp(prefix="test_sparse_")
    try:
        result = RepoManager.clone_local(fake_repo, target)
        assert result["success"]
        ok = RepoManager.apply_sparse_checkout(target, ["src/app.py", "src/utils.py"])
        assert ok is True
        # Target files should exist
        assert os.path.exists(os.path.join(target, "src", "app.py"))
        assert os.path.exists(os.path.join(target, "src", "utils.py"))
        # Non-target files should not
        assert not os.path.exists(os.path.join(target, "README.md"))
    finally:
        import shutil
        shutil.rmtree(target, ignore_errors=True)


def test_sparse_checkout_fallback_on_failure(fake_repo):
    """Sparse checkout failure should leave full clone intact."""
    target = tempfile.mkdtemp(prefix="test_sparse_fail_")
    try:
        result = RepoManager.clone_local(fake_repo, target)
        assert result["success"]
        # Pass empty list — should gracefully fail and leave clone intact
        ok = RepoManager.apply_sparse_checkout(target, [])
        assert ok is False
        # Full clone files still present
        assert os.path.exists(os.path.join(target, "README.md"))
    finally:
        import shutil
        shutil.rmtree(target, ignore_errors=True)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_repo_manager_sparse.py -v 2>&1 | tail -15`
Expected: FAIL — `clone_local` and `apply_sparse_checkout` do not exist.

**Step 3: Add clone_local and apply_sparse_checkout to RepoManager**

Add the following methods to `RepoManager` class in `backend/src/utils/repo_manager.py` (after the existing `cleanup_repo` method at line 101):

```python
    @staticmethod
    def clone_local(source_path: str, target_path: str) -> Dict[str, Any]:
        """Clone from a local path (for testing). Shallow, no network."""
        try:
            if os.path.exists(target_path):
                shutil.rmtree(target_path)
            Path(target_path).parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--depth", "1", source_path, target_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {"success": False, "error": result.stderr}
            file_count = sum(1 for _ in Path(target_path).rglob("*") if _.is_file())
            return {"success": True, "path": target_path, "file_count": file_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def apply_sparse_checkout(repo_path: str, target_files: list[str]) -> bool:
        """Enable sparse checkout and keep only the specified files.

        Falls back gracefully — if sparse checkout fails, the full clone
        remains intact. Returns True if sparse checkout succeeded.
        """
        if not target_files:
            return False
        try:
            # Enable sparse checkout
            subprocess.run(
                ["git", "sparse-checkout", "init", "--cone"],
                cwd=repo_path, capture_output=True, text=True, check=True, timeout=10,
            )
            # Determine directories containing target files
            dirs = set()
            for f in target_files:
                parts = Path(f).parts
                if len(parts) > 1:
                    dirs.add(str(Path(*parts[:-1])))
                else:
                    dirs.add(".")
            # Set sparse checkout paths
            subprocess.run(
                ["git", "sparse-checkout", "set"] + list(dirs),
                cwd=repo_path, capture_output=True, text=True, check=True, timeout=10,
            )
            logger.info(
                "Sparse checkout applied",
                extra={"extra": {"dirs": list(dirs), "file_count": len(target_files)}},
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            logger.warning("Sparse checkout failed, keeping full clone: %s", e)
            # Disable sparse checkout to restore full tree
            try:
                subprocess.run(
                    ["git", "sparse-checkout", "disable"],
                    cwd=repo_path, capture_output=True, text=True, timeout=10,
                )
            except Exception:
                pass
            return False
```

Also, change `clone_repo` to use shallow clone by default (already `shallow=True` default, which is correct). The caller in `supervisor.py` currently passes `shallow=False` — that will be changed in Task 4.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_repo_manager_sparse.py -v 2>&1 | tail -15`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add backend/src/utils/repo_manager.py backend/tests/test_repo_manager_sparse.py
git commit -m "feat(fix-pipeline): add sparse checkout support to RepoManager"
```

---

### Task 3: Add structured error types for fix pipeline

**Files:**
- Modify: `backend/src/agents/agent3/fix_generator.py`

**Step 1: Add RetryableFixError usage to fix_generator**

At the top of `backend/src/agents/agent3/fix_generator.py`, add import:

```python
from src.utils.fix_job_queue import RetryableFixError
```

In the `generate_fix` method (around line 484), wrap the LLM call with retry-friendly errors:

Replace the bare `response = await self.llm_client.chat(...)` call (line 484-488) with:

```python
        try:
            response = await self.llm_client.chat(
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=16384 if is_multi else 8192,
            )
        except Exception as e:
            raise RetryableFixError(
                f"LLM call failed: {e}",
                stage="generating",
                suggestion="The AI model timed out or is overloaded. Will retry automatically.",
            ) from e
```

Also add to the `_collect_fix_targets` fallback (around line 312) to raise a clear non-retryable error:

The existing `raise ValueError("No target files identified in code analysis")` at line 312 is already non-retryable (not wrapped in `RetryableFixError`), so it's correct. No change needed there.

**Step 2: Run type check**

Run: `cd backend && python -c "from src.agents.agent3.fix_generator import Agent3FixGenerator; print('OK')" 2>&1`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/agents/agent3/fix_generator.py
git commit -m "feat(fix-pipeline): use RetryableFixError for LLM failures in fix generator"
```

---

### Task 4: Refactor supervisor to use FixJobQueue

**Files:**
- Modify: `backend/src/agents/supervisor.py`

**Step 1: Extract `_execute_fix_generation` from `start_fix_generation`**

This is the biggest refactor. The existing `start_fix_generation` method (lines 2487-2724) needs to be split:

1. `start_fix_generation` becomes a thin wrapper that submits to the job queue
2. `_execute_fix_generation` contains the actual logic (clone, generate, verify, stage, approval loop)

Replace the `start_fix_generation` method with:

```python
    async def start_fix_generation(
        self,
        state: DiagnosticState,
        event_emitter: EventEmitter,
        human_guidance: str = "",
    ) -> str:
        """Submit fix generation to the job queue. Returns job_id."""
        from src.utils.fix_job_queue import FixJobQueue

        queue = FixJobQueue.get_instance()

        # Build executor closure that captures state, emitter, guidance
        async def executor(job):
            await self._execute_fix_generation(state, event_emitter, human_guidance, job)

        job = queue.submit(session_id=state.session_id, executor=executor)
        return job.id

    async def _execute_fix_generation(
        self,
        state: DiagnosticState,
        event_emitter: EventEmitter,
        human_guidance: str = "",
        job=None,
    ) -> None:
        """Execute fix generation — called by job queue worker.

        This contains the full pipeline: clone → generate → verify → stage → approval.
        Temp dirs are tracked by the job queue for cleanup.
        RetryableFixError is raised for transient failures (queue handles retry).
        """
        import tempfile
        import os
        from src.utils.fix_job_queue import FixJobQueue, RetryableFixError

        queue = FixJobQueue.get_instance()
        tmp_path = ""

        try:
            state.phase = DiagnosticPhase.FIX_IN_PROGRESS
            state.fix_result = FixResult(fix_status=FixStatus.GENERATING)
            if job:
                job.current_stage = "cloning"
            await event_emitter.emit("fix_generator", "started", "Fix generation started",
                                      details={"job_id": job.id if job else None,
                                                "attempt": job.attempt if job else 1})

            # Resolve github token
            token = ""
            if self._connection_config and self._connection_config.github_token:
                token = self._connection_config.github_token
            if not token:
                token = os.getenv("GITHUB_TOKEN", "")

            # M2: Validate repo_url format before parsing
            repo_url = state.repo_url or ""
            if repo_url and not (repo_url.startswith("https://") or repo_url.startswith("http://") or repo_url.startswith("git@")):
                state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", f"Invalid repository URL format: {repo_url}")
                return

            # Parse owner/repo
            owner_repo = self._parse_owner_repo(repo_url) if repo_url else None
            if not owner_repo:
                state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", "Cannot generate fix — no valid repository URL")
                return

            # Clone repo (shallow to reduce FD usage)
            from src.utils.repo_manager import RepoManager
            tmp_path = tempfile.mkdtemp(prefix="fix_")
            queue.track_temp_dir(tmp_path)

            try:
                clone_result = RepoManager.clone_repo(owner_repo, tmp_path, shallow=True, token=token)
            except Exception as e:
                raise RetryableFixError(
                    f"Clone failed: {e}",
                    stage="cloning",
                    suggestion="Check network connectivity and GitHub token",
                ) from e

            if not clone_result["success"]:
                raise RetryableFixError(
                    f"Clone failed: {clone_result.get('error', 'unknown')}",
                    stage="cloning",
                    suggestion="Check repository URL and access permissions",
                )

            # Apply sparse checkout for target files (best-effort)
            from src.agents.agent3.fix_generator import Agent3FixGenerator
            target_files = Agent3FixGenerator._collect_fix_targets_static(state)
            if target_files:
                RepoManager.apply_sparse_checkout(tmp_path, target_files)

            if job:
                job.current_stage = "generating"

            # Verify clone contents
            import glob as _glob
            cloned_files = _glob.glob(os.path.join(tmp_path, "**"), recursive=True)
            logger.info("Clone contents", extra={
                "extra": {"tmp_path": tmp_path, "file_count": len(cloned_files),
                          "files": [f for f in cloned_files[:20] if "/.git/" not in f]}
            })

            # Create Agent 3 instance
            agent3 = Agent3FixGenerator(
                repo_path=tmp_path,
                llm_client=self.llm_client,
                event_emitter=event_emitter,
            )

            # === Fix generation loop (same as before from here) ===
            current_guidance = human_guidance
            while True:
                state.fix_result.fix_status = FixStatus.GENERATING
                generated_fixes = await agent3.generate_fix(state, current_guidance, event_emitter)

                fixed_files: list[FixedFile] = []
                combined_diffs: list[str] = []
                for fp, fixed_code in generated_fixes.items():
                    try:
                        orig, resolved = agent3._read_original_file(fp)
                        if resolved != fp:
                            fp = resolved
                    except (FileNotFoundError, ValueError):
                        orig = ""
                    d = agent3._generate_diff(orig, fixed_code)
                    fixed_files.append(FixedFile(
                        file_path=fp, original_code=orig, fixed_code=fixed_code, diff=d,
                    ))
                    combined_diffs.append(f"--- {fp} ---\n{d}")

                primary = fixed_files[0] if fixed_files else FixedFile(file_path="unknown")
                target_file = primary.file_path
                diff = "\n".join(combined_diffs)

                state.fix_result.target_file = target_file
                state.fix_result.original_code = primary.original_code
                state.fix_result.generated_fix = primary.fixed_code
                state.fix_result.diff = diff
                state.fix_result.fixed_files = fixed_files
                state.fix_result.fix_explanation = self._build_fix_explanation(state, target_file, diff)

                # Verify with code_agent
                if job:
                    job.current_stage = "verifying"
                state.fix_result.fix_status = FixStatus.VERIFICATION_IN_PROGRESS
                await event_emitter.emit("fix_generator", "progress", "Verifying fix with code agent...")
                await self._verify_fix_with_code_agent(state, event_emitter)

                verification_failed = (state.fix_result.fix_status == FixStatus.VERIFICATION_FAILED)

                # Run Agent 3 Phase 1 (validation + staging)
                if job:
                    job.current_stage = "staging"
                code_agent_vr = state.fix_result.verification_result if state.fix_result else None
                if code_agent_vr and not isinstance(code_agent_vr, dict):
                    code_agent_vr = code_agent_vr.model_dump() if hasattr(code_agent_vr, 'model_dump') else dict(code_agent_vr)
                pr_data = await agent3.run_verification_phase(state, generated_fixes, verification_result=code_agent_vr)
                state.fix_result.pr_data = pr_data

                if job:
                    job.current_stage = "awaiting_review"
                state.fix_result.fix_status = FixStatus.AWAITING_REVIEW
                state.fix_result.attempt_count += 1

                # Arm the approval gate
                self._pending_fix_approval = True
                self._fix_human_decision = None
                self._fix_event.clear()
                await event_emitter.emit(
                    "fix_generator", "waiting_for_input",
                    "Fix proposed — awaiting human review",
                    details={"input_type": "fix_approval"},
                )

                # Present fix to human via WebSocket
                file_label = ", ".join(f"`{ff.file_path}`" for ff in fixed_files)
                summary_lines = [
                    f"**Fix generated for** {file_label} ({len(fixed_files)} file(s))\n",
                    f"**Diff:**\n```\n{diff[:3000]}\n```\n",
                ]
                if state.fix_result.fix_explanation:
                    summary_lines.append(f"**Explanation:** {state.fix_result.fix_explanation}\n")
                if verification_failed:
                    summary_lines.append("**WARNING: Code agent flagged issues with this fix.**")
                if state.fix_result.verification_result:
                    vr = state.fix_result.verification_result
                    vr_verdict = getattr(vr, 'verdict', None) or (vr.get('verdict', 'unknown') if isinstance(vr, dict) else 'unknown')
                    vr_confidence = getattr(vr, 'confidence', None) or (vr.get('confidence', 0) if isinstance(vr, dict) else 0)
                    vr_issues = getattr(vr, 'issues_found', None) or (vr.get('issues_found', []) if isinstance(vr, dict) else [])
                    vr_risks = getattr(vr, 'regression_risks', None) or (vr.get('regression_risks', []) if isinstance(vr, dict) else [])
                    summary_lines.append(f"**Code agent verdict:** {vr_verdict} (confidence: {vr_confidence}%)")
                    if vr_issues:
                        summary_lines.append(f"**Issues:** {', '.join(vr_issues[:3])}")
                    if vr_risks:
                        summary_lines.append(f"**Regression risks:** {', '.join(vr_risks[:3])}")

                summary_text = "\n".join(summary_lines)
                await event_emitter.emit("fix_generator", "fix_proposal", summary_text)

                # Wait for human decision (timeout 600s)
                try:
                    decision = await asyncio.wait_for(self._wait_for_fix_decision(), timeout=600)
                except asyncio.TimeoutError:
                    state.fix_result.fix_status = FixStatus.FAILED
                    await event_emitter.emit("fix_generator", "error", "Fix approval timed out (10 minutes)")
                    break

                decision_lower = decision.strip().lower()
                if decision_lower == "approve":
                    await self._execute_fix_approval(state, agent3, event_emitter)
                    return
                elif decision_lower == "reject":
                    state.fix_result.fix_status = FixStatus.REJECTED
                    await event_emitter.emit("fix_generator", "rejected", "Fix rejected by user")
                    return
                else:
                    # Feedback — loop with new guidance
                    state.fix_result.human_feedback = state.fix_result.human_feedback or []
                    state.fix_result.human_feedback.append(decision)
                    if state.fix_result.attempt_count >= state.fix_result.max_attempts:
                        state.fix_result.fix_status = FixStatus.FAILED
                        await event_emitter.emit("fix_generator", "error",
                            f"Max fix attempts ({state.fix_result.max_attempts}) reached")
                        return
                    await event_emitter.emit("fix_generator", "progress",
                        f"Regenerating fix with feedback (attempt {state.fix_result.attempt_count + 1}/{state.fix_result.max_attempts})")
                    current_guidance = decision

        except Exception as e:
            # Let RetryableFixError propagate to job queue for retry handling
            from src.utils.fix_job_queue import RetryableFixError
            if isinstance(e, RetryableFixError):
                if state.fix_result:
                    state.fix_result.fix_status = FixStatus.FAILED
                await event_emitter.emit("fix_generator", "error", str(e),
                    details={
                        "stage": e.stage,
                        "attempt": job.attempt if job else 1,
                        "max_attempts": job.max_attempts if job else 3,
                        "retrying": (job.attempt < job.max_attempts) if job else False,
                        "suggestion": e.suggestion,
                    })
                raise  # Let queue handle retry
            # Non-retryable
            logger.error("Fix generation failed: %s", e, exc_info=True)
            if state.fix_result:
                state.fix_result.fix_status = FixStatus.FAILED
            await event_emitter.emit("fix_generator", "error", f"Fix generation failed: {str(e)}")
        finally:
            if tmp_path:
                queue.untrack_temp_dir(tmp_path)
                from src.utils.repo_manager import RepoManager
                RepoManager.cleanup_repo(tmp_path)
```

Also need to add a static method to `Agent3FixGenerator` for collecting fix targets without an instance (used before clone to determine sparse checkout paths). Add to `fix_generator.py`:

```python
    @staticmethod
    def _collect_fix_targets_static(state) -> list[str]:
        """Collect fix target file paths from state without needing a repo clone."""
        targets = []
        if state.code_analysis:
            if state.code_analysis.root_cause_location and state.code_analysis.root_cause_location.file_path:
                targets.append(state.code_analysis.root_cause_location.file_path)
            for fa in (state.code_analysis.suggested_fix_areas or []):
                if fa.file_path and fa.file_path not in targets:
                    targets.append(fa.file_path)
            for imp in (state.code_analysis.impacted_files or []):
                fp = imp.file_path if hasattr(imp, 'file_path') else (imp.get('file_path') if isinstance(imp, dict) else None)
                fix_needed = imp.must_fix if hasattr(imp, 'must_fix') else (imp.get('must_fix', False) if isinstance(imp, dict) else False)
                if fp and fix_needed and fp not in targets:
                    targets.append(fp)
        return targets
```

**Step 2: Verify import works**

Run: `cd backend && python -c "from src.agents.supervisor import SupervisorAgent; print('OK')" 2>&1`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/agents/agent3/fix_generator.py
git commit -m "refactor(fix-pipeline): extract _execute_fix_generation, route through job queue"
```

---

### Task 5: Update routes to use job queue

**Files:**
- Modify: `backend/src/api/routes_v4.py`

**Step 1: Start job queue at app startup**

At the top of `routes_v4.py`, after existing imports (around line 34), add:

```python
from src.utils.fix_job_queue import FixJobQueue
```

Find the startup event or add one. Add queue startup to where the session cleanup loop starts. If there's a `@router_v4.on_event("startup")` or similar, add `FixJobQueue.get_instance().start()` there. Otherwise add it inline after the router creation.

**Step 2: Update `generate_fix` endpoint (lines 1439-1488)**

Replace the existing endpoint with:

```python
@router_v4.post("/session/{session_id}/fix/generate")
async def generate_fix(session_id: str, request: FixRequest):
    """Start fix generation for a completed diagnosis."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    supervisor = supervisors.get(session_id)
    emitter = session.get("emitter")

    if not state or not supervisor or not emitter:
        raise HTTPException(status_code=400, detail="Session not ready")

    from src.models.schemas import DiagnosticPhase, FixStatus, FixResult
    if state.phase != DiagnosticPhase.DIAGNOSIS_COMPLETE and state.phase != DiagnosticPhase.FIX_IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail=f"Fix generation requires DIAGNOSIS_COMPLETE phase, current: {state.phase.value}",
        )

    # Guard: require attestation before fix generation
    if not supervisor._attestation_acknowledged:
        raise HTTPException(
            status_code=403,
            detail="Attestation required — approve diagnosis findings before generating a fix",
        )

    # Submit to job queue (handles concurrency guard internally)
    queue = FixJobQueue.get_instance()
    try:
        job_id = await supervisor.start_fix_generation(state, emitter, request.guidance)
    except ValueError as e:
        # Session already has active job
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        # Queue full
        raise HTTPException(status_code=429, detail=str(e))

    return {"status": "queued", "job_id": job_id}
```

**Step 3: Enhance `get_fix_status` endpoint (lines 1491-1517)**

Add job queue info to the response. After the existing return, add job info:

```python
@router_v4.get("/session/{session_id}/fix/status", response_model=FixStatusResponse)
async def get_fix_status(session_id: str):
    """Get current fix generation status."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.fix_result:
        return FixStatusResponse(fix_status="not_started")

    fr = state.fix_result

    # Enrich with job queue info
    queue = FixJobQueue.get_instance()
    active_job = queue.get_active_job(session_id)
    job_info = active_job.to_dict() if active_job else None

    return FixStatusResponse(
        fix_status=fr.fix_status.value if hasattr(fr.fix_status, 'value') else str(fr.fix_status),
        target_file=fr.target_file,
        diff=fr.diff,
        fix_explanation=fr.fix_explanation,
        fixed_files=[
            FixStatusFileEntry(file_path=ff.file_path, diff=ff.diff)
            for ff in (fr.fixed_files or [])
        ],
        verification_result=_dump(fr.verification_result),
        pr_url=fr.pr_url,
        pr_number=fr.pr_number,
        attempt_count=fr.attempt_count,
    )
```

**Step 4: Add cancel endpoint**

After the `fix_decide` endpoint (after line 1547), add:

```python
@router_v4.delete("/session/{session_id}/fix/cancel")
async def cancel_fix(session_id: str):
    """Cancel a running or queued fix generation job."""
    _validate_session_id(session_id)
    queue = FixJobQueue.get_instance()
    cancelled = queue.cancel_for_session(session_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active fix job for this session")
    return {"status": "cancelled"}
```

**Step 5: Add job queue cancellation to session cleanup (line 186-218)**

In `_session_cleanup_loop`, after cancelling critic tasks (line 195), add:

```python
                # Cancel any active fix jobs for this session
                try:
                    fix_queue = FixJobQueue.get_instance()
                    fix_queue.cancel_for_session(sid)
                except Exception:
                    pass
```

**Step 6: Start queue in the cleanup loop initialization**

Find where `_session_cleanup_loop` is started (likely in a startup event or background task). Add queue startup there. If it's in `main.py`, add it there. Search for where `_session_cleanup_loop` is called and add `FixJobQueue.get_instance().start()` just before or after.

**Step 7: Verify syntax**

Run: `cd backend && python -c "from src.api.routes_v4 import router_v4; print('OK')" 2>&1`
Expected: `OK`

**Step 8: Commit**

```bash
git add backend/src/api/routes_v4.py
git commit -m "feat(fix-pipeline): route fix generation through job queue, add cancel endpoint"
```

---

### Task 6: Update frontend to show retry progress and cancel

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/Investigation/FixPipelinePanel.tsx`
- Modify: `frontend/src/types/index.ts`

**Step 1: Add `cancelFix` to api.ts**

After the `decideOnFix` function in `frontend/src/services/api.ts` (around line 270), add:

```typescript
export const cancelFix = async (
  sessionId: string
): Promise<{ status: string }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/fix/cancel`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to cancel fix'));
  }
  return response.json();
};
```

**Step 2: Update `FixStatus` type in `frontend/src/types/index.ts`**

Add `'queued'` and `'retrying'` to the `FixStatus` type (line 430):

```typescript
export type FixStatus =
  | 'not_started' | 'queued' | 'generating' | 'retrying' | 'awaiting_review'
  | 'human_feedback' | 'verification_in_progress'
  | 'verified' | 'verification_failed'
  | 'approved' | 'rejected'
  | 'pr_creating' | 'pr_created' | 'failed';
```

**Step 3: Update FixPipelinePanel progress section**

In `frontend/src/components/Investigation/FixPipelinePanel.tsx`:

Add import for `cancelFix`:
```typescript
import { decideOnFix, submitAttestation, cancelFix } from '../../services/api';
```

Add `queued` and `retrying` to `statusConfig` (after line 21):
```typescript
  queued: { label: 'QUEUED', color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' },
  retrying: { label: 'RETRYING', color: 'text-amber-400 bg-amber-500/10 border-amber-500/20' },
```

Update `renderProgressSection` (around line 329) to handle new statuses and show a cancel button:

```tsx
  const handleCancel = async () => {
    setLoading('cancelling');
    setError(null);
    try {
      await cancelFix(sessionId);
      onRefresh();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to cancel fix');
    } finally {
      setLoading(null);
    }
  };

  const renderProgressSection = () => (
    <div className="space-y-2">
      <div className="flex items-center gap-3 py-2">
        <div className="w-5 h-5 border-2 border-slate-700 border-t-emerald-500 rounded-full animate-spin" />
        <div className="flex-1">
          <div className="text-[11px] text-slate-300">
            {fixStatus === 'queued' && 'Fix job queued — waiting for available worker...'}
            {fixStatus === 'generating' && 'Generating fix...'}
            {fixStatus === 'retrying' && 'Retrying fix generation...'}
            {fixStatus === 'verification_in_progress' && 'Verifying generated fix...'}
            {fixStatus === 'pr_creating' && 'Creating pull request...'}
            {fixStatus === 'human_feedback' && 'Processing your feedback...'}
          </div>
          {fixData?.fixed_files && fixData.fixed_files.length > 1 ? (
            <div className="text-[10px] font-mono text-slate-500 mt-0.5">
              {fixData.fixed_files.length} files: {fixData.fixed_files.map(f => f.file_path.split('/').pop()).join(', ')}
            </div>
          ) : fixData?.target_file ? (
            <div className="text-[10px] font-mono text-slate-500 mt-0.5">{fixData.target_file}</div>
          ) : null}
        </div>
        <button
          onClick={handleCancel}
          disabled={loading === 'cancelling'}
          className="text-[9px] font-bold px-2 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 disabled:opacity-50"
        >
          {loading === 'cancelling' ? 'Cancelling...' : 'Cancel'}
        </button>
      </div>
    </div>
  );
```

Also add `'queued'` and `'retrying'` to the condition that renders the progress section. Find the section that checks fixStatus and renders either the generate section or progress section. Ensure:

```tsx
  const isInProgress = ['generating', 'queued', 'retrying', 'verification_in_progress', 'pr_creating', 'human_feedback'].includes(fixStatus);
```

**Step 4: Run type check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to FixStatus.

**Step 5: Run build**

Run: `cd frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/types/index.ts frontend/src/components/Investigation/FixPipelinePanel.tsx
git commit -m "feat(fix-pipeline): frontend shows retry progress, queue position, cancel button"
```

---

### Task 7: Wire up queue startup and add integration test

**Files:**
- Modify: `backend/src/api/main.py` (or wherever FastAPI app startup is configured)
- Create: `backend/tests/test_fix_pipeline_integration.py`

**Step 1: Find and update app startup**

Find where the FastAPI app is created. Add queue startup on `startup` event:

```python
from src.utils.fix_job_queue import FixJobQueue

@app.on_event("startup")
async def startup_fix_queue():
    FixJobQueue.get_instance().start()

@app.on_event("shutdown")
async def shutdown_fix_queue():
    await FixJobQueue.get_instance().shutdown()
```

If `@app.on_event("startup")` already exists, add the queue start call there.

**Step 2: Write integration test**

```python
# backend/tests/test_fix_pipeline_integration.py
"""Integration test: fix job queue processes a mock fix generation."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.fix_job_queue import FixJobQueue, FixJobStatus, RetryableFixError


@pytest.fixture
def fresh_queue():
    """Fresh queue instance (not singleton)."""
    FixJobQueue.reset_instance()
    q = FixJobQueue()
    yield q
    # Cleanup
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(q.shutdown())


@pytest.mark.asyncio
async def test_end_to_end_fix_job(fresh_queue):
    """Submit a job, start workers, verify it completes."""
    results = {}

    async def mock_executor(job):
        job.current_stage = "generating"
        await asyncio.sleep(0.05)
        results["executed"] = True

    job = fresh_queue.submit(session_id="test-sess", executor=mock_executor)
    assert job.status == FixJobStatus.QUEUED

    # Process manually
    await fresh_queue._process_one()

    assert job.status == FixJobStatus.COMPLETED
    assert results.get("executed") is True


@pytest.mark.asyncio
async def test_retry_then_success(fresh_queue):
    """Job should retry on RetryableFixError and eventually succeed."""
    attempt_count = 0

    async def flaky_executor(job):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            raise RetryableFixError("timeout", stage="cloning")

    job = fresh_queue.submit(session_id="test-sess", executor=flaky_executor)
    job._backoff_base = 0.01

    # Process twice (first attempt fails, second succeeds)
    await fresh_queue._process_one()  # fails, re-enqueues
    assert job.status == FixJobStatus.QUEUED  # re-enqueued after backoff
    await fresh_queue._process_one()  # succeeds
    assert job.status == FixJobStatus.COMPLETED
    assert attempt_count == 2


@pytest.mark.asyncio
async def test_cancel_during_execution(fresh_queue):
    """Cancelling a job should stop it."""
    job = fresh_queue.submit(
        session_id="test-sess",
        executor=AsyncMock(side_effect=asyncio.sleep(10)),
    )

    cancelled = fresh_queue.cancel(job.id)
    assert cancelled is True
    assert job.status == FixJobStatus.CANCELLED


@pytest.mark.asyncio
async def test_duplicate_session_rejected(fresh_queue):
    """Second submit for same session should raise ValueError."""
    fresh_queue.submit(session_id="test-sess", executor=AsyncMock())
    with pytest.raises(ValueError, match="already has an active"):
        fresh_queue.submit(session_id="test-sess", executor=AsyncMock())


@pytest.mark.asyncio
async def test_orphan_cleanup(fresh_queue, tmp_path):
    """Orphan temp dirs should be purged on init."""
    import os
    import tempfile

    # Create fake orphan dirs
    d1 = tempfile.mkdtemp(prefix="fix_")
    d2 = tempfile.mkdtemp(prefix="fix_")
    assert os.path.exists(d1)
    assert os.path.exists(d2)

    # Purge
    fresh_queue._purge_orphan_temp_dirs()

    assert not os.path.exists(d1)
    assert not os.path.exists(d2)
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_fix_pipeline_integration.py -v 2>&1 | tail -20`
Expected: All PASS.

**Step 4: Commit**

```bash
git add backend/src/api/main.py backend/tests/test_fix_pipeline_integration.py
git commit -m "feat(fix-pipeline): wire queue startup/shutdown, add integration tests"
```

---

## Summary

| Task | File(s) | Description |
|------|---------|-------------|
| 1 | `fix_job_queue.py`, tests | Core job queue: bounded workers, retry, temp dir tracking |
| 2 | `repo_manager.py`, tests | Sparse checkout support for large repos |
| 3 | `fix_generator.py` | Typed RetryableFixError for transient LLM failures |
| 4 | `supervisor.py`, `fix_generator.py` | Extract `_execute_fix_generation`, route through queue |
| 5 | `routes_v4.py` | Routes use queue, add cancel endpoint, session cleanup |
| 6 | `api.ts`, `index.ts`, `FixPipelinePanel.tsx` | Frontend: retry progress, cancel button, new statuses |
| 7 | `main.py`, integration tests | Wire startup/shutdown, end-to-end tests |
