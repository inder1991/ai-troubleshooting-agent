# KG Architecture Overhaul — Phase 2: Neo4j Graph Database Integration

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Neo4j as the graph query engine behind the TopologyRepository interface. SQLite remains the system of record (writes go to SQLite first, then sync to Neo4j). Neo4j handles graph-native queries: pathfinding, blast radius, topology export, and neighbor traversal.

**Architecture:** New `Neo4jRepository` implements `TopologyRepository`. It wraps SQLiteRepository for writes (dual-write: SQLite + Neo4j) and uses Cypher for graph reads. A `GraphSyncService` keeps Neo4j in sync with SQLite. Neo4j can be fully rebuilt from SQLite at any time (crash recovery).

**Tech Stack:** neo4j Python driver, Docker (neo4j:5-community), pytest, existing TopologyRepository interface from Phase 1.

**Design Doc:** `docs/plans/2026-03-16-kg-architecture-overhaul-design.md`

**Depends on:** Phase 1 complete (TopologyRepository, SQLiteRepository, domain models, neighbor_links table)

---

## Task 1: Neo4j Infrastructure Setup

**Files:**
- Create: `backend/docker-compose.neo4j.yml`
- Create: `backend/src/network/repository/neo4j_connection.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_neo4j_connection.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_neo4j_connection.py
"""Tests for Neo4j connection manager."""
import os
import pytest

# Skip entire module if Neo4j is not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set — Neo4j not available"
)

from src.network.repository.neo4j_connection import Neo4jConnectionManager


class TestNeo4jConnection:
    def test_connect_and_verify(self):
        """Can connect to Neo4j and run a simple query."""
        manager = Neo4jConnectionManager(
            uri=os.environ["NEO4J_URI"],
            username=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
        )
        try:
            result = manager.execute_read("RETURN 1 AS n")
            assert result[0]["n"] == 1
        finally:
            manager.close()

    def test_connection_context_manager(self):
        """Works as a context manager."""
        with Neo4jConnectionManager(
            uri=os.environ["NEO4J_URI"],
            username=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
        ) as manager:
            result = manager.execute_read("RETURN 'hello' AS msg")
            assert result[0]["msg"] == "hello"

    def test_execute_write(self):
        """Can write and read back a node."""
        with Neo4jConnectionManager(
            uri=os.environ["NEO4J_URI"],
            username=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
        ) as manager:
            # Clean up
            manager.execute_write("MATCH (n:_TestNode) DELETE n")
            # Write
            manager.execute_write(
                "CREATE (n:_TestNode {id: $id, name: $name})",
                {"id": "test-1", "name": "Test Node"}
            )
            # Read back
            result = manager.execute_read(
                "MATCH (n:_TestNode {id: $id}) RETURN n.name AS name",
                {"id": "test-1"}
            )
            assert result[0]["name"] == "Test Node"
            # Clean up
            manager.execute_write("MATCH (n:_TestNode) DELETE n")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_neo4j_connection.py -v`
Expected: SKIP (NEO4J_URI not set) or FAIL (module not found)

**Step 3: Write implementation**

```yaml
# backend/docker-compose.neo4j.yml
version: '3.8'
services:
  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"   # HTTP browser
      - "7687:7687"   # Bolt protocol
    environment:
      NEO4J_AUTH: neo4j/debugduck
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_memory_heap_max__size: 1G
      NEO4J_dbms_memory_pagecache_size: 512M
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "debugduck", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  neo4j_data:
```

Add to `backend/requirements.txt`:
```
# Graph Database
neo4j>=5.0.0
```

```python
# backend/src/network/repository/neo4j_connection.py
"""Neo4j connection manager with session pooling."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Neo4jConnectionManager:
    """Manages Neo4j driver lifecycle and provides read/write session helpers.

    Usage:
        with Neo4jConnectionManager(uri, user, password) as mgr:
            result = mgr.execute_read("MATCH (n) RETURN count(n) AS c")
    """

    def __init__(self, uri: str, username: str = "neo4j",
                 password: str = "debugduck", database: str = "neo4j"):
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database
        # Verify connectivity
        self._driver.verify_connectivity()
        logger.info("Neo4j connected: %s", uri)

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> Neo4jConnectionManager:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def execute_read(self, query: str, params: dict = None) -> list[dict]:
        """Execute a read-only Cypher query and return results as dicts."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def execute_write(self, query: str, params: dict = None) -> list[dict]:
        """Execute a write Cypher query and return results as dicts."""
        with self._driver.session(database=self._database) as session:
            result = session.run(query, params or {})
            return [dict(record) for record in result]

    def execute_write_tx(self, queries: list[tuple[str, dict]]) -> None:
        """Execute multiple write queries in a single transaction."""
        with self._driver.session(database=self._database) as session:
            with session.begin_transaction() as tx:
                for query, params in queries:
                    tx.run(query, params or {})
                tx.commit()
```

**Step 4: Start Neo4j and run tests**

```bash
cd backend && docker compose -f docker-compose.neo4j.yml up -d
# Wait for health check
sleep 10
NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_connection.py -v
```
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/docker-compose.neo4j.yml backend/src/network/repository/neo4j_connection.py backend/tests/test_neo4j_connection.py backend/requirements.txt
git commit -m "feat(neo4j): add Neo4j connection manager + Docker setup"
```

---

## Task 2: Neo4j Schema Setup (Constraints + Indexes)

**Files:**
- Create: `backend/src/network/repository/neo4j_schema.py`
- Test: `backend/tests/test_neo4j_schema.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_neo4j_schema.py
"""Tests for Neo4j schema initialization."""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set"
)

from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager


@pytest.fixture
def manager():
    mgr = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
    )
    yield mgr
    mgr.close()


