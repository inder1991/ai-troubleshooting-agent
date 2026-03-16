"""Tests for neighbor_links persistence — TopologyStore table + SQLiteRepository."""

import pytest
from datetime import datetime, timezone

from src.network.topology_store import TopologyStore
from src.network.models import Device as PydanticDevice, DeviceType
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import NeighborLink


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


@pytest.fixture
def repo(store):
    return SQLiteRepository(store)


@pytest.fixture
def seeded(store, repo):
    store.add_device(PydanticDevice(
        id="dev-1",
        name="core-rtr-01",
        vendor="Cisco",
        device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
    ))
    store.add_device(PydanticDevice(
        id="dev-2",
        name="edge-sw-01",
        vendor="Arista",
        device_type=DeviceType.SWITCH,
        management_ip="10.0.0.2",
    ))
    store.add_device(PydanticDevice(
        id="dev-3",
        name="edge-sw-02",
        vendor="Arista",
        device_type=DeviceType.SWITCH,
        management_ip="10.0.0.3",
    ))
    return repo


# ── Tests ────────────────────────────────────────────────────────────────


class TestUpsertAndRead:
    def test_upsert_and_read(self, seeded):
        now = datetime.now(timezone.utc)
        link = NeighborLink(
            id="link-1",
            device_id="dev-1",
            local_interface="dev-1:Gi0/0",
            remote_device="dev-2",
            remote_interface="dev-2:Gi0/1",
            protocol="lldp",
            sources=["lldp_adapter"],
            first_seen=now,
            last_seen=now,
            confidence=0.95,
        )
        result = seeded.upsert_neighbor_link(link)
        assert result.id == "link-1"

        neighbors = seeded.get_neighbors("dev-1")
        assert len(neighbors) == 1
        n = neighbors[0]
        assert isinstance(n, NeighborLink)
        assert n.id == "link-1"
        assert n.device_id == "dev-1"
        assert n.local_interface == "dev-1:Gi0/0"
        assert n.remote_device == "dev-2"
        assert n.remote_interface == "dev-2:Gi0/1"
        assert n.protocol == "lldp"
        assert n.sources == ["lldp_adapter"]
        assert isinstance(n.first_seen, datetime)
        assert isinstance(n.last_seen, datetime)
        assert n.confidence == 0.95


class TestUpsertIdempotent:
    def test_upsert_idempotent(self, seeded):
        now = datetime.now(timezone.utc)
        link = NeighborLink(
            id="link-1",
            device_id="dev-1",
            local_interface="dev-1:Gi0/0",
            remote_device="dev-2",
            remote_interface="dev-2:Gi0/1",
            protocol="lldp",
            sources=["lldp_adapter"],
            first_seen=now,
            last_seen=now,
            confidence=0.8,
        )
        seeded.upsert_neighbor_link(link)
        seeded.upsert_neighbor_link(link)

        neighbors = seeded.get_neighbors("dev-1")
        assert len(neighbors) == 1


class TestGetNeighborsEmpty:
    def test_get_neighbors_empty(self, seeded):
        neighbors = seeded.get_neighbors("nonexistent-device")
        assert neighbors == []


class TestMultipleNeighbors:
    def test_multiple_neighbors(self, seeded):
        now = datetime.now(timezone.utc)
        link1 = NeighborLink(
            id="link-1",
            device_id="dev-1",
            local_interface="dev-1:Gi0/0",
            remote_device="dev-2",
            remote_interface="dev-2:Gi0/1",
            protocol="lldp",
            sources=["lldp_adapter"],
            first_seen=now,
            last_seen=now,
            confidence=0.9,
        )
        link2 = NeighborLink(
            id="link-2",
            device_id="dev-1",
            local_interface="dev-1:Gi0/1",
            remote_device="dev-3",
            remote_interface="dev-3:Gi0/0",
            protocol="cdp",
            sources=["cdp_adapter"],
            first_seen=now,
            last_seen=now,
            confidence=0.85,
        )
        seeded.upsert_neighbor_link(link1)
        seeded.upsert_neighbor_link(link2)

        neighbors = seeded.get_neighbors("dev-1")
        assert len(neighbors) == 2
        ids = {n.id for n in neighbors}
        assert ids == {"link-1", "link-2"}

        # dev-2 should have no neighbors (links are directional from device_id)
        assert seeded.get_neighbors("dev-2") == []
