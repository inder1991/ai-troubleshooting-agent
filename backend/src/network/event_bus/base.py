"""Abstract event bus interface for network event distribution.

All concrete implementations (Redis Streams, in-memory queues) share this
contract so upstream code never couples to a transport.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable

# ── Channel Constants ──────────────────────────────────────────────────

TRAPS = "network.traps"
SYSLOG = "network.syslog"
FLOWS = "network.flows"
METRICS = "network.metrics"
ALERTS = "network.alerts"

ALL_CHANNELS = [TRAPS, SYSLOG, FLOWS, METRICS, ALERTS]

# Handler signature: async def handler(channel: str, event: dict) -> None
EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class EventBus(ABC):
    """Publish/subscribe event bus for network monitoring events.

    Implementations guarantee at-least-once delivery within a single
    process (MemoryEventBus) or across a cluster (RedisEventBus).
    """

    @abstractmethod
    async def publish(self, channel: str, event: dict[str, Any]) -> str:
        """Publish an event to *channel*.

        Returns an implementation-specific message ID (Redis Stream ID,
        UUID for in-memory, etc.).
        """

    @abstractmethod
    async def subscribe(
        self, channel: str, handler: EventHandler
    ) -> str:
        """Register *handler* for events on *channel*.

        Returns a subscription ID that can be passed to ``unsubscribe``.
        """

    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a previously registered subscription."""

    @abstractmethod
    async def start(self) -> None:
        """Start background consumer tasks / connections."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully tear down consumers and close connections."""

    @abstractmethod
    def get_dlq(self, channel: str) -> list[dict]:
        """Return dead-letter entries for *channel*.

        Each entry is a dict with keys ``event``, ``error``, and ``timestamp``.
        """
