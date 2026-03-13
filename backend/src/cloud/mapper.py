"""CloudResourceMapper — translates cloud_resources to canonical models."""
from __future__ import annotations

import json
import uuid
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)

MAPPER_VERSION = 1


def _extract_cidrs(raw: dict, provider: str) -> list[str]:
    if provider == "aws":
        cidrs = [raw.get("CidrBlock", "")]
        cidrs += [a["CidrBlock"] for a in raw.get("CidrBlockAssociationSet", [])
                  if "CidrBlock" in a]
        return [c for c in cidrs if c]
    elif provider == "azure":
        return raw.get("address_space", {}).get("address_prefixes", [])
    elif provider == "oracle":
        cidr = raw.get("cidr_block", "")
        return [cidr] if cidr else []
    return []


class CloudResourceMapper:
    """Translates cloud_resources rows into canonical models
    and writes to topology_store / policy_store."""

    _MAPPERS = {
        "vpc": "_map_network_segment",
        "subnet": "_map_subnet",
        "security_group": "_map_policy_group",
        "nacl": "_map_policy_group",
        "route_table": "_map_routing_table",
    }

    def __init__(self, topology_store, policy_store):
        self._topology_store = topology_store
        self._policy_store = policy_store

    async def map_resource(self, resource) -> None:
        handler_name = self._MAPPERS.get(resource.resource_type)
        if handler_name:
            handler = getattr(self, handler_name)
            try:
                raw = json.loads(resource.raw_json) if isinstance(resource.raw_json, str) else resource.raw_json
                await handler(resource, raw)
            except Exception as e:
                logger.warning(
                    "Mapper failed for %s %s: %s",
                    resource.resource_type, resource.resource_id, e,
                )

    async def _map_network_segment(self, resource, raw: dict) -> None:
        cidrs = _extract_cidrs(raw, resource.provider)
        await self._topology_store.upsert_network_segment({
            "id": resource.resource_id,
            "name": resource.name or raw.get("VpcId", ""),
            "cidr_blocks": cidrs,
            "provider": resource.provider,
            "account_id": resource.account_id,
            "region": resource.region,
            "cloud_resource_id": resource.resource_id,
        })

    async def _map_subnet(self, resource, raw: dict) -> None:
        await self._topology_store.upsert_subnet_segment({
            "id": resource.resource_id,
            "name": resource.name or raw.get("SubnetId", ""),
            "cidr": raw.get("CidrBlock", ""),
            "network_segment_id": raw.get("VpcId", ""),
            "availability_zone": raw.get("AvailabilityZone"),
            "cloud_resource_id": resource.resource_id,
        })

    async def _map_policy_group(self, resource, raw: dict) -> None:
        await self._policy_store.upsert_policy_group(
            policy_group_id=resource.resource_id,
            name=resource.name or raw.get("GroupName", raw.get("NetworkAclId", "")),
            provider=resource.provider,
            source_type=resource.resource_type,
            cloud_resource_id=resource.resource_id,
        )
        rules = self._extract_rules(resource, raw)
        await self._policy_store.replace_rules(resource.resource_id, rules)

    def _extract_rules(self, resource, raw: dict) -> list[dict]:
        rules = []
        if resource.resource_type == "security_group":
            for perm in raw.get("IpPermissions", []):
                for cidr_range in perm.get("IpRanges", []):
                    rules.append({
                        "rule_id": str(uuid.uuid4()),
                        "direction": "inbound",
                        "action": "allow",
                        "protocol": perm.get("IpProtocol", "all"),
                        "port_range_start": perm.get("FromPort"),
                        "port_range_end": perm.get("ToPort"),
                        "source_cidr": cidr_range.get("CidrIp"),
                    })
            for perm in raw.get("IpPermissionsEgress", []):
                for cidr_range in perm.get("IpRanges", []):
                    rules.append({
                        "rule_id": str(uuid.uuid4()),
                        "direction": "outbound",
                        "action": "allow",
                        "protocol": perm.get("IpProtocol", "all"),
                        "port_range_start": perm.get("FromPort"),
                        "port_range_end": perm.get("ToPort"),
                        "dest_cidr": cidr_range.get("CidrIp"),
                    })
        elif resource.resource_type == "nacl":
            for entry in raw.get("Entries", []):
                rules.append({
                    "rule_id": str(uuid.uuid4()),
                    "direction": "inbound" if not entry.get("Egress") else "outbound",
                    "action": "allow" if entry.get("RuleAction") == "allow" else "deny",
                    "protocol": str(entry.get("Protocol", "-1")),
                    "source_cidr": entry.get("CidrBlock"),
                    "priority": entry.get("RuleNumber"),
                })
        return rules

    async def _map_routing_table(self, resource, raw: dict) -> None:
        routes = []
        for route in raw.get("Routes", []):
            target = (
                route.get("GatewayId")
                or route.get("NatGatewayId")
                or route.get("InstanceId")
                or route.get("TransitGatewayId")
                or route.get("VpcPeeringConnectionId")
                or "local"
            )
            target_type = "local"
            if route.get("GatewayId"):
                target_type = "gateway"
            elif route.get("NatGatewayId"):
                target_type = "nat"
            elif route.get("TransitGatewayId"):
                target_type = "tgw"
            elif route.get("VpcPeeringConnectionId"):
                target_type = "peering"
            elif route.get("InstanceId"):
                target_type = "instance"
            routes.append({
                "destination_cidr": route.get("DestinationCidrBlock", ""),
                "target_type": target_type,
                "target_id": target,
            })
        await self._topology_store.upsert_routing_table({
            "id": resource.resource_id,
            "name": resource.name or raw.get("RouteTableId", ""),
            "network_segment_id": raw.get("VpcId", ""),
            "routes": routes,
            "cloud_resource_id": resource.resource_id,
        })
