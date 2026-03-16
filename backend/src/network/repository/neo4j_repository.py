"""Neo4jRepository — delegates simple reads to SQLite, graph queries to Neo4j.

This hybrid repository keeps SQLite as the system-of-record for basic CRUD
while leveraging Neo4j for graph-native operations (path finding, blast
radius, topology export).  Write operations persist to SQLite first and
then MERGE into Neo4j; Neo4j write failures are logged but never crash
the caller.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .domain import (
    Device,
    Interface,
    IPAddress,
    NeighborLink,
    Route,
    SecurityPolicy,
)
from .interface import TopologyRepository
from .sqlite_repository import SQLiteRepository
from .neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)


def _safe_str(value) -> str | None:
    """Convert datetime or other non-primitive values to strings for Cypher params."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class Neo4jRepository(TopologyRepository):
    """Hybrid repository: SQLite for CRUD, Neo4j for graph queries."""

    def __init__(
        self,
        sqlite_repo: SQLiteRepository,
        neo4j: Neo4jConnectionManager,
    ) -> None:
        self._sqlite = sqlite_repo
        self._neo4j = neo4j

    # ── Read methods (delegate to SQLite) ─────────────────────────────

    def get_device(self, device_id: str) -> Optional[Device]:
        return self._sqlite.get_device(device_id)

    def get_devices(
        self, site_id: str = None, device_type: str = None
    ) -> list[Device]:
        return self._sqlite.get_devices(site_id=site_id, device_type=device_type)

    def get_interfaces(self, device_id: str) -> list[Interface]:
        return self._sqlite.get_interfaces(device_id)

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        return self._sqlite.get_ip_addresses(interface_id)

    def get_routes(
        self, device_id: str, vrf_instance_id: str = None
    ) -> list[Route]:
        return self._sqlite.get_routes(device_id, vrf_instance_id=vrf_instance_id)

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

    # ── Write methods (SQLite + Neo4j sync) ───────────────────────────

    def upsert_device(self, device: Device) -> Device:
        result = self._sqlite.upsert_device(device)
        try:
            self._neo4j.execute_write(
                """
                MERGE (d:Device {id: $id})
                SET d.hostname = $hostname, d.vendor = $vendor, d.model = $model,
                    d.serial = $serial, d.device_type = $device_type, d.site_id = $site_id,
                    d.ha_mode = $ha_mode, d.confidence = $confidence, d.last_synced = timestamp()
                """,
                {
                    "id": device.id,
                    "hostname": device.hostname,
                    "vendor": device.vendor,
                    "model": device.model,
                    "serial": device.serial,
                    "device_type": device.device_type,
                    "site_id": device.site_id,
                    "ha_mode": device.ha_mode or "",
                    "confidence": device.confidence,
                },
            )
        except Exception:
            logger.warning("Neo4j sync failed for device %s", device.id, exc_info=True)
        return result

    def upsert_interface(self, interface: Interface) -> Interface:
        result = self._sqlite.upsert_interface(interface)
        try:
            self._neo4j.execute_write(
                """
                MATCH (d:Device {id: $device_id})
                MERGE (i:Interface {id: $id})
                SET i.name = $name, i.device_id = $device_id, i.mac = $mac,
                    i.admin_state = $admin_state, i.oper_state = $oper_state,
                    i.speed = $speed, i.mtu = $mtu, i.vrf_instance_id = $vrf_instance_id,
                    i.confidence = $confidence, i.last_synced = timestamp()
                MERGE (d)-[:HAS_INTERFACE]->(i)
                """,
                {
                    "id": interface.id,
                    "device_id": interface.device_id,
                    "name": interface.name,
                    "mac": interface.mac or "",
                    "admin_state": interface.admin_state,
                    "oper_state": interface.oper_state,
                    "speed": interface.speed or "",
                    "mtu": interface.mtu or 0,
                    "vrf_instance_id": interface.vrf_instance_id or "",
                    "confidence": interface.confidence,
                },
            )
        except Exception:
            logger.warning("Neo4j sync failed for interface %s", interface.id, exc_info=True)
        return result

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        result = self._sqlite.upsert_neighbor_link(link)
        try:
            self._neo4j.execute_write(
                """
                MATCH (i1:Interface {id: $local_iface})
                MATCH (i2:Interface {id: $remote_iface})
                MERGE (l:Link {id: $link_id})
                SET l.protocol = $protocol, l.confidence = $confidence,
                    l.last_synced = timestamp()
                MERGE (i1)-[:CONNECTED_TO]->(l)
                MERGE (l)-[:CONNECTED_TO]->(i2)
                """,
                {
                    "link_id": link.id,
                    "local_iface": link.local_interface,
                    "remote_iface": link.remote_interface,
                    "protocol": link.protocol,
                    "confidence": link.confidence,
                },
            )
        except Exception:
            logger.warning("Neo4j sync failed for neighbor link %s", link.id, exc_info=True)
        return result

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        return self._sqlite.upsert_ip_address(ip_address)

    def upsert_route(self, route: Route) -> Route:
        return self._sqlite.upsert_route(route)

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        return self._sqlite.upsert_security_policy(policy)

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        return self._sqlite.mark_stale(entity_type, entity_id)

    # ── Graph queries (Neo4j) ─────────────────────────────────────────

    def find_paths(
        self, src_ip: str, dst_ip: str, vrf: str = "default", k: int = 3
    ) -> list[dict]:
        """Return up to *k* shortest forwarding paths between two IP addresses."""
        try:
            rows = self._neo4j.execute_read(
                """
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
                """,
                {"src_ip": src_ip, "dst_ip": dst_ip, "k": k},
            )
            return [{"hops": row["hops"], "hop_count": row["hop_count"]} for row in rows]
        except Exception:
            logger.warning(
                "Neo4j find_paths failed for %s -> %s", src_ip, dst_ip, exc_info=True
            )
            return []

    def blast_radius(self, device_id: str) -> dict:
        """Compute the blast radius if the given device fails."""
        try:
            rows = self._neo4j.execute_read(
                """
                MATCH (failed:Device {id: $device_id})
                OPTIONAL MATCH (failed)-[:HAS_INTERFACE]->(i1:Interface)
                               -[:CONNECTED_TO]-(l:Link)
                               -[:CONNECTED_TO]-(i2:Interface)
                               <-[:HAS_INTERFACE]-(neighbor:Device)
                WHERE neighbor.id <> $device_id
                WITH failed, COLLECT(DISTINCT neighbor.id) AS affected
                OPTIONAL MATCH (failed)-[:HAS_INTERFACE]->(i1:Interface)
                               -[:CONNECTED_TO]-(l1:Link)
                               -[:CONNECTED_TO]-(i2:Interface)
                               <-[:HAS_INTERFACE]-(n1:Device)
                               -[:HAS_INTERFACE]->(i3:Interface)
                               -[:CONNECTED_TO]-(l2:Link)
                               -[:CONNECTED_TO]-(i4:Interface)
                               <-[:HAS_INTERFACE]-(n2:Device)
                WHERE n2.id <> $device_id AND NOT n2.id IN affected
                WITH affected, COLLECT(DISTINCT n2.id) AS hop2
                WITH affected + hop2 AS all_affected
                RETURN all_affected AS affected_devices
                """,
                {"device_id": device_id},
            )
            affected = rows[0]["affected_devices"] if rows else []
            return {
                "failed_device": device_id,
                "affected_devices": affected,
                "affected_tunnels": [],
                "affected_sites": [],
                "affected_vpcs": [],
                "severed_paths": 0,
            }
        except Exception:
            logger.warning(
                "Neo4j blast_radius failed for %s", device_id, exc_info=True
            )
            return {
                "failed_device": device_id,
                "affected_devices": [],
                "affected_tunnels": [],
                "affected_sites": [],
                "affected_vpcs": [],
                "severed_paths": 0,
            }

    def get_topology_export(self, site_id: str = None) -> dict:
        """Export the topology graph, optionally scoped to a site."""
        try:
            # ── Nodes ──
            if site_id:
                node_rows = self._neo4j.execute_read(
                    "MATCH (d:Device) WHERE d.site_id = $site_id RETURN d",
                    {"site_id": site_id},
                )
            else:
                node_rows = self._neo4j.execute_read("MATCH (d:Device) RETURN d")

            nodes = []
            device_ids = []
            for row in node_rows:
                props = dict(row["d"])
                nodes.append(props)
                device_ids.append(props["id"])

            if not device_ids:
                return {"nodes": [], "edges": [], "device_count": 0, "edge_count": 0}

            # ── Edges ──
            # Use elementId(d1) < elementId(d2) to deduplicate undirected edges
            # since string comparison on device IDs may not match the
            # directed CONNECTED_TO pattern (Interface->Link->Interface).
            edge_rows = self._neo4j.execute_read(
                """
                MATCH (d1:Device)-[:HAS_INTERFACE]->(i1:Interface)
                      -[:CONNECTED_TO]->(l:Link)
                      -[:CONNECTED_TO]->(i2:Interface)
                      <-[:HAS_INTERFACE]-(d2:Device)
                WHERE d1.id IN $device_ids AND d2.id IN $device_ids
                      AND elementId(d1) < elementId(d2)
                RETURN d1.id AS source, d2.id AS target,
                       i1.id AS source_interface, i2.id AS target_interface,
                       l.protocol AS protocol, l.confidence AS confidence
                """,
                {"device_ids": device_ids},
            )
            edges = [dict(row) for row in edge_rows]

            return {
                "nodes": nodes,
                "edges": edges,
                "device_count": len(nodes),
                "edge_count": len(edges),
            }
        except Exception:
            logger.warning("Neo4j get_topology_export failed", exc_info=True)
            return {"nodes": [], "edges": [], "device_count": 0, "edge_count": 0}
