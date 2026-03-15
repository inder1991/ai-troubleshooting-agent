"""F5 BIG-IP health collector.

Collects: VIP status, pool member health, current connections, SSL TPS,
certificate expiry, TMM memory/CPU, HA sync status.

Production: iControl REST API.
Current: Mock data.
"""

from __future__ import annotations
import random
import asyncio
import time
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def collect_f5_health(device: dict, metrics_store) -> None:
    """Collect health metrics from an F5 BIG-IP."""
    device_id = device.get("id", "")
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # Virtual server stats
    vips = device.get("vips", [
        {"name": "web-app-vip", "status": "available", "connections": random.randint(50, 500)},
        {"name": "api-gateway-vip", "status": "available", "connections": random.randint(20, 200)},
        {"name": "internal-api-vip", "status": "available", "connections": random.randint(10, 80)},
    ])
    for vip in vips:
        status_val = 1 if vip.get("status") == "available" else 0
        metrics_store.write_device_metric(device_id, f"vip_{vip['name']}_status", status_val)
        metrics_store.write_device_metric(device_id, f"vip_{vip['name']}_connections", vip.get("connections", 0))
        metrics_store.write_device_metric(device_id, f"vip_{vip['name']}_bps_in", random.randint(1000000, 50000000))
        metrics_store.write_device_metric(device_id, f"vip_{vip['name']}_bps_out", random.randint(500000, 30000000))

    # Pool member health
    pools = device.get("pools", [
        {"name": "web-app-pool", "up": 2, "total": 3},
        {"name": "api-pool", "up": 2, "total": 2},
    ])
    for pool in pools:
        metrics_store.write_device_metric(device_id, f"pool_{pool['name']}_members_up", pool["up"])
        metrics_store.write_device_metric(device_id, f"pool_{pool['name']}_members_total", pool["total"])

    # SSL TPS
    ssl_tps = random.randint(100, 2000)
    metrics_store.write_device_metric(device_id, "ssl_tps", ssl_tps)

    # Certificate expiry (days left)
    certs = device.get("certs", [
        {"name": "api-tls-cert", "days_left": 12},
        {"name": "web-ssl-cert", "days_left": 180},
    ])
    for cert in certs:
        metrics_store.write_device_metric(device_id, f"cert_{cert['name']}_days_left", cert["days_left"])

    # TMM memory and CPU
    metrics_store.write_device_metric(device_id, "tmm_memory_pct", random.uniform(40, 75), "%")
    metrics_store.write_device_metric(device_id, "tmm_cpu_pct", random.uniform(15, 60), "%")

    # HA sync
    ha_synced = 1 if random.random() > 0.05 else 0
    metrics_store.write_device_metric(device_id, "ha_sync_status", ha_synced)

    # Persistence table entries
    metrics_store.write_device_metric(device_id, "persistence_entries", random.randint(100, 5000))

    logger.debug("F5 health collected for %s", device_id)
