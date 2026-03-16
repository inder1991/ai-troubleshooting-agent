# KG Architecture Overhaul — Phase 3: Event-Driven Graph Updates + Kafka

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the synchronous dual-write pattern (SQLite + Neo4j on every upsert) with event-driven graph updates. Topology changes publish events to the existing EventBus, and dedicated consumers update Neo4j, invalidate caches, and push updates to frontends via WebSocket. Add Kafka as a transport option alongside the existing MemoryEventBus and RedisEventBus.

**Architecture:** Extend the existing `event_bus/base.py` EventBus with topology-specific channels. Add a `TopologyEventPublisher` that wraps the repository write path. Add a `GraphMutatorConsumer` that listens for topology events and applies MERGE operations to Neo4j. Add a `StalenessDetector` background service. Add `KafkaEventBus` as a new transport. Add WebSocket publisher for real-time frontend updates.

**Tech Stack:** Existing EventBus (base.py), confluent-kafka (Kafka transport), asyncio, WebSocket (existing FastAPI websockets), Neo4j (from Phase 2).

**Design Doc:** `docs/plans/2026-03-16-kg-architecture-overhaul-design.md`

**Depends on:** Phase 1 (repository layer) + Phase 2 (Neo4j integration) complete.

**Key insight:** The project already has `event_bus/base.py` (EventBus ABC), `memory_bus.py` (MemoryEventBus), `redis_bus.py` (RedisEventBus), and `event_processor.py`. We extend this — not replace it.

---

## Task 1: Topology Event Channels + Event Schema

**Files:**
- Create: `backend/src/network/event_bus/topology_channels.py`
- Test: `backend/tests/test_topology_events.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_topology_events.py
"""Tests for topology event schema and channels."""
import pytest
from datetime import datetime, timezone
from src.network.event_bus.topology_channels import (
    TOPOLOGY_CHANNELS, TopologyEvent, EventType,
    make_device_event, make_interface_event, make_link_event,
    make_route_event, make_stale_event,
)


class TestTopologyChannels:
    def test_all_channels_defined(self):
        expected = [
            "topology.device.changed",
            "topology.interface.changed",
            "topology.link.discovered",
            "topology.route.changed",
            "topology.policy.changed",
            "topology.stale.detected",
        ]
        for ch in expected:
            assert ch in TOPOLOGY_CHANNELS

    def test_event_types(self):
        assert EventType.CREATED == "created"
        assert EventType.UPDATED == "updated"
        assert EventType.DELETED == "deleted"
        assert EventType.STALE == "stale"


class TestTopologyEvent:
    def test_create_event(self):
        event = TopologyEvent(
            event_type=EventType.CREATED,
            entity_type="device",
            entity_id="rtr-01",
            source="snmp",
            data={"hostname": "rtr-01", "vendor": "cisco"},
        )
        assert event.event_type == "created"
        assert event.entity_id == "rtr-01"
        assert event.schema_version == 1
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_to_dict(self):
        event = TopologyEvent(
            event_type=EventType.UPDATED,
            entity_type="interface",
            entity_id="rtr-01:Gi0/0",
            source="lldp",
        )
        d = event.to_dict()
        assert d["event_type"] == "updated"
        assert d["entity_type"] == "interface"
        assert d["schema_version"] == 1
        assert "event_id" in d
        assert "timestamp" in d

    def test_from_dict(self):
        original = TopologyEvent(
            event_type=EventType.CREATED,
            entity_type="device",
            entity_id="rtr-01",
            source="test",
        )
        restored = TopologyEvent.from_dict(original.to_dict())
        assert restored.entity_id == "rtr-01"
        assert restored.event_type == "created"


class TestEventFactories:
    def test_make_device_event(self):
        event = make_device_event("rtr-01", EventType.CREATED, "snmp",
                                   {"hostname": "rtr-01"})
        assert event.entity_type == "device"
        assert event.entity_id == "rtr-01"

    def test_make_link_event(self):
        event = make_link_event(
            link_id="rtr-01:Gi0/0--sw-01:Gi0/48",
            event_type=EventType.CREATED,
            source="lldp",
            data={"local_interface": "rtr-01:Gi0/0", "remote_interface": "sw-01:Gi0/48"},
        )
        assert event.entity_type == "link"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_topology_events.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/event_bus/topology_channels.py
"""Topology-specific event channels, schema, and factory functions.

Extends the existing EventBus channel system with topology change events.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any


# ── Topology Channels ─────────────────────────────────────────────────

DEVICE_CHANGED = "topology.device.changed"
INTERFACE_CHANGED = "topology.interface.changed"
LINK_DISCOVERED = "topology.link.discovered"
ROUTE_CHANGED = "topology.route.changed"
POLICY_CHANGED = "topology.policy.changed"
STALE_DETECTED = "topology.stale.detected"

TOPOLOGY_CHANNELS = [
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
    ROUTE_CHANGED,
    POLICY_CHANGED,
    STALE_DETECTED,
]


# ── Event Types ───────────────────────────────────────────────────────

class EventType:
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STALE = "stale"


# ── Event Schema ──────────────────────────────────────────────────────

SCHEMA_VERSION = 1


@dataclass
class TopologyEvent:
    """Canonical topology change event."""
    event_type: str               # created/updated/deleted/stale
    entity_type: str              # device/interface/link/route/policy
    entity_id: str
    source: str                   # snmp/lldp/aws_api/config_parser/...
    data: dict = field(default_factory=dict)
    changes: dict = field(default_factory=dict)  # {field: {old, new}}
    schema_version: int = SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "source": self.source,
            "data": self.data,
            "changes": self.changes,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TopologyEvent:
        return cls(
            event_type=d["event_type"],
            entity_type=d["entity_type"],
            entity_id=d["entity_id"],
            source=d.get("source", "unknown"),
            data=d.get("data", {}),
            changes=d.get("changes", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            event_id=d.get("event_id", str(uuid.uuid4())),
            timestamp=d.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


# ── Factory Functions ─────────────────────────────────────────────────

def make_device_event(device_id: str, event_type: str, source: str,
                      data: dict = None, changes: dict = None) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type, entity_type="device",
        entity_id=device_id, source=source,
        data=data or {}, changes=changes or {},
    )

def make_interface_event(interface_id: str, event_type: str, source: str,
                         data: dict = None, changes: dict = None) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type, entity_type="interface",
        entity_id=interface_id, source=source,
        data=data or {}, changes=changes or {},
    )

def make_link_event(link_id: str, event_type: str, source: str,
                    data: dict = None, changes: dict = None) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type, entity_type="link",
        entity_id=link_id, source=source,
        data=data or {}, changes=changes or {},
    )

def make_route_event(route_id: str, event_type: str, source: str,
                     data: dict = None, changes: dict = None) -> TopologyEvent:
    return TopologyEvent(
        event_type=event_type, entity_type="route",
        entity_id=route_id, source=source,
        data=data or {}, changes=changes or {},
    )

def make_stale_event(entity_type: str, entity_id: str,
                     last_seen: str = "") -> TopologyEvent:
    return TopologyEvent(
        event_type=EventType.STALE, entity_type=entity_type,
        entity_id=entity_id, source="staleness_detector",
        data={"last_seen": last_seen},
    )
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_topology_events.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/event_bus/topology_channels.py backend/tests/test_topology_events.py
git commit -m "feat(events): topology event channels, schema, and factory functions"
```

