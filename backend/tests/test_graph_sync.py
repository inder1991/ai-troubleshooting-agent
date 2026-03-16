"""Tests for GraphSyncService — SQLite → Neo4j sync.

All tests are skip-gated on NEO4J_URI env var.
Run with: NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_sync.py -v
"""

import os
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set — Neo4j not available",
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def neo4j():
    """Create a Neo4jConnectionManager, apply schema, and clean before each test."""
    from src.network.repository.neo4j_connection import Neo4jConnectionManager
    from src.network.repository.neo4j_schema import Neo4jSchemaManager

    uri = os.environ["NEO4J_URI"]
    mgr = Neo4jConnectionManager(
        uri=uri,
        username="neo4j",
        password="debugduck",
    )
    Neo4jSchemaManager(mgr).apply()
    mgr.execute_write("MATCH (n) DETACH DELETE n")
    yield mgr
    mgr.close()


@pytest.fixture
def sqlite_repo(tmp_path):
    """Create a SQLiteRepository seeded with 2 devices, 2 interfaces, 1 subnet, 1 neighbor link."""
    from src.network.topology_store import TopologyStore
    from src.network.repository.sqlite_repository import SQLiteRepository
    from src.network.models import (
        Device as PydanticDevice,
        Interface as PydanticInterface,
        Subnet as PydanticSubnet,
        DeviceType,
    )
    from src.network.repository.domain import NeighborLink

    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)

    # Seed 2 devices
    now = datetime.now(timezone.utc).isoformat()
    store.add_device(PydanticDevice(
        id="dev-1",
        name="switch-1",
        vendor="Cisco",
        device_type=DeviceType.SWITCH,
        model="C9300",
        serial_number="SN001",
        site_id="site-a",
        discovered_at=now,
        last_seen=now,
    ))
    store.add_device(PydanticDevice(
        id="dev-2",
        name="router-1",
        vendor="Juniper",
        device_type=DeviceType.ROUTER,
        model="MX204",
        serial_number="SN002",
        site_id="site-a",
        discovered_at=now,
        last_seen=now,
    ))

    # Seed 2 interfaces (one per device) with IPs
    store.add_interface(PydanticInterface(
        id="dev-1:eth0",
        device_id="dev-1",
        name="eth0",
        ip="10.0.0.1",
        mac="00:11:22:33:44:55",
        admin_status="up",
        oper_status="up",
        speed="10G",
        mtu=9000,
    ))
    store.add_interface(PydanticInterface(
        id="dev-2:ge-0/0/0",
        device_id="dev-2",
        name="ge-0/0/0",
        ip="10.0.0.2",
        mac="AA:BB:CC:DD:EE:FF",
        admin_status="up",
        oper_status="up",
        speed="1G",
        mtu=1500,
    ))

    # Seed 1 subnet
    store.add_subnet(PydanticSubnet(
        id="subnet-1",
        cidr="10.0.0.0/24",
        gateway_ip="10.0.0.1",
    ))

    # Seed 1 neighbor link
    link = NeighborLink(
        id="link-1",
        device_id="dev-1",
        local_interface="dev-1:eth0",
        remote_device="dev-2",
        remote_interface="dev-2:ge-0/0/0",
        protocol="lldp",
        sources=["topology_store"],
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        confidence=0.95,
    )
    repo.upsert_neighbor_link(link)

    return repo


@pytest.fixture
def sync_service(sqlite_repo, neo4j):
    """Create a GraphSyncService wired to the test fixtures."""
    from src.network.repository.graph_sync import GraphSyncService

    return GraphSyncService(sqlite_repo, neo4j)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_sync_devices(sync_service, neo4j):
    """sync_devices should create 2 Device nodes."""
    count = sync_service.sync_devices()
    assert count == 2

    rows = neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS cnt")
    assert rows[0]["cnt"] == 2


def test_sync_interfaces_with_edges(sync_service, neo4j):
    """sync_interfaces should create 2 Interface nodes + 2 HAS_INTERFACE edges."""
    # Devices must exist first for MATCH to succeed
    sync_service.sync_devices()
    count = sync_service.sync_interfaces()
    assert count == 2

    rows = neo4j.execute_read("MATCH (i:Interface) RETURN count(i) AS cnt")
    assert rows[0]["cnt"] == 2

    rows = neo4j.execute_read("MATCH ()-[r:HAS_INTERFACE]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] == 2


def test_sync_ip_addresses(sync_service, neo4j):
    """sync_ip_addresses should create IPAddress nodes + HAS_IP edges."""
    sync_service.sync_devices()
    sync_service.sync_interfaces()
    count = sync_service.sync_ip_addresses()
    assert count >= 1

    rows = neo4j.execute_read("MATCH (ip:IPAddress) RETURN count(ip) AS cnt")
    assert rows[0]["cnt"] >= 1

    rows = neo4j.execute_read("MATCH ()-[r:HAS_IP]->() RETURN count(r) AS cnt")
    assert rows[0]["cnt"] >= 1


def test_sync_neighbor_links(sync_service, neo4j):
    """sync_neighbor_links should create 1 Link + CONNECTED_TO pattern."""
    sync_service.sync_devices()
    sync_service.sync_interfaces()
    count = sync_service.sync_neighbor_links()
    assert count == 1

    rows = neo4j.execute_read("MATCH (l:Link) RETURN count(l) AS cnt")
    assert rows[0]["cnt"] == 1

    # Verify full pattern: Interface → Link → Interface
    rows = neo4j.execute_read(
        "MATCH (i1:Interface)-[:CONNECTED_TO]->(l:Link)-[:CONNECTED_TO]->(i2:Interface) "
        "RETURN i1.id AS src, l.id AS link, i2.id AS dst"
    )
    assert len(rows) == 1
    assert rows[0]["link"] == "link-1"


def test_sync_subnets(sync_service, neo4j):
    """sync_subnets should create a Subnet node with correct cidr."""
    count = sync_service.sync_subnets()
    assert count == 1

    rows = neo4j.execute_read("MATCH (s:Subnet) RETURN s.id AS id, s.cidr AS cidr")
    assert len(rows) == 1
    assert rows[0]["id"] == "subnet-1"
    assert rows[0]["cidr"] == "10.0.0.0/24"


def test_full_sync(sync_service, neo4j):
    """full_sync should return a report with correct counts."""
    report = sync_service.full_sync()

    assert report["devices"] == 2
    assert report["interfaces"] == 2
    assert report["subnets"] == 1
    assert report["neighbor_links"] == 1
    assert report["ip_addresses"] >= 1


def test_sync_idempotent(sync_service, neo4j):
    """Running full_sync twice should not duplicate nodes."""
    sync_service.full_sync()
    sync_service.full_sync()

    rows = neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS cnt")
    assert rows[0]["cnt"] == 2

    rows = neo4j.execute_read("MATCH (i:Interface) RETURN count(i) AS cnt")
    assert rows[0]["cnt"] == 2

    rows = neo4j.execute_read("MATCH (l:Link) RETURN count(l) AS cnt")
    assert rows[0]["cnt"] == 1
