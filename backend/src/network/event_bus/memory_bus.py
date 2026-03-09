"""In-process event bus using asyncio.Queue — zero external dependencies.

Used as the default transport when ``REDIS_URL`` is not set.  All events
stay within a single process, so this is not suitable for multi-worker
deployments but is perfect for development, testing, and single-instance
production setups.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any

from .base import EventBus, EventHandler
from .errors import BackpressureError

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_MAXSIZE = 10_000


class MemoryEventBus(EventBus):
    """Lightweight in-process pub/sub using ``asyncio.Queue`` per channel.

    * ``publish`` serializes the event to JSON (to match Redis semantics
      and catch serialization bugs early), then enqueues it.
    * ``subscribe`` registers a handler; a per-channel consumer task drains
      the queue and fans out to all registered handlers.
    * Back-pressure: if a channel queue hits ``maxsize`` the oldest event
      is dropped and a warning is logged.
    """

    def __init__(self, maxsize: int = _DEFAULT_QUEUE_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._queues: dict[str, asyncio.Queue[tuple[str, str]]] = {}  # channel -> Queue of (msg_id, json_str)
        self._handlers: dict[str, tuple[str, EventHandler]] = {}  # sub_id -> (channel, handler)
        self._tasks: dict[str, asyncio.Task] = {}  # channel -> consumer task
        self._dlq: dict[str, deque] = {}  # channel -> deque of dead-letter entries
        self._running = False
        self._msg_counter = 0

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        logger.info("MemoryEventBus started (in-process mode)")

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._queues.clear()
        logger.info("MemoryEventBus stopped")

    # ── Publish ────────────────────────────────────────────────────────

    async def publish(self, channel: str, event: dict[str, Any]) -> str:
        """Enqueue the event on the channel's ``asyncio.Queue``.

        Returns a locally-unique message ID.
        """
        queue = self._ensure_queue(channel)

        # ── Backpressure check ────────────────────────────────────────
        if queue.qsize() > self._maxsize * 0.8:
            raise BackpressureError(
                f"Channel '{channel}' queue at {queue.qsize()}/{self._maxsize} "
                f"(>{int(self._maxsize * 0.8)} threshold) — apply backpressure"
            )

        self._msg_counter += 1
        msg_id = f"mem-{self._msg_counter}"

        # Serialize to JSON (mirrors Redis to catch issues early)
        payload = json.dumps(event, default=str)

        if queue.full():
            # Drop oldest to make room — log a warning
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            logger.warning(
                "Channel %s queue full (%d); dropped oldest event",
                channel, self._maxsize,
            )

        queue.put_nowait((msg_id, payload))
        logger.debug("Published %s to %s", msg_id, channel)
        return msg_id

    # ── Subscribe / Unsubscribe ────────────────────────────────────────

    async def subscribe(self, channel: str, handler: EventHandler) -> str:
        sub_id = f"msub-{uuid.uuid4().hex}"
        self._handlers[sub_id] = (channel, handler)

        # Ensure a queue and consumer task exist for this channel
        self._ensure_queue(channel)
        if channel not in self._tasks or self._tasks[channel].done():
            self._tasks[channel] = asyncio.create_task(
                self._consumer_loop(channel),
                name=f"mem-consumer-{channel}",
            )

        logger.info("Subscribed %s to channel %s (in-memory)", sub_id, channel)
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        entry = self._handlers.pop(subscription_id, None)
        if entry is None:
            return

        channel = entry[0]
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
        """Return dead-letter entries for *channel* as a list of dicts."""
        return list(self._dlq.get(channel, []))

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_queue(self, channel: str) -> asyncio.Queue:
        if channel not in self._queues:
            self._queues[channel] = asyncio.Queue(maxsize=self._maxsize)
        return self._queues[channel]

    async def _consumer_loop(self, channel: str) -> None:
        """Drain the channel queue and dispatch to handlers."""
        queue = self._ensure_queue(channel)

        while self._running:
            try:
                msg_id, payload = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Malformed JSON in message %s on %s", msg_id, channel)
                continue

            handlers = [
                handler
                for _, (ch, handler) in self._handlers.items()
                if ch == channel
            ]

            for handler in handlers:
                try:
                    await handler(channel, event)
                except Exception as e:
                    logger.exception(
                        "Handler error processing %s on %s", msg_id, channel,
                    )
                    # Route failed event to dead-letter queue
                    if channel not in self._dlq:
                        self._dlq[channel] = deque(maxlen=10_000)
                    self._dlq[channel].append({
                        "event": event,
                        "error": str(e),
                        "timestamp": time.time(),
                    })
