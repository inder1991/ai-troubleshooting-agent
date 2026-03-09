"""SNMP Protocol Collector — queries OIDs defined in matched device profiles."""
from __future__ import annotations

import asyncio
import logging
import time

from .base import CollectorProtocol, ProtocolCollector
from .models import (
    CollectedData,
    CollectorHealth,
    DeviceInstance,
    DeviceProfile,
    MetricDefinition,
    SNMPCredentials,
    SNMPVersion,
)

logger = logging.getLogger(__name__)

# sysObjectID OID
SYS_OBJECT_ID_OID = "1.3.6.1.2.1.1.2.0"


def _get_snmp_creds(instance: DeviceInstance) -> SNMPCredentials | None:
    """Extract SNMP credentials from device's protocol configs."""
    for pc in instance.protocols:
        if pc.protocol == "snmp" and pc.enabled and pc.snmp:
            return pc.snmp
    return None


class SNMPProtocolCollector(ProtocolCollector):
    """Singleton SNMP collector that handles all SNMP-enabled devices.

    Uses pysnmp for actual SNMP operations. If pysnmp is not installed,
    falls back to simulated collection for development.
    """

    protocol = CollectorProtocol.SNMP

    def __init__(self) -> None:
        self._pysnmp_available = False
        try:
            from pysnmp.hlapi.v3arch.asyncio import (  # noqa: F401
                CommunityData,
                ContextData,
                ObjectIdentity,
                ObjectType,
                SnmpEngine,
                UdpTransportTarget,
                getCmd,
                bulkCmd,
            )
            self._pysnmp_available = True
        except ImportError:
            logger.info("pysnmp not available — SNMP collector will use simulated mode")

    async def collect(
        self, instance: DeviceInstance, profile: DeviceProfile
    ) -> CollectedData:
        """Collect metrics from a device using its matched profile."""
        creds = _get_snmp_creds(instance)
        if not creds:
            raise ValueError(f"No SNMP credentials for device {instance.device_id}")

        if self._pysnmp_available:
            return await self._collect_real(instance, profile, creds)
        return await self._collect_simulated(instance, profile, creds)

    async def health_check(self, instance: DeviceInstance) -> CollectorHealth:
        """Check SNMP connectivity by querying sysObjectID."""
        creds = _get_snmp_creds(instance)
        if not creds:
            return CollectorHealth(
                protocol="snmp", status="error",
                message="No SNMP credentials configured",
            )

        try:
            oid = await self._query_oid(instance.management_ip, creds, SYS_OBJECT_ID_OID)
            if oid:
                return CollectorHealth(
                    protocol="snmp", status="ok",
                    message=f"sysObjectID: {oid}",
                    devices_collected=1,
                    last_collection=time.time(),
                )
            return CollectorHealth(
                protocol="snmp", status="error",
                message="No response to sysObjectID query",
            )
        except Exception as e:
            return CollectorHealth(
                protocol="snmp", status="error", message=str(e),
            )

    async def query_sys_object_id(self, ip: str, creds: dict) -> str | None:
        """Query sysObjectID from a device given raw credential dict."""
        snmp_creds = SNMPCredentials(**creds)
        return await self._query_oid(ip, snmp_creds, SYS_OBJECT_ID_OID)

    async def collect_batch(
        self, instances: list[tuple[DeviceInstance, DeviceProfile]]
    ) -> list[CollectedData]:
        """Collect from multiple devices concurrently."""
        tasks = []
        for inst, prof in instances:
            tasks.append(self._safe_collect(inst, prof))
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    # ── Internal ──

    async def _safe_collect(
        self, instance: DeviceInstance, profile: DeviceProfile
    ) -> CollectedData | None:
        try:
            return await self.collect(instance, profile)
        except Exception as e:
            logger.warning("SNMP collect failed for %s: %s", instance.management_ip, e)
            return None

    async def _query_oid(self, ip: str, creds: SNMPCredentials, oid: str) -> str | None:
        """Query a single OID from a device."""
        if not self._pysnmp_available:
            return None

        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            UsmUserData,
            getCmd,
            usmHMACSHAAuthProtocol,
            usmHMACMD5AuthProtocol,
            usmAesCfb128Protocol,
            usmDESPrivProtocol,
        )

        engine = SnmpEngine()
        if creds.version == SNMPVersion.V3:
            auth_proto = {
                "MD5": usmHMACMD5AuthProtocol,
                "SHA": usmHMACSHAAuthProtocol,
            }.get(creds.v3_auth_protocol.value if creds.v3_auth_protocol else "SHA", usmHMACSHAAuthProtocol)
            priv_proto = {
                "DES": usmDESPrivProtocol,
                "AES": usmAesCfb128Protocol,
            }.get(creds.v3_priv_protocol.value if creds.v3_priv_protocol else "AES", usmAesCfb128Protocol)

            auth_data = UsmUserData(
                creds.v3_user or "",
                creds.v3_auth_key or "",
                creds.v3_priv_key or "",
                authProtocol=auth_proto,
                privProtocol=priv_proto,
            )
        else:
            auth_data = CommunityData(creds.community, mpModel=0 if creds.version == SNMPVersion.V1 else 1)

        try:
            error_indication, error_status, _, var_binds = await getCmd(
                engine,
                auth_data,
                await UdpTransportTarget.create((ip, creds.port), timeout=5, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            if error_indication or error_status:
                return None
            for _, val in var_binds:
                return str(val)
        except Exception as e:
            logger.debug("SNMP query %s on %s failed: %s", oid, ip, e)
            return None
        finally:
            engine.close_dispatcher()

        return None

    async def _collect_real(
        self, instance: DeviceInstance, profile: DeviceProfile, creds: SNMPCredentials
    ) -> CollectedData:
        """Collect using pysnmp — query all OIDs in the profile."""
        custom_metrics: dict[str, float] = {}
        metadata: dict[str, str] = {}
        interface_metrics: dict[str, dict[str, float]] = {}
        cpu_pct = None
        mem_pct = None
        temperature = None
        uptime = None

        # Collect scalar metrics
        for metric_def in profile.metrics:
            if metric_def.symbol:
                val = await self._query_oid(instance.management_ip, creds, metric_def.symbol.OID)
                if val is not None:
                    try:
                        fval = float(val)
                        custom_metrics[metric_def.symbol.name] = fval
                        # Map well-known metrics
                        if "CPU" in metric_def.symbol.name or "Processor" in metric_def.symbol.name:
                            cpu_pct = fval
                        elif "Temp" in metric_def.symbol.name:
                            temperature = fval
                        elif "UpTime" in metric_def.symbol.name:
                            uptime = int(fval / 100)  # timeticks to seconds
                    except (ValueError, TypeError):
                        custom_metrics[metric_def.symbol.name] = 0

        # Collect metadata fields
        for field_name, field_def in profile.metadata_fields.items():
            if field_def.value:
                metadata[field_name] = field_def.value
            elif field_def.symbol:
                val = await self._query_oid(instance.management_ip, creds, field_def.symbol.OID)
                if val:
                    metadata[field_name] = str(val)

        return CollectedData(
            device_id=instance.device_id,
            protocol=CollectorProtocol.SNMP.value,
            timestamp=time.time(),
            cpu_pct=cpu_pct,
            mem_pct=mem_pct,
            uptime_seconds=uptime,
            temperature=temperature,
            interface_metrics=interface_metrics,
            metadata=metadata,
            custom_metrics=custom_metrics,
        )

    async def _collect_simulated(
        self, instance: DeviceInstance, profile: DeviceProfile, creds: SNMPCredentials
    ) -> CollectedData:
        """Simulated collection for development without pysnmp."""
        import random

        await asyncio.sleep(0.05)  # Simulate network delay

        metadata = {"vendor": profile.vendor, "device_type": profile.device_type}
        for field_name, field_def in profile.metadata_fields.items():
            if field_def.value:
                metadata[field_name] = field_def.value

        return CollectedData(
            device_id=instance.device_id,
            protocol=CollectorProtocol.SNMP.value,
            timestamp=time.time(),
            cpu_pct=round(random.uniform(5, 85), 1),
            mem_pct=round(random.uniform(20, 75), 1),
            uptime_seconds=random.randint(3600, 8640000),
            temperature=round(random.uniform(25, 65), 1),
            interface_metrics={
                "GigabitEthernet0/0": {
                    "ifInOctets": random.uniform(1e6, 1e9),
                    "ifOutOctets": random.uniform(1e6, 1e9),
                    "ifInErrors": random.uniform(0, 100),
                    "ifOutErrors": random.uniform(0, 50),
                    "ifOperStatus": 1.0,
                },
                "GigabitEthernet0/1": {
                    "ifInOctets": random.uniform(1e6, 1e9),
                    "ifOutOctets": random.uniform(1e6, 1e9),
                    "ifInErrors": random.uniform(0, 100),
                    "ifOutErrors": random.uniform(0, 50),
                    "ifOperStatus": 1.0,
                },
            },
            metadata=metadata,
            custom_metrics={m.symbol.name: round(random.uniform(0, 100), 2)
                          for m in profile.metrics if m.symbol},
        )
