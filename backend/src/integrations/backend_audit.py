"""Audit logging for every external-backend call.

Every tool dispatch — ELK search, Prometheus query, K8s list, Jira issue —
writes one row into ``backend_call_audit`` with run_id / agent / tool /
backend / duration / response code / error. The row survives restart so
incident postmortems can reconstruct 'which calls did agent X make, in
which order, at what latency, with what failures'.

Writes are async fire-and-forget via a bounded asyncio.Queue. A slow DB
can't back-pressure a live investigation; when the queue fills the oldest
pending entry is dropped and a counter ticks so operators notice.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from sqlalchemy import text

from src.database.engine import get_session

logger = logging.getLogger(__name__)


_QUEUE_MAX: int = 1000
_MAX_ERROR_LEN: int = 1024


@dataclass(frozen=True)
class AuditRow:
    run_id: str
    agent: str
    tool: str
    backend: str
    query_hash: str
    response_code: Optional[int]
    duration_ms: int
    bytes: Optional[int]
    error: Optional[str]


def hash_query(tool: str, params: dict | str) -> str:
    payload = params if isinstance(params, str) else json.dumps(
        params, sort_keys=True, default=str
    )
    return hashlib.sha256(f"{tool}|{payload}".encode()).hexdigest()


class BackendAudit:
    """Bounded queue + background drainer writing rows to Postgres."""

    def __init__(self, *, queue_max: int = _QUEUE_MAX) -> None:
        self._queue: asyncio.Queue[AuditRow] = asyncio.Queue(maxsize=queue_max)
        self._drops: int = 0
        self._writes: int = 0
        self._drainer_task: Optional[asyncio.Task[None]] = None
        self._stopping: asyncio.Event = asyncio.Event()

    async def start(self) -> None:
        """Start the background drainer. Idempotent."""
        if self._drainer_task is not None and not self._drainer_task.done():
            return
        self._stopping.clear()
        self._drainer_task = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        self._stopping.set()
        task = self._drainer_task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        self._drainer_task = None

    def record(
        self,
        *,
        run_id: str,
        agent: str,
        tool: str,
        backend: str,
        params: dict,
        response_code: Optional[int],
        duration_ms: int,
        bytes_: Optional[int] = None,
        error: Optional[str] = None,
    ) -> None:
        """Enqueue an audit row. Never blocks, never raises.

        If the queue is full, we drop the OLDEST pending row in favour of
        the new one — recent events are more useful for 'what just happened'
        analysis than a stale backlog.
        """
        row = AuditRow(
            run_id=run_id,
            agent=agent,
            tool=tool,
            backend=backend,
            query_hash=hash_query(tool, params),
            response_code=response_code,
            duration_ms=duration_ms,
            bytes=bytes_,
            error=(error[:_MAX_ERROR_LEN] if error else None),
        )
        try:
            self._queue.put_nowait(row)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._drops += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(row)
            except asyncio.QueueFull:
                self._drops += 1

    async def flush(self) -> None:
        """Drain the queue synchronously — used by tests."""
        while not self._queue.empty():
            row = await self._queue.get()
            await self._write_row(row)
            self._queue.task_done()

    async def _drain(self) -> None:
        while not self._stopping.is_set():
            try:
                row = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await self._write_row(row)
            finally:
                self._queue.task_done()

    async def _write_row(self, row: AuditRow) -> None:
        try:
            async with get_session() as session:
                async with session.begin():
                    await session.execute(
                        text(
                            "INSERT INTO backend_call_audit ("
                            "run_id, agent, tool, backend, query_hash, "
                            "response_code, duration_ms, bytes, error"
                            ") VALUES ("
                            ":run_id, :agent, :tool, :backend, :query_hash, "
                            ":response_code, :duration_ms, :bytes, :error"
                            ")"
                        ),
                        dict(
                            run_id=row.run_id,
                            agent=row.agent,
                            tool=row.tool,
                            backend=row.backend,
                            query_hash=row.query_hash,
                            response_code=row.response_code,
                            duration_ms=row.duration_ms,
                            bytes=row.bytes,
                            error=row.error,
                        ),
                    )
            self._writes += 1
        except Exception as exc:
            logger.warning("backend_audit write failed: %s", exc)

    def snapshot(self) -> dict:
        return {
            "queued": self._queue.qsize(),
            "queue_max": self._queue.maxsize,
            "writes": self._writes,
            "drops": self._drops,
        }


@asynccontextmanager
async def timed_call(
    audit: BackendAudit,
    *,
    run_id: str,
    agent: str,
    tool: str,
    backend: str,
    params: dict,
) -> AsyncIterator[dict]:
    """Wrap a tool call to auto-audit on success AND failure.

    Usage:
        async with timed_call(audit, run_id=..., agent=..., tool=...,
                              backend=..., params=...) as ctx:
            resp = await some_call()
            ctx["response_code"] = resp.status_code
            ctx["bytes"] = len(resp.content)
    """
    start = time.monotonic()
    ctx: dict[str, Any] = {"response_code": None, "bytes": None, "error": None}
    try:
        yield ctx
    except Exception as exc:
        ctx["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        audit.record(
            run_id=run_id,
            agent=agent,
            tool=tool,
            backend=backend,
            params=params,
            response_code=ctx.get("response_code"),
            duration_ms=duration_ms,
            bytes_=ctx.get("bytes"),
            error=ctx.get("error"),
        )
