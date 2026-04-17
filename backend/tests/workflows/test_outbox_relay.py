"""OutboxRelay drains unrelayed Postgres outbox rows to a Sink.

Spec: drain in seq order, mark ``relayed_at``, never lose events on crash
(the same Postgres tx that emits also marks the row). Sink emits must be
idempotent for at-least-once semantics.
"""
from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.database.engine import get_engine, get_session
from src.workflows.outbox_relay import (
    BroadcastSSESink,
    MultiSink,
    OutboxRelay,
    RedisStreamSink,
    _sse_subscribers,
)


_TEST_RUN_ID = f"relay-test-{uuid4().hex}"
_TEST_RUN_ID_BATCH = f"relay-batch-{uuid4().hex}"
_TEST_RUN_ID_EMPTY = f"relay-empty-{uuid4().hex}"
_TEST_RUN_ID_MULTI = f"relay-multi-{uuid4().hex}"
_TEST_RUN_ID_MULTI_FAIL = f"relay-multi-fail-{uuid4().hex}"
_TEST_RUN_ID_REDIS = f"relay-redis-{uuid4().hex}"
_TEST_RUN_ID_SSE = f"relay-sse-{uuid4().hex}"

_ALL_TEST_RUN_IDS = [
    _TEST_RUN_ID,
    _TEST_RUN_ID_BATCH,
    _TEST_RUN_ID_EMPTY,
    _TEST_RUN_ID_MULTI,
    _TEST_RUN_ID_MULTI_FAIL,
    _TEST_RUN_ID_REDIS,
    _TEST_RUN_ID_SSE,
]


@pytest_asyncio.fixture(autouse=True)
async def _isolate_db():
    await get_engine().dispose(close=False)
    await _purge()
    _sse_subscribers.clear()
    yield
    await _purge()
    _sse_subscribers.clear()
    await get_engine().dispose(close=False)


async def _purge() -> None:
    async with get_session() as session:
        async with session.begin():
            await session.execute(
                text("DELETE FROM investigation_outbox WHERE run_id = ANY(:ids)"),
                {"ids": _ALL_TEST_RUN_IDS},
            )


async def _seed(rows: list[tuple[str, int, str, dict]]) -> None:
    async with get_session() as session:
        async with session.begin():
            for run_id, seq, kind, payload in rows:
                await session.execute(
                    text(
                        "INSERT INTO investigation_outbox (run_id, seq, kind, payload) "
                        "VALUES (:r, :s, :k, CAST(:p AS json))"
                    ),
                    {"r": run_id, "s": seq, "k": kind, "p": json.dumps(payload)},
                )


async def _fetch_relayed_at(run_id: str) -> list[tuple[int, bool]]:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT seq, relayed_at IS NOT NULL AS relayed "
                "FROM investigation_outbox WHERE run_id = :r ORDER BY seq"
            ),
            {"r": run_id},
        )
        return [(row.seq, row.relayed) for row in result]


