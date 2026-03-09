"""Redis Streams-backed event bus with consumer groups for horizontal scaling."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from .base import EventBus, EventHandler, ALL_CHANNELS
from .errors import BackpressureError

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────

_DEFAULT_CONSUMER_GROUP = os.getenv("EVENT_BUS_GROUP", "debugduck")
_DEFAULT_BLOCK_MS = 1_000
_STREAM_MAXLEN = 100_000
_RECONNECT_DELAY_S = 2.0
_MAX_RECONNECT_DELAY_S = 30.0


class RedisEventBus(EventBus):
    """Publish/subscribe bus backed by Redis Streams.

    * ``publish`` appends to a stream via ``XADD`` (automatic ``*`` ID).
    * ``subscribe`` spawns an ``asyncio.Task`` that reads via ``XREADGROUP``
      so multiple workers can share load within the same consumer group.
    * Streams are trimmed to ~100 000 entries to bound memory.
    * Lost connections are retried with exponential back-off.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        consumer_group: str = _DEFAULT_CONSUMER_GROUP,
        consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._group = consumer_group
        self._consumer = consumer_name or f"consumer-{uuid.uuid4().hex[:8]}"
        self._redis: Any = None  # redis.asyncio.Redis instance
        self._handlers: dict[str, tuple[str, EventHandler]] = {}  # sub_id -> (channel, handler)
        self._tasks: dict[str, asyncio.Task] = {}  # channel -> reader task
        self._running = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect to Redis and ensure consumer groups exist on all channels."""
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
            retry_on_timeout=True,
        )
        # Verify connectivity
        await self._redis.ping()
        logger.info("RedisEventBus connected to %s", self._redis_url)

        # Ensure consumer groups exist (idempotent)
        for channel in ALL_CHANNELS:
            try:
                await self._redis.xgroup_create(
                    name=channel,
                    groupname=self._group,
                    id="0",
                    mkstream=True,
                )
                logger.debug("Created consumer group '%s' on stream '%s'", self._group, channel)
            except Exception as exc:
                # BUSYGROUP means group already exists — perfectly fine
                if "BUSYGROUP" not in str(exc):
                    logger.warning("xgroup_create failed for %s: %s", channel, exc)

        self._running = True

    async def stop(self) -> None:
        """Cancel all consumer tasks and close the Redis connection."""
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        logger.info("RedisEventBus stopped")

    # ── Publish ────────────────────────────────────────────────────────

    async def publish(self, channel: str, event: dict[str, Any]) -> str:
        """XADD the event as a JSON-encoded ``data`` field.

        The stream is approximately trimmed to ``_STREAM_MAXLEN`` entries.
        """
        if self._redis is None:
            raise RuntimeError("RedisEventBus not started — call start() first")

        # ── Backpressure check ────────────────────────────────────────
        stream_len = await self._redis.xlen(channel)
        threshold = int(_STREAM_MAXLEN * 0.8)
        if stream_len > threshold:
            raise BackpressureError(
                f"Channel '{channel}' stream at {stream_len}/{_STREAM_MAXLEN} "
                f"(>{threshold} threshold) — apply backpressure"
            )

        payload = {"data": json.dumps(event, default=str)}
        msg_id: str = await self._redis.xadd(
            name=channel,
            fields=payload,
            maxlen=_STREAM_MAXLEN,
            approximate=True,
        )
        logger.debug("Published to %s: %s", channel, msg_id)
        return msg_id

    # ── Subscribe / Unsubscribe ────────────────────────────────────────

    async def subscribe(self, channel: str, handler: EventHandler) -> str:
        sub_id = f"sub-{uuid.uuid4().hex}"
        self._handlers[sub_id] = (channel, handler)

        # Start a consumer task for this channel if one isn't running
        if channel not in self._tasks or self._tasks[channel].done():
            self._tasks[channel] = asyncio.create_task(
                self._consumer_loop(channel),
                name=f"redis-consumer-{channel}",
            )

        logger.info("Subscribed %s to channel %s", sub_id, channel)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        entry = self._handlers.pop(subscription_id, None)
        if entry is None:
            return

        channel = entry[0]
        # If no remaining handlers on this channel, cancel its task
        remaining = any(ch == channel for ch, _ in self._handlers.values())
        if not remaining and channel in self._tasks:
            self._tasks[channel].cancel()
            try:
                await self._tasks[channel]
            except asyncio.CancelledError:
                pass
            del self._tasks[channel]

        logger.info("Unsubscribed %s from channel %s", subscription_id, channel)

    # ── Dead-letter queue ──────────────────────────────────────────────

    def get_dlq(self, channel: str) -> list[dict]:
        """Return an empty list — DLQ entries live in Redis ``{channel}:dlq``.

        A full implementation would XRANGE the DLQ stream; for now callers
        should query Redis directly if they need historical failures.
        """
        return []

    # ── Consumer loop (XREADGROUP) ─────────────────────────────────────

    async def _consumer_loop(self, channel: str) -> None:
        """Read from the stream using XREADGROUP, dispatch to handlers.

        Automatically acknowledges messages after successful handler dispatch.
        Reconnects with exponential back-off on connection loss.
        """
        delay = _RECONNECT_DELAY_S

        while self._running:
            try:
                results = await self._redis.xreadgroup(
                    groupname=self._group,
                    consumername=self._consumer,
                    streams={channel: ">"},
                    count=100,
                    block=_DEFAULT_BLOCK_MS,
                )

                if not results:
                    continue

                # Reset back-off on successful read
                delay = _RECONNECT_DELAY_S

                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        await self._dispatch(channel, msg_id, fields)

            except asyncio.CancelledError:
                logger.debug("Consumer loop for %s cancelled", channel)
                return
            except Exception as exc:
                if not self._running:
                    return
                logger.warning(
                    "Redis consumer error on %s (retry in %.1fs): %s",
                    channel, delay, exc,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY_S)

    async def _dispatch(
        self, channel: str, msg_id: str, fields: dict[str, str]
    ) -> None:
        """Decode the event and fan out to every handler registered for *channel*."""
        raw = fields.get("data")
        if raw is None:
            logger.warning("Message %s on %s missing 'data' field", msg_id, channel)
            await self._redis.xack(channel, self._group, msg_id)
            return

        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Malformed JSON in message %s on %s", msg_id, channel)
            await self._redis.xack(channel, self._group, msg_id)
            return

        handlers = [
            handler
            for sub_id, (ch, handler) in self._handlers.items()
            if ch == channel
        ]

        for handler in handlers:
            try:
                await handler(channel, event)
            except Exception as e:
                logger.exception(
                    "Handler error processing %s on %s", msg_id, channel,
                )
                # Route failed event to Redis dead-letter stream
                try:
                    dlq_payload = {
                        "data": json.dumps(event, default=str),
                        "error": str(e),
                    }
                    await self._redis.xadd(
                        name=f"{channel}:dlq",
                        fields=dlq_payload,
                        maxlen=10_000,
                        approximate=True,
                    )
                except Exception:
                    logger.exception("Failed to write to DLQ for %s", channel)

        # ACK after all handlers have run (at-least-once semantics)
        await self._redis.xack(channel, self._group, msg_id)
