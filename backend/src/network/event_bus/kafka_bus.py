"""Kafka-backed event bus for production-grade distributed event streaming.

Uses ``confluent-kafka`` under the hood.  The library is an **optional**
dependency — if it is not installed the module still imports cleanly but
``KafkaEventBus.__init__`` raises ``ImportError`` at construction time.

Kafka topics are derived from channel names by replacing dots with hyphens
(e.g. ``network.flows`` → ``network-flows``).

Note: the consumer polling loop is *not* implemented yet.  ``subscribe``
registers handlers but actual message dispatch will land in a follow-up PR
once the consumer-group rebalancing strategy is finalized.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .base import EventBus, EventHandler

logger = logging.getLogger(__name__)

# ── Optional dependency gate ──────────────────────────────────────────

try:
    import confluent_kafka  # noqa: F401
    from confluent_kafka import Producer as _KafkaProducer

    HAS_KAFKA = True
except ImportError:  # pragma: no cover — CI may not have confluent-kafka
    HAS_KAFKA = False
    _KafkaProducer = None  # type: ignore[assignment, misc]


def _channel_to_topic(channel: str) -> str:
    """Convert a dot-separated channel name to a Kafka-friendly topic."""
    return channel.replace(".", "-")


class KafkaEventBus(EventBus):
    """Publish/subscribe bus backed by Apache Kafka via *confluent-kafka*.

    * ``publish`` produces a JSON-encoded message to the Kafka topic derived
      from the channel name.
    * ``subscribe`` registers a handler locally (consumer polling is TBD).
    * ``get_dlq`` returns an empty list — Kafka dead-letters are managed via
      a dedicated ``<topic>.dlq`` topic (not yet wired).

    Parameters
    ----------
    bootstrap_servers:
        Comma-separated ``host:port`` list for the Kafka cluster.
    group_id:
        Consumer group ID for offset management.
    client_id:
        Unique client identifier.  Auto-generated if not supplied.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "debugduck-topology",
        client_id: str | None = None,
    ) -> None:
        if not HAS_KAFKA:
            raise ImportError(
                "confluent-kafka is required for KafkaEventBus but is not installed. "
                "Install it with: pip install confluent-kafka"
            )

        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._client_id = client_id or f"debugduck-{uuid.uuid4().hex[:8]}"

        self._producer: Any | None = None  # confluent_kafka.Producer
        self._handlers: dict[str, tuple[str, EventHandler]] = {}  # sub_id -> (channel, handler)
        self._running = False
        self._msg_counter = 0

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create the Kafka Producer (consumers are not yet started)."""
        self._producer = _KafkaProducer({
            "bootstrap.servers": self._bootstrap_servers,
            "client.id": self._client_id,
            "acks": "all",
            "retries": 3,
            "retry.backoff.ms": 200,
        })
        self._running = True
        logger.info(
            "KafkaEventBus started (bootstrap=%s, group=%s, client=%s)",
            self._bootstrap_servers,
            self._group_id,
            self._client_id,
        )

    async def stop(self) -> None:
        """Flush the producer and release resources."""
        self._running = False

        if self._producer is not None:
            # Flush pending messages with a generous timeout
            remaining = self._producer.flush(timeout=10.0)
            if remaining > 0:
                logger.warning(
                    "KafkaEventBus: %d messages were not delivered on shutdown",
                    remaining,
                )
            self._producer = None

        self._handlers.clear()
        logger.info("KafkaEventBus stopped")

    # ── Publish ────────────────────────────────────────────────────────

    async def publish(self, channel: str, event: dict[str, Any]) -> str:
        """Produce *event* to the Kafka topic mapped from *channel*.

        Returns a locally-generated message ID (the actual Kafka offset is
        available asynchronously via the delivery callback).
        """
        if self._producer is None:
            raise RuntimeError("KafkaEventBus not started — call start() first")

        topic = _channel_to_topic(channel)
        self._msg_counter += 1
        msg_id = f"kafka-{self._msg_counter}"

        payload = json.dumps(event, default=str).encode("utf-8")

        # Non-blocking produce; delivery confirmation comes via poll()
        self._producer.produce(
            topic=topic,
            value=payload,
            key=msg_id.encode("utf-8"),
            headers={"msg_id": msg_id.encode("utf-8")},
            callback=self._delivery_callback,
        )
        # Trigger callbacks for any previously-completed deliveries
        self._producer.poll(0)

        logger.debug("Published %s to topic %s (channel %s)", msg_id, topic, channel)
        return msg_id

    # ── Subscribe / Unsubscribe ────────────────────────────────────────

    async def subscribe(self, channel: str, handler: EventHandler) -> str:
        """Register *handler* for events on *channel*.

        NOTE: actual Kafka consumer polling is not yet implemented.
        Handlers are stored locally and will be dispatched once the
        consumer loop lands.
        """
        sub_id = f"ksub-{uuid.uuid4().hex}"
        self._handlers[sub_id] = (channel, handler)
        logger.info(
            "Subscribed %s to channel %s (Kafka consumer loop TBD)", sub_id, channel,
        )
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """Remove a previously registered subscription."""
        entry = self._handlers.pop(subscription_id, None)
        if entry is not None:
            logger.info("Unsubscribed %s from channel %s", subscription_id, entry[0])

    # ── Dead-letter queue ──────────────────────────────────────────────

    def get_dlq(self, channel: str) -> list[dict]:
        """Return an empty list — Kafka DLQ is managed via a separate topic.

        A full implementation would consume from ``<topic>.dlq``; for now
        callers should query the DLQ topic directly.
        """
        return []

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _delivery_callback(err: Any, msg: Any) -> None:
        """Called by confluent-kafka when a message delivery completes."""
        if err is not None:
            logger.error(
                "Kafka delivery failed for topic %s: %s",
                msg.topic() if msg else "unknown",
                err,
            )
        else:
            logger.debug(
                "Kafka delivery confirmed: topic=%s partition=%s offset=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )
