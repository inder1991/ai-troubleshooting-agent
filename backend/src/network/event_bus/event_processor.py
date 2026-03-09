"""Central event processor that routes bus events to storage backends.

Subscribes to every channel on the event bus and batches writes into the
appropriate store (traps, syslog, metrics).  Includes:

* **Batching** -- accumulate up to ``BATCH_SIZE`` events or ``BATCH_WINDOW_S``
  seconds, whichever comes first, then flush.
* **Deduplication** -- a sliding window rejects events whose
  ``(channel, key-fields)`` hash was already seen within the last
  ``DEDUP_WINDOW_S`` seconds.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from .base import EventBus, ALL_CHANNELS, TRAPS, SYSLOG, FLOWS, METRICS, ALERTS

logger = logging.getLogger(__name__)

# ── Tunables ───────────────────────────────────────────────────────────

BATCH_SIZE = 100
BATCH_WINDOW_S = 1.0
DEDUP_WINDOW_S = 5.0

# Fields used to compute the dedup hash per channel
_DEDUP_KEYS: dict[str, list[str]] = {
    TRAPS: ["device_id", "oid", "value", "timestamp"],
    SYSLOG: ["device_id", "facility", "severity", "message"],
    FLOWS: ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"],
    METRICS: ["device_id", "metric", "value"],
    ALERTS: ["rule_id", "device_id", "severity"],
}


class EventProcessor:
    """Routes events from the bus into storage backends with batching and dedup.

    Parameters
    ----------
    bus:
        The ``EventBus`` instance to subscribe on.
    event_store:
        Storage backend exposing ``insert_trap_batch`` / ``insert_syslog_batch``.
        May be ``None`` if trap/syslog persistence is not configured.
    metrics_store:
        ``MetricsStore`` instance for writing device/flow metrics.
        May be ``None`` if InfluxDB is not configured.
    """

    def __init__(
        self,
        bus: EventBus,
        event_store: Any = None,
        metrics_store: Any = None,
    ) -> None:
        self._bus = bus
        self._event_store = event_store
        self._metrics_store = metrics_store

        # Per-channel accumulation buffers
        self._buffers: dict[str, list[dict[str, Any]]] = {ch: [] for ch in ALL_CHANNELS}
        self._buffer_locks: dict[str, asyncio.Lock] = {ch: asyncio.Lock() for ch in ALL_CHANNELS}

        # Dedup: hash -> expiry timestamp
        self._seen: dict[str, float] = {}
        self._seen_lock = asyncio.Lock()

        self._subscription_ids: list[str] = []
        self._flush_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Subscribe to all channels and start the flush timer."""
        self._running = True

        for channel in ALL_CHANNELS:
            sub_id = await self._bus.subscribe(channel, self._on_event)
            self._subscription_ids.append(sub_id)

        self._flush_task = asyncio.create_task(
            self._flush_loop(), name="event-processor-flush"
        )
        self._cleanup_task = asyncio.create_task(
            self._dedup_cleanup_loop(), name="event-processor-dedup-cleanup"
        )
        logger.info("EventProcessor started on %d channels", len(ALL_CHANNELS))

    async def stop(self) -> None:
        """Unsubscribe, flush remaining buffers, and cancel background tasks."""
        self._running = False

        for sub_id in self._subscription_ids:
            await self._bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Final flush of any remaining events
        for channel in ALL_CHANNELS:
            await self._flush_channel(channel)

        logger.info("EventProcessor stopped")

    # ── Event handler (called by the bus) ──────────────────────────────

    async def _on_event(self, channel: str, event: dict[str, Any]) -> None:
        """Receive a single event, dedup, and buffer for batch flush."""
        if await self._is_duplicate(channel, event):
            logger.debug("Duplicate event on %s dropped", channel)
            return

        batch: list[dict[str, Any]] | None = None

        async with self._buffer_locks[channel]:
            self._buffers[channel].append(event)

            # Flush immediately when buffer hits threshold
            if len(self._buffers[channel]) >= BATCH_SIZE:
                batch = self._buffers[channel][:]
                self._buffers[channel].clear()

        # Flush outside the lock if threshold was reached
        if batch is not None:
            await self._write_batch(channel, batch)

    # ── Deduplication ──────────────────────────────────────────────────

    async def _is_duplicate(self, channel: str, event: dict[str, Any]) -> bool:
        """Return True if this event's key-field hash was seen within the dedup window."""
        key_fields = _DEDUP_KEYS.get(channel, [])
        raw = channel + "|" + "|".join(
            str(event.get(k, "")) for k in key_fields
        )
        digest = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

        now = time.monotonic()
        async with self._seen_lock:
            expiry = self._seen.get(digest)
            if expiry is not None and now < expiry:
                return True
            self._seen[digest] = now + DEDUP_WINDOW_S
        return False

    async def _dedup_cleanup_loop(self) -> None:
        """Periodically prune expired dedup entries to bound memory."""
        while self._running:
            try:
                await asyncio.sleep(DEDUP_WINDOW_S * 2)
                now = time.monotonic()
                async with self._seen_lock:
                    expired = [k for k, exp in self._seen.items() if now >= exp]
                    for k in expired:
                        del self._seen[k]
                    if expired:
                        logger.debug("Dedup cleanup: pruned %d entries", len(expired))
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Dedup cleanup error")

    # ── Batch flush ────────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        """Timer-based flush: every ``BATCH_WINDOW_S`` seconds, flush all channels."""
        while self._running:
            try:
                await asyncio.sleep(BATCH_WINDOW_S)
                for channel in ALL_CHANNELS:
                    await self._flush_channel(channel)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Flush loop error")

    async def _flush_channel(self, channel: str) -> None:
        """Drain the buffer for *channel* and write the batch."""
        async with self._buffer_locks[channel]:
            if not self._buffers[channel]:
                return
            batch = self._buffers[channel][:]
            self._buffers[channel].clear()

        await self._write_batch(channel, batch)

    async def _write_batch(self, channel: str, batch: list[dict[str, Any]]) -> None:
        """Route the batch to the appropriate storage backend."""
        if not batch:
            return

        count = len(batch)
        try:
            if channel == TRAPS:
                await self._write_traps(batch)
            elif channel == SYSLOG:
                await self._write_syslog(batch)
            elif channel == FLOWS:
                await self._write_flows(batch)
            elif channel == METRICS:
                await self._write_metrics(batch)
            elif channel == ALERTS:
                await self._write_alerts(batch)
            else:
                logger.warning("Unknown channel %s — dropped %d events", channel, count)
                return

            logger.debug("Flushed %d events on %s", count, channel)
        except Exception:
            logger.exception("Failed to write %d events on %s", count, channel)

    # ── Per-channel write helpers ──────────────────────────────────────

    async def _write_traps(self, batch: list[dict[str, Any]]) -> None:
        if self._event_store is None:
            logger.debug("No event_store configured; dropping %d traps", len(batch))
            return
        await self._event_store.insert_trap_batch(batch)

    async def _write_syslog(self, batch: list[dict[str, Any]]) -> None:
        if self._event_store is None:
            logger.debug("No event_store configured; dropping %d syslog events", len(batch))
            return
        await self._event_store.insert_syslog_batch(batch)

    async def _write_flows(self, batch: list[dict[str, Any]]) -> None:
        if self._metrics_store is None:
            return
        for event in batch:
            try:
                await self._metrics_store.write_device_metric(
                    device_id=event.get("device_id", "unknown"),
                    metric=event.get("metric", "flow_bytes"),
                    value=float(event.get("value", 0)),
                )
            except Exception:
                logger.debug("Skipped malformed flow event: %s", event)

    async def _write_metrics(self, batch: list[dict[str, Any]]) -> None:
        if self._metrics_store is None:
            return
        for event in batch:
            try:
                await self._metrics_store.write_device_metric(
                    device_id=event.get("device_id", "unknown"),
                    metric=event.get("metric", ""),
                    value=float(event.get("value", 0)),
                )
            except Exception:
                logger.debug("Skipped malformed metric event: %s", event)

    async def _write_alerts(self, batch: list[dict[str, Any]]) -> None:
        if self._metrics_store is None:
            return
        for event in batch:
            try:
                await self._metrics_store.write_alert_event(
                    device_id=event.get("device_id", "unknown"),
                    rule_id=event.get("rule_id", ""),
                    severity=event.get("severity", "info"),
                    value=float(event.get("value", 0)),
                    threshold=float(event.get("threshold", 0)),
                    message=event.get("message", ""),
                )
            except Exception:
                logger.debug("Skipped malformed alert event: %s", event)
