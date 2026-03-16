"""Tests for Neo4jRepository — hybrid SQLite + Neo4j graph queries.

All tests are skip-gated on NEO4J_URI env var.
Run with: cd backend && NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_repository.py -v
"""

import os
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set — Neo4j not available",
)


@pytest.fixture
def neo4j_repo(tmp_path):
    """Create full stack: SQLite seeded with 3 devices, synced to Neo4j."""
    from src.network.topology_store import TopologyStore
    from src.network.models import (
        Device as PydanticDevice,
        DeviceType,
        Interface as PydanticInterface,
    )
    from src.network.repository.sqlite_repository import SQLiteRepository
    from src.network.repository.neo4j_connection import Neo4jConnectionManager
    from src.network.repository.neo4j_schema import Neo4jSchemaManager
    from src.network.repository.graph_sync import GraphSyncService
    from src.network.repository.neo4j_repository import Neo4jRepository

    # ── SQLite setup ──
    db_path = str(tmp_path / "test_neo4j_repo.db")
    store = TopologyStore(db_path)
    sqlite_repo = SQLiteRepository(store)

    # ── Seed 3 devices ──
    store.add_device(PydanticDevice(
        id="rtr-01",
        name="core-router",
        vendor="Cisco",
        device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
        model="ISR4451",
        serial_number="RTR001",
        site_id="site-a",
    ))
    store.add_device(PydanticDevice(
        id="fw-01",
        name="edge-firewall",
        vendor="Palo Alto",
        device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.2",
        model="PA-5260",
        serial_number="FW001",
        site_id="site-a",
    ))
    store.add_device(PydanticDevice(
        id="sw-01",
        name="access-switch",
        vendor="Arista",
        device_type=DeviceType.SWITCH,
        management_ip="10.0.0.3",
        model="7050X",
        serial_number="SW001",
        site_id="site-a",
    ))

    # ── Seed interfaces ──
    # rtr-01 interfaces
    store.add_interface(PydanticInterface(
        id="rtr-01:eth0",
        device_id="rtr-01",
        name="eth0",
        ip="10.1.1.1",
        mac="AA:BB:CC:01:00:00",
        speed="10G",
        status="up",
    ))
    store.add_interface(PydanticInterface(
        id="rtr-01:eth1",
        device_id="rtr-01",
        name="eth1",
        ip="10.1.2.1",
        mac="AA:BB:CC:01:00:01",
        speed="10G",
        status="up",
    ))

    # fw-01 interfaces
    store.add_interface(PydanticInterface(
        id="fw-01:eth0",
        device_id="fw-01",
        name="eth0",
        ip="10.1.1.2",
        mac="AA:BB:CC:02:00:00",
        speed="10G",
        status="up",
    ))
    store.add_interface(PydanticInterface(
        id="fw-01:eth1",
        device_id="fw-01",
        name="eth1",
        ip="10.1.3.1",
        mac="AA:BB:CC:02:00:01",
        speed="10G",
        status="up",
    ))

    # sw-01 interfaces
    store.add_interface(PydanticInterface(
        id="sw-01:eth0",
        device_id="sw-01",
        name="eth0",
        ip="10.1.3.2",
        mac="AA:BB:CC:03:00:00",
        speed="1G",
        status="up",
    ))

    # ── Seed neighbor links: rtr-01 <-> fw-01, fw-01 <-> sw-01 ──
    import json
    now = datetime.now(timezone.utc).isoformat()

    store.upsert_neighbor_link(
        link_id="link-rtr-fw",
        device_id="rtr-01",
        local_interface="rtr-01:eth0",
        remote_device="fw-01",
        remote_interface="fw-01:eth0",
        protocol="lldp",
        sources=json.dumps(["lldp"]),
        first_seen=now,
        last_seen=now,
        confidence=0.95,
    )
    store.upsert_neighbor_link(
        link_id="link-fw-sw",
        device_id="fw-01",
        local_interface="fw-01:eth1",
        remote_device="sw-01",
        remote_interface="sw-01:eth0",
        protocol="lldp",
        sources=json.dumps(["lldp"]),
        first_seen=now,
        last_seen=now,
        confidence=0.95,
    )

    # ── Neo4j setup ──
    uri = os.environ["NEO4J_URI"]
    neo4j_mgr = Neo4jConnectionManager(
        uri=uri,
        username="neo4j",
        password="debugduck",
    )

    # Apply schema
    schema = Neo4jSchemaManager(neo4j_mgr)
    schema.apply()

    # Clean test data from Neo4j (avoid cross-test contamination)
    neo4j_mgr.execute_write("MATCH (n) DETACH DELETE n")

    # Sync SQLite → Neo4j
    sync = GraphSyncService(sqlite_repo, neo4j_mgr)
    sync.full_sync()

    # Create the hybrid repository
    repo = Neo4jRepository(sqlite_repo, neo4j_mgr)

    yield repo

    # Cleanup Neo4j
    neo4j_mgr.execute_write("MATCH (n) DETACH DELETE n")
    neo4j_mgr.close()


