"""Palo Alto PAN-OS health collector.

Collects: session count, throughput, threat hits, SSL decrypt stats,
HA state, GlobalProtect users, packet buffer utilization.

Production: PAN-OS XML API.
Current: Mock data.
"""

from __future__ import annotations
import random
import asyncio
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def collect_paloalto_health(device: dict, metrics_store) -> None:
    """Collect health metrics from a Palo Alto firewall."""
    device_id = device.get("id", "")
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # Session count
    max_sessions = 2000000  # PA-5260 supports ~2M sessions
    current_sessions = random.randint(50000, 800000)
    metrics_store.write_device_metric(device_id, "session_count", current_sessions)
    metrics_store.write_device_metric(device_id, "session_max", max_sessions)
    metrics_store.write_device_metric(device_id, "session_utilization_pct", round(current_sessions / max_sessions * 100, 1), "%")

    # Throughput
    throughput_mbps = random.randint(500, 8000)
    metrics_store.write_device_metric(device_id, "throughput_mbps", throughput_mbps, "Mbps")
    metrics_store.write_device_metric(device_id, "packets_per_second", random.randint(50000, 500000), "pps")
    metrics_store.write_device_metric(device_id, "connections_per_second", random.randint(1000, 20000), "cps")

    # Threat prevention
    metrics_store.write_device_metric(device_id, "threat_hits_total", random.randint(0, 50))
    metrics_store.write_device_metric(device_id, "threat_blocked", random.randint(0, 45))
    metrics_store.write_device_metric(device_id, "url_categories_blocked", random.randint(0, 200))

    # SSL decryption
    ssl_sessions = random.randint(1000, 10000)
    ssl_failures = random.randint(0, 50)
    metrics_store.write_device_metric(device_id, "ssl_decrypt_sessions", ssl_sessions)
    metrics_store.write_device_metric(device_id, "ssl_decrypt_failures", ssl_failures)

    # HA state
    ha_role = device.get("ha_role", "active")
    metrics_store.write_device_metric(device_id, "ha_state_active", 1 if ha_role == "active" else 0)
    metrics_store.write_device_metric(device_id, "ha_sync_state", 1 if random.random() > 0.03 else 0)

    # GlobalProtect VPN
    gp_users = random.randint(0, 200) if device.get("has_globalprotect", False) else 0
    metrics_store.write_device_metric(device_id, "gp_users_connected", gp_users)

    # Packet buffer utilization
    pkt_buffer = random.uniform(10, 60)
    metrics_store.write_device_metric(device_id, "packet_buffer_pct", round(pkt_buffer, 1), "%")

    # Zone-based policy hit counts (top zones)
    zones = ["Trust-Production", "DMZ", "Cloud-Transit", "Untrust"]
    for zone in zones:
        hits = random.randint(100, 50000)
        metrics_store.write_device_metric(device_id, f"zone_{zone}_hits", hits)

    logger.debug("Palo Alto health collected for %s", device_id)