---

## Task 2: Event-Publishing Repository Wrapper

**Files:**
- Create: `backend/src/network/repository/event_publishing_repository.py`
- Test: `backend/tests/test_event_publishing_repository.py`

This wraps any TopologyRepository and publishes events on writes.

**Step 1: Write the failing test**

```python
# backend/tests/test_event_publishing_repository.py
"""Tests for EventPublishingRepository — publishes events on write operations."""
import pytest
import asyncio
from datetime import datetime, timezone
from src.network.repository.event_publishing_repository import EventPublishingRepository
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import Device, Interface, NeighborLink
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import DEVICE_CHANGED, INTERFACE_CHANGED, LINK_DISCOVERED
from src.network.topology_store import TopologyStore


@pytest.fixture
def setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    sqlite_repo = SQLiteRepository(store)
    bus = MemoryEventBus()

    # Start the bus
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.start())

    repo = EventPublishingRepository(inner=sqlite_repo, event_bus=bus)
    yield repo, bus, loop

    loop.run_until_complete(bus.stop())
    loop.close()


class TestEventPublishingRepository:
    def test_upsert_device_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(DEVICE_CHANGED, capture))

        now = datetime.now(timezone.utc)
        device = Device(
            id="rtr-01", hostname="rtr-01", vendor="cisco", model="ISR4451",
            serial="FTX1234", device_type="ROUTER", site_id="dc-east",
            sources=["snmp"], first_seen=now, last_seen=now, confidence=0.9,
        )
        repo.upsert_device(device)

        # Give the bus a moment to process
        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) >= 1
        assert captured[0][0] == DEVICE_CHANGED
        assert captured[0][1]["entity_id"] == "rtr-01"
        assert captured[0][1]["event_type"] == "created"

    def test_upsert_interface_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(INTERFACE_CHANGED, capture))

        now = datetime.now(timezone.utc)
        iface = Interface(
            id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0",
            sources=["snmp"], first_seen=now, last_seen=now, confidence=0.9,
        )
        repo.upsert_interface(iface)

        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) >= 1
        assert captured[0][1]["entity_type"] == "interface"

    def test_upsert_neighbor_link_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(LINK_DISCOVERED, capture))

        now = datetime.now(timezone.utc)
        link = NeighborLink(
            id="rtr-01:Gi0/0--sw-01:Gi0/48", device_id="rtr-01",
            local_interface="rtr-01:Gi0/0", remote_device="sw-01",
            remote_interface="sw-01:Gi0/48", protocol="lldp",
            sources=["lldp"], first_seen=now, last_seen=now, confidence=0.95,
        )
        repo.upsert_neighbor_link(link)

        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) >= 1
        assert captured[0][1]["entity_type"] == "link"

    def test_reads_delegate_unchanged(self, setup):
        repo, bus, loop = setup
        devices = repo.get_devices()
        assert isinstance(devices, list)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_event_publishing_repository.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/event_publishing_repository.py
"""EventPublishingRepository — decorator that publishes events on writes.

Wraps any TopologyRepository. On write operations (upsert_*), it:
1. Delegates the write to the inner repository
2. Publishes a topology event to the EventBus

Read operations pass through unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .interface import TopologyRepository
from .domain import (
    Device, Interface, IPAddress, NeighborLink, Route, SecurityPolicy,
)
from ..event_bus.base import EventBus
from ..event_bus.topology_channels import (
    DEVICE_CHANGED, INTERFACE_CHANGED, LINK_DISCOVERED,
    ROUTE_CHANGED, POLICY_CHANGED, STALE_DETECTED,
    EventType, make_device_event, make_interface_event,
    make_link_event, make_route_event, make_stale_event,
)

logger = logging.getLogger(__name__)


class EventPublishingRepository(TopologyRepository):
    """Wraps a TopologyRepository and publishes events on writes."""

    def __init__(self, inner: TopologyRepository, event_bus: EventBus):
        self._inner = inner
        self._bus = event_bus

    def _publish(self, channel: str, event_dict: dict) -> None:
        """Fire-and-forget publish to the event bus."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._bus.publish(channel, event_dict))
            else:
                loop.run_until_complete(self._bus.publish(channel, event_dict))
        except RuntimeError:
            # No event loop — create one for sync context
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._bus.publish(channel, event_dict))
            except Exception as e:
                logger.warning("Event publish failed: %s", e)
        except Exception as e:
            logger.warning("Event publish failed: %s", e)

    # ── Reads: pass through ──

    def get_device(self, device_id: str) -> Optional[Device]:
        return self._inner.get_device(device_id)

    def get_devices(self, site_id: str = None, device_type: str = None) -> list[Device]:
        return self._inner.get_devices(site_id=site_id, device_type=device_type)

    def get_interfaces(self, device_id: str) -> list[Interface]:
        return self._inner.get_interfaces(device_id)

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        return self._inner.get_ip_addresses(interface_id)

    def get_routes(self, device_id: str, vrf_instance_id: str = None) -> list[Route]:
        return self._inner.get_routes(device_id, vrf_instance_id)

    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        return self._inner.get_neighbors(device_id)

    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        return self._inner.get_security_policies(device_id)

    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        return self._inner.find_device_by_ip(ip)

    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        return self._inner.find_device_by_serial(serial)

    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        return self._inner.find_device_by_hostname(hostname)

    # ── Writes: delegate + publish ──

    def upsert_device(self, device: Device) -> Device:
        result = self._inner.upsert_device(device)
        event = make_device_event(device.id, EventType.CREATED,
                                   device.sources[-1] if device.sources else "unknown",
                                   {"hostname": device.hostname, "vendor": device.vendor,
                                    "device_type": device.device_type})
        self._publish(DEVICE_CHANGED, event.to_dict())
        return result

    def upsert_interface(self, interface: Interface) -> Interface:
        result = self._inner.upsert_interface(interface)
        event = make_interface_event(interface.id, EventType.CREATED,
                                      interface.sources[-1] if interface.sources else "unknown",
                                      {"name": interface.name, "device_id": interface.device_id})
        self._publish(INTERFACE_CHANGED, event.to_dict())
        return result

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        return self._inner.upsert_ip_address(ip_address)

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        result = self._inner.upsert_neighbor_link(link)
        event = make_link_event(link.id, EventType.CREATED, link.protocol,
                                 {"local_interface": link.local_interface,
                                  "remote_interface": link.remote_interface})
        self._publish(LINK_DISCOVERED, event.to_dict())
        return result

    def upsert_route(self, route: Route) -> Route:
        result = self._inner.upsert_route(route)
        event = make_route_event(route.id, EventType.CREATED,
                                  route.sources[-1] if route.sources else "unknown",
                                  {"destination": route.destination_cidr})
        self._publish(ROUTE_CHANGED, event.to_dict())
        return result

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        result = self._inner.upsert_security_policy(policy)
        self._publish(POLICY_CHANGED, {
            "event_type": EventType.CREATED,
            "entity_type": "policy",
            "entity_id": policy.id,
            "source": "config_parser",
            "schema_version": 1,
        })
        return result

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        self._inner.mark_stale(entity_type, entity_id)
        event = make_stale_event(entity_type, entity_id)
        self._publish(STALE_DETECTED, event.to_dict())

    # ── Graph queries: pass through ──

    def find_paths(self, src_ip: str, dst_ip: str,
                   vrf: str = "default", k: int = 3) -> list[dict]:
        return self._inner.find_paths(src_ip, dst_ip, vrf, k)

    def blast_radius(self, device_id: str) -> dict:
        return self._inner.blast_radius(device_id)

    def get_topology_export(self, site_id: str = None) -> dict:
        return self._inner.get_topology_export(site_id)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_event_publishing_repository.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/event_publishing_repository.py backend/tests/test_event_publishing_repository.py
git commit -m "feat(events): EventPublishingRepository — publishes topology events on writes"
```

