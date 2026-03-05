"""SNMP v2c/v3 collector for network device health metrics."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STANDARD_OIDS = {
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2",
    "memTotalReal": "1.3.6.1.4.1.2021.4.5.0",
    "memAvailReal": "1.3.6.1.4.1.2021.4.6.0",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
}


@dataclass
class SNMPDeviceConfig:
    device_id: str
    ip: str
    version: str = "v2c"
    community: str = "public"
    port: int = 161
    v3_user: str = ""
    v3_auth_proto: str = ""
    v3_auth_key: str = ""
    v3_priv_proto: str = ""
    v3_priv_key: str = ""


class SNMPCollector:
    """Polls SNMP OIDs and writes metrics to MetricsStore."""

    def __init__(self, metrics_store: Any) -> None:
        self.metrics = metrics_store
        self._prev_counters: dict[tuple[str, int], tuple[dict, float]] = {}

    def _compute_rates(
        self, device_id: str, if_index: int, counters: dict
    ) -> dict | None:
        key = (device_id, if_index)
        now = time.time()
        prev = self._prev_counters.get(key)
        self._prev_counters[key] = (counters, now)

        if prev is None:
            return None

        prev_counters, prev_time = prev
        dt = now - prev_time
        if dt <= 0:
            return None

        speed = counters.get("ifSpeed", 1_000_000_000) or 1_000_000_000
        d_in = counters.get("ifInOctets", 0) - prev_counters.get("ifInOctets", 0)
        d_out = counters.get("ifOutOctets", 0) - prev_counters.get("ifOutOctets", 0)
        d_errs = (
            (counters.get("ifInErrors", 0) - prev_counters.get("ifInErrors", 0))
            + (counters.get("ifOutErrors", 0) - prev_counters.get("ifOutErrors", 0))
        )
        d_total = d_in + d_out

        # Handle 32-bit counter wraps
        if d_in < 0:
            d_in += 2**32
        if d_out < 0:
            d_out += 2**32

        bps_in = (d_in * 8) / dt
        bps_out = (d_out * 8) / dt
        utilization = max(bps_in, bps_out) / speed if speed > 0 else 0
        error_rate = d_errs / d_total if d_total > 0 else 0

        return {
            "bps_in": bps_in,
            "bps_out": bps_out,
            "utilization": utilization,
            "error_rate": error_rate,
        }

    async def _snmp_get(self, cfg: SNMPDeviceConfig) -> dict:
        """Execute SNMP GET/WALK against a device. Returns parsed metrics dict."""
        try:
            from pysnmp.hlapi.v3arch.asyncio import (
                get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity,
            )
        except ImportError:
            logger.error("pysnmp not installed — pip install pysnmp-lextudio")
            return {}

        engine = SnmpEngine()
        target = await UdpTransportTarget.create((cfg.ip, cfg.port), timeout=5, retries=1)

        if cfg.version == "v2c":
            auth = CommunityData(cfg.community, mpModel=1)
        else:
            from pysnmp.hlapi.v3arch.asyncio import UsmUserData
            auth = UsmUserData(cfg.v3_user, cfg.v3_auth_key, cfg.v3_priv_key)

        result: dict[str, Any] = {"interfaces": {}}

        # System scalars
        for name, oid in [
            ("cpu_pct", STANDARD_OIDS["hrProcessorLoad"]),
            ("mem_total", STANDARD_OIDS["memTotalReal"]),
            ("mem_avail", STANDARD_OIDS["memAvailReal"]),
        ]:
            err_indication, err_status, _, var_binds = await get_cmd(
                engine, auth, target, ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            if not err_indication and not err_status and var_binds:
                val = var_binds[0][1]
                result[name] = float(val) if hasattr(val, "__float__") else 0.0

        engine.close_dispatcher()
        return result

    async def poll_device(self, cfg: SNMPDeviceConfig) -> dict:
        """Poll a single device, write metrics, return summary."""
        data = await self._snmp_get(cfg)
        device_id = cfg.device_id

        cpu = data.get("cpu_pct", 0)
        mem_total = data.get("mem_total", 0)
        mem_avail = data.get("mem_avail", 0)
        mem_pct = ((mem_total - mem_avail) / mem_total * 100) if mem_total > 0 else 0

        await self.metrics.write_device_metric(device_id, "cpu_pct", cpu)
        await self.metrics.write_device_metric(device_id, "mem_pct", mem_pct)

        for if_idx, if_data in data.get("interfaces", {}).items():
            rates = self._compute_rates(device_id, if_idx, if_data)
            if rates:
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_bps_in", rates["bps_in"]
                )
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_bps_out", rates["bps_out"]
                )
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_utilization", rates["utilization"]
                )

        return {"device_id": device_id, "cpu_pct": cpu, "mem_pct": mem_pct}

    async def poll_all(self, configs: list[SNMPDeviceConfig]) -> list[dict]:
        """Poll all configured devices."""
        results = []
        for cfg in configs:
            try:
                r = await self.poll_device(cfg)
                results.append(r)
            except Exception as e:
                logger.warning("SNMP poll failed for %s: %s", cfg.device_id, e)
                results.append({"device_id": cfg.device_id, "error": str(e)})
        return results