class TestNeo4jSchema:
    def test_apply_schema(self, manager):
        """Schema applies without error."""
        schema = Neo4jSchemaManager(manager)
        schema.apply()

    def test_constraints_created(self, manager):
        """Required uniqueness constraints exist after schema apply."""
        schema = Neo4jSchemaManager(manager)
        schema.apply()

        constraints = manager.execute_read("SHOW CONSTRAINTS")
        constraint_labels = {c.get("labelsOrTypes", [None])[0] for c in constraints if c.get("labelsOrTypes")}

        assert "Device" in constraint_labels
        assert "Interface" in constraint_labels
        assert "IPAddress" in constraint_labels
        assert "Subnet" in constraint_labels

    def test_indexes_created(self, manager):
        """Required property indexes exist after schema apply."""
        schema = Neo4jSchemaManager(manager)
        schema.apply()

        indexes = manager.execute_read("SHOW INDEXES")
        index_labels = {i.get("labelsOrTypes", [None])[0] for i in indexes if i.get("labelsOrTypes")}

        assert "Device" in index_labels
        assert "Interface" in index_labels

    def test_schema_idempotent(self, manager):
        """Applying schema twice doesn't error."""
        schema = Neo4jSchemaManager(manager)
        schema.apply()
        schema.apply()  # Second apply should not raise
```

**Step 2: Run test to verify it fails**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_schema.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/neo4j_schema.py
"""Neo4j schema management — constraints, indexes, and migrations."""
from __future__ import annotations

import logging
from .neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)

# Schema version for migration tracking
SCHEMA_VERSION = 1

# Uniqueness constraints (also create indexes automatically)
CONSTRAINTS = [
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT interface_id IF NOT EXISTS FOR (i:Interface) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT ip_id IF NOT EXISTS FOR (ip:IPAddress) REQUIRE ip.id IS UNIQUE",
    "CREATE CONSTRAINT subnet_id IF NOT EXISTS FOR (s:Subnet) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT vrf_instance_id IF NOT EXISTS FOR (v:VRFInstance) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT route_id IF NOT EXISTS FOR (r:Route) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT site_id IF NOT EXISTS FOR (s:Site) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT zone_id IF NOT EXISTS FOR (z:Zone) REQUIRE z.id IS UNIQUE",
    "CREATE CONSTRAINT vlan_id IF NOT EXISTS FOR (v:VLAN) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT link_id IF NOT EXISTS FOR (l:Link) REQUIRE l.id IS UNIQUE",
    "CREATE CONSTRAINT neighbor_link_id IF NOT EXISTS FOR (nl:NeighborLink) REQUIRE nl.id IS UNIQUE",
    "CREATE CONSTRAINT tunnel_id IF NOT EXISTS FOR (t:Tunnel) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT security_policy_id IF NOT EXISTS FOR (sp:SecurityPolicy) REQUIRE sp.id IS UNIQUE",
]

# Additional property indexes for query performance
INDEXES = [
    "CREATE INDEX device_hostname IF NOT EXISTS FOR (d:Device) ON (d.hostname)",
    "CREATE INDEX device_serial IF NOT EXISTS FOR (d:Device) ON (d.serial)",
    "CREATE INDEX device_type_site IF NOT EXISTS FOR (d:Device) ON (d.device_type, d.site_id)",
    "CREATE INDEX interface_mac IF NOT EXISTS FOR (i:Interface) ON (i.mac)",
    "CREATE INDEX interface_device IF NOT EXISTS FOR (i:Interface) ON (i.device_id)",
    "CREATE INDEX ip_address IF NOT EXISTS FOR (ip:IPAddress) ON (ip.ip)",
    "CREATE INDEX subnet_cidr IF NOT EXISTS FOR (s:Subnet) ON (s.cidr)",
    "CREATE INDEX route_dest IF NOT EXISTS FOR (r:Route) ON (r.destination_cidr)",
    "CREATE INDEX vrf_device IF NOT EXISTS FOR (v:VRFInstance) ON (v.device_id)",
    "CREATE INDEX secpol_device_order IF NOT EXISTS FOR (sp:SecurityPolicy) ON (sp.device_id, sp.rule_order)",
]


class Neo4jSchemaManager:
    """Applies and manages Neo4j schema (constraints + indexes)."""

    def __init__(self, connection: Neo4jConnectionManager):
        self._conn = connection

    def apply(self) -> None:
        """Apply all constraints and indexes. Idempotent (IF NOT EXISTS)."""
        for stmt in CONSTRAINTS:
            try:
                self._conn.execute_write(stmt)
            except Exception as e:
                # Some Neo4j versions handle IF NOT EXISTS differently
                if "already exists" not in str(e).lower():
                    logger.warning("Constraint apply warning: %s", e)

        for stmt in INDEXES:
            try:
                self._conn.execute_write(stmt)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning("Index apply warning: %s", e)

        logger.info("Neo4j schema applied (v%d): %d constraints, %d indexes",
                     SCHEMA_VERSION, len(CONSTRAINTS), len(INDEXES))

    def get_schema_info(self) -> dict:
        """Return current schema state."""
        constraints = self._conn.execute_read("SHOW CONSTRAINTS")
        indexes = self._conn.execute_read("SHOW INDEXES")
        return {
            "schema_version": SCHEMA_VERSION,
            "constraints": len(constraints),
            "indexes": len(indexes),
        }
```

