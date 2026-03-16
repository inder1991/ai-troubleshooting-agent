"""Tests for KafkaEventBus.

Most tests are skip-gated on ``KAFKA_BOOTSTRAP_SERVERS`` because they
require a live Kafka cluster.  The importability test always runs.
"""

from __future__ import annotations

import os

import pytest


# ── Always-run tests (no Kafka needed) ────────────────────────────────


def test_kafka_bus_importable():
    """The kafka_bus module can be imported regardless of whether
    confluent-kafka is installed."""
    from src.network.event_bus import kafka_bus  # noqa: F401

    # Module-level flag should be a bool
    assert isinstance(kafka_bus.HAS_KAFKA, bool)


def test_channel_to_topic_conversion():
    """Dots in channel names are replaced with hyphens for Kafka topics."""
    from src.network.event_bus.kafka_bus import _channel_to_topic

    assert _channel_to_topic("network.flows") == "network-flows"
    assert _channel_to_topic("network.traps") == "network-traps"
    assert _channel_to_topic("a.b.c") == "a-b-c"
    assert _channel_to_topic("plain") == "plain"


# ── Skip-gated tests (require live Kafka) ─────────────────────────────

pytestmark_kafka = pytest.mark.skipif(
    not os.environ.get("KAFKA_BOOTSTRAP_SERVERS"),
    reason="KAFKA_BOOTSTRAP_SERVERS not set — Kafka not available",
)


@pytestmark_kafka
def test_instantiation():
    """KafkaEventBus can be constructed when confluent-kafka is installed
    and KAFKA_BOOTSTRAP_SERVERS is set."""
    from src.network.event_bus.kafka_bus import KafkaEventBus

    servers = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    bus = KafkaEventBus(bootstrap_servers=servers)

    assert bus._bootstrap_servers == servers
    assert bus._group_id == "debugduck-topology"
    assert bus._client_id.startswith("debugduck-")
    assert bus._running is False
    assert bus._producer is None


@pytestmark_kafka
def test_custom_parameters():
    """Constructor respects custom group_id and client_id."""
    from src.network.event_bus.kafka_bus import KafkaEventBus

    servers = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    bus = KafkaEventBus(
        bootstrap_servers=servers,
        group_id="custom-group",
        client_id="custom-client",
    )

    assert bus._group_id == "custom-group"
    assert bus._client_id == "custom-client"


@pytestmark_kafka
def test_get_dlq_returns_empty():
    """get_dlq returns an empty list (Kafka DLQ via separate topic)."""
    from src.network.event_bus.kafka_bus import KafkaEventBus

    servers = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
    bus = KafkaEventBus(bootstrap_servers=servers)

    assert bus.get_dlq("network.flows") == []
    assert bus.get_dlq("anything") == []