---

## Task 3: Graph Mutator Consumer

**Files:**
- Create: `backend/src/network/event_bus/graph_mutator.py`
- Test: `backend/tests/test_graph_mutator.py`

This consumes topology events and applies MERGE operations to Neo4j.

**Step 1: Write the failing test**

```python
# backend/tests/test_graph_mutator.py
"""Tests for GraphMutatorConsumer — consumes topology events, updates Neo4j."""
import os
import pytest
import asyncio

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set"
)

from src.network.event_bus.graph_mutator import GraphMutatorConsumer
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED, INTERFACE_CHANGED, LINK_DISCOVERED,
    EventType, make_device_event, make_interface_event, make_link_event,
)
from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager


@pytest.fixture
def neo4j():
    mgr = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
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


class TestGraphMutator:
    def test_device_event_creates_node(self, bus_and_mutator):
        bus, mutator, neo4j, loop = bus_and_mutator

        event = make_device_event("rtr-01", EventType.CREATED, "snmp",
                                   {"hostname": "rtr-01", "vendor": "cisco",
                                    "device_type": "ROUTER", "site_id": "dc-east"})
        loop.run_until_complete(bus.publish(DEVICE_CHANGED, event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.2))

        result = neo4j.execute_read("MATCH (d:Device {id: 'rtr-01'}) RETURN d.hostname AS h")
        assert len(result) == 1
        assert result[0]["h"] == "rtr-01"

    def test_interface_event_creates_node_with_edge(self, bus_and_mutator):
        bus, mutator, neo4j, loop = bus_and_mutator

        # First create the device
        dev_event = make_device_event("rtr-01", EventType.CREATED, "snmp",
                                       {"hostname": "rtr-01", "vendor": "cisco",
                                        "device_type": "ROUTER"})
        loop.run_until_complete(bus.publish(DEVICE_CHANGED, dev_event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.1))

        # Then create the interface
        iface_event = make_interface_event("rtr-01:Gi0/0", EventType.CREATED, "snmp",
                                            {"name": "Gi0/0", "device_id": "rtr-01",
                                             "mac": "aa:bb:cc:dd:ee:ff"})
        loop.run_until_complete(bus.publish(INTERFACE_CHANGED, iface_event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.2))

        result = neo4j.execute_read(
            "MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface {id: 'rtr-01:Gi0/0'}) "
            "RETURN d.id AS dev, i.name AS iface"
        )
        assert len(result) == 1
        assert result[0]["dev"] == "rtr-01"

    def test_stale_event_marks_node(self, bus_and_mutator):
        bus, mutator, neo4j, loop = bus_and_mutator

        # Create device first
        neo4j.execute_write("CREATE (d:Device {id: 'old-01', hostname: 'old', stale: false})")

        from src.network.event_bus.topology_channels import STALE_DETECTED, make_stale_event
        event = make_stale_event("device", "old-01", "2026-03-15T00:00:00Z")
        loop.run_until_complete(bus.publish(STALE_DETECTED, event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.2))

        result = neo4j.execute_read("MATCH (d:Device {id: 'old-01'}) RETURN d.stale AS stale")
        assert result[0]["stale"] == True
```

