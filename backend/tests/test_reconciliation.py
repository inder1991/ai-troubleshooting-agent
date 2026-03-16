"""Tests for ReconciliationService — SQLite ↔ Neo4j drift detection and repair.

All tests are skip-gated on NEO4J_URI env var.
Run with: NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_reconciliation.py -v
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
def setup(tmp_path):
    """Create SQLite store + repo with 2 devices, Neo4j connection with clean graph."""
    from src.network.topology_store import TopologyStore
    from src.network.repository.sqlite_repository import SQLiteRepository
    from src.network.repository.neo4j_connection import Neo4jConnectionManager
    from src.network.repository.neo4j_schema import Neo4jSchemaManager
    from src.network.models import (
        Device as PydanticDevice,
        DeviceType,
    )

    # SQLite side
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)

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

    # Neo4j side
    uri = os.environ["NEO4J_URI"]
    neo4j = Neo4jConnectionManager(
        uri=uri,
        username="neo4j",
        password="debugduck",
    )
    Neo4jSchemaManager(neo4j).apply()
    neo4j.execute_write("MATCH (n) DETACH DELETE n")

    yield repo, neo4j
    neo4j.close()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_full_reconciliation(setup):
    """reconcile() should sync all devices and report status=ok."""
    repo, neo4j = setup
    from src.network.repository.reconciliation import ReconciliationService

    svc = ReconciliationService(repo, neo4j)
    report = svc.reconcile()

    assert report["status"] == "ok"
    assert report["devices_in_sqlite"] == 2
    assert report["devices_in_neo4j"] == 2


def test_detects_stale_neo4j_nodes(setup):
    """An orphan Neo4j node not in SQLite should appear in stale_in_neo4j."""
    repo, neo4j = setup
    from src.network.repository.reconciliation import ReconciliationService
    from src.network.repository.graph_sync import GraphSyncService

    # Sync first so Neo4j has the 2 real devices
    GraphSyncService(repo, neo4j).full_sync()

    # Create an orphan device directly in Neo4j
    neo4j.execute_write(
        "CREATE (d:Device {id: $id, hostname: 'ghost'})",
        {"id": "orphan-01"},
    )

    svc = ReconciliationService(repo, neo4j)
    report = svc.reconcile()

    assert "orphan-01" in report["stale_in_neo4j"]
    # After full_sync the orphan still exists (MERGE won't delete it),
    # but it was marked stale
    rows = neo4j.execute_read(
        "MATCH (d:Device {id: 'orphan-01'}) RETURN d.stale AS stale"
    )
    assert len(rows) == 1
    assert rows[0]["stale"] is True


def test_detects_missing_neo4j_nodes(setup):
    """Without a prior sync, both devices should be detected as missing and then synced."""
    repo, neo4j = setup
    from src.network.repository.reconciliation import ReconciliationService

    # Do NOT sync first — Neo4j is empty
    svc = ReconciliationService(repo, neo4j)
    report = svc.reconcile()

    # Both should have been missing
    assert sorted(report["missing_in_neo4j"]) == ["dev-1", "dev-2"]

    # After reconciliation Neo4j should have both devices
    rows = neo4j.execute_read("MATCH (d:Device) RETURN d.id AS id ORDER BY d.id")
    assert [r["id"] for r in rows] == ["dev-1", "dev-2"]
