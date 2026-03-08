"""SNMP v2c/v3 collector for network device health metrics."""

from __future__ import annotations

import asyncio
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
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
    # ARP table OIDs (Phase 6: Multi-Source Discovery)
    "ipNetToMediaPhysAddress": "1.3.6.1.2.1.4.22.1.2",
    "ipNetToMediaNetAddress": "1.3.6.1.2.1.4.22.1.3",
    "ipNetToMediaType": "1.3.6.1.2.1.4.22.1.4",
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

        # Prefer 64-bit HC counters over 32-bit when available
        if "ifHCInOctets" in counters and "ifHCInOctets" in prev_counters:
            delta_in = counters["ifHCInOctets"] - prev_counters["ifHCInOctets"]
            delta_out = counters["ifHCOutOctets"] - prev_counters["ifHCOutOctets"]
            wrap_threshold = 2 ** 64
        else:
            delta_in = counters.get("ifInOctets", 0) - prev_counters.get("ifInOctets", 0)
            delta_out = counters.get("ifOutOctets", 0) - prev_counters.get("ifOutOctets", 0)
            wrap_threshold = 2 ** 32

        if delta_in < 0:
            delta_in += wrap_threshold
        if delta_out < 0:
            delta_out += wrap_threshold

        d_in = delta_in
        d_out = delta_out
        d_errs = (
            (counters.get("ifInErrors", 0) - prev_counters.get("ifInErrors", 0))
            + (counters.get("ifOutErrors", 0) - prev_counters.get("ifOutErrors", 0))
        )
        d_total = d_in + d_out

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

    async def _walk_interfaces(self, cfg: SNMPDeviceConfig) -> dict[int, dict]:
        """SNMP BULKWALK of interface table — returns {if_index: {counters}}."""
        try:
            from pysnmp.hlapi.v3arch.asyncio import (
                bulk_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity, UsmUserData,
            )
        except ImportError:
            logger.error("pysnmp-lextudio not installed")
            return {}

        engine = SnmpEngine()
        target = UdpTransportTarget((cfg.ip, cfg.port), timeout=5, retries=1)
        if cfg.version == "v3":
            auth = UsmUserData(cfg.v3_user, cfg.v3_auth_key, cfg.v3_priv_key)
        else:
            auth = CommunityData(cfg.community, mpModel=1)

        walk_oids = {
            "ifDescr": "1.3.6.1.2.1.2.2.1.2",
            "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
            "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
            "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
            "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
            "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
            "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
            "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
            "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
        }

        interfaces: dict[int, dict] = {}

        for name, base_oid in walk_oids.items():
            marker = base_oid
            while True:
                try:
                    err_indication, err_status, err_index, var_binds = await bulk_cmd(
                        engine, auth, target, ContextData(),
                        0, 25,
                        ObjectType(ObjectIdentity(marker)),
                    )
                except Exception:
                    break
                if err_indication or err_status:
                    break
                out_of_subtree = False
                for var_bind_row in var_binds:
                    for oid, val in var_bind_row:
                        oid_str = str(oid)
                        if not oid_str.startswith(base_oid):
                            out_of_subtree = True
                            break
                        if_index = int(oid_str.split(".")[-1])
                        if if_index not in interfaces:
                            interfaces[if_index] = {}
                        interfaces[if_index][name] = int(val) if name != "ifDescr" else str(val)
                        marker = oid_str
                    if out_of_subtree:
                        break
                if out_of_subtree:
                    break

        return interfaces

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
        result["interfaces"] = await self._walk_interfaces(cfg)
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

    async def walk_arp_table(self, cfg: SNMPDeviceConfig) -> list[dict]:
        """BULKWALK ipNetToMediaTable. Returns [{ip, mac, type, device_id}]."""
        try:
            from pysnmp.hlapi.v3arch.asyncio import (
                bulk_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity, UsmUserData,
            )
        except ImportError:
            logger.error("pysnmp-lextudio not installed")
            return []

        engine = SnmpEngine()
        target = UdpTransportTarget((cfg.ip, cfg.port), timeout=5, retries=1)
        if cfg.version == "v3":
            auth = UsmUserData(cfg.v3_user, cfg.v3_auth_key, cfg.v3_priv_key)
        else:
            auth = CommunityData(cfg.community, mpModel=1)

        base_oid = STANDARD_OIDS["ipNetToMediaPhysAddress"]
        entries: list[dict] = []
        marker = base_oid

        while True:
            try:
                err_indication, err_status, err_index, var_binds = await bulk_cmd(
                    engine, auth, target, ContextData(),
                    0, 25,
                    ObjectType(ObjectIdentity(marker)),
                )
            except Exception:
                break
            if err_indication or err_status:
                break
            out_of_subtree = False
            for var_bind_row in var_binds:
                for oid, val in var_bind_row:
                    oid_str = str(oid)
                    if not oid_str.startswith(base_oid):
                        out_of_subtree = True
                        break
                    # OID format: base_oid.ifIndex.ip1.ip2.ip3.ip4
                    parts = oid_str[len(base_oid) + 1:].split(".")
                    if len(parts) >= 5:
                        ip_addr = ".".join(parts[1:5])
                        mac_hex = val.prettyPrint() if hasattr(val, "prettyPrint") else str(val)
                        entries.append({
                            "ip": ip_addr,
                            "mac": mac_hex,
                            "type": "dynamic",
                            "device_id": cfg.device_id,
                        })
                    marker = oid_str
                if out_of_subtree:
                    break
            if out_of_subtree:
                break

        return entries

    _MAX_CONCURRENT = 10

    async def poll_all(self, configs: list[SNMPDeviceConfig]) -> list[dict]:
        """Poll all configured devices concurrently (max 10 at a time)."""
        sem = asyncio.Semaphore(self._MAX_CONCURRENT)

        async def _poll(cfg: SNMPDeviceConfig) -> dict:
            async with sem:
                try:
                    return await self.poll_device(cfg)
                except Exception as e:
                    logger.warning("SNMP poll failed for %s: %s", cfg.device_id, e)
                    return {"device_id": cfg.device_id, "error": str(e)}

        return list(await asyncio.gather(*[_poll(c) for c in configs]))
