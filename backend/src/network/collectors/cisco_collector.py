"""Cisco IOS-XE/NX-OS health collector.

Collects: BGP peer state, OSPF neighbors, QoS drops, GRE tunnel status,
routing table size, interface counters.

Production: SSH show commands via Netmiko + SNMP.
Current: Mock data for end-to-end pipeline validation.
"""

from __future__ import annotations
import random
import asyncio
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def collect_cisco_health(device: dict, metrics_store) -> None:
    """Collect health metrics from a Cisco device."""
    device_id = device.get("id", "")
    await asyncio.sleep(random.uniform(0.05, 0.15))  # Simulate SSH delay

    # BGP peer states
    bgp_peers = device.get("bgp_peers", [])
    if not bgp_peers:
        # Default mock: 2-3 peers
        bgp_peers = [
            {"neighbor": "10.255.0.2", "state": "Established", "prefixes": 45},
            {"neighbor": "169.254.100.2", "state": "Established", "prefixes": 12},
        ]
    for peer in bgp_peers:
        state_val = 1 if peer["state"] == "Established" else 0
        metrics_store.write_device_metric(device_id, f"bgp_peer_{peer['neighbor']}_state", state_val)
        metrics_store.write_device_metric(device_id, f"bgp_peer_{peer['neighbor']}_prefixes", peer.get("prefixes", 0))

    # OSPF neighbor count
    ospf_count = random.randint(2, 6)
    metrics_store.write_device_metric(device_id, "ospf_neighbor_count", ospf_count)

    # QoS class-map drops
    qos_classes = ["voice", "video", "critical-data", "best-effort"]
    for cls in qos_classes:
        drops = random.randint(0, 50) if random.random() < 0.3 else 0
        metrics_store.write_device_metric(device_id, f"qos_drops_{cls}", drops)

    # Routing table size
    route_count = random.randint(80, 500)
    metrics_store.write_device_metric(device_id, "route_table_size_ipv4", route_count)
    metrics_store.write_device_metric(device_id, "route_table_size_ipv6", random.randint(10, 50))

    # GRE tunnel states
    tunnels = device.get("tunnels", [])
    if not tunnels:
        tunnels = [{"name": "Tunnel100", "status": "up"}, {"name": "Tunnel200", "status": "down"}]
    for tunnel in tunnels:
        metrics_store.write_device_metric(device_id, f"tunnel_{tunnel['name']}_up", 1 if tunnel["status"] == "up" else 0)

    # Interface CRC errors (SNMP-based)
    for i in range(random.randint(2, 4)):
        crc = random.randint(0, 10) if random.random() < 0.15 else 0
        metrics_store.write_device_metric(device_id, f"iface_eth{i}_crc_errors", crc)

    logger.debug("Cisco health collected for %s", device_id)
