"""Enterprise network fixture loader — populates topology store + KG on startup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger
from src.network.models import (
    Device, Interface, Subnet, Zone,
    Route, NATRule, FirewallRule,
    VPC, TransitGateway, VPNTunnel, DirectConnect,
    LoadBalancer, LBTargetGroup,
    VLAN, MPLSCircuit, HAGroup,
)

logger = get_logger(__name__)

FIXTURE_PATH = (
    Path(__file__).parent.parent / "agents" / "fixtures" / "enterprise_network" / "topology.json"
)


def load_enterprise_fixtures(topology_store) -> dict:
    """Load enterprise network fixtures into the topology store.

    Entities are loaded in dependency order so that foreign-key relationships
    (zone_id, device_id, vpc_id, etc.) resolve correctly.

    Returns a summary dict of what was loaded.
    """
    if not FIXTURE_PATH.exists():
        logger.info("No enterprise fixtures found at %s", FIXTURE_PATH)
        return {"loaded": False}

    with open(FIXTURE_PATH, "r") as f:
        data: dict[str, list[dict[str, Any]]] = json.load(f)

    counts: dict[str, int] = {}

    # ── 1. Zones ──
    for item in data.get("zones", []):
        try:
            topology_store.add_zone(Zone(**item))
        except Exception as e:
            logger.warning("Failed to load zone %s: %s", item.get("id"), e)
    counts["zones"] = len(data.get("zones", []))

    # ── 2. VLANs ──
    for item in data.get("vlans", []):
        try:
            topology_store.add_vlan(VLAN(**item))
        except Exception as e:
            logger.warning("Failed to load VLAN %s: %s", item.get("id"), e)
    counts["vlans"] = len(data.get("vlans", []))

    # ── 3. Subnets ──
    for item in data.get("subnets", []):
        try:
            topology_store.add_subnet(Subnet(**item))
        except Exception as e:
            logger.warning("Failed to load subnet %s: %s", item.get("id"), e)
    counts["subnets"] = len(data.get("subnets", []))

    # ── 4. VPCs ──
    for item in data.get("vpcs", []):
        try:
            topology_store.add_vpc(VPC(**item))
        except Exception as e:
            logger.warning("Failed to load VPC %s: %s", item.get("id"), e)
    counts["vpcs"] = len(data.get("vpcs", []))

    # ── 5. HA Groups (before devices, since devices reference ha_group_id) ──
    for item in data.get("ha_groups", []):
        try:
            topology_store.add_ha_group(HAGroup(**item))
        except Exception as e:
            logger.warning("Failed to load HA group %s: %s", item.get("id"), e)
    counts["ha_groups"] = len(data.get("ha_groups", []))

    # ── 6. Devices ──
    for item in data.get("devices", []):
        try:
            topology_store.add_device(Device(**item))
        except Exception as e:
            logger.warning("Failed to load device %s: %s", item.get("id"), e)
    counts["devices"] = len(data.get("devices", []))

    # ── 7. Interfaces ──
    for item in data.get("interfaces", []):
        try:
            topology_store.add_interface(Interface(**item))
        except Exception as e:
            logger.warning("Failed to load interface %s: %s", item.get("id"), e)
    counts["interfaces"] = len(data.get("interfaces", []))

    # ── 8. Routes ──
    for item in data.get("routes", []):
        try:
            topology_store.add_route(Route(**item))
        except Exception as e:
            logger.warning("Failed to load route %s: %s", item.get("id"), e)
    counts["routes"] = len(data.get("routes", []))

    # ── 9. Firewall Rules ──
    for item in data.get("firewall_rules", []):
        try:
            topology_store.add_firewall_rule(FirewallRule(**item))
        except Exception as e:
            logger.warning("Failed to load firewall rule %s: %s", item.get("id"), e)
    counts["firewall_rules"] = len(data.get("firewall_rules", []))

    # ── 10. NAT Rules ──
    for item in data.get("nat_rules", []):
        try:
            topology_store.add_nat_rule(NATRule(**item))
        except Exception as e:
            logger.warning("Failed to load NAT rule %s: %s", item.get("id"), e)
    counts["nat_rules"] = len(data.get("nat_rules", []))

    # ── 11. VPN Tunnels ──
    for item in data.get("vpn_tunnels", []):
        try:
            topology_store.add_vpn_tunnel(VPNTunnel(**item))
        except Exception as e:
            logger.warning("Failed to load VPN tunnel %s: %s", item.get("id"), e)
    counts["vpn_tunnels"] = len(data.get("vpn_tunnels", []))

    # ── 12. Direct Connects ──
    for item in data.get("direct_connects", []):
        try:
            topology_store.add_direct_connect(DirectConnect(**item))
        except Exception as e:
            logger.warning("Failed to load direct connect %s: %s", item.get("id"), e)
    counts["direct_connects"] = len(data.get("direct_connects", []))

    # ── 13. Load Balancers ──
    for item in data.get("load_balancers", []):
        try:
            topology_store.add_load_balancer(LoadBalancer(**item))
        except Exception as e:
            logger.warning("Failed to load LB %s: %s", item.get("id"), e)
    counts["load_balancers"] = len(data.get("load_balancers", []))

    # ── 14. LB Target Groups ──
    for item in data.get("lb_target_groups", []):
        try:
            topology_store.add_lb_target_group(LBTargetGroup(**item))
        except Exception as e:
            logger.warning("Failed to load target group %s: %s", item.get("id"), e)
    counts["lb_target_groups"] = len(data.get("lb_target_groups", []))

    # ── 15. Transit Gateways ──
    for item in data.get("transit_gateways", []):
        try:
            topology_store.add_transit_gateway(TransitGateway(**item))
        except Exception as e:
            logger.warning("Failed to load TGW %s: %s", item.get("id"), e)
    counts["transit_gateways"] = len(data.get("transit_gateways", []))

    # ── 16. MPLS Circuits ──
    for item in data.get("mpls_circuits", []):
        try:
            topology_store.add_mpls_circuit(MPLSCircuit(**item))
        except Exception as e:
            logger.warning("Failed to load MPLS %s: %s", item.get("id"), e)
    counts["mpls_circuits"] = len(data.get("mpls_circuits", []))

    total = sum(counts.values())
    logger.info(
        "Enterprise fixtures loaded: %d entities (%s)",
        total,
        ", ".join(f"{k}={v}" for k, v in counts.items() if v > 0),
    )

    return {"loaded": True, "counts": counts, "total": total}
