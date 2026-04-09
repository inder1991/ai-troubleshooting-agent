"""
Asyncio-based fix job queue with bounded concurrency, retry logic,
and temp directory lifecycle management.

Usage:
    from src.utils.fix_job_queue import FixJobQueue

    queue = FixJobQueue.get_instance()
    await queue.start()
    job = await queue.submit(session_id, executor=my_coroutine)
"""

from __future__ import annotations

import asyncio
import glob
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from src.utils.logger import get_logger

logger = get_logger("fix_job_queue")


# ── Status enum ──────────────────────────────────────────────────────

class FixJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Retryable error ─────────────────────────────────────────────────

class RetryableFixError(Exception):
    """Signals a transient failure that should be retried."""

    def __init__(self, message: str, *, stage: str = "", suggestion: str = ""):
        super().__init__(message)
        self.stage = stage
        self.suggestion = suggestion


# ── Job dataclass ────────────────────────────────────────────────────

@dataclass
class FixJob:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    status: FixJobStatus = FixJobStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempt: int = 0
    max_attempts: int = 3
    error_message: Optional[str] = None
    current_stage: Optional[str] = None
    executor: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _backoff_base: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "error_message": self.error_message,
            "current_stage": self.current_stage,
        }


# ── Queue (singleton) ───────────────────────────────────────────────

class FixJobQueue:
    _instance: Optional[FixJobQueue] = None

    _MAX_WORKERS: int = 2
    _MAX_QUEUE_SIZE: int = 10
    _TEMP_DIR_PREFIX: str = "fix_"

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._MAX_QUEUE_SIZE)
        self._jobs: dict[str, FixJob] = {}
        self._temp_dirs: set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._started: bool = False
        self._shutdown: bool = False

    # ── Singleton ────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> FixJobQueue:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ── Lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._shutdown = False
        self._purge_orphan_temp_dirs()
        for i in range(self._MAX_WORKERS):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)
        logger.info("FixJobQueue started", extra={"workers": self._MAX_WORKERS})

    async def shutdown(self) -> None:
        self._shutdown = True
        # Cancel running jobs
        for job in self._jobs.values():
            if job.status in (FixJobStatus.RUNNING, FixJobStatus.RETRYING):
                if job._task and not job._task.done():
                    job._task.cancel()
                job.status = FixJobStatus.CANCELLED
        # Cancel workers
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        # Clean temp dirs
        for d in list(self._temp_dirs):
            self._cleanup_dir(d)
        self._temp_dirs.clear()
        self._started = False
        logger.info("FixJobQueue shut down")

    # ── Public API ───────────────────────────────────────────────────

    async def submit(
        self,
        session_id: str,
        executor: Callable[[], Coroutine[Any, Any, Any]],
        max_attempts: int = 3,
    ) -> FixJob:
        # Reject if session already has an active job
        if self.get_active_job(session_id) is not None:
            raise ValueError(f"Session {session_id} already has an active job")

        # Reject if queue full
        if self._queue.full():
            raise RuntimeError("Job queue is full — try again later")

        job = FixJob(
            session_id=session_id,
            executor=executor,
            max_attempts=max_attempts,
        )
        self._jobs[job.id] = job
        await self._queue.put(job.id)
        logger.info(
            "Job submitted",
            extra={"session_id": session_id, "job_id": job.id},
        )
        return job

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job._task and not job._task.done():
            job._task.cancel()
        job.status = FixJobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info("Job cancelled", extra={"job_id": job_id})
        return True

    async def cancel_for_session(self, session_id: str) -> bool:
        job = self.get_active_job(session_id)
        if job is None:
            return False
        return await self.cancel(job.id)

    def get_status(self, job_id: str) -> Optional[dict[str, Any]]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return job.to_dict()

    def get_active_job(self, session_id: str) -> Optional[FixJob]:
        active_statuses = {FixJobStatus.QUEUED, FixJobStatus.RUNNING, FixJobStatus.RETRYING}
        for job in self._jobs.values():
            if job.session_id == session_id and job.status in active_statuses:
                return job
        return None

    # ── Temp dir management ──────────────────────────────────────────

    def track_temp_dir(self, path: str) -> None:
        self._temp_dirs.add(path)

    def untrack_temp_dir(self, path: str) -> None:
        self._temp_dirs.discard(path)

    def _cleanup_dir(self, path: str) -> None:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    def _purge_orphan_temp_dirs(self) -> None:
        pattern = f"/tmp/{self._TEMP_DIR_PREFIX}*"
        for d in glob.glob(pattern):
            logger.info("Purging orphan temp dir", extra={"path": d})
            self._cleanup_dir(d)

    # ── Worker internals ─────────────────────────────────────────────

    async def _worker_loop(self, worker_id: int) -> None:
        logger.info(f"Worker {worker_id} started")
        try:
            while not self._shutdown:
                try:
                    await self._process_one()
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception(f"Worker {worker_id} unexpected error")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        logger.info(f"Worker {worker_id} stopped")

    async def _process_one(self) -> None:
        job_id = await self._queue.get()
        job = self._jobs.get(job_id)

        if job is None or job.status == FixJobStatus.CANCELLED:
            return

        job.status = FixJobStatus.RUNNING
        job.attempt += 1
        job.started_at = job.started_at or datetime.now(timezone.utc).isoformat()
        job.error_message = None

        try:
            if job.executor:
                await job.executor()
            job.status = FixJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Job completed",
                extra={"job_id": job.id, "attempt": job.attempt},
            )

        except RetryableFixError as exc:
            job.current_stage = exc.stage
            if job.attempt < job.max_attempts:
                job.status = FixJobStatus.RETRYING
                job.error_message = str(exc)
                backoff = job._backoff_base ** job.attempt
                logger.warning(
                    "Retryable error — re-enqueueing",
                    extra={
                        "job_id": job.id,
                        "attempt": job.attempt,
                        "backoff_s": backoff,
                        "stage": exc.stage,
                        "suggestion": exc.suggestion,
                    },
                )
                await asyncio.sleep(backoff)
                await self._queue.put(job.id)
            else:
                job.status = FixJobStatus.FAILED
                job.error_message = str(exc)
                job.completed_at = datetime.now(timezone.utc).isoformat()
                logger.error(
                    "Job failed after max retries",
                    extra={"job_id": job.id, "attempts": job.attempt},
                )

        except asyncio.CancelledError:
            job.status = FixJobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info("Job cancelled via task", extra={"job_id": job.id})

        except Exception as exc:
            job.status = FixJobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.error(
                "Job failed (non-retryable)",
                extra={"job_id": job.id, "error": str(exc)},
            )
