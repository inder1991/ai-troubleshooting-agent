"""Neo4j schema manager — applies constraints and indexes for the knowledge graph.

Usage::

    with Neo4jConnectionManager(uri="bolt://localhost:7687") as mgr:
        schema = Neo4jSchemaManager(mgr)
        schema.apply()
        info = schema.get_schema_info()
"""

from __future__ import annotations

import logging
from typing import Any

from src.network.repository.neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ------------------------------------------------------------------
# Uniqueness constraints (13)
# ------------------------------------------------------------------
_UNIQUENESS_CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT interface_id IF NOT EXISTS FOR (i:Interface) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT ipaddress_id IF NOT EXISTS FOR (ip:IPAddress) REQUIRE ip.id IS UNIQUE",
    "CREATE CONSTRAINT subnet_id IF NOT EXISTS FOR (s:Subnet) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT vrfinstance_id IF NOT EXISTS FOR (v:VRFInstance) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT route_id IF NOT EXISTS FOR (r:Route) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT site_id IF NOT EXISTS FOR (s:Site) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT zone_id IF NOT EXISTS FOR (z:Zone) REQUIRE z.id IS UNIQUE",
    "CREATE CONSTRAINT vlan_id IF NOT EXISTS FOR (v:VLAN) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT link_id IF NOT EXISTS FOR (l:Link) REQUIRE l.id IS UNIQUE",
    "CREATE CONSTRAINT neighborlink_id IF NOT EXISTS FOR (n:NeighborLink) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT tunnel_id IF NOT EXISTS FOR (t:Tunnel) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT securitypolicy_id IF NOT EXISTS FOR (sp:SecurityPolicy) REQUIRE sp.id IS UNIQUE",
]

# ------------------------------------------------------------------
# Indexes (10)
# ------------------------------------------------------------------
_INDEXES: list[str] = [
    "CREATE INDEX device_hostname IF NOT EXISTS FOR (d:Device) ON (d.hostname)",
    "CREATE INDEX device_serial IF NOT EXISTS FOR (d:Device) ON (d.serial)",
    "CREATE INDEX device_type_site IF NOT EXISTS FOR (d:Device) ON (d.device_type, d.site_id)",
    "CREATE INDEX interface_mac IF NOT EXISTS FOR (i:Interface) ON (i.mac)",
    "CREATE INDEX interface_device_id IF NOT EXISTS FOR (i:Interface) ON (i.device_id)",
    "CREATE INDEX ipaddress_ip IF NOT EXISTS FOR (ip:IPAddress) ON (ip.ip)",
    "CREATE INDEX subnet_cidr IF NOT EXISTS FOR (s:Subnet) ON (s.cidr)",
    "CREATE INDEX route_destination_cidr IF NOT EXISTS FOR (r:Route) ON (r.destination_cidr)",
    "CREATE INDEX vrfinstance_device_id IF NOT EXISTS FOR (v:VRFInstance) ON (v.device_id)",
    "CREATE INDEX securitypolicy_device_rule IF NOT EXISTS FOR (sp:SecurityPolicy) ON (sp.device_id, sp.rule_order)",
]


class Neo4jSchemaManager:
    """Applies and inspects the Neo4j graph schema (constraints + indexes).

    All DDL statements use ``IF NOT EXISTS`` so ``apply()`` is idempotent.
    """

    def __init__(self, connection_manager: Neo4jConnectionManager) -> None:
        self._conn = connection_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self) -> None:
        """Apply all constraints and indexes.  Safe to call repeatedly."""
        for stmt in _UNIQUENESS_CONSTRAINTS:
            self._run_ddl(stmt)
        for stmt in _INDEXES:
            self._run_ddl(stmt)
        logger.info(
            "Schema v%d applied: %d constraints, %d indexes",
            SCHEMA_VERSION,
            len(_UNIQUENESS_CONSTRAINTS),
            len(_INDEXES),
        )

    def get_schema_info(self) -> dict[str, Any]:
        """Return a summary of the current schema state."""
        constraints = self._conn.execute_read("SHOW CONSTRAINTS")
        indexes = self._conn.execute_read("SHOW INDEXES")
        return {
            "schema_version": SCHEMA_VERSION,
            "constraint_count": len(constraints),
            "index_count": len(indexes),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_ddl(self, statement: str) -> None:
        """Execute a single DDL statement, logging but not raising on error."""
        try:
            self._conn.execute_write(statement)
        except Exception:
            logger.warning("DDL statement failed (may be expected on some editions): %s", statement, exc_info=True)