**Step 4: Run tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_schema.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/neo4j_schema.py backend/tests/test_neo4j_schema.py
git commit -m "feat(neo4j): schema manager with constraints and indexes"
```

---

## Task 3: Graph Sync Service (SQLite → Neo4j)

**Files:**
- Create: `backend/src/network/repository/graph_sync.py`
- Test: `backend/tests/test_graph_sync.py`

This is the core sync engine — reads canonical data from SQLite via the repository and materializes it in Neo4j.

**Step 1: Write the failing test**

```python
# backend/tests/test_graph_sync.py
"""Tests for GraphSyncService — syncs SQLite canonical data into Neo4j."""
import os
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set"
)

from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager
from src.network.repository.graph_sync import GraphSyncService
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device as PydanticDevice, DeviceType,
    Interface as PydanticInterface, Subnet,
)
from src.network.repository.domain import NeighborLink


@pytest.fixture
def neo4j():
    mgr = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
    )
    # Apply schema
    Neo4jSchemaManager(mgr).apply()
    # Clean graph before each test
    mgr.execute_write("MATCH (n) DETACH DELETE n")
    yield mgr
    mgr.close()


@pytest.fixture
def sqlite_repo(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)

    # Seed devices
    store.add_device(PydanticDevice(
        id="rtr-01", name="rtr-01", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco", model="ISR4451",
        serial_number="FTX1234", role="core", site_id="dc-east",
    ))
    store.add_device(PydanticDevice(
        id="sw-01", name="sw-01", device_type=DeviceType.switch,
        management_ip="10.0.0.2", vendor="cisco", model="C9300",
        role="access", site_id="dc-east",
    ))

    # Seed interfaces
    store.add_interface(PydanticInterface(
        id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0", ip="10.0.0.1/30",
    ))
    store.add_interface(PydanticInterface(
        id="sw-01:Gi0/48", device_id="sw-01", name="Gi0/48", ip="10.0.0.2/30",
    ))

    # Seed subnet
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30", gateway_ip="10.0.0.1"))

    # Seed neighbor link
    now = datetime.now(timezone.utc)
    repo.upsert_neighbor_link(NeighborLink(
        id="rtr-01:Gi0/0--sw-01:Gi0/48",
        device_id="rtr-01",
        local_interface="rtr-01:Gi0/0",
        remote_device="sw-01",
        remote_interface="sw-01:Gi0/48",
        protocol="lldp",
        sources=["lldp"],
        first_seen=now, last_seen=now, confidence=0.95,
    ))

    return repo


