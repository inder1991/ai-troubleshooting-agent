"""Tests for EventPublishingRepository — decorator that publishes events on writes."""

import asyncio
import pytest
from datetime import datetime, timezone

from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import (
    Device,
    Interface,
    NeighborLink,
)
from src.network.repository.event_publishing_repository import EventPublishingRepository
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    sqlite_repo = SQLiteRepository(store)
    bus = MemoryEventBus()
    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.start())
    repo = EventPublishingRepository(inner=sqlite_repo, event_bus=bus)
    yield repo, bus, loop
    loop.run_until_complete(bus.stop())
    loop.close()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Tests ────────────────────────────────────────────────────────────────


class TestUpsertDevicePublishesEvent:
    def test_upsert_device_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(DEVICE_CHANGED, capture))

        now = _now()
        device = Device(
            id="dev-1",
            hostname="core-rtr-01",
            vendor="Cisco",
            model="ISR4451",
            serial="FTX1234",
            device_type="router",
            site_id="site-east",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
        )
        result = repo.upsert_device(device)
        assert result.id == "dev-1"

        # Let the bus process the event
        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) == 1
        channel, event = captured[0]
        assert channel == DEVICE_CHANGED
        assert event["entity_id"] == "dev-1"
        assert event["entity_type"] == "device"


class TestUpsertInterfacePublishesEvent:
    def test_upsert_interface_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(INTERFACE_CHANGED, capture))

        now = _now()
        # Need a device first
        repo.upsert_device(Device(
            id="dev-x", hostname="x", vendor="", model="", serial="",
            device_type="host", site_id="", sources=["topology_store"],
            first_seen=now, last_seen=now, confidence=0.9,
        ))
        # Drain any unrelated events
        loop.run_until_complete(asyncio.sleep(0.05))
        captured.clear()

        iface = Interface(
            id="dev-x:eth0",
            device_id="dev-x",
            name="eth0",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
            mac="AA:BB:CC:DD:EE:FF",
        )
        result = repo.upsert_interface(iface)
        assert result.id == "dev-x:eth0"

        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) == 1
        channel, event = captured[0]
        assert channel == INTERFACE_CHANGED
        assert event["entity_id"] == "dev-x:eth0"
        assert event["entity_type"] == "interface"


class TestUpsertNeighborLinkPublishesEvent:
    def test_upsert_neighbor_link_publishes_event(self, setup):
        repo, bus, loop = setup
        captured = []

        async def capture(channel, event):
            captured.append((channel, event))

        loop.run_until_complete(bus.subscribe(LINK_DISCOVERED, capture))

        now = _now()
        link = NeighborLink(
            id="link-1",
            device_id="dev-1",
            local_interface="dev-1:Gi0/0",
            remote_device="dev-2",
            remote_interface="dev-2:Gi0/1",
            protocol="lldp",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
        )
        result = repo.upsert_neighbor_link(link)
        assert result.id == "link-1"

        loop.run_until_complete(asyncio.sleep(0.1))

        assert len(captured) == 1
        channel, event = captured[0]
        assert channel == LINK_DISCOVERED
        assert event["entity_id"] == "link-1"
        assert event["entity_type"] == "link"


class TestReadsDelegateUnchanged:
    def test_reads_delegate_unchanged(self, setup):
        repo, bus, loop = setup

        # Empty repo should return an empty list
        devices = repo.get_devices()
        assert isinstance(devices, list)
        assert len(devices) == 0

        # Add a device via the repo, then read it back
        now = _now()
        repo.upsert_device(Device(
            id="dev-read",
            hostname="read-test",
            vendor="Juniper",
            model="MX480",
            serial="JN9999",
            device_type="router",
            site_id="site-west",
            sources=["topology_store"],
            first_seen=now,
            last_seen=now,
            confidence=0.85,
        ))

        devices = repo.get_devices()
        assert len(devices) == 1
        assert devices[0].id == "dev-read"
        assert devices[0].hostname == "read-test"