# ── Read delegation tests ─────────────────────────────────────────────


def test_get_device(neo4j_repo):
    """Reads a device from SQLite through Neo4jRepository."""
    device = neo4j_repo.get_device("rtr-01")
    assert device is not None
    assert device.id == "rtr-01"
    assert device.hostname == "core-router"
    assert device.vendor == "Cisco"


def test_get_devices(neo4j_repo):
    """Returns all 3 seeded devices."""
    devices = neo4j_repo.get_devices()
    assert len(devices) == 3
    ids = {d.id for d in devices}
    assert ids == {"rtr-01", "fw-01", "sw-01"}


def test_get_interfaces(neo4j_repo):
    """Returns interfaces for a specific device."""
    interfaces = neo4j_repo.get_interfaces("rtr-01")
    assert len(interfaces) == 2
    names = {i.name for i in interfaces}
    assert names == {"eth0", "eth1"}


def test_get_neighbors(neo4j_repo):
    """Returns neighbors for a device that has neighbor links."""
    neighbors = neo4j_repo.get_neighbors("rtr-01")
    assert len(neighbors) >= 1
    remote_devices = {n.remote_device for n in neighbors}
    assert "fw-01" in remote_devices


# ── Graph query tests ─────────────────────────────────────────────────


def test_find_paths(neo4j_repo):
    """Find path from rtr-01 IP to sw-01 IP — path should have >= 2 device hops."""
    paths = neo4j_repo.find_paths("10.1.1.1", "10.1.3.2")
    assert len(paths) >= 1
    first_path = paths[0]
    assert "hops" in first_path
    assert "hop_count" in first_path
    # Path should include at least src and dst devices
    assert len(first_path["hops"]) >= 2
    assert "rtr-01" in first_path["hops"]
    assert "sw-01" in first_path["hops"]


def test_blast_radius(neo4j_repo):
    """Blast radius of fw-01 should affect at least 1 device."""
    result = neo4j_repo.blast_radius("fw-01")
    assert result["failed_device"] == "fw-01"
    assert isinstance(result["affected_devices"], list)
    assert len(result["affected_devices"]) >= 1
    # fw-01 connects rtr-01 and sw-01, so at least one should be affected
    affected_set = set(result["affected_devices"])
    assert affected_set & {"rtr-01", "sw-01"}
    # Verify structure has all expected keys
    assert "affected_tunnels" in result
    assert "affected_sites" in result
    assert "affected_vpcs" in result
    assert "severed_paths" in result


def test_topology_export(neo4j_repo):
    """Export should have 3 nodes and >= 2 edges."""
    export = neo4j_repo.get_topology_export()
    assert export["device_count"] == 3
    assert len(export["nodes"]) == 3
    assert export["edge_count"] >= 2
    assert len(export["edges"]) >= 2

    # Verify node structure
    node_ids = {n["id"] for n in export["nodes"]}
    assert node_ids == {"rtr-01", "fw-01", "sw-01"}

    # Verify edge structure
    for edge in export["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "source_interface" in edge
        assert "target_interface" in edge


def test_topology_export_filtered_by_site(neo4j_repo):
    """Export filtered by site_id returns only matching devices."""
    export = neo4j_repo.get_topology_export(site_id="site-a")
    assert export["device_count"] == 3

    # Non-existent site returns empty
    export_empty = neo4j_repo.get_topology_export(site_id="site-nonexistent")
    assert export_empty["device_count"] == 0
    assert export_empty["edge_count"] == 0
