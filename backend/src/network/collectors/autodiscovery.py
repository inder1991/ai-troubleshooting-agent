"""Autodiscovery engine — scan subnets, query sysObjectID, match profiles."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import time
from uuid import uuid4

from .models import (
    DeviceInstance,
    DeviceStatus,
    DiscoveryConfig,
    PingConfig,
    ProtocolConfig,
    SNMPCredentials,
    SNMPVersion,
)
from .profile_loader import ProfileLoader
from .snmp_collector import SNMPProtocolCollector

logger = logging.getLogger(__name__)


class AutodiscoveryEngine:
    """Datadog-style SNMP autodiscovery by subnet scanning.

    Scans CIDR ranges, queries sysObjectID per reachable IP,
    matches against loaded device profiles, creates DeviceInstances.
    """

    def __init__(
        self,
        profile_loader: ProfileLoader,
        snmp_collector: SNMPProtocolCollector,
        max_concurrent: int | None = None,
    ) -> None:
        self._profiles = profile_loader
        self._snmp = snmp_collector
        # Concurrency limit from env var or constructor arg (default 50)
        limit = max_concurrent if max_concurrent is not None else int(
            os.getenv("DISCOVERY_MAX_CONCURRENT_PROBES", "50")
        )
        self._max_concurrent = limit
        self._semaphore = asyncio.Semaphore(limit)
        self._last_scan: dict[str, float] = {}  # config_id → timestamp

    async def scan_network(
        self, config: DiscoveryConfig
    ) -> list[DeviceInstance]:
        """Scan a CIDR range, query sysObjectID per reachable IP, match to profile."""
        try:
            network = ipaddress.ip_network(config.cidr, strict=False)
        except ValueError as e:
            logger.error("Invalid CIDR %s: %s", config.cidr, e)
            return []

        excluded = set(config.excluded_ips)
        hosts = [str(ip) for ip in network.hosts() if str(ip) not in excluded]

        if len(hosts) > 1024:
            logger.warning("Large subnet %s (%d hosts) — limiting to first 1024", config.cidr, len(hosts))
            hosts = hosts[:1024]

        logger.info("Autodiscovery: scanning %d hosts in %s", len(hosts), config.cidr)

        # Build SNMP creds from discovery config
        creds = self._build_creds(config)

        # Scan all hosts concurrently (with semaphore)
        tasks = [self._probe_host(ip, creds, config) for ip in hosts]
        results = await asyncio.gather(*tasks)

        discovered = [d for d in results if d is not None]
        self._last_scan[config.config_id] = time.time()
        logger.info("Autodiscovery: found %d devices in %s", len(discovered), config.cidr)
        return discovered

    async def should_scan(self, config: DiscoveryConfig) -> bool:
        """Check if enough time has elapsed since last scan."""
        if not config.enabled:
            return False
        last = self._last_scan.get(config.config_id, 0)
        return (time.time() - last) >= config.interval_seconds

    async def run_discovery_cycle(
        self, configs: list[DiscoveryConfig]
    ) -> list[DeviceInstance]:
        """Run discovery for all configs that are due."""
        all_discovered: list[DeviceInstance] = []
        for config in configs:
            if await self.should_scan(config):
                devices = await self.scan_network(config)
                all_discovered.extend(devices)
        return all_discovered

    def match_profile(self, sys_object_id: str) -> str | None:
        """Match sysObjectID against loaded profiles. Returns profile name or None."""
        profile = self._profiles.match(sys_object_id)
        return profile.name if profile else None

    # ── Internal ──

    async def _probe_host(
        self, ip: str, creds: SNMPCredentials, config: DiscoveryConfig
    ) -> DeviceInstance | None:
        """Probe a single host: query sysObjectID, match profile."""
        async with self._semaphore:
            try:
                creds_dict = {
                    "version": creds.version.value,
                    "community": creds.community,
                    "port": creds.port,
                    "v3_user": creds.v3_user,
                    "v3_auth_protocol": creds.v3_auth_protocol.value if creds.v3_auth_protocol else None,
                    "v3_auth_key": creds.v3_auth_key,
                    "v3_priv_protocol": creds.v3_priv_protocol.value if creds.v3_priv_protocol else None,
                    "v3_priv_key": creds.v3_priv_key,
                }
                sys_oid = await self._snmp.query_sys_object_id(ip, creds_dict)
                if not sys_oid:
                    return None

                # Match profile
                profile = self._profiles.match(sys_oid)
                profile_name = profile.name if profile else None

                # Get sysName for hostname
                hostname = ""
                if self._snmp._pysnmp_available:
                    name_val = await self._snmp._query_oid(ip, creds, "1.3.6.1.2.1.1.5.0")
                    if name_val:
                        hostname = str(name_val)

                return DeviceInstance(
                    device_id=str(uuid4()),
                    hostname=hostname or ip,
                    management_ip=ip,
                    sys_object_id=sys_oid,
                    matched_profile=profile_name,
                    vendor=profile.vendor if profile else "",
                    model="",
                    os_family="",
                    protocols=[ProtocolConfig(
                        protocol="snmp",
                        priority=5,
                        snmp=creds,
                    )],
                    discovered=True,
                    tags=list(config.tags),
                    ping_config=PingConfig(enabled=config.ping.enabled),
                    status=DeviceStatus.NEW,
                )

            except Exception as e:
                logger.debug("Probe %s failed: %s", ip, e)
                return None

    @staticmethod
    def _build_creds(config: DiscoveryConfig) -> SNMPCredentials:
        return SNMPCredentials(
            version=config.snmp_version,
            community=config.community,
            port=config.port,
            v3_user=config.v3_user,
            v3_auth_protocol=config.v3_auth_protocol,
            v3_auth_key=config.v3_auth_key,
            v3_priv_protocol=config.v3_priv_protocol,
            v3_priv_key=config.v3_priv_key,
        )
