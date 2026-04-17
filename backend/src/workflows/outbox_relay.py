"""Polling relay: drains the Postgres outbox to live Sinks.

Pairs with ``OutboxWriter`` (Task 1.3). The writer commits ``(state, event)``
pairs atomically; this relay reads unrelayed events in seq order, hands each
to a ``Sink`` (Redis Streams + in-memory SSE broadcaster in production), then
marks the row ``relayed_at = now()`` inside the same Postgres transaction.

Crash semantics: a process killed mid-drain leaves rows un-marked, so the
next ``drain_once`` re-emits them. Sinks must be idempotent — at-least-once
is the contract.

Per project rules there is no in-memory fallback. If the DB is unreachable,
``drain_once`` propagates the exception. ``run_forever`` catches per-iteration
exceptions so a transient blip doesn't kill the loop, but ``CancelledError``
is always re-raised so callers can shut down the task.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable, Protocol

from sqlalchemy import func, select

from src.database.engine import get_session
from src.database.models import Outbox

logger = logging.getLogger(__name__)


class Sink(Protocol):
    async def emit(
        self, kind: str, payload: dict[str, Any], *, run_id: str, seq: int
    ) -> None: ...


class OutboxRelay:
    def __init__(self, sink: Sink, batch: int = 500, poll_ms: int = 200) -> None:
        self._sink = sink
        self._batch = batch
        self._poll_ms = poll_ms

    async def drain_once(self) -> int:
        async with get_session() as session:
            async with session.begin():
                stmt = (
                    select(Outbox)
                    .where(Outbox.relayed_at.is_(None))
                    .order_by(Outbox.run_id, Outbox.seq)
                    .limit(self._batch)
                )
                result = await session.execute(stmt)
                # Materialise the cursor before iterating: SQLAlchemy's async
                # result is single-shot, and we both iterate (to emit) and need
                # the count after the loop. The plan's pseudocode called
                # ``len(rows.all())`` *after* ``rows.scalars()`` consumed the
                # cursor — that always returns 0.
                rows = list(result.scalars().all())
                for row in rows:
                    await self._sink.emit(
                        row.kind,
                        row.payload,
                        run_id=row.run_id,
                        seq=row.seq,
                    )
                    row.relayed_at = func.now()
                return len(rows)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.drain_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("OutboxRelay drain iteration failed")
            await asyncio.sleep(self._poll_ms / 1000)


class RedisStreamSink:
    """Writes events to Redis Stream ``investigation:{run_id}:events`` via XADD.

    Cross-process fan-out: any worker can XREAD the stream to follow a run.
    """

    def __init__(self, client: Any, key_template: str = "investigation:{run_id}:events") -> None:
        self._client = client
        self._key_template = key_template

    async def emit(
        self, kind: str, payload: dict[str, Any], *, run_id: str, seq: int
    ) -> None:
        await self._client.xadd(
            self._key_template.format(run_id=run_id),
            {
                "kind": kind,
                "seq": str(seq),
                "payload": json.dumps(payload),
            },
        )


# Module-level registry: run_id -> list of subscriber queues. Lives in-process,
# so it only fans out to SSE clients connected to the same worker. For
# cross-worker fan-out, clients XREAD the Redis stream instead.
_sse_subscribers: dict[str, list[asyncio.Queue]] = {}


class BroadcastSSESink:
    """In-memory broadcaster: hands each event to every subscriber queue.

    SSE handlers (wired in a later task) call ``subscribe(run_id)`` to get a
    queue, then ``async for`` over it. ``unsubscribe`` is idempotent — safe to
    call from a ``finally`` block when the client disconnects.
    """

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        _sse_subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        subs = _sse_subscribers.get(run_id)
        if not subs:
            return
        try:
            subs.remove(queue)
        except ValueError:
            return
        if not subs:
            _sse_subscribers.pop(run_id, None)

    async def emit(
        self, kind: str, payload: dict[str, Any], *, run_id: str, seq: int
    ) -> None:
        for queue in list(_sse_subscribers.get(run_id, ())):
            await queue.put(
                {"kind": kind, "payload": payload, "run_id": run_id, "seq": seq}
            )


class MultiSink:
    """Fan-out to a list of inner sinks.

    Failure policy (deliberate, see test_multi_sink_*):
      - emit each inner sink sequentially, swallowing per-sink exceptions
      - if at least one inner sink succeeded, return normally so the relay
        marks the row relayed (avoids re-delivery duplicates on the working
        sinks)
      - if every inner sink raised, re-raise the last exception so the relay
        leaves the row unrelayed and the next drain retries
    """

    def __init__(self, sinks: Iterable[Sink]) -> None:
        self._sinks = list(sinks)
        if not self._sinks:
            raise ValueError("MultiSink requires at least one inner sink")

    async def emit(
        self, kind: str, payload: dict[str, Any], *, run_id: str, seq: int
    ) -> None:
        last_exc: Exception | None = None
        any_success = False
        for sink in self._sinks:
            try:
                await sink.emit(kind, payload, run_id=run_id, seq=seq)
                any_success = True
            except Exception as exc:
                last_exc = exc
                logger.exception(
                    "Sink %s failed to emit run_id=%s seq=%s kind=%s",
                    type(sink).__name__,
                    run_id,
                    seq,
                    kind,
                )
        if not any_success and last_exc is not None:
            raise last_exc
