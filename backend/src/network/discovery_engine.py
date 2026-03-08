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

    async def scan_subnet_for_ipam(self, subnet_cidr: str, max_hosts: int = 4096) -> list[dict]:
        """Ping sweep a specific subnet for IPAM, returning alive hosts with reverse DNS.

        Safety: Limited to max_hosts (default 4096 = /20).
        Returns: [{"ip": str, "alive": bool, "hostname": str}]
        """
        try:
            network = ipaddress.ip_network(subnet_cidr, strict=False)
        except ValueError:
            return []
        hosts = list(network.hosts())
        if len(hosts) > max_hosts:
            return []  # Subnet too large for on-demand scan

        results = []
        # Batch ping in chunks of 50 for performance
        for i in range(0, len(hosts), 50):
            batch = hosts[i:i + 50]
            tasks = [self._ping_check(str(h)) for h in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in batch_results:
                if isinstance(result, Exception):
                    continue
                ip_str, alive = result
                hostname = ""
                if alive:
                    hostname = await self.reverse_dns(ip_str)
                results.append({
                    "ip": ip_str,
                    "alive": alive,
                    "hostname": hostname,
                })
        return results

    # Confidence scoring by discovery source
    SOURCE_CONFIDENCE = {
        "manual": 1.0,
        "arp": 0.95,
        "snmp": 0.90,
        "adapter_neighbor": 0.85,
        "dhcp": 0.80,
        "netflow": 0.60,
        "probe": 0.50,
    }

    async def discover_from_arp(self, snmp_collector) -> list[dict]:
        """Source 3: Walk ARP tables on SNMP-enabled devices for IP→MAC mappings."""
        from .snmp_collector import SNMPDeviceConfig
        known = self._known_ips()
        candidates = []
        for device in self.store.list_devices():
            if not device.management_ip:
                continue
            # Check SNMP capability via KG
            node_data = {}
            if hasattr(self.kg, 'graph') and device.id in self.kg.graph:
                node_data = dict(self.kg.graph.nodes[device.id])
            if not node_data.get("snmp_enabled"):
                continue
            cfg = SNMPDeviceConfig(
                device_id=device.id, ip=device.management_ip,
                version=node_data.get("snmp_version", "v2c"),
                community=node_data.get("snmp_community", "public"),
                port=int(node_data.get("snmp_port", 161)),
            )
            try:
                arp_entries = await snmp_collector.walk_arp_table(cfg)
                for entry in arp_entries:
                    ip = entry.get("ip", "")
                    if ip and ip not in known:
                        hostname = await self.reverse_dns(ip)
                        candidates.append({
                            "ip": ip,
                            "mac": entry.get("mac", ""),
                            "hostname": hostname,
                            "discovered_via": "arp",
                            "source_device_id": device.id,
                            "confidence_score": self.SOURCE_CONFIDENCE["arp"],
                        })
                        known.add(ip)
            except Exception as e:
                logger.debug("ARP walk failed for %s: %s", device.id, e)
        return candidates

    async def discover_from_flows(self, metrics_store) -> list[dict]:
        """Source 4: Extract unknown IPs from recent NetFlow/metrics data."""
        known = self._known_ips()
        candidates = []
        if not metrics_store:
            return candidates
        try:
            # Query recent flow records (last 5 minutes)
            flow_ips = await metrics_store.get_recent_flow_ips(minutes=5)
            for ip in flow_ips:
                if ip not in known:
                    hostname = await self.reverse_dns(ip)
                    candidates.append({
                        "ip": ip,
                        "mac": "",
                        "hostname": hostname,
                        "discovered_via": "netflow",
                        "source_device_id": "",
                        "confidence_score": self.SOURCE_CONFIDENCE["netflow"],
                    })
                    known.add(ip)
        except Exception as e:
            logger.debug("Flow discovery failed: %s", e)
        return candidates

    async def reverse_dns(self, ip: str) -> str:
        """Best-effort reverse DNS lookup."""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, socket.gethostbyaddr, ip)
            return result[0]
        except (socket.herror, socket.gaierror, OSError):
            return ""
