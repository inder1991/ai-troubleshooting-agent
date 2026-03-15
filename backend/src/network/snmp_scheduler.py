"""SNMP polling scheduler -- polls all SNMP-enabled devices on interval."""

from __future__ import annotations

import asyncio
import random
from typing import Any
from src.config import is_demo_mode
from src.network.sqlite_metrics_store import SQLiteMetricsStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Common SNMP OIDs
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_CPU_LOAD = "1.3.6.1.4.1.9.9.109.1.1.1.1.8"  # Cisco CPU 5s
OID_MEMORY_USED = "1.3.6.1.4.1.9.9.48.1.1.1.5"  # Cisco memory used
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
OID_IF_IN_DISCARDS = "1.3.6.1.2.1.2.2.1.13"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"


async def _mock_snmp_poll(device_id: str, management_ip: str) -> dict:
    """Mock SNMP poll -- returns realistic metrics.

    In production, this would use pysnmp or net-snmp subprocess.
    For now, generates plausible values so the metrics pipeline works end-to-end.
    """
    # Simulate network delay
    await asyncio.sleep(random.uniform(0.05, 0.2))

    base_cpu = hash(device_id) % 40 + 20  # 20-60% base
    base_mem = hash(device_id) % 30 + 40  # 40-70% base

    return {
        "cpu_pct": base_cpu + random.uniform(-5, 10),
        "memory_pct": base_mem + random.uniform(-3, 5),
        "uptime_seconds": random.randint(86400, 86400 * 365),
        "interfaces": _mock_interface_metrics(device_id),
    }


def _mock_interface_metrics(device_id: str) -> list[dict]:
    """Generate mock interface metrics."""
    interfaces = []
    for i in range(random.randint(2, 6)):
        speed_mbps = random.choice([1000, 10000])
        util_pct = random.uniform(5, 85)
        bps = speed_mbps * 1_000_000 * util_pct / 100
        interfaces.append({
            "name": f"eth{i}",
            "bps_in": bps * random.uniform(0.3, 0.7),
            "bps_out": bps * random.uniform(0.3, 0.7),
            "errors_in": random.randint(0, 5) if random.random() < 0.2 else 0,
            "errors_out": random.randint(0, 3) if random.random() < 0.1 else 0,
            "discards_in": random.randint(0, 2) if random.random() < 0.1 else 0,
            "oper_status": "up" if random.random() > 0.05 else "down",
            "utilization_pct": round(util_pct, 1),
        })
    return interfaces


class SNMPPollingScheduler:
    """Polls devices via SNMP at regular intervals."""

    def __init__(self, metrics_store: SQLiteMetricsStore, interval_seconds: int = 60):
        self.store = metrics_store
        self.interval = interval_seconds
        self._running = False
        self._devices: list[dict] = []

    def set_devices(self, devices: list[dict]) -> None:
        """Update the list of devices to poll."""
        self._devices = devices
        logger.info("SNMP scheduler: %d devices configured", len(devices))

    async def start(self) -> None:
        """Start the polling loop."""
        self._running = True
        logger.info("SNMP polling started (interval: %ds, devices: %d)", self.interval, len(self._devices))
        while self._running:
            if self._devices:
                tasks = [self._poll_device(d) for d in self._devices]
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(self.interval)

    async def _poll_device(self, device: dict) -> None:
        """Poll a single device."""
        device_id = device.get("id", "")
        management_ip = device.get("management_ip", "")
        if not device_id or not management_ip:
            return

        try:
            if is_demo_mode():
                metrics = await _mock_snmp_poll(device_id, management_ip)
            else:
                metrics = await _real_snmp_poll(device_id, management_ip, device)

            # Store device-level metrics
            self.store.write_device_metric(device_id, "cpu_pct", metrics["cpu_pct"], "%")
            self.store.write_device_metric(device_id, "memory_pct", metrics["memory_pct"], "%")
            self.store.write_device_metric(device_id, "uptime_seconds", metrics["uptime_seconds"], "s")

            # Store interface-level metrics
            for iface in metrics.get("interfaces", []):
                iface_name = iface["name"]
                self.store.write_interface_metric(device_id, iface_name, "bps_in", iface["bps_in"], "bps")
                self.store.write_interface_metric(device_id, iface_name, "bps_out", iface["bps_out"], "bps")
                self.store.write_interface_metric(device_id, iface_name, "errors_in", iface["errors_in"])
                self.store.write_interface_metric(device_id, iface_name, "errors_out", iface["errors_out"])
                self.store.write_interface_metric(device_id, iface_name, "utilization_pct", iface["utilization_pct"], "%")

            # Vendor-specific health collection
            vendor = device.get("vendor", "").lower()
            try:
                if "cisco" in vendor:
                    from src.network.collectors.cisco_collector import collect_cisco_health
                    await collect_cisco_health(device, self.store)
                elif "palo alto" in vendor or "paloalto" in vendor:
                    from src.network.collectors.paloalto_collector import collect_paloalto_health
                    await collect_paloalto_health(device, self.store)
                elif "f5" in vendor:
                    from src.network.collectors.f5_collector import collect_f5_health
                    await collect_f5_health(device, self.store)
                elif "checkpoint" in vendor or "check point" in vendor:
                    from src.network.collectors.checkpoint_collector import collect_checkpoint_health
                    await collect_checkpoint_health(device, self.store)
            except Exception as e:
                logger.warning("Vendor health collection failed for %s (%s): %s", device_id, vendor, e)

        except Exception as e:
            logger.error("SNMP poll failed for %s: %s", device_id, e)

    def stop(self) -> None:
        self._running = False
        logger.info("SNMP polling stopped")


async def _real_snmp_poll(device_id: str, management_ip: str, device: dict) -> dict:
    """Real SNMP poll — uses pysnmp or net-snmp subprocess.

    TODO: Implement when pysnmp is available.
    For now, falls back to mock in production too with a warning.
    """
    logger.warning("Real SNMP not yet implemented for %s — using mock", device_id)
    return await _mock_snmp_poll(device_id, management_ip)
