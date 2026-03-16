"""Tests for GraphMutatorConsumer — event-driven Neo4j updates.

All tests are skip-gated on NEO4J_URI so they only run when a live
Neo4j instance is available.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from src.network.event_bus.graph_mutator import GraphMutatorConsumer
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    STALE_DETECTED,
    EventType,
    make_device_event,
    make_interface_event,
    make_stale_event,
)
from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set — skipping Neo4j integration tests",
)


@pytest.fixture
def neo4j():
    mgr = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username="neo4j",
        password="debugduck",
    )
    Neo4jSchemaManager(mgr).apply()
    mgr.execute_write("MATCH (n) DETACH DELETE n")
    yield mgr
    mgr.close()


@pytest.fixture
def bus_and_mutator(neo4j):
    bus = MemoryEventBus()
    mutator = GraphMutatorConsumer(neo4j)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.start())
    loop.run_until_complete(mutator.subscribe(bus))
    yield bus, mutator, neo4j, loop
    loop.run_until_complete(bus.stop())
    loop.close()


def test_device_event_creates_node(bus_and_mutator):
    bus, mutator, neo4j, loop = bus_and_mutator

    event = make_device_event(
        device_id="dev-001",
        event_type=EventType.CREATED,
        source="test",
        data={
            "hostname": "core-rtr-01",
            "vendor": "cisco",
            "device_type": "router",
            "site_id": "site-a",
        },
    )
    loop.run_until_complete(bus.publish(DEVICE_CHANGED, event.to_dict()))
    time.sleep(0.2)

    rows = neo4j.execute_read(
        "MATCH (d:Device {id: 'dev-001'}) RETURN d.hostname AS hostname"
    )
    assert len(rows) == 1
    assert rows[0]["hostname"] == "core-rtr-01"


def test_interface_event_creates_node_with_edge(bus_and_mutator):
    bus, mutator, neo4j, loop = bus_and_mutator

    # Pre-create the device so the HAS_INTERFACE edge can be formed
    neo4j.execute_write(
        "CREATE (d:Device {id: 'dev-002', hostname: 'sw-01'})"
    )

    event = make_interface_event(
        interface_id="iface-001",
        event_type=EventType.CREATED,
        source="test",
        data={
            "name": "GigabitEthernet0/1",
            "device_id": "dev-002",
            "mac": "aa:bb:cc:dd:ee:ff",
        },
    )
    loop.run_until_complete(bus.publish(INTERFACE_CHANGED, event.to_dict()))
    time.sleep(0.2)

    rows = neo4j.execute_read(
        "MATCH (d:Device {id: 'dev-002'})-[:HAS_INTERFACE]->(i:Interface {id: 'iface-001'}) "
        "RETURN i.name AS name"
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "GigabitEthernet0/1"


def test_stale_event_marks_node(bus_and_mutator):
    bus, mutator, neo4j, loop = bus_and_mutator

    # Pre-create the device with confidence
    neo4j.execute_write(
        "CREATE (d:Device {id: 'dev-003', hostname: 'old-rtr', confidence: 1.0})"
    )

    event = make_stale_event(
        entity_type="device",
        entity_id="dev-003",
    )
    loop.run_until_complete(bus.publish(STALE_DETECTED, event.to_dict()))
    time.sleep(0.2)

    rows = neo4j.execute_read(
        "MATCH (d:Device {id: 'dev-003'}) "
        "RETURN d.stale AS stale, d.confidence AS confidence"
    )
    assert len(rows) == 1
    assert rows[0]["stale"] is True
    assert rows[0]["confidence"] == 0.5