class FakeSink:
    """In-memory sink: records every emit in order."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(
        self, kind: str, payload: dict, *, run_id: str, seq: int
    ) -> None:
        self.events.append(
            {"kind": kind, "payload": payload, "run_id": run_id, "seq": seq}
        )


class _RaisingSink:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    async def emit(self, kind, payload, *, run_id, seq) -> None:
        self.calls += 1
        raise self._exc


@pytest.mark.asyncio
async def test_relay_drains_unrelayed_rows_in_seq_order():
    await _seed(
        [
            (_TEST_RUN_ID, 1, "x", {"v": "a"}),
            (_TEST_RUN_ID, 3, "y", {"v": "c"}),
            (_TEST_RUN_ID, 2, "z", {"v": "b"}),
        ]
    )

    sink = FakeSink()
    relay = OutboxRelay(sink=sink, batch=100)

    drained = await relay.drain_once()

    assert drained == 3
    assert [e["seq"] for e in sink.events] == [1, 2, 3]
    assert [e["kind"] for e in sink.events] == ["x", "z", "y"]

    rows = await _fetch_relayed_at(_TEST_RUN_ID)
    assert rows == [(1, True), (2, True), (3, True)]


@pytest.mark.asyncio
async def test_drain_once_returns_zero_when_outbox_empty():
    sink = FakeSink()
    relay = OutboxRelay(sink=sink, batch=100)

    drained = await relay.drain_once()

    assert drained == 0
    assert sink.events == []


@pytest.mark.asyncio
async def test_drain_once_respects_batch_size():
    await _seed(
        [(_TEST_RUN_ID_BATCH, i, "k", {"i": i}) for i in range(1, 6)]
    )

    sink = FakeSink()
    relay = OutboxRelay(sink=sink, batch=2)

    first = await relay.drain_once()
    second = await relay.drain_once()
    third = await relay.drain_once()
    fourth = await relay.drain_once()

    assert (first, second, third, fourth) == (2, 2, 1, 0)
    assert [e["seq"] for e in sink.events] == [1, 2, 3, 4, 5]
    rows = await _fetch_relayed_at(_TEST_RUN_ID_BATCH)
    assert all(relayed for _, relayed in rows)


@pytest.mark.asyncio
async def test_drain_once_does_not_re_emit_relayed_rows():
    await _seed([(_TEST_RUN_ID_EMPTY, 1, "k", {})])
    sink = FakeSink()
    relay = OutboxRelay(sink=sink, batch=100)

    assert await relay.drain_once() == 1
    assert await relay.drain_once() == 0
    assert len(sink.events) == 1


@pytest.mark.asyncio
async def test_multi_sink_partial_failure_still_marks_relayed():
    """Policy: as long as at least one inner sink succeeds, the row is relayed.

    Justification: at-least-once delivery is the invariant. A single sink
    failing (e.g., a Redis blip) shouldn't block the SSE broadcaster from
    fanning out to live clients — and re-draining would produce duplicates
    on the working sink.
    """
    await _seed([(_TEST_RUN_ID_MULTI, 1, "k", {"v": 1})])

    good = FakeSink()
    bad = _RaisingSink(RuntimeError("redis down"))
    multi = MultiSink([bad, good])

    relay = OutboxRelay(sink=multi, batch=100)
    drained = await relay.drain_once()

    assert drained == 1
    assert good.events == [
        {"kind": "k", "payload": {"v": 1}, "run_id": _TEST_RUN_ID_MULTI, "seq": 1}
    ]
    assert bad.calls == 1
    rows = await _fetch_relayed_at(_TEST_RUN_ID_MULTI)
    assert rows == [(1, True)]


@pytest.mark.asyncio
async def test_multi_sink_all_failures_propagate():
    """Policy: if every sink raises, re-raise so the row stays unrelayed."""
    await _seed([(_TEST_RUN_ID_MULTI_FAIL, 1, "k", {})])

    bad1 = _RaisingSink(RuntimeError("redis down"))
    bad2 = _RaisingSink(RuntimeError("sse offline"))
    multi = MultiSink([bad1, bad2])

    relay = OutboxRelay(sink=multi, batch=100)

    with pytest.raises(RuntimeError):
        await relay.drain_once()

    rows = await _fetch_relayed_at(_TEST_RUN_ID_MULTI_FAIL)
    assert rows == [(1, False)]


@pytest.mark.asyncio
async def test_broadcast_sse_sink_delivers_to_subscribers():
    sink = BroadcastSSESink()
    queue = sink.subscribe(_TEST_RUN_ID_SSE)

    await sink.emit(
        "step_update", {"step_id": "s1"}, run_id=_TEST_RUN_ID_SSE, seq=7
    )

    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert msg == {
        "kind": "step_update",
        "payload": {"step_id": "s1"},
        "seq": 7,
        "run_id": _TEST_RUN_ID_SSE,
    }


@pytest.mark.asyncio
async def test_broadcast_sse_sink_with_no_subscribers_is_noop():
    sink = BroadcastSSESink()
    await sink.emit("k", {}, run_id="nobody-listening", seq=1)


def _redis_reachable() -> bool:
    if os.environ.get("SKIP_REDIS_TESTS"):
        return False
    try:
        import redis
    except ImportError:
        return False
    try:
        client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            socket_connect_timeout=1,
        )
        client.ping()
        client.close()
        return True
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis unreachable; RedisStreamSink integration smoke skipped",
)
async def test_redis_stream_sink_writes_xadd():
    import redis.asyncio as aredis

    client = aredis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
    )
    stream_key = f"investigation:{_TEST_RUN_ID_REDIS}:events"
    try:
        await client.delete(stream_key)
        sink = RedisStreamSink(client)
        await sink.emit(
            "step_update", {"step_id": "s1"}, run_id=_TEST_RUN_ID_REDIS, seq=4
        )
        entries = await client.xrange(stream_key)
        assert len(entries) == 1
        _, fields = entries[0]
        decoded = {
            (k.decode() if isinstance(k, bytes) else k):
                (v.decode() if isinstance(v, bytes) else v)
            for k, v in fields.items()
        }
        assert decoded["kind"] == "step_update"
        assert decoded["seq"] == "4"
        assert json.loads(decoded["payload"]) == {"step_id": "s1"}
    finally:
        await client.delete(stream_key)
        await client.aclose()


@pytest.mark.asyncio
async def test_run_forever_drains_then_cancels_cleanly():
    await _seed([(_TEST_RUN_ID, i, "k", {"i": i}) for i in range(1, 4)])

    sink = FakeSink()
    relay = OutboxRelay(sink=sink, batch=100, poll_ms=10)

    task = asyncio.create_task(relay.run_forever())
    for _ in range(50):
        if len(sink.events) == 3:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [e["seq"] for e in sink.events] == [1, 2, 3]