class TestGraphSync:
    def test_sync_devices(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.sync_devices()

        result = neo4j.execute_read("MATCH (d:Device) RETURN d.id AS id ORDER BY d.id")
        ids = [r["id"] for r in result]
        assert ids == ["rtr-01", "sw-01"]

    def test_sync_interfaces_with_edges(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.sync_devices()
        sync.sync_interfaces()

        # Interfaces exist
        result = neo4j.execute_read("MATCH (i:Interface) RETURN count(i) AS c")
        assert result[0]["c"] == 2

        # HAS_INTERFACE edges exist
        result = neo4j.execute_read(
            "MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface) RETURN count(*) AS c"
        )
        assert result[0]["c"] == 2

    def test_sync_ip_addresses(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.sync_devices()
        sync.sync_interfaces()
        sync.sync_ip_addresses()

        result = neo4j.execute_read("MATCH (ip:IPAddress) RETURN count(ip) AS c")
        assert result[0]["c"] >= 1

        # HAS_IP edges
        result = neo4j.execute_read(
            "MATCH (i:Interface)-[:HAS_IP]->(ip:IPAddress) RETURN count(*) AS c"
        )
        assert result[0]["c"] >= 1

    def test_sync_neighbor_links(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.sync_devices()
        sync.sync_interfaces()
        sync.sync_neighbor_links()

        # Link node exists
        result = neo4j.execute_read("MATCH (l:Link) RETURN count(l) AS c")
        assert result[0]["c"] == 1

        # CONNECTED_TO edges: Interface → Link → Interface
        result = neo4j.execute_read(
            "MATCH (i1:Interface)-[:CONNECTED_TO]->(l:Link)-[:CONNECTED_TO]->(i2:Interface) "
            "RETURN i1.id AS src, i2.id AS dst"
        )
        assert len(result) == 1

    def test_sync_subnets(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.sync_devices()
        sync.sync_interfaces()
        sync.sync_ip_addresses()
        sync.sync_subnets()

        result = neo4j.execute_read("MATCH (s:Subnet) RETURN s.cidr AS cidr")
        assert result[0]["cidr"] == "10.0.0.0/30"

    def test_full_sync(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        report = sync.full_sync()

        assert report["devices_synced"] == 2
        assert report["interfaces_synced"] == 2
        assert report["neighbor_links_synced"] == 1
        assert report["subnets_synced"] >= 1

    def test_sync_idempotent(self, neo4j, sqlite_repo):
        sync = GraphSyncService(sqlite_repo, neo4j)
        sync.full_sync()
        sync.full_sync()  # Second sync

        result = neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS c")
        assert result[0]["c"] == 2  # Not duplicated
```

**Step 2: Run test to verify it fails**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_sync.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/graph_sync.py
"""GraphSyncService — syncs canonical data from SQLite into Neo4j.

Reads from TopologyRepository (SQLite) and materializes nodes/edges
in Neo4j using idempotent MERGE operations.
"""
from __future__ import annotations

import logging
from .interface import TopologyRepository
from .neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)


class GraphSyncService:
    """Sync topology from repository (SQLite) into Neo4j graph."""

    def __init__(self, repo: TopologyRepository, neo4j: Neo4jConnectionManager):
        self._repo = repo
        self._neo4j = neo4j

    def full_sync(self) -> dict:
        """Run all sync steps in dependency order. Returns sync report."""
        report = {}
        report["devices_synced"] = self.sync_devices()
        report["interfaces_synced"] = self.sync_interfaces()
        report["ip_addresses_synced"] = self.sync_ip_addresses()
        report["subnets_synced"] = self.sync_subnets()
        report["neighbor_links_synced"] = self.sync_neighbor_links()
        logger.info("Full sync complete: %s", report)
        return report

    def sync_devices(self) -> int:
        """MERGE all devices into Neo4j."""
        devices = self._repo.get_devices()
        for device in devices:
            self._neo4j.execute_write("""
                MERGE (d:Device {id: $id})
                SET d.hostname = $hostname,
                    d.vendor = $vendor,
                    d.model = $model,
                    d.serial = $serial,
                    d.device_type = $device_type,
                    d.site_id = $site_id,
                    d.ha_mode = $ha_mode,
                    d.confidence = $confidence,
                    d.last_synced = timestamp()
            """, {
                "id": device.id,
                "hostname": device.hostname,
                "vendor": device.vendor,
                "model": device.model,
                "serial": device.serial,
                "device_type": device.device_type,
                "site_id": device.site_id,
                "ha_mode": device.ha_mode,
                "confidence": device.confidence,
            })
        return len(devices)

    def sync_interfaces(self) -> int:
        """MERGE all interfaces and create HAS_INTERFACE edges."""
        count = 0
        for device in self._repo.get_devices():
            interfaces = self._repo.get_interfaces(device.id)
            for iface in interfaces:
                self._neo4j.execute_write("""
                    MATCH (d:Device {id: $device_id})
                    MERGE (i:Interface {id: $id})
                    SET i.name = $name,
                        i.device_id = $device_id,
                        i.mac = $mac,
                        i.admin_state = $admin_state,
                        i.oper_state = $oper_state,
                        i.speed = $speed,
                        i.mtu = $mtu,
                        i.vrf_instance_id = $vrf_instance_id,
                        i.confidence = $confidence,
                        i.last_synced = timestamp()
                    MERGE (d)-[:HAS_INTERFACE]->(i)
                """, {
                    "id": iface.id,
                    "device_id": iface.device_id,
                    "name": iface.name,
                    "mac": iface.mac,
                    "admin_state": iface.admin_state,
                    "oper_state": iface.oper_state,
                    "speed": iface.speed,
                    "mtu": iface.mtu,
                    "vrf_instance_id": iface.vrf_instance_id,
                    "confidence": iface.confidence,
                })
                count += 1
        return count

    def sync_ip_addresses(self) -> int:
        """MERGE IP addresses and create HAS_IP edges."""
        count = 0
        for device in self._repo.get_devices():
            for iface in self._repo.get_interfaces(device.id):
                ips = self._repo.get_ip_addresses(iface.id)
                for ip in ips:
                    self._neo4j.execute_write("""
                        MATCH (i:Interface {id: $iface_id})
                        MERGE (ip:IPAddress {id: $id})
                        SET ip.ip = $ip,
                            ip.prefix_len = $prefix_len,
                            ip.assigned_to = $assigned_to,
                            ip.last_synced = timestamp()
                        MERGE (i)-[:HAS_IP]->(ip)
                    """, {
                        "id": ip.id,
                        "iface_id": iface.id,
                        "ip": ip.ip,
                        "prefix_len": ip.prefix_len,
                        "assigned_to": ip.assigned_to,
                    })
                    count += 1
        return count

    def sync_subnets(self) -> int:
        """MERGE subnets and create IN_SUBNET edges from IP addresses."""
        # Get subnets from SQLite store directly (repo may not expose this yet)
        try:
            subnets = self._repo._store.list_subnets() if hasattr(self._repo, '_store') else []
        except Exception:
            subnets = []

        for subnet in subnets:
            self._neo4j.execute_write("""
                MERGE (s:Subnet {id: $id})
                SET s.cidr = $cidr,
                    s.gateway_ip = $gateway_ip,
                    s.last_synced = timestamp()
            """, {
                "id": subnet.id,
                "cidr": subnet.cidr,
                "gateway_ip": subnet.gateway_ip or "",
            })

            # Link IP addresses to subnets via CIDR containment
            self._neo4j.execute_write("""
                MATCH (ip:IPAddress)
                WHERE ip.ip IS NOT NULL
                MATCH (s:Subnet {id: $subnet_id})
                WITH ip, s
                WHERE ip.ip STARTS WITH $prefix
                MERGE (ip)-[:IN_SUBNET]->(s)
            """, {
                "subnet_id": subnet.id,
                "prefix": subnet.cidr.split("/")[0].rsplit(".", 1)[0],  # rough prefix match
            })

        return len(subnets)

    def sync_neighbor_links(self) -> int:
        """MERGE neighbor links as Interface → Link → Interface."""
        count = 0
        for device in self._repo.get_devices():
            neighbors = self._repo.get_neighbors(device.id)
            for link in neighbors:
                self._neo4j.execute_write("""
                    MATCH (i1:Interface {id: $local_iface})
                    MATCH (i2:Interface {id: $remote_iface})
                    MERGE (l:Link {id: $link_id})
                    SET l.protocol = $protocol,
                        l.confidence = $confidence,
                        l.last_synced = timestamp()
                    MERGE (i1)-[:CONNECTED_TO]->(l)
                    MERGE (l)-[:CONNECTED_TO]->(i2)
                """, {
                    "link_id": link.id,
                    "local_iface": link.local_interface,
                    "remote_iface": link.remote_interface,
                    "protocol": link.protocol,
                    "confidence": link.confidence,
                })
                count += 1
        return count
```

**Step 4: Run tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_graph_sync.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/graph_sync.py backend/tests/test_graph_sync.py
git commit -m "feat(neo4j): GraphSyncService — full sync from SQLite to Neo4j"
```

---

## Task 4: Neo4j Repository — Graph Query Methods

**Files:**
- Create: `backend/src/network/repository/neo4j_repository.py`
- Test: `backend/tests/test_neo4j_repository.py`

This is the Neo4jRepository that implements TopologyRepository. Reads go to Neo4j (graph queries). Writes go to SQLite first, then sync to Neo4j.

**Step 1: Write the failing test**

```python
# backend/tests/test_neo4j_repository.py
"""Tests for Neo4jRepository — graph queries backed by Neo4j."""
import os
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set"
)

from src.network.repository.neo4j_repository import Neo4jRepository
from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager
from src.network.repository.graph_sync import GraphSyncService
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import Device, Interface, NeighborLink
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device as PydanticDevice, DeviceType,
    Interface as PydanticInterface, Subnet,
)


@pytest.fixture
def neo4j_repo(tmp_path):
    """Full stack: SQLite + Neo4j synced, wrapped in Neo4jRepository."""
    # SQLite
    store = TopologyStore(str(tmp_path / "test.db"))
    sqlite_repo = SQLiteRepository(store)

    # Seed data
    store.add_device(PydanticDevice(id="rtr-01", name="rtr-01", device_type=DeviceType.router,
                                     management_ip="10.0.0.1", vendor="cisco", role="core", site_id="dc-east"))
    store.add_device(PydanticDevice(id="fw-01", name="fw-01", device_type=DeviceType.firewall,
                                     management_ip="10.0.0.2", vendor="palo_alto", role="perimeter", site_id="dc-east"))
    store.add_device(PydanticDevice(id="sw-01", name="sw-01", device_type=DeviceType.switch,
                                     management_ip="10.0.0.3", vendor="cisco", role="access", site_id="dc-east"))

    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30", gateway_ip="10.0.0.1"))
    store.add_interface(PydanticInterface(id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0", ip="10.0.0.1/30"))
    store.add_interface(PydanticInterface(id="fw-01:eth1/1", device_id="fw-01", name="eth1/1", ip="10.0.0.2/30"))
    store.add_interface(PydanticInterface(id="sw-01:Gi0/48", device_id="sw-01", name="Gi0/48", ip="10.0.0.3/24"))

    # Neighbor links: rtr-01 ↔ fw-01, fw-01 ↔ sw-01
    now = datetime.now(timezone.utc)
    sqlite_repo.upsert_neighbor_link(NeighborLink(
        id="rtr-01:Gi0/0--fw-01:eth1/1", device_id="rtr-01",
        local_interface="rtr-01:Gi0/0", remote_device="fw-01",
        remote_interface="fw-01:eth1/1", protocol="lldp",
        sources=["lldp"], first_seen=now, last_seen=now, confidence=0.95,
    ))
    sqlite_repo.upsert_neighbor_link(NeighborLink(
        id="fw-01:eth1/1--sw-01:Gi0/48", device_id="fw-01",
        local_interface="fw-01:eth1/1", remote_device="sw-01",
        remote_interface="sw-01:Gi0/48", protocol="lldp",
        sources=["lldp"], first_seen=now, last_seen=now, confidence=0.95,
    ))

    # Neo4j
    neo4j_mgr = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
    )
    Neo4jSchemaManager(neo4j_mgr).apply()
    neo4j_mgr.execute_write("MATCH (n) DETACH DELETE n")

    # Sync
    sync = GraphSyncService(sqlite_repo, neo4j_mgr)
    sync.full_sync()

    # Create Neo4jRepository
    repo = Neo4jRepository(sqlite_repo=sqlite_repo, neo4j=neo4j_mgr)
    yield repo
    neo4j_mgr.close()


class TestNeo4jRepositoryReads:
    def test_get_device(self, neo4j_repo):
        device = neo4j_repo.get_device("rtr-01")
        assert device is not None
        assert device.hostname == "rtr-01"

    def test_get_devices(self, neo4j_repo):
        devices = neo4j_repo.get_devices()
        assert len(devices) == 3

    def test_get_interfaces(self, neo4j_repo):
        ifaces = neo4j_repo.get_interfaces("rtr-01")
        assert len(ifaces) >= 1

    def test_get_neighbors(self, neo4j_repo):
        neighbors = neo4j_repo.get_neighbors("rtr-01")
        assert len(neighbors) >= 1


class TestNeo4jGraphQueries:
    def test_find_paths(self, neo4j_repo):
        """Find path from rtr-01 to sw-01 (through fw-01)."""
        paths = neo4j_repo.find_paths("10.0.0.1", "10.0.0.3")
        assert len(paths) >= 1
        # Path should traverse rtr-01 → fw-01 → sw-01
        assert len(paths[0]["hops"]) >= 2

    def test_blast_radius(self, neo4j_repo):
        """Blast radius of fw-01 should affect rtr-01 and sw-01."""
        result = neo4j_repo.blast_radius("fw-01")
        assert "affected_devices" in result
        assert len(result["affected_devices"]) >= 1

    def test_topology_export(self, neo4j_repo):
        """Export produces nodes and edges."""
        export = neo4j_repo.get_topology_export()
        assert "nodes" in export
        assert "edges" in export
        assert len(export["nodes"]) == 3
        assert len(export["edges"]) >= 2
```

**Step 2: Run test to verify it fails**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_repository.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/neo4j_repository.py
"""Neo4jRepository — graph-backed TopologyRepository.

Delegates writes to SQLiteRepository (system of record) and
uses Neo4j for graph-native queries (pathfinding, blast radius, export).
"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime, timezone

from .interface import TopologyRepository
from .domain import (
    Device, Interface, IPAddress, NeighborLink, Route, SecurityPolicy,
)
from .sqlite_repository import SQLiteRepository
from .neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)


class Neo4jRepository(TopologyRepository):
    """Hybrid repository: SQLite for writes, Neo4j for graph queries."""

    def __init__(self, sqlite_repo: SQLiteRepository, neo4j: Neo4jConnectionManager):
        self._sqlite = sqlite_repo
        self._neo4j = neo4j

    # ── Reads: delegate to SQLite (source of truth) ──

    def get_device(self, device_id: str) -> Optional[Device]:
        return self._sqlite.get_device(device_id)

    def get_devices(self, site_id: str = None, device_type: str = None) -> list[Device]:
        return self._sqlite.get_devices(site_id=site_id, device_type=device_type)

    def get_interfaces(self, device_id: str) -> list[Interface]:
        return self._sqlite.get_interfaces(device_id)

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        return self._sqlite.get_ip_addresses(interface_id)

    def get_routes(self, device_id: str, vrf_instance_id: str = None) -> list[Route]:
        return self._sqlite.get_routes(device_id, vrf_instance_id)

    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        return self._sqlite.get_neighbors(device_id)

    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        return self._sqlite.get_security_policies(device_id)

    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        return self._sqlite.find_device_by_ip(ip)

    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        return self._sqlite.find_device_by_serial(serial)

    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        return self._sqlite.find_device_by_hostname(hostname)

    # ── Writes: delegate to SQLite (source of truth) ──

    def upsert_device(self, device: Device) -> Device:
        result = self._sqlite.upsert_device(device)
        # Sync to Neo4j
        try:
            self._neo4j.execute_write("""
                MERGE (d:Device {id: $id})
                SET d.hostname = $hostname, d.vendor = $vendor,
                    d.device_type = $device_type, d.site_id = $site_id,
                    d.confidence = $confidence, d.last_synced = timestamp()
            """, {
                "id": device.id, "hostname": device.hostname,
                "vendor": device.vendor, "device_type": device.device_type,
                "site_id": device.site_id, "confidence": device.confidence,
            })
        except Exception as e:
            logger.warning("Neo4j sync failed for device %s: %s", device.id, e)
        return result

    def upsert_interface(self, interface: Interface) -> Interface:
        result = self._sqlite.upsert_interface(interface)
        try:
            self._neo4j.execute_write("""
                MATCH (d:Device {id: $device_id})
                MERGE (i:Interface {id: $id})
                SET i.name = $name, i.device_id = $device_id,
                    i.mac = $mac, i.oper_state = $oper_state,
                    i.confidence = $confidence, i.last_synced = timestamp()
                MERGE (d)-[:HAS_INTERFACE]->(i)
            """, {
                "id": interface.id, "device_id": interface.device_id,
                "name": interface.name, "mac": interface.mac,
                "oper_state": interface.oper_state,
                "confidence": interface.confidence,
            })
        except Exception as e:
            logger.warning("Neo4j sync failed for interface %s: %s", interface.id, e)
        return result

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        return self._sqlite.upsert_ip_address(ip_address)

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        result = self._sqlite.upsert_neighbor_link(link)
        try:
            self._neo4j.execute_write("""
                MATCH (i1:Interface {id: $local_iface})
                MATCH (i2:Interface {id: $remote_iface})
                MERGE (l:Link {id: $link_id})
                SET l.protocol = $protocol, l.confidence = $confidence,
                    l.last_synced = timestamp()
                MERGE (i1)-[:CONNECTED_TO]->(l)
                MERGE (l)-[:CONNECTED_TO]->(i2)
            """, {
                "link_id": link.id,
                "local_iface": link.local_interface,
                "remote_iface": link.remote_interface,
                "protocol": link.protocol,
                "confidence": link.confidence,
            })
        except Exception as e:
            logger.warning("Neo4j sync failed for link %s: %s", link.id, e)
        return result

    def upsert_route(self, route: Route) -> Route:
        return self._sqlite.upsert_route(route)

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        return self._sqlite.upsert_security_policy(policy)

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        self._sqlite.mark_stale(entity_type, entity_id)
        try:
            label = entity_type.capitalize()
            self._neo4j.execute_write(
                f"MATCH (n:{label} {{id: $id}}) SET n.stale = true, n.confidence = n.confidence * 0.5",
                {"id": entity_id}
            )
        except Exception as e:
            logger.warning("Neo4j stale marking failed: %s", e)

    # ── Graph queries: use Neo4j (graph-native) ──

    def find_paths(self, src_ip: str, dst_ip: str,
                   vrf: str = "default", k: int = 3) -> list[dict]:
        """Find paths between two IPs using Neo4j graph traversal.

        Path structure: Device → Interface → Link → Interface → Device → ...
        """
        result = self._neo4j.execute_read("""
            MATCH (src_ip:IPAddress {ip: $src_ip})<-[:HAS_IP]-(src_iface:Interface)
                  <-[:HAS_INTERFACE]-(src_dev:Device)
            MATCH (dst_ip:IPAddress {ip: $dst_ip})<-[:HAS_IP]-(dst_iface:Interface)
                  <-[:HAS_INTERFACE]-(dst_dev:Device)
            MATCH path = shortestPath(
                (src_dev)-[:HAS_INTERFACE|CONNECTED_TO*..15]-(dst_dev)
            )
            WITH path, src_dev, dst_dev,
                 [n IN nodes(path) WHERE n:Device | n.id] AS device_hops,
                 length(path) AS hops
            RETURN device_hops AS hops, hops AS hop_count
            ORDER BY hop_count
            LIMIT $k
        """, {"src_ip": src_ip, "dst_ip": dst_ip, "k": k})

        return [{"hops": r["hops"], "hop_count": r["hop_count"]} for r in result]

    def blast_radius(self, device_id: str) -> dict:
        """Compute blast radius using Neo4j BFS from failed device."""
        result = self._neo4j.execute_read("""
            MATCH (failed:Device {id: $device_id})

            // Direct neighbors (1 hop via interfaces + links)
            OPTIONAL MATCH (failed)-[:HAS_INTERFACE]->()-[:CONNECTED_TO]->
                           ()<-[:CONNECTED_TO]-()<-[:HAS_INTERFACE]-(neighbor:Device)
            WHERE neighbor.id <> $device_id
            WITH failed, COLLECT(DISTINCT neighbor.id) AS affected

            // 2nd hop neighbors
            OPTIONAL MATCH (failed)-[:HAS_INTERFACE]->()-[:CONNECTED_TO]->
                           ()<-[:CONNECTED_TO]-()<-[:HAS_INTERFACE]-(n1:Device)
                           -[:HAS_INTERFACE]->()-[:CONNECTED_TO]->
                           ()<-[:CONNECTED_TO]-()<-[:HAS_INTERFACE]-(n2:Device)
            WHERE n2.id <> $device_id AND NOT n2.id IN affected
            WITH affected + COLLECT(DISTINCT n2.id) AS all_affected

            RETURN all_affected AS affected_devices
        """, {"device_id": device_id})

        affected = result[0]["affected_devices"] if result else []
        return {
            "failed_device": device_id,
            "affected_devices": affected,
            "affected_tunnels": [],
            "affected_sites": [],
            "affected_vpcs": [],
            "severed_paths": 0,
        }

    def get_topology_export(self, site_id: str = None) -> dict:
        """Export topology graph from Neo4j for frontend rendering."""
        # Nodes: all devices
        if site_id:
            device_rows = self._neo4j.execute_read(
                "MATCH (d:Device {site_id: $site_id}) RETURN d", {"site_id": site_id}
            )
        else:
            device_rows = self._neo4j.execute_read("MATCH (d:Device) RETURN d")

        nodes = []
        for row in device_rows:
            d = dict(row["d"])
            nodes.append({
                "id": d["id"],
                "type": "device",
                "hostname": d.get("hostname", ""),
                "vendor": d.get("vendor", ""),
                "device_type": d.get("device_type", ""),
                "site_id": d.get("site_id", ""),
                "confidence": d.get("confidence", 0.5),
                "stale": d.get("stale", False),
            })

        # Edges: all links between devices in scope
        device_ids = [n["id"] for n in nodes]
        edge_rows = self._neo4j.execute_read("""
            MATCH (d1:Device)-[:HAS_INTERFACE]->(i1:Interface)
                  -[:CONNECTED_TO]->(l:Link)
                  -[:CONNECTED_TO]->(i2:Interface)
                  <-[:HAS_INTERFACE]-(d2:Device)
            WHERE d1.id IN $device_ids AND d2.id IN $device_ids
              AND d1.id < d2.id
            RETURN d1.id AS source, d2.id AS target,
                   i1.id AS source_interface, i2.id AS target_interface,
                   l.protocol AS protocol, l.confidence AS confidence
        """, {"device_ids": device_ids})

        edges = []
        for row in edge_rows:
            edges.append({
                "id": f"e-{row['source']}-{row['target']}",
                "source": row["source"],
                "target": row["target"],
                "source_interface": row["source_interface"],
                "target_interface": row["target_interface"],
                "protocol": row.get("protocol", ""),
                "confidence": row.get("confidence", 0.5),
                "edge_type": "physical",
            })

        return {
            "nodes": nodes,
            "edges": edges,
            "device_count": len(nodes),
            "edge_count": len(edges),
        }
```

**Step 4: Run tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_repository.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/neo4j_repository.py backend/tests/test_neo4j_repository.py
git commit -m "feat(neo4j): Neo4jRepository with graph queries — paths, blast radius, export"
```

---

## Task 5: Nightly Reconciliation

**Files:**
- Create: `backend/src/network/repository/reconciliation.py`
- Test: `backend/tests/test_reconciliation.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_reconciliation.py
"""Tests for nightly reconciliation — rebuild Neo4j from SQLite."""
import os
import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_URI"),
    reason="NEO4J_URI not set"
)

from src.network.repository.neo4j_connection import Neo4jConnectionManager
from src.network.repository.neo4j_schema import Neo4jSchemaManager
from src.network.repository.graph_sync import GraphSyncService
from src.network.repository.reconciliation import ReconciliationService
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore
from src.network.models import Device as PydanticDevice, DeviceType


@pytest.fixture
def setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    store.add_device(PydanticDevice(id="rtr-01", name="rtr-01", device_type=DeviceType.router,
                                     management_ip="10.0.0.1", vendor="cisco"))
    store.add_device(PydanticDevice(id="sw-01", name="sw-01", device_type=DeviceType.switch,
                                     management_ip="10.0.0.2", vendor="cisco"))

    neo4j = Neo4jConnectionManager(
        uri=os.environ["NEO4J_URI"],
        username=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "debugduck"),
    )
    Neo4jSchemaManager(neo4j).apply()
    neo4j.execute_write("MATCH (n) DETACH DELETE n")

    yield repo, neo4j
    neo4j.close()


class TestReconciliation:
    def test_full_reconciliation(self, setup):
        repo, neo4j = setup
        recon = ReconciliationService(repo, neo4j)
        report = recon.reconcile()

        assert report["status"] == "ok"
        assert report["devices_in_sqlite"] == 2
        assert report["devices_in_neo4j"] == 2

    def test_detects_stale_neo4j_nodes(self, setup):
        """If Neo4j has nodes not in SQLite, reconciliation detects them."""
        repo, neo4j = setup

        # Sync first
        sync = GraphSyncService(repo, neo4j)
        sync.sync_devices()

        # Add orphan node directly to Neo4j
        neo4j.execute_write("CREATE (d:Device {id: 'orphan-01', hostname: 'orphan'})")

        recon = ReconciliationService(repo, neo4j)
        report = recon.reconcile()

        assert report["devices_in_sqlite"] == 2
        assert "orphan-01" in report.get("stale_in_neo4j", [])

    def test_detects_missing_neo4j_nodes(self, setup):
        """If SQLite has devices not in Neo4j, reconciliation syncs them."""
        repo, neo4j = setup

        recon = ReconciliationService(repo, neo4j)
        report = recon.reconcile()

        # After reconciliation, Neo4j should have both devices
        result = neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS c")
        assert result[0]["c"] == 2
```

**Step 2: Run test to verify it fails**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_reconciliation.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/repository/reconciliation.py
"""Nightly reconciliation — compare SQLite (truth) vs Neo4j, fix drift."""
from __future__ import annotations

import logging
from .interface import TopologyRepository
from .neo4j_connection import Neo4jConnectionManager
from .graph_sync import GraphSyncService

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Compares SQLite canonical state against Neo4j graph.

    Detects:
    - Nodes in Neo4j but not SQLite (stale → mark or remove)
    - Nodes in SQLite but not Neo4j (missing → sync)
    - Attribute drift (Neo4j out of date → update)
    """

    def __init__(self, repo: TopologyRepository, neo4j: Neo4jConnectionManager):
        self._repo = repo
        self._neo4j = neo4j
        self._sync = GraphSyncService(repo, neo4j)

    def reconcile(self) -> dict:
        """Run full reconciliation. Returns report."""
        report = {"status": "ok"}

        # Get device IDs from both stores
        sqlite_devices = {d.id for d in self._repo.get_devices()}
        neo4j_result = self._neo4j.execute_read("MATCH (d:Device) RETURN d.id AS id")
        neo4j_devices = {r["id"] for r in neo4j_result}

        report["devices_in_sqlite"] = len(sqlite_devices)
        report["devices_in_neo4j_before"] = len(neo4j_devices)

        # Find stale nodes (in Neo4j but not SQLite)
        stale = neo4j_devices - sqlite_devices
        if stale:
            report["stale_in_neo4j"] = list(stale)
            for device_id in stale:
                self._neo4j.execute_write(
                    "MATCH (d:Device {id: $id}) SET d.stale = true",
                    {"id": device_id}
                )
            logger.warning("Marked %d stale devices in Neo4j: %s", len(stale), stale)

        # Find missing nodes (in SQLite but not Neo4j)
        missing = sqlite_devices - neo4j_devices
        if missing:
            report["missing_in_neo4j"] = list(missing)
            logger.info("Syncing %d missing devices to Neo4j", len(missing))

        # Full re-sync to fix any drift
        sync_report = self._sync.full_sync()
        report.update(sync_report)

        # Re-count Neo4j after sync
        neo4j_after = self._neo4j.execute_read("MATCH (d:Device) RETURN count(d) AS c")
        report["devices_in_neo4j"] = neo4j_after[0]["c"]

        return report
```

**Step 4: Run tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_reconciliation.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/reconciliation.py backend/tests/test_reconciliation.py
git commit -m "feat(neo4j): nightly reconciliation — detect drift between SQLite and Neo4j"
```

---

## Task 6: Run Full Test Suite — Verify No Regressions

**Files:** None (verification only)

**Step 1: Run all Phase 1 tests (no Neo4j required)**

Run: `cd backend && python3 -m pytest tests/test_repository_domain.py tests/test_repository_interface.py tests/test_sqlite_repository.py tests/test_neighbor_links.py tests/test_topology_validation.py tests/test_kg_uses_repository.py tests/test_repository_api_wiring.py -v`
Expected: ALL PASS (54 tests)

**Step 2: Run all Phase 2 Neo4j tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_connection.py tests/test_neo4j_schema.py tests/test_graph_sync.py tests/test_neo4j_repository.py tests/test_reconciliation.py -v`
Expected: ALL PASS

**Step 3: Run existing KG + topology tests**

Run: `cd backend && python3 -m pytest tests/test_knowledge_graph.py tests/test_topology_store_crud.py -v`
Expected: ALL PASS (61 tests, no regressions)

**Step 4: Commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: resolve test regressions from Neo4j integration"
```

---

## Summary

| Task | What | Files | Neo4j Required |
|------|------|-------|---------------|
| 1 | Connection manager + Docker | `neo4j_connection.py`, `docker-compose.neo4j.yml` | Yes |
| 2 | Schema (constraints + indexes) | `neo4j_schema.py` | Yes |
| 3 | Graph sync (SQLite → Neo4j) | `graph_sync.py` | Yes |
| 4 | Neo4jRepository (graph queries) | `neo4j_repository.py` | Yes |
| 5 | Nightly reconciliation | `reconciliation.py` | Yes |
| 6 | Full regression test | None | Both |

**After Phase 2 is complete:**
- Neo4j runs as graph query engine (pathfinding, blast radius, export)
- SQLite remains system of record (all writes go there first)
- GraphSyncService keeps Neo4j in sync
- ReconciliationService detects and fixes drift nightly
- All Neo4j tests are skip-gated (run only when NEO4J_URI is set)
- Phase 1 tests continue passing without Neo4j
- Ready for Phase 3: Kafka Event Bus (replaces sync with event-driven updates)
