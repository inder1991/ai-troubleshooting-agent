"""Checkpoint health collector.

Collects: SIC state, ClusterXL state, connection table, policy install status,
IPS signature version, log rate.

Production: Checkpoint Management API (HTTPS).
Current: Mock data.
"""

from __future__ import annotations
import random
import asyncio
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def collect_checkpoint_health(device: dict, metrics_store) -> None:
    """Collect health metrics from a Checkpoint firewall."""
    device_id = device.get("id", "")
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # SIC (Secure Internal Communication) state
    sic_ok = 1 if random.random() > 0.02 else 0
    metrics_store.write_device_metric(device_id, "sic_state", sic_ok)

    # ClusterXL state
    ha_role = device.get("ha_role", "active")
    metrics_store.write_device_metric(device_id, "clusterxl_active", 1 if ha_role == "active" else 0)
    sync_pct = random.uniform(95, 100) if random.random() > 0.05 else random.uniform(70, 94)
    metrics_store.write_device_metric(device_id, "clusterxl_sync_pct", round(sync_pct, 1), "%")

    # Connection table
    max_connections = 1000000
    current_connections = random.randint(10000, 400000)
    metrics_store.write_device_metric(device_id, "connection_count", current_connections)
    metrics_store.write_device_metric(device_id, "connection_peak", current_connections + random.randint(1000, 50000))
    metrics_store.write_device_metric(device_id, "connection_table_pct", round(current_connections / max_connections * 100, 1), "%")

    # Policy installation
    policy_age_hours = random.uniform(0.5, 72)
    metrics_store.write_device_metric(device_id, "policy_install_age_hours", round(policy_age_hours, 1), "hours")
    metrics_store.write_device_metric(device_id, "policy_rule_count", random.randint(200, 800))

    # IPS
    ips_sig_version = random.choice(["8.120", "8.119", "8.118"])
    metrics_store.write_device_metric(device_id, "ips_enabled", 1)
    # Store version as a numeric approximation
    metrics_store.write_device_metric(device_id, "ips_sig_version_num", float(ips_sig_version.replace(".", "")))

    # SmartEvent log rate
    log_rate = random.randint(100, 5000)
    metrics_store.write_device_metric(device_id, "smartevent_log_rate", log_rate, "events/min")

    # Throughput
    metrics_store.write_device_metric(device_id, "throughput_mbps", random.randint(100, 5000), "Mbps")

    logger.debug("Checkpoint health collected for %s", device_id)