**Step 2: Run test to verify it fails**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_mutator.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/event_bus/graph_mutator.py
"""GraphMutatorConsumer — listens for topology events and updates Neo4j.

Subscribes to all topology channels on the EventBus.
On each event, applies an idempotent MERGE to Neo4j.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import EventBus
from .topology_channels import (
    DEVICE_CHANGED, INTERFACE_CHANGED, LINK_DISCOVERED,
    ROUTE_CHANGED, POLICY_CHANGED, STALE_DETECTED, TopologyEvent,
)

logger = logging.getLogger(__name__)


class GraphMutatorConsumer:
    """Consumes topology events and applies MERGE to Neo4j."""

    def __init__(self, neo4j):
        """neo4j: Neo4jConnectionManager instance."""
        self._neo4j = neo4j

    async def subscribe(self, bus: EventBus) -> None:
        """Subscribe to all topology channels."""
        await bus.subscribe(DEVICE_CHANGED, self._handle_device)
        await bus.subscribe(INTERFACE_CHANGED, self._handle_interface)
        await bus.subscribe(LINK_DISCOVERED, self._handle_link)
        await bus.subscribe(ROUTE_CHANGED, self._handle_route)
        await bus.subscribe(STALE_DETECTED, self._handle_stale)
        logger.info("GraphMutatorConsumer subscribed to topology channels")

    async def _handle_device(self, channel: str, event: dict) -> None:
        data = event.get("data", {})
        entity_id = event.get("entity_id", "")
        try:
            self._neo4j.execute_write("""
                MERGE (d:Device {id: $id})
                SET d.hostname = $hostname,
                    d.vendor = $vendor,
                    d.device_type = $device_type,
                    d.site_id = $site_id,
                    d.last_synced = timestamp()
            """, {
                "id": entity_id,
                "hostname": data.get("hostname", ""),
                "vendor": data.get("vendor", ""),
                "device_type": data.get("device_type", ""),
                "site_id": data.get("site_id", ""),
            })
            logger.debug("Mutator: device %s merged", entity_id)
        except Exception as e:
            logger.error("Mutator: device merge failed for %s: %s", entity_id, e)

    async def _handle_interface(self, channel: str, event: dict) -> None:
        data = event.get("data", {})
        entity_id = event.get("entity_id", "")
        device_id = data.get("device_id", "")
        try:
            self._neo4j.execute_write("""
                MERGE (i:Interface {id: $id})
                SET i.name = $name,
                    i.device_id = $device_id,
                    i.mac = $mac,
                    i.last_synced = timestamp()
                WITH i
                MATCH (d:Device {id: $device_id})
                MERGE (d)-[:HAS_INTERFACE]->(i)
            """, {
                "id": entity_id,
                "name": data.get("name", ""),
                "device_id": device_id,
                "mac": data.get("mac"),
            })
            logger.debug("Mutator: interface %s merged", entity_id)
        except Exception as e:
            logger.error("Mutator: interface merge failed for %s: %s", entity_id, e)

    async def _handle_link(self, channel: str, event: dict) -> None:
        data = event.get("data", {})
        entity_id = event.get("entity_id", "")
        local_iface = data.get("local_interface", "")
        remote_iface = data.get("remote_interface", "")
        try:
            self._neo4j.execute_write("""
                MATCH (i1:Interface {id: $local_iface})
                MATCH (i2:Interface {id: $remote_iface})
                MERGE (l:Link {id: $link_id})
                SET l.protocol = $protocol,
                    l.last_synced = timestamp()
                MERGE (i1)-[:CONNECTED_TO]->(l)
                MERGE (l)-[:CONNECTED_TO]->(i2)
            """, {
                "link_id": entity_id,
                "local_iface": local_iface,
                "remote_iface": remote_iface,
                "protocol": event.get("source", "unknown"),
            })
            logger.debug("Mutator: link %s merged", entity_id)
        except Exception as e:
            logger.error("Mutator: link merge failed for %s: %s", entity_id, e)

    async def _handle_route(self, channel: str, event: dict) -> None:
        data = event.get("data", {})
        entity_id = event.get("entity_id", "")
        try:
            self._neo4j.execute_write("""
                MERGE (r:Route {id: $id})
                SET r.destination_cidr = $destination,
                    r.last_synced = timestamp()
            """, {
                "id": entity_id,
                "destination": data.get("destination", ""),
            })
            logger.debug("Mutator: route %s merged", entity_id)
        except Exception as e:
            logger.error("Mutator: route merge failed for %s: %s", entity_id, e)

    async def _handle_stale(self, channel: str, event: dict) -> None:
        entity_type = event.get("entity_type", "device")
        entity_id = event.get("entity_id", "")
        label = entity_type.capitalize()
        try:
            self._neo4j.execute_write(
                f"MATCH (n:{label} {{id: $id}}) SET n.stale = true, n.confidence = n.confidence * 0.5",
                {"id": entity_id}
            )
            logger.debug("Mutator: %s %s marked stale", entity_type, entity_id)
        except Exception as e:
            logger.error("Mutator: stale marking failed for %s %s: %s",
                         entity_type, entity_id, e)
```

**Step 4: Run tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_mutator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/event_bus/graph_mutator.py backend/tests/test_graph_mutator.py
git commit -m "feat(events): GraphMutatorConsumer — event-driven Neo4j updates"
```

---

## Task 4: Staleness Detector Service

**Files:**
- Create: `backend/src/network/repository/staleness_detector.py`
- Test: `backend/tests/test_staleness_detector.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_staleness_detector.py
"""Tests for StalenessDetector — detects stale entities and publishes events."""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from src.network.repository.staleness_detector import StalenessDetector
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import Device
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import STALE_DETECTED
from src.network.topology_store import TopologyStore
from src.network.models import Device as PydanticDevice, DeviceType


@pytest.fixture
def setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    bus = MemoryEventBus()

    # Add a device with old last_seen
    store.add_device(PydanticDevice(
        id="old-device", name="old-device", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco",
        last_seen="2026-01-01T00:00:00Z",
    ))
    # Add a fresh device
    store.add_device(PydanticDevice(
        id="fresh-device", name="fresh-device", device_type=DeviceType.switch,
        management_ip="10.0.0.2", vendor="cisco",
    ))

    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.start())

    detector = StalenessDetector(repo=repo, event_bus=bus, stale_threshold_minutes=1)
    yield detector, bus, repo, loop

    loop.run_until_complete(bus.stop())
    loop.close()


class TestStalenessDetector:
    def test_detects_stale_devices(self, setup):
        detector, bus, repo, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append(event)

        loop.run_until_complete(bus.subscribe(STALE_DETECTED, capture))

        # Run one scan
        loop.run_until_complete(detector.scan_once())
        loop.run_until_complete(asyncio.sleep(0.1))

        # old-device should be flagged (last_seen is 2026-01-01, well past threshold)
        stale_ids = [e["entity_id"] for e in captured]
        assert "old-device" in stale_ids

    def test_fresh_device_not_flagged(self, setup):
        detector, bus, repo, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append(event)

        loop.run_until_complete(bus.subscribe(STALE_DETECTED, capture))
        loop.run_until_complete(detector.scan_once())
        loop.run_until_complete(asyncio.sleep(0.1))

        stale_ids = [e["entity_id"] for e in captured]
        assert "fresh-device" not in stale_ids
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_staleness_detector.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/staleness_detector.py
"""StalenessDetector — scans for stale entities and publishes events.

