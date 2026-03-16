"""GraphSyncService — reads from SQLiteRepository and materializes nodes/edges in Neo4j.

All writes use idempotent MERGE so the sync is safe to run repeatedly.

Usage::

    sync = GraphSyncService(sqlite_repo, neo4j_manager)
    report = sync.full_sync()
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .sqlite_repository import SQLiteRepository
from .neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)


def _safe_str(value: Any) -> str | None:
    """Convert datetime or other non-primitive values to strings for Cypher params."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class GraphSyncService:
    """Synchronises the SQLite topology data into Neo4j using idempotent MERGE."""

    def __init__(
        self,
        repo: SQLiteRepository,
        neo4j: Neo4jConnectionManager,
    ) -> None:
        self._repo = repo
        self._neo4j = neo4j

    # ------------------------------------------------------------------
    # Full sync
    # ------------------------------------------------------------------

    def full_sync(self) -> dict:
        """Run every sync step in order and return a summary report."""
        report: dict[str, Any] = {}
        report["devices"] = self.sync_devices()
        report["interfaces"] = self.sync_interfaces()
        report["ip_addresses"] = self.sync_ip_addresses()
        report["subnets"] = self.sync_subnets()
        report["neighbor_links"] = self.sync_neighbor_links()
        logger.info("Full sync complete: %s", report)
        return report

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def sync_devices(self) -> int:
        """MERGE all devices from SQLite into Neo4j. Returns count synced."""
        devices = self._repo.get_devices()
        for dev in devices:
            self._neo4j.execute_write(
                """
                MERGE (d:Device {id: $id})
                SET d.hostname = $hostname, d.vendor = $vendor, d.model = $model,
                    d.serial = $serial, d.device_type = $device_type, d.site_id = $site_id,
                    d.ha_mode = $ha_mode, d.confidence = $confidence, d.last_synced = timestamp()
                """,
                {
                    "id": dev.id,
                    "hostname": dev.hostname,
                    "vendor": dev.vendor,
                    "model": dev.model,
                    "serial": dev.serial,
                    "device_type": dev.device_type,
                    "site_id": dev.site_id,
                    "ha_mode": dev.ha_mode or "",
                    "confidence": dev.confidence,
                },
            )
        logger.info("Synced %d devices", len(devices))
        return len(devices)

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    def sync_interfaces(self) -> int:
        """MERGE interfaces + HAS_INTERFACE edges. Returns count synced."""
        devices = self._repo.get_devices()
        count = 0
        for dev in devices:
            interfaces = self._repo.get_interfaces(dev.id)
            for iface in interfaces:
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
                        "id": iface.id,
                        "device_id": iface.device_id,
                        "name": iface.name,
                        "mac": iface.mac or "",
                        "admin_state": iface.admin_state,
                        "oper_state": iface.oper_state,
                        "speed": iface.speed or "",
                        "mtu": iface.mtu or 0,
                        "vrf_instance_id": iface.vrf_instance_id or "",
                        "confidence": iface.confidence,
                    },
                )
                count += 1
        logger.info("Synced %d interfaces", count)
        return count

    # ------------------------------------------------------------------
    # IP Addresses
    # ------------------------------------------------------------------

    def sync_ip_addresses(self) -> int:
        """MERGE IP addresses + HAS_IP edges. Returns count synced."""
        devices = self._repo.get_devices()
        count = 0
        for dev in devices:
            interfaces = self._repo.get_interfaces(dev.id)
            for iface in interfaces:
                ips = self._repo.get_ip_addresses(iface.id)
                for ip_addr in ips:
                    self._neo4j.execute_write(
                        """
                        MATCH (i:Interface {id: $iface_id})
                        MERGE (ip:IPAddress {id: $id})
                        SET ip.ip = $ip, ip.prefix_len = $prefix_len,
                            ip.assigned_to = $assigned_to, ip.last_synced = timestamp()
                        MERGE (i)-[:HAS_IP]->(ip)
                        """,
                        {
                            "id": ip_addr.id,
                            "iface_id": ip_addr.assigned_to,
                            "ip": ip_addr.ip,
                            "prefix_len": ip_addr.prefix_len or 0,
                            "assigned_to": ip_addr.assigned_to,
                        },
                    )
                    count += 1
        logger.info("Synced %d IP addresses", count)
        return count

    # ------------------------------------------------------------------
    # Subnets
    # ------------------------------------------------------------------

    def sync_subnets(self) -> int:
        """MERGE subnets. Returns count synced."""
        store = self._repo._store
        if not hasattr(store, "list_subnets"):
            logger.warning("TopologyStore has no list_subnets — skipping subnet sync")
            return 0

        subnets = store.list_subnets()
        for subnet in subnets:
            self._neo4j.execute_write(
                """
                MERGE (s:Subnet {id: $id})
                SET s.cidr = $cidr, s.gateway_ip = $gateway_ip, s.last_synced = timestamp()
                """,
                {
                    "id": subnet.id,
                    "cidr": subnet.cidr,
                    "gateway_ip": subnet.gateway_ip if hasattr(subnet, "gateway_ip") else "",
                },
            )
        logger.info("Synced %d subnets", len(subnets))
        return len(subnets)

    # ------------------------------------------------------------------
    # Neighbor Links
    # ------------------------------------------------------------------

    def sync_neighbor_links(self) -> int:
        """MERGE neighbor links as Interface → Link → Interface. Returns count synced."""
        devices = self._repo.get_devices()
        seen_link_ids: set[str] = set()
        count = 0

        for dev in devices:
            neighbors = self._repo.get_neighbors(dev.id)
            for link in neighbors:
                # Avoid syncing the same link twice (each end-device reports it)
                if link.id in seen_link_ids:
                    continue
                seen_link_ids.add(link.id)

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
                count += 1
        logger.info("Synced %d neighbor links", count)
        return count
