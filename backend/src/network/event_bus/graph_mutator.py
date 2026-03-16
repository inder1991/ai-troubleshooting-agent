"""GraphMutatorConsumer — subscribes to topology events and applies MERGE to Neo4j.

Listens on all topology channels and translates each event into the
corresponding Cypher MERGE so that the knowledge graph stays in sync
with the live topology state.
"""

from __future__ import annotations

import logging
from typing import Any

from src.network.event_bus.base import EventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED,
    INTERFACE_CHANGED,
    LINK_DISCOVERED,
    ROUTE_CHANGED,
    POLICY_CHANGED,
    STALE_DETECTED,
)
from src.network.repository.neo4j_connection import Neo4jConnectionManager

logger = logging.getLogger(__name__)


class GraphMutatorConsumer:
    """Consumes topology events and writes corresponding mutations to Neo4j."""

    def __init__(self, neo4j: Neo4jConnectionManager) -> None:
        self._neo4j = neo4j

    async def subscribe(self, bus: EventBus) -> None:
        """Subscribe to all topology channels on *bus*."""
        await bus.subscribe(DEVICE_CHANGED, self._handle_device)
        await bus.subscribe(INTERFACE_CHANGED, self._handle_interface)
        await bus.subscribe(LINK_DISCOVERED, self._handle_link)
        await bus.subscribe(ROUTE_CHANGED, self._handle_route)
        await bus.subscribe(POLICY_CHANGED, self._handle_policy)
        await bus.subscribe(STALE_DETECTED, self._handle_stale)

    # ── Handlers ──────────────────────────────────────────────────────

    async def _handle_device(self, channel: str, event: dict[str, Any]) -> None:
        data = event["data"]
        entity_id = event["entity_id"]
        query = (
            "MERGE (d:Device {id: $id}) "
            "SET d.hostname=$hostname, d.vendor=$vendor, "
            "d.device_type=$device_type, d.site_id=$site_id, "
            "d.last_synced=timestamp()"
        )
        params = {
            "id": entity_id,
            "hostname": data.get("hostname", ""),
            "vendor": data.get("vendor", ""),
            "device_type": data.get("device_type", ""),
            "site_id": data.get("site_id", ""),
        }
        try:
            self._neo4j.execute_write(query, params)
            logger.info("MERGE Device %s", entity_id)
        except Exception:
            logger.error("Failed to MERGE Device %s", entity_id, exc_info=True)

    async def _handle_interface(self, channel: str, event: dict[str, Any]) -> None:
        data = event["data"]
        entity_id = event["entity_id"]
        query = (
            "MERGE (i:Interface {id: $id}) "
            "SET i.name=$name, i.device_id=$device_id, i.mac=$mac, "
            "i.last_synced=timestamp() "
            "WITH i "
            "MATCH (d:Device {id: $device_id}) "
            "MERGE (d)-[:HAS_INTERFACE]->(i)"
        )
        params = {
            "id": entity_id,
            "name": data.get("name", ""),
            "device_id": data.get("device_id", ""),
            "mac": data.get("mac", ""),
        }
        try:
            self._neo4j.execute_write(query, params)
            logger.info("MERGE Interface %s", entity_id)
        except Exception:
            logger.error("Failed to MERGE Interface %s", entity_id, exc_info=True)

    async def _handle_link(self, channel: str, event: dict[str, Any]) -> None:
        data = event["data"]
        entity_id = event["entity_id"]
        query = (
            "MATCH (i1:Interface {id: $local_iface}) "
            "MATCH (i2:Interface {id: $remote_iface}) "
            "MERGE (l:Link {id: $link_id}) "
            "SET l.protocol=$protocol, l.last_synced=timestamp() "
            "MERGE (i1)-[:CONNECTED_TO]->(l) "
            "MERGE (l)-[:CONNECTED_TO]->(i2)"
        )
        params = {
            "link_id": entity_id,
            "local_iface": data.get("local_iface", ""),
            "remote_iface": data.get("remote_iface", ""),
            "protocol": data.get("protocol", ""),
        }
        try:
            self._neo4j.execute_write(query, params)
            logger.info("MERGE Link %s", entity_id)
        except Exception:
            logger.error("Failed to MERGE Link %s", entity_id, exc_info=True)

    async def _handle_route(self, channel: str, event: dict[str, Any]) -> None:
        data = event["data"]
        entity_id = event["entity_id"]
        query = (
            "MERGE (r:Route {id: $id}) "
            "SET r.destination_cidr=$destination_cidr, "
            "r.next_hop=$next_hop, r.protocol=$protocol, "
            "r.last_synced=timestamp()"
        )
        params = {
            "id": entity_id,
            "destination_cidr": data.get("destination_cidr", ""),
            "next_hop": data.get("next_hop", ""),
            "protocol": data.get("protocol", ""),
        }
        try:
            self._neo4j.execute_write(query, params)
            logger.info("MERGE Route %s", entity_id)
        except Exception:
            logger.error("Failed to MERGE Route %s", entity_id, exc_info=True)

    async def _handle_policy(self, channel: str, event: dict[str, Any]) -> None:
        data = event.get("data", {})
        entity_id = event.get("entity_id", "")
        query = (
            "MERGE (sp:SecurityPolicy {id: $id}) "
            "SET sp.device_id=$device_id, sp.name=$name, "
            "sp.action=$action, sp.rule_order=$rule_order, "
            "sp.last_synced=timestamp()"
        )
        params = {
            "id": entity_id,
            "device_id": data.get("device_id", ""),
            "name": data.get("name", ""),
            "action": data.get("action", ""),
            "rule_order": data.get("rule_order", 0),
        }
        try:
            self._neo4j.execute_write(query, params)
            logger.info("MERGE SecurityPolicy %s", entity_id)
        except Exception:
            logger.error("Failed to MERGE SecurityPolicy %s", entity_id, exc_info=True)

    async def _handle_stale(self, channel: str, event: dict[str, Any]) -> None:
        entity_id = event["entity_id"]
        entity_type = event["entity_type"]
        label = entity_type.capitalize()
        query = (
            f"MATCH (n:{label} {{id: $id}}) "
            "SET n.stale=true, n.confidence=n.confidence*0.5"
        )
        params = {"id": entity_id}
        try:
            self._neo4j.execute_write(query, params)
            logger.info("SET stale on %s %s", label, entity_id)
        except Exception:
            logger.error("Failed to SET stale on %s %s", label, entity_id, exc_info=True)
