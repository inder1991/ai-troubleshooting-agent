"""Auto-discovery engine -- finds network devices not yet in the Knowledge Graph."""
import asyncio
import ipaddress
import logging
import random
import socket

from .topology_store import TopologyStore

logger = logging.getLogger(__name__)

# Safety limits
_MAX_SUBNET_PREFIX_MIN = 20  # skip subnets larger than /20
_MAX_HOSTS_PER_SUBNET = 50   # sample per cycle


class DiscoveryEngine:
    """Finds devices on the network not yet in the Knowledge Graph."""

    def __init__(self, store: TopologyStore, kg):
        self.store = store
        self.kg = kg

    def _known_ips(self) -> set[str]:
        return set(self.kg._device_index.keys())

    async def discover_from_adapters(self, adapters) -> list[dict]:
        """Source 1: Check adapter interface tables for unknown IPs."""
        known = self._known_ips()
        candidates = []
        for instance_id, adapter in adapters.all_instances().items():
            try:
                ifaces = await adapter.get_interfaces()
                for iface in ifaces:
                    if iface.ip and iface.ip not in known:
                        hostname = await self.reverse_dns(iface.ip)
                        candidates.append({
                            "ip": iface.ip,
                            "mac": getattr(iface, "mac", ""),
                            "hostname": hostname or getattr(iface, "name", ""),
                            "discovered_via": "adapter_neighbor",
                            "source_device_id": instance_id,
                        })
                        known.add(iface.ip)  # don't double-count within cycle
            except Exception as e:
                logger.debug("Discovery: adapter %s failed: %s", instance_id, e)
                continue
        return candidates

    async def probe_known_subnets(self) -> list[dict]:
        """Source 2: Ping-sweep subnets in the KG to find responsive unknown IPs."""
        known = self._known_ips()
        subnets = self.store.list_subnets()
        candidates = []

        for subnet in subnets:
            try:
                network = ipaddress.ip_network(subnet.cidr, strict=False)
            except ValueError:
                continue
            if network.num_addresses > (2 ** (32 - _MAX_SUBNET_PREFIX_MIN)):
                continue

            hosts = list(network.hosts())
            unknown_hosts = [str(h) for h in hosts if str(h) not in known]
            if len(unknown_hosts) > _MAX_HOSTS_PER_SUBNET:
                unknown_hosts = random.sample(unknown_hosts, _MAX_HOSTS_PER_SUBNET)

            tasks = [self._ping_check(ip) for ip in unknown_hosts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    continue
                ip_str, alive = result
                if alive:
                    hostname = await self.reverse_dns(ip_str)
                    candidates.append({
                        "ip": ip_str,
                        "mac": "",
                        "hostname": hostname,
                        "discovered_via": "probe",
                        "source_device_id": "",
                    })
                    known.add(ip_str)
        return candidates

    async def _ping_check(self, ip: str) -> tuple[str, bool]:
        """Single async ping with 2s timeout."""
        try:
            from icmplib import async_ping
            result = await asyncio.wait_for(
                async_ping(ip, count=1, timeout=2),
                timeout=3,
            )
            return (ip, result.is_alive)
        except Exception:
            return (ip, False)

    async def reverse_dns(self, ip: str) -> str:
        """Best-effort reverse DNS lookup."""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            return result[0]
        except (socket.herror, socket.gaierror, OSError):
            return ""