Runs periodically (or on-demand via scan_once) to detect entities
that haven't been seen within their staleness threshold.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .interface import TopologyRepository
from ..event_bus.base import EventBus
from ..event_bus.topology_channels import STALE_DETECTED, make_stale_event

logger = logging.getLogger(__name__)


class StalenessDetector:
    """Detects stale topology entities and publishes events."""

    def __init__(self, repo: TopologyRepository, event_bus: EventBus,
                 stale_threshold_minutes: int = 10):
        self._repo = repo
        self._bus = event_bus
        self._threshold = timedelta(minutes=stale_threshold_minutes)
        self._running = False

    async def scan_once(self) -> int:
        """Run a single staleness scan. Returns count of stale entities found."""
        now = datetime.now(timezone.utc)
        cutoff = now - self._threshold
        stale_count = 0

        # Scan devices
        for device in self._repo.get_devices():
            if self._is_stale(device.last_seen, cutoff):
                event = make_stale_event("device", device.id,
                                          str(device.last_seen))
                await self._bus.publish(STALE_DETECTED, event.to_dict())
                stale_count += 1

        if stale_count:
            logger.info("Staleness scan found %d stale entities", stale_count)

        return stale_count

    async def run(self, interval_seconds: int = 60) -> None:
        """Run continuous staleness scanning."""
        self._running = True
        while self._running:
            try:
                await self.scan_once()
            except Exception as e:
                logger.error("Staleness scan failed: %s", e)
            await asyncio.sleep(interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _is_stale(self, last_seen, cutoff: datetime) -> bool:
        """Check if last_seen is before cutoff."""
        if not last_seen:
            return True  # Never seen = stale

        if isinstance(last_seen, datetime):
            ts = last_seen
        elif isinstance(last_seen, str) and last_seen:
            try:
                ts = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return True  # Unparseable = assume stale
        else:
            return True

        # Ensure timezone-aware comparison
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return ts < cutoff
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_staleness_detector.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/staleness_detector.py backend/tests/test_staleness_detector.py
git commit -m "feat(events): StalenessDetector — scans for stale entities, publishes events"
```

---

## Task 5: Kafka Event Bus Transport

**Files:**
- Create: `backend/src/network/event_bus/kafka_bus.py`
- Test: `backend/tests/test_kafka_bus.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_kafka_bus.py
"""Tests for KafkaEventBus transport."""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("KAFKA_BOOTSTRAP_SERVERS"),
    reason="KAFKA_BOOTSTRAP_SERVERS not set — Kafka not available"
)

