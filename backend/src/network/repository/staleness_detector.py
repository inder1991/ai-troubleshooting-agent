"""StalenessDetector — periodically scans for stale topology entities.

Queries the repository for all devices, checks their ``last_seen``
timestamp against a configurable threshold, and publishes a
``STALE_DETECTED`` event for each entity that has gone stale.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Union

from ..event_bus.base import EventBus
from ..event_bus.topology_channels import STALE_DETECTED, make_stale_event
from .interface import TopologyRepository

logger = logging.getLogger(__name__)


class StalenessDetector:
    """Scans topology entities and publishes events for stale ones.

    Parameters
    ----------
    repo:
        Any ``TopologyRepository`` implementation (SQLite, Neo4j, ...).
    event_bus:
        The event bus to publish ``STALE_DETECTED`` events on.
    stale_threshold_minutes:
        A device is considered stale if its ``last_seen`` is older than
        ``now - stale_threshold_minutes``.
    """

    def __init__(
        self,
        repo: TopologyRepository,
        event_bus: EventBus,
        stale_threshold_minutes: int = 10,
    ) -> None:
        self._repo = repo
        self._bus = event_bus
        self._threshold = timedelta(minutes=stale_threshold_minutes)
        self._running = False

    # ── Public API ────────────────────────────────────────────────────

    async def scan_once(self) -> int:
        """Scan all devices and publish events for stale ones.

        Returns the number of stale devices detected.
        """
        now = datetime.now(timezone.utc)
        cutoff = now - self._threshold
        devices = self._repo.get_devices()
        stale_count = 0

        for device in devices:
            if self._is_stale(device.last_seen, cutoff):
                last_seen_str = self._to_iso(device.last_seen)
                event = make_stale_event(
                    entity_type="device",
                    entity_id=device.id,
                    last_seen=last_seen_str,
                )
                await self._bus.publish(STALE_DETECTED, event.to_dict())
                stale_count += 1
                logger.info(
                    "Stale device detected: %s (last_seen=%s)",
                    device.id,
                    last_seen_str,
                )

        logger.info(
            "Staleness scan complete: %d stale out of %d devices",
            stale_count,
            len(devices),
        )
        return stale_count

    async def run(self, interval_seconds: int = 60) -> None:
        """Continuously scan at *interval_seconds* until ``stop()`` is called."""
        self._running = True
        logger.info(
            "StalenessDetector started (interval=%ds, threshold=%s)",
            interval_seconds,
            self._threshold,
        )
        while self._running:
            try:
                await self.scan_once()
            except Exception:
                logger.exception("Error during staleness scan")
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        """Signal the run loop to exit after the current iteration."""
        self._running = False
        logger.info("StalenessDetector stop requested")

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _is_stale(last_seen: Union[datetime, str, None], cutoff: datetime) -> bool:
        """Return True if *last_seen* is before *cutoff*.

        Handles datetime objects, ISO-format strings, None, and empty
        strings.  Anything unparseable is treated as stale.
        """
        if last_seen is None or last_seen == "":
            return True

        ts: datetime | None = None

        if isinstance(last_seen, datetime):
            ts = last_seen
        elif isinstance(last_seen, str):
            try:
                ts = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return True  # unparseable → stale
        else:
            return True  # unexpected type → stale

        # Make naive datetimes timezone-aware (assume UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return ts < cutoff

    @staticmethod
    def _to_iso(last_seen: Union[datetime, str, None]) -> str:
        """Best-effort conversion of last_seen to an ISO string."""
        if last_seen is None or last_seen == "":
            return ""
        if isinstance(last_seen, datetime):
            return last_seen.isoformat()
        return str(last_seen)
