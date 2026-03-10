"""Async job queue with per-profile concurrency limiting.

Heavy diagnostic operations (EXPLAIN ANALYZE, full pg_stat scans)
are enqueued here instead of running inline. Each profile gets at
most max_concurrent_per_profile simultaneous jobs.
"""

import asyncio
import uuid
from typing import Any, Callable, Coroutine


class JobQueue:
    def __init__(self, max_concurrent_per_profile: int = 1):
        self._max = max_concurrent_per_profile
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._jobs: dict[str, dict] = {}
        self._events: dict[str, asyncio.Event] = {}

    def _get_semaphore(self, profile_id: str) -> asyncio.Semaphore:
        if profile_id not in self._semaphores:
            self._semaphores[profile_id] = asyncio.Semaphore(self._max)
        return self._semaphores[profile_id]

    async def enqueue(
        self,
        profile_id: str,
        tool_name: str,
        coro_factory: Callable[[], Coroutine],
    ) -> str:
        job_id = f"J-{uuid.uuid4().hex[:8]}"
        event = asyncio.Event()
        self._events[job_id] = event
        self._jobs[job_id] = {
            "job_id": job_id,
            "profile_id": profile_id,
            "tool": tool_name,
            "status": "pending",
            "result": None,
            "error": None,
        }

        asyncio.create_task(self._run(job_id, profile_id, coro_factory, event))
        return job_id

    async def _run(
        self,
        job_id: str,
        profile_id: str,
        coro_factory: Callable[[], Coroutine],
        event: asyncio.Event,
    ) -> None:
        sem = self._get_semaphore(profile_id)
        async with sem:
            self._jobs[job_id]["status"] = "running"
            try:
                result = await coro_factory()
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["status"] = "completed"
            except Exception as e:
                self._jobs[job_id]["error"] = str(e)
                self._jobs[job_id]["status"] = "failed"
            finally:
                event.set()

    async def wait_for(self, job_id: str, timeout: float = 30.0) -> Any:
        event = self._events.get(job_id)
        if event is None:
            raise ValueError(f"Unknown job: {job_id}")
        await asyncio.wait_for(event.wait(), timeout=timeout)
        job = self._jobs[job_id]
        if job["status"] == "failed":
            raise RuntimeError(job["error"])
        return job["result"]

    def get_status(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if job is None:
            return {"status": "unknown", "job_id": job_id}
        return {
            "job_id": job["job_id"],
            "profile_id": job["profile_id"],
            "tool": job["tool"],
            "status": job["status"],
        }

    def queue_length(self, profile_id: str) -> int:
        return sum(
            1 for j in self._jobs.values()
            if j["profile_id"] == profile_id and j["status"] == "pending"
        )

    def active_count(self, profile_id: str) -> int:
        return sum(
            1 for j in self._jobs.values()
            if j["profile_id"] == profile_id and j["status"] == "running"
        )