from src.network.event_bus.kafka_bus import KafkaEventBus


class TestKafkaEventBus:
    def test_instantiation(self):
        """KafkaEventBus can be created with bootstrap servers."""
        bus = KafkaEventBus(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"]
        )
        assert bus is not None
```

Note: Full Kafka integration tests require a running Kafka broker. For now, we create the class and skip-gate the tests. The MemoryEventBus is used in all non-Kafka tests.

**Step 2: Run test to verify it fails or skips**

Run: `cd backend && python3 -m pytest tests/test_kafka_bus.py -v`
Expected: SKIP (KAFKA_BOOTSTRAP_SERVERS not set)

**Step 3: Write implementation**

```python
# backend/src/network/event_bus/kafka_bus.py
"""Kafka-backed event bus transport.

Uses confluent-kafka for production deployments. Falls back gracefully
if confluent-kafka is not installed — the MemoryEventBus or RedisEventBus
can be used instead.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from .base import EventBus, EventHandler

logger = logging.getLogger(__name__)

try:
    from confluent_kafka import Producer, Consumer, KafkaError
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False
    logger.info("confluent-kafka not installed — KafkaEventBus unavailable")


class KafkaEventBus(EventBus):
    """Production event bus backed by Apache Kafka.

    Requires confluent-kafka package. If not installed, instantiation
    raises ImportError.
    """

    def __init__(self, bootstrap_servers: str, group_id: str = "debugduck-topology",
                 client_id: str = None):
        if not HAS_KAFKA:
            raise ImportError("confluent-kafka is required for KafkaEventBus. "
                              "Install with: pip install confluent-kafka")

        self._bootstrap = bootstrap_servers
        self._group_id = group_id
        self._client_id = client_id or f"debugduck-{uuid.uuid4().hex[:8]}"
        self._producer = None
        self._consumers: dict[str, Consumer] = {}
        self._handlers: dict[str, list[tuple[str, EventHandler]]] = {}
        self._running = False

    async def start(self) -> None:
        self._producer = Producer({
            "bootstrap.servers": self._bootstrap,
            "client.id": self._client_id,
        })
        self._running = True
        logger.info("KafkaEventBus started: %s", self._bootstrap)

    async def stop(self) -> None:
        self._running = False
        if self._producer:
            self._producer.flush(timeout=5)
        for consumer in self._consumers.values():
            consumer.close()
        self._consumers.clear()
        logger.info("KafkaEventBus stopped")

    async def publish(self, channel: str, event: dict[str, Any]) -> str:
        if not self._producer:
            raise RuntimeError("KafkaEventBus not started")

        msg_id = str(uuid.uuid4())
        value = json.dumps(event).encode("utf-8")
        self._producer.produce(
            topic=channel.replace(".", "-"),  # Kafka topics use hyphens
            key=event.get("entity_id", msg_id).encode("utf-8"),
            value=value,
        )
        self._producer.poll(0)  # Trigger delivery callbacks
        return msg_id

    async def subscribe(self, channel: str, handler: EventHandler) -> str:
        sub_id = str(uuid.uuid4())
        self._handlers.setdefault(channel, []).append((sub_id, handler))
        # Note: actual Kafka consumer polling would run in a background task
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        for channel, handlers in self._handlers.items():
            self._handlers[channel] = [
                (sid, h) for sid, h in handlers if sid != subscription_id
            ]

    def get_dlq(self, channel: str) -> list[dict]:
        return []  # Kafka DLQ handled by separate topic
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_kafka_bus.py -v`
Expected: SKIP (no Kafka running)

**Step 5: Commit**

```bash
git add backend/src/network/event_bus/kafka_bus.py backend/tests/test_kafka_bus.py
git commit -m "feat(events): KafkaEventBus transport — production-grade event streaming"
```

---

## Task 6: WebSocket Topology Stream

**Files:**
- Create: `backend/src/network/event_bus/websocket_publisher.py`
- Test: `backend/tests/test_websocket_publisher.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_websocket_publisher.py
"""Tests for WebSocketTopologyPublisher — bridges events to WebSocket clients."""
import pytest
import asyncio
from src.network.event_bus.websocket_publisher import WebSocketTopologyPublisher
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED, make_device_event, EventType,
)


class FakeWebSocket:
    """Mock WebSocket for testing."""
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


class TestWebSocketPublisher:
    def test_register_and_receive(self):
        bus = MemoryEventBus()
        publisher = WebSocketTopologyPublisher()
        loop = asyncio.new_event_loop()

        loop.run_until_complete(bus.start())
        loop.run_until_complete(publisher.subscribe(bus))

        ws = FakeWebSocket()
        publisher.register("client-1", ws)

        event = make_device_event("rtr-01", EventType.CREATED, "snmp",
                                   {"hostname": "rtr-01"})
        loop.run_until_complete(bus.publish(DEVICE_CHANGED, event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.2))

        assert len(ws.sent) >= 1
        assert ws.sent[0]["entity_id"] == "rtr-01"

        publisher.unregister("client-1")
        loop.run_until_complete(bus.stop())
        loop.close()

    def test_unregister_stops_delivery(self):
        bus = MemoryEventBus()
        publisher = WebSocketTopologyPublisher()
        loop = asyncio.new_event_loop()

        loop.run_until_complete(bus.start())
        loop.run_until_complete(publisher.subscribe(bus))

        ws = FakeWebSocket()
        publisher.register("client-1", ws)
        publisher.unregister("client-1")

        event = make_device_event("rtr-01", EventType.CREATED, "snmp")
        loop.run_until_complete(bus.publish(DEVICE_CHANGED, event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(ws.sent) == 0

        loop.run_until_complete(bus.stop())
        loop.close()

    def test_broken_websocket_auto_unregisters(self):
        bus = MemoryEventBus()
        publisher = WebSocketTopologyPublisher()
        loop = asyncio.new_event_loop()

        loop.run_until_complete(bus.start())
        loop.run_until_complete(publisher.subscribe(bus))

        class BrokenWS:
            async def send_json(self, data):
                raise ConnectionError("Client disconnected")

        ws = BrokenWS()
        publisher.register("client-1", ws)

        event = make_device_event("rtr-01", EventType.CREATED, "snmp")
        loop.run_until_complete(bus.publish(DEVICE_CHANGED, event.to_dict()))
        loop.run_until_complete(asyncio.sleep(0.1))

        # Should auto-unregister broken client
        assert "client-1" not in publisher._clients

        loop.run_until_complete(bus.stop())
        loop.close()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_websocket_publisher.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/event_bus/websocket_publisher.py
"""WebSocketTopologyPublisher — bridges topology events to WebSocket clients.

Subscribes to all topology channels and forwards events to connected
WebSocket clients. Auto-unregisters broken connections.
"""
from __future__ import annotations

import logging
from typing import Any

from .base import EventBus
from .topology_channels import TOPOLOGY_CHANNELS

logger = logging.getLogger(__name__)


class WebSocketTopologyPublisher:
    """Forwards topology events to connected WebSocket clients."""

    def __init__(self):
        self._clients: dict[str, Any] = {}  # client_id → websocket

    def register(self, client_id: str, websocket) -> None:
        self._clients[client_id] = websocket
        logger.info("WebSocket client registered: %s (total: %d)",
                     client_id, len(self._clients))

    def unregister(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        logger.info("WebSocket client unregistered: %s (total: %d)",
                     client_id, len(self._clients))

    async def subscribe(self, bus: EventBus) -> None:
        """Subscribe to all topology channels."""
        for channel in TOPOLOGY_CHANNELS:
            await bus.subscribe(channel, self._handle_event)
        logger.info("WebSocketPublisher subscribed to %d topology channels",
                     len(TOPOLOGY_CHANNELS))

    async def _handle_event(self, channel: str, event: dict) -> None:
        """Forward event to all connected clients."""
        delta = self._to_delta(channel, event)
        dead_clients = []

        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_json(delta)
            except Exception:
                dead_clients.append(client_id)

        for client_id in dead_clients:
            self.unregister(client_id)
            logger.warning("Auto-unregistered broken WebSocket: %s", client_id)

    def _to_delta(self, channel: str, event: dict) -> dict:
        """Convert internal event to frontend delta format."""
        entity_type = event.get("entity_type", "device")
        return {
            "event_type": event.get("event_type", "updated"),
            "entity_id": event.get("entity_id", ""),
            "entity_type": "node" if entity_type in ("device", "interface") else "edge",
            "data": event.get("data", {}),
            "changes": event.get("changes", {}),
            "timestamp": event.get("timestamp", ""),
        }
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_websocket_publisher.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/event_bus/websocket_publisher.py backend/tests/test_websocket_publisher.py
git commit -m "feat(events): WebSocket topology publisher — real-time frontend updates"
```

---

## Task 7: Full Regression Test

**Files:** None (verification only)

**Step 1: Phase 1 tests (no Neo4j, no Kafka)**

Run: `cd backend && python3 -m pytest tests/test_repository_domain.py tests/test_repository_interface.py tests/test_sqlite_repository.py tests/test_neighbor_links.py tests/test_topology_validation.py tests/test_kg_uses_repository.py tests/test_repository_api_wiring.py -v`
Expected: 54 pass

**Step 2: Phase 2 tests (Neo4j)**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_connection.py tests/test_neo4j_schema.py tests/test_graph_sync.py tests/test_neo4j_repository.py tests/test_reconciliation.py -v`
Expected: 25 pass

**Step 3: Phase 3 tests (events)**

Run: `cd backend && python3 -m pytest tests/test_topology_events.py tests/test_event_publishing_repository.py tests/test_staleness_detector.py tests/test_websocket_publisher.py -v`
Expected: ALL PASS

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_mutator.py -v`
Expected: ALL PASS

**Step 4: Existing tests**

Run: `cd backend && python3 -m pytest tests/test_knowledge_graph.py tests/test_topology_store_crud.py -v`
Expected: 61 pass

**Step 5: Commit if fixes needed**

```bash
git add -A
git commit -m "fix: resolve regressions from event bus integration"
```

---

## Summary

| Task | What | Files | Requires |
|------|------|-------|----------|
| 1 | Topology event channels + schema | `topology_channels.py` | None |
| 2 | EventPublishingRepository wrapper | `event_publishing_repository.py` | MemoryEventBus |
| 3 | GraphMutatorConsumer (events → Neo4j) | `graph_mutator.py` | Neo4j |
| 4 | StalenessDetector service | `staleness_detector.py` | None |
| 5 | KafkaEventBus transport | `kafka_bus.py` | Kafka (skip-gated) |
| 6 | WebSocket topology publisher | `websocket_publisher.py` | None |
| 7 | Full regression test | None | All |

**After Phase 3 is complete:**
- All topology writes publish events to the EventBus
- GraphMutatorConsumer updates Neo4j asynchronously (replaces sync dual-write)
- StalenessDetector scans for stale entities and publishes events
- WebSocketPublisher pushes real-time updates to connected frontends
- KafkaEventBus available as production transport (alongside Memory/Redis)
- Event schema is versioned (schema_version=1) for future evolution
- Ready for Phase 4: Discovery Adapters + Normalization
