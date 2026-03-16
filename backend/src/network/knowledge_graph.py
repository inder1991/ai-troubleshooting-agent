"""Network Knowledge Graph -- NetworkX MultiDiGraph with confidence-weighted edges."""
import itertools
import logging
import time
import networkx as nx
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from .models import (
    Device, DeviceType, Subnet, Zone, Interface, EdgeMetadata, EdgeSource, Route,
    VPC, TransitGateway, VPNTunnel, DirectConnect, NACL, LoadBalancer,
    LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone, VPCPeering,
)
from .topology_store import TopologyStore
from .ip_resolver import IPResolver
from .interface_validation import validate_device_interfaces


def _strip_cidr(ip: str) -> str:
    """Strip prefix length from CIDR notation. '10.0.0.1/30' → '10.0.0.1'."""
    return ip.split("/")[0] if ip and "/" in ip else ip


def _safe_int(val, default: int = 0) -> int:
    """Safely convert to int, returning default on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ── Topology export cache (module-level) ──
_topo_cache: dict | None = None
_topo_cache_ts: float = 0
_topo_cache_hash: str = ""
_TOPO_CACHE_TTL = 60  # seconds

# Topology penalties for dual cost model
_TOPOLOGY_PENALTIES = {
    "vrf_boundary": 0.3,
    "inter_site": 0.2,
    "overlay_tunnel": 0.15,
    "vpn_tunnel": 0.15,
    "direct_connect": 0.05,
    "mpls_circuit": 0.05,
    "cross_vpc": 0.25,
    "transit_gateway": 0.1,
    "load_balancer": 0.1,
    "low_bandwidth": 0.1,
}


class NetworkKnowledgeGraph:
    """In-memory NetworkX graph backed by SQLite persistence.

    Only topology entities live in the graph.
    Investigation artifacts (flows, traces) stay in SQLite.
    """

    def __init__(self, store: TopologyStore):
        self.store = store
        self.graph = nx.MultiDiGraph()
        self.ip_resolver = IPResolver()
        self._device_index: dict[str, str] = {}  # ip -> device_id

    def load_from_store(self) -> None:
        """Load all topology entities from SQLite into the graph."""
        self.graph.clear()
        self._device_index.clear()

        # Rebuild pytricia first (needed for interface->subnet mapping)
        subnets = self.store.list_subnets()
        self.ip_resolver.load_subnets([s.model_dump(mode="json") for s in subnets])

        # Load devices
        for d in self.store.list_devices():
            self.graph.add_node(d.id, **d.model_dump(mode="json"), node_type="device")
            if d.management_ip:
                self._device_index[d.management_ip] = d.id

        # Load subnets
        for s in subnets:
            self.graph.add_node(s.id, **s.model_dump(mode="json"), node_type="subnet")

        # Load zones
        for z in self.store.list_zones():
            self.graph.add_node(z.id, **z.model_dump(mode="json"), node_type="zone")

        # Load interfaces and create edges (device -> subnet via interface)
        for d in self.store.list_devices():
            for iface in self.store.list_interfaces(device_id=d.id):
                if iface.ip:
                    bare_ip = _strip_cidr(iface.ip)
                    self._device_index[bare_ip] = d.id
                    self._device_index[iface.ip] = d.id  # Also index with CIDR for route lookups
                # Find which subnet this interface IP belongs to
                subnet_meta = self.ip_resolver.resolve(_strip_cidr(iface.ip)) if iface.ip else None
                if subnet_meta:
                    self.graph.add_edge(
                        d.id, subnet_meta.get("id", iface.ip),
                        edge_type="connected_to",
                        interface=iface.name,
                        ip=iface.ip,
                        confidence=0.9,
                        source=EdgeSource.API.value,
                        last_verified_at=datetime.now(timezone.utc).isoformat(),
                    )

        # Load VPCs (don't overwrite if already loaded as device)
        for vpc in self.store.list_vpcs():
            if vpc.id not in self.graph:
                self.graph.add_node(vpc.id, **vpc.model_dump(mode="json"), node_type="vpc")
            # VPC contains subnets — find subnets whose CIDR falls within VPC CIDRs
            for s in subnets:
                for vpc_cidr in vpc.cidr_blocks:
                    try:
                        import ipaddress
                        if ipaddress.ip_network(s.cidr, strict=False).subnet_of(
                            ipaddress.ip_network(vpc_cidr, strict=False)
                        ):
                            self.graph.add_edge(vpc.id, s.id, edge_type="vpc_contains",
                                                confidence=1.0, source=EdgeSource.MANUAL.value)
                    except (ValueError, TypeError):
                        pass

        # Load VPC peerings
        for p in self.store.list_vpc_peerings():
            self.graph.add_edge(p.requester_vpc_id, p.accepter_vpc_id,
                                edge_type="peered_to", confidence=0.95,
                                source=EdgeSource.API.value, peering_id=p.id)
            self.graph.add_edge(p.accepter_vpc_id, p.requester_vpc_id,
                                edge_type="peered_to", confidence=0.95,
                                source=EdgeSource.API.value, peering_id=p.id)

        # Load Transit Gateways (don't overwrite if already loaded as device)
        for tgw in self.store.list_transit_gateways():
            if tgw.id not in self.graph:
                self.graph.add_node(tgw.id, **tgw.model_dump(mode="json"), node_type="transit_gateway")
            for vpc_id in tgw.attached_vpc_ids:
                self.graph.add_edge(vpc_id, tgw.id, edge_type="attached_to",
                                    confidence=0.95, source=EdgeSource.API.value)
                self.graph.add_edge(tgw.id, vpc_id, edge_type="attached_to",
                                    confidence=0.95, source=EdgeSource.API.value)

        # Load VPN Tunnels
        for vpn in self.store.list_vpn_tunnels():
            self.graph.add_node(vpn.id, **vpn.model_dump(mode="json"), node_type="vpn_tunnel")
            if vpn.local_gateway_id:
                self.graph.add_edge(vpn.local_gateway_id, vpn.id, edge_type="tunnel_to",
                                    confidence=0.9, source=EdgeSource.API.value)
                self.graph.add_edge(vpn.id, vpn.local_gateway_id, edge_type="tunnel_to",
                                    confidence=0.9, source=EdgeSource.API.value)

        # Load Direct Connects
        for dx in self.store.list_direct_connects():
            self.graph.add_node(dx.id, **dx.model_dump(mode="json"), node_type="direct_connect")

        # Load NACLs
        for nacl in self.store.list_nacls():
            self.graph.add_node(nacl.id, **nacl.model_dump(mode="json"), node_type="nacl")
            for sid in nacl.subnet_ids:
                self.graph.add_edge(nacl.id, sid, edge_type="nacl_guards",
                                    confidence=1.0, source=EdgeSource.API.value)

        # Load Load Balancers
        for lb in self.store.list_load_balancers():
            self.graph.add_node(lb.id, **lb.model_dump(mode="json"), node_type="load_balancer")
            for tg in self.store.list_lb_target_groups(lb_id=lb.id):
                for target_id in tg.target_ids:
                    # Only add edge if target exists as a device (avoid phantom nodes from IPs)
                    resolved = target_id
                    if target_id not in self.graph:
                        resolved = self._device_index.get(_strip_cidr(target_id))
                    if resolved and resolved in self.graph:
                        self.graph.add_edge(lb.id, resolved, edge_type="load_balances",
                                            confidence=0.9, source=EdgeSource.API.value,
                                            port=tg.port, protocol=tg.protocol)

        # Load VLANs
        for vlan in self.store.list_vlans():
            self.graph.add_node(vlan.id, **vlan.model_dump(mode="json"), node_type="vlan")

        # Load MPLS Circuits
        for mpls in self.store.list_mpls_circuits():
            self.graph.add_node(mpls.id, **mpls.model_dump(mode="json"), node_type="mpls")
            # Connect endpoints
            endpoints = mpls.endpoints
            for i in range(len(endpoints) - 1):
                self.graph.add_edge(endpoints[i], endpoints[i + 1],
                                    edge_type="mpls_path", confidence=0.95,
                                    source=EdgeSource.API.value, label=mpls.label)

        # Load Compliance Zones
        for cz in self.store.list_compliance_zones():
            self.graph.add_node(cz.id, **cz.model_dump(mode="json"), node_type="compliance_zone")

        # ══════════════════════════════════════════════════════════════
        # Device-to-device edges (L2, P2P L3, routes, HA, tunnels)
        # ══════════════════════════════════════════════════════════════

        # ── Layer-2 links from LLDP/CDP neighbor tables ──
        try:
            from src.network.discovery_scheduler import MOCK_NEIGHBORS
            for device_id, neighbors in MOCK_NEIGHBORS.items():
                if device_id not in self.graph:
                    continue
                for n in neighbors:
                    remote_id = n.get("remote_device", "")
                    if remote_id not in self.graph:
                        continue
                    # Avoid duplicate L2 edges
                    existing_l2 = any(
                        d.get("edge_type") == "layer2_link"
                        for _, _, d in self.graph.edges(device_id, data=True)
                        if _ == remote_id
                    )
                    if not existing_l2:
                        self.graph.add_edge(device_id, remote_id,
                            edge_type="layer2_link",
                            local_port=n.get("local_port", ""),
                            remote_port=n.get("remote_port", ""),
                            protocol=n.get("protocol", "LLDP"),
                            confidence=1.0,
                            source=EdgeSource.API.value,
                            last_verified_at=datetime.now(timezone.utc).isoformat())
        except ImportError:
            pass
        except Exception as e:
            logger.warning("L2 neighbor edge creation failed: %s", e)

        # ── P2P shared subnet → device-to-device links (only /30, /31) ──
        import ipaddress as _ipaddress

        subnet_devices: dict[str, list[tuple[str, str, str]]] = {}
        for d in self.store.list_devices():
            for iface in self.store.list_interfaces(device_id=d.id):
                if iface.ip:
                    s_meta = self.ip_resolver.resolve(iface.ip)
                    if s_meta:
                        sid = s_meta.get("id", "")
                        subnet_devices.setdefault(sid, []).append((d.id, iface.name, iface.ip))

        for sid, members in subnet_devices.items():
            if len(members) < 2:
                continue
            # Only P2P subnets get device↔device edges
            subnet_obj = next((s for s in subnets if s.id == sid), None)
            if not subnet_obj:
                continue
            try:
                net = _ipaddress.ip_network(subnet_obj.cidr, strict=False)
                if net.prefixlen < 30:
                    continue  # Large subnet — devices connect via subnet node, not each other
            except (ValueError, TypeError):
                continue

            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    d1_id, d1_iface, d1_ip = members[i]
                    d2_id, d2_iface, d2_ip = members[j]
                    self.graph.add_edge(d1_id, d2_id,
                        edge_type="layer3_link",
                        src_interface=d1_iface, dst_interface=d2_iface,
                        src_ip=d1_ip, dst_ip=d2_ip,
                        subnet_id=sid,
                        confidence=0.9,
                        source=EdgeSource.API.value,
                        last_verified_at=datetime.now(timezone.utc).isoformat())

        # ── Route-based forwarding edges (default + summary routes only) ──
        for route in self.store.list_routes():
            src_device = route.device_id
            if src_device not in self.graph:
                continue
            next_hop_device = self._device_index.get(route.next_hop)
            if not next_hop_device or next_hop_device == src_device:
                continue
            if next_hop_device not in self.graph:
                continue

            try:
                net = _ipaddress.ip_network(route.destination_cidr, strict=False)
                is_default = route.destination_cidr == "0.0.0.0/0"
                is_summary = net.prefixlen <= 24
                is_dynamic = route.protocol.upper() in ("BGP", "OSPF", "EIGRP", "IS-IS")
            except (ValueError, TypeError):
                continue

            if not (is_default or (is_summary and is_dynamic)):
                continue

            # Avoid duplicate route edges to same next-hop
            existing_route = any(
                d.get("edge_type") == "routes_via" and d.get("destination") == route.destination_cidr
                for _, target, d in self.graph.edges(src_device, data=True)
                if target == next_hop_device
            )
            if not existing_route:
                self.graph.add_edge(src_device, next_hop_device,
                    edge_type="routes_via",
                    destination=route.destination_cidr,
                    protocol=route.protocol,
                    metric=route.metric,
                    confidence=0.85,
                    source=EdgeSource.API.value,
                    last_verified_at=datetime.now(timezone.utc).isoformat())

        # ── HA peer edges ──
        for ha in self.store.list_ha_groups():
            members = ha.member_ids
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    if members[i] in self.graph and members[j] in self.graph:
                        self.graph.add_edge(members[i], members[j],
                            edge_type="ha_peer",
                            ha_group=ha.id, ha_mode=ha.ha_mode.value,
                            confidence=1.0,
                            source=EdgeSource.API.value,
                            last_verified_at=datetime.now(timezone.utc).isoformat())
                        self.graph.add_edge(members[j], members[i],
                            edge_type="ha_peer",
                            ha_group=ha.id, ha_mode=ha.ha_mode.value,
                            confidence=1.0,
                            source=EdgeSource.API.value,
                            last_verified_at=datetime.now(timezone.utc).isoformat())

        # ── VPN tunnel device-to-device links ──
        for vpn in self.store.list_vpn_tunnels():
            if vpn.local_gateway_id and vpn.remote_gateway_ip:
                remote_device = self._device_index.get(vpn.remote_gateway_ip)
                if remote_device and vpn.local_gateway_id in self.graph and remote_device in self.graph:
                    if vpn.local_gateway_id != remote_device:
                        self.graph.add_edge(vpn.local_gateway_id, remote_device,
                            edge_type="tunnel_link",
                            tunnel_id=vpn.id,
                            tunnel_type=vpn.tunnel_type.value,
                            status=vpn.status.value,
                            confidence=0.9,
                            source=EdgeSource.API.value,
                            last_verified_at=datetime.now(timezone.utc).isoformat())

        # Restore persisted edge confidences
        for ec in self.store.list_edge_confidences():
            src, dst = ec["src_id"], ec["dst_id"]
            if self.graph.has_edge(src, dst):
                for key in self.graph[src][dst]:
                    self.graph[src][dst][key]["confidence"] = ec["confidence"]
                    self.graph[src][dst][key]["last_verified_at"] = ec["last_verified_at"]

    def add_device(self, device: Device) -> None:
        self.store.add_device(device)
        self.graph.add_node(device.id, **device.model_dump(mode="json"), node_type="device")
        if device.management_ip:
            self._device_index[device.management_ip] = device.id

    def add_subnet(self, subnet: Subnet) -> None:
        self.store.add_subnet(subnet)
        self.graph.add_node(subnet.id, **subnet.model_dump(mode="json"), node_type="subnet")
        # Rebuild resolver
        subnets = self.store.list_subnets()
        self.ip_resolver.load_subnets([s.model_dump(mode="json") for s in subnets])

    def add_edge(self, src_id: str, dst_id: str, metadata: EdgeMetadata, **attrs) -> None:
        self.graph.add_edge(
            src_id, dst_id,
            confidence=metadata.confidence,
            source=metadata.source.value,
            last_verified_at=metadata.last_verified_at,
            edge_type=metadata.edge_type,
            **attrs,
        )

    def resolve_ip(self, ip: str) -> dict:
        """Resolve an IP to subnet + device metadata."""
        subnet = self.ip_resolver.resolve(ip)
        device_id = self._device_index.get(ip)
        device = None
        if device_id:
            device = self.store.get_device(device_id)
        return {
            "ip": ip,
            "subnet": subnet,
            "device": device.model_dump(mode="json") if device else None,
            "device_id": device_id,
        }

    def find_device_by_ip(self, ip: str) -> Optional[str]:
        """Find device_id for a given IP (interface or management IP)."""
        device_id = self._device_index.get(ip)
        if device_id:
            return device_id
        iface = self.store.find_interface_by_ip(ip)
        if iface:
            return iface.device_id
        return None

    def find_candidate_devices(self, ip: str) -> list[dict]:
        """When IP is in a known subnet but can't be uniquely attributed,
        return all devices with interfaces in that subnet."""
        subnet_meta = self.ip_resolver.resolve(ip)
        if not subnet_meta:
            return []
        subnet_cidr = subnet_meta.get("cidr", "")
        candidates = []
        for d in self.store.list_devices():
            for iface in self.store.list_interfaces(device_id=d.id):
                iface_subnet = self.ip_resolver.resolve(iface.ip)
                if iface_subnet and iface_subnet.get("cidr") == subnet_cidr:
                    candidates.append({
                        "device_id": d.id,
                        "device_name": d.name,
                        "interface_ip": iface.ip,
                        "interface_name": iface.name,
                    })
        return candidates

    def build_route_edges(self, src_ip: str, dst_ip: str) -> None:
        """Dynamically build routes_to edges relevant to a specific path query."""
        for node_id, data in self.graph.nodes(data=True):
            if data.get("node_type") != "device":
                continue
            routes = self.store.list_routes(device_id=node_id)
            for route in routes:
                next_device = self.find_device_by_ip(route.next_hop)
                if next_device and next_device != node_id:
                    self.graph.add_edge(
                        node_id, next_device,
                        edge_type="routes_to",
                        destination=route.destination_cidr,
                        next_hop=route.next_hop,
                        metric=route.metric,
                        protocol=route.protocol,
                        vrf=route.vrf,
                        confidence=0.85,
                        source=EdgeSource.API.value,
                        last_verified_at=route.last_updated or "",
                    )

    # Maximum number of paths to enumerate before stopping (prevents hang on dense graphs)
    MAX_PATH_ENUMERATION = 1000
    # Maximum path depth (number of nodes) to consider
    MAX_PATH_DEPTH = 15

    def find_k_shortest_paths(
        self, src_id: str, dst_id: str, k: int = 3, max_depth: int | None = None
    ) -> list[list[str]]:
        """Find K shortest paths using confidence-weighted dual cost model.
        cost = (1 - confidence) + topology_penalty

        Bounded to enumerate at most MAX_PATH_ENUMERATION paths total and
        filters out paths longer than *max_depth* nodes (default MAX_PATH_DEPTH).
        """
        if src_id not in self.graph or dst_id not in self.graph:
            return []

        depth_limit = max_depth if max_depth is not None else self.MAX_PATH_DEPTH

        cost_graph = nx.DiGraph()
        for u, v, data in self.graph.edges(data=True):
            confidence = data.get("confidence", 0.5)
            penalty = 0.0
            if data.get("vrf") and data.get("vrf") != "":
                penalty += _TOPOLOGY_PENALTIES["vrf_boundary"]
            if data.get("edge_type") == "overlay":
                penalty += _TOPOLOGY_PENALTIES["overlay_tunnel"]
            if data.get("edge_type") == "tunnel_to":
                penalty += _TOPOLOGY_PENALTIES["vpn_tunnel"]
            if data.get("edge_type") == "attached_to":
                penalty += _TOPOLOGY_PENALTIES["transit_gateway"]
            if data.get("edge_type") == "load_balances":
                penalty += _TOPOLOGY_PENALTIES["load_balancer"]
            if data.get("edge_type") == "peered_to":
                penalty += _TOPOLOGY_PENALTIES["cross_vpc"]
            if data.get("edge_type") == "mpls_path":
                penalty += _TOPOLOGY_PENALTIES["mpls_circuit"]
            cost = (1.0 - confidence) + penalty
            if cost_graph.has_edge(u, v):
                if cost < cost_graph[u][v]["weight"]:
                    cost_graph[u][v]["weight"] = cost
            else:
                cost_graph.add_edge(u, v, weight=cost)

        try:
            bounded_paths = itertools.islice(
                nx.shortest_simple_paths(cost_graph, src_id, dst_id, weight="weight"),
                self.MAX_PATH_ENUMERATION,
            )
            result = []
            for path in bounded_paths:
                if len(path) <= depth_limit:
                    result.append(path)
                if len(result) >= k:
                    break
            return result
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def boost_edge_confidence(self, src_id: str, dst_id: str, boost: float = 0.05) -> None:
        """Boost confidence on a verified edge and persist to SQLite."""
        if self.graph.has_edge(src_id, dst_id):
            new_conf = 0.5  # default
            for key in self.graph[src_id][dst_id]:
                current = self.graph[src_id][dst_id][key].get("confidence", 0.5)
                new_conf = min(1.0, current + boost)
                self.graph[src_id][dst_id][key]["confidence"] = new_conf
                self.graph[src_id][dst_id][key]["last_verified_at"] = \
                    datetime.now(timezone.utc).isoformat()
            # Persist to SQLite
            self.store.save_edge_confidence(src_id, dst_id, new_conf, "diagnosis")

    def writeback_discovered_hops(self, hops: list[dict]) -> int:
        """Write diagnosis-discovered hops back to topology as devices/edges.
        Each hop dict: {ip, device_id?, device_name?, rtt_ms, status}
        Returns count of new devices added.
        """
        added = 0
        prev_device_id = None
        for hop in hops:
            ip = hop.get("ip", "")
            if not ip or ip == "*":
                continue
            device_id = hop.get("device_id") or self.find_device_by_ip(ip)
            if not device_id:
                # New device discovered by diagnosis
                device_id = f"device-discovered-{ip.replace('.', '-')}"
                device = Device(
                    id=device_id,
                    name=hop.get("device_name", f"discovered-{ip}"),
                    device_type=DeviceType.HOST,
                    management_ip=ip,
                )
                self.add_device(device)
                added += 1
            # Create edge from previous hop
            if prev_device_id and prev_device_id != device_id:
                self.add_edge(
                    prev_device_id, device_id,
                    EdgeMetadata(
                        confidence=0.7,
                        source=EdgeSource.DIAGNOSIS,
                        edge_type="routes_to",
                    ),
                )
            prev_device_id = device_id
        return added

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

    def promote_from_canvas(self, nodes: list[dict], edges: list[dict]) -> dict:
        """Promote canvas nodes/edges into the authoritative KG.

        Validates against Pydantic models, upserts into SQLite + NetworkX.
        Returns summary: {devices_promoted, edges_promoted, errors}.
        """
        stats = {"devices_promoted": 0, "edges_promoted": 0, "errors": []}

        # Load VIPs from HA groups to suppress false duplicate warnings
        ha_groups = self.store.list_ha_groups()
        known_vips: set[str] = set()
        for hg in ha_groups:
            known_vips.update(hg.virtual_ips)

        # Pre-validation: collect IPs for duplicate detection
        seen_ips: dict[str, str] = {}  # ip -> first node label

        # Canvas-only container types that don't persist to KG
        CANVAS_ONLY_TYPES = {"availability_zone", "auto_scaling_group"}

        for node in nodes:
            try:
                node_type = node.get("type", "device")
                data = node.get("data", {})
                node_id = node.get("id", "")

                # Skip canvas-only container types
                if node_type in CANVAS_ONLY_TYPES:
                    continue

                if node_type == "device":
                    ip = data.get("ip", "")

                    # Duplicate IP detection (skip known HA VIPs)
                    if ip and ip in seen_ips and ip not in known_vips:
                        stats["errors"].append(
                            f"Duplicate IP '{ip}' on '{data.get('label', node_id)}' "
                            f"(already used by '{seen_ips[ip]}')"
                        )
                        continue
                    if ip:
                        seen_ips[ip] = data.get("label", node_id)

                    dt_str = (data.get("deviceType") or "HOST").upper()
                    try:
                        dt = DeviceType[dt_str]
                    except KeyError:
                        dt = DeviceType.HOST

                    device = Device(
                        id=node_id,
                        name=data.get("label", node_id),
                        device_type=dt,
                        management_ip=data.get("ip", ""),
                        vendor=data.get("vendor", ""),
                        location=data.get("location", ""),
                        zone_id=data.get("zone", ""),
                        vlan_id=_safe_int(data.get("vlan"), 0),
                        description=data.get("description", ""),
                    )
                    self.store.add_device(device)
                    self.add_device(device)
                    stats["devices_promoted"] += 1

                    # Process interfaces from canvas data
                    iface_list = data.get("interfaces", [])
                    for iface_data in iface_list:
                        iface = Interface(
                            id=iface_data.get("id", f"iface-{node_id}-{iface_data.get('name', '')}"),
                            device_id=node_id,
                            name=iface_data.get("name", ""),
                            ip=iface_data.get("ip", ""),
                            role=iface_data.get("role", ""),
                            zone_id=iface_data.get("zone", ""),
                            subnet_id=iface_data.get("subnetId", ""),
                        )
                        self.store.add_interface(iface)
                        if iface.ip:
                            self._device_index[iface.ip] = node_id

                elif node_type == "subnet":
                    cidr = data.get("cidr") or data.get("ip", "")
                    if cidr:
                        # Check if a subnet with this CIDR already exists to avoid
                        # INSERT OR REPLACE deleting the old row and breaking FK refs
                        existing_subnets = self.store.list_subnets()
                        existing_cidrs = {s.cidr: s.id for s in existing_subnets}
                        if cidr in existing_cidrs:
                            subnet_id = existing_cidrs[cidr]  # reuse existing
                            stats["subnets_reused"] = stats.get("subnets_reused", 0) + 1
                        else:
                            subnet_id = node_id

                        subnet = Subnet(
                            id=subnet_id,
                            cidr=cidr,
                            zone_id=data.get("zone", ""),
                            vlan_id=_safe_int(data.get("vlan"), 0),
                            description=data.get("description", ""),
                        )
                        try:
                            self.store.add_subnet(subnet)
                            stats["devices_promoted"] += 1
                        except Exception as e:
                            stats.setdefault("errors", []).append(f"Subnet {subnet.id}: {e}")
                        self.add_subnet(subnet)

            except Exception as e:
                stats["errors"].append(f"Node {node.get('id', '?')}: {str(e)}")

        for edge in edges:
            try:
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                if src and tgt:
                    edge_data = edge.get("data", {})
                    edge_label = edge_data.get("label") if edge_data else None
                    if not edge_label:
                        edge_label = edge.get("label", "connected_to")
                    extra_attrs = {}
                    if edge_data:
                        src_handle = edge_data.get("sourceHandle", "")
                        tgt_handle = edge_data.get("targetHandle", "")
                        if src_handle:
                            extra_attrs["source_handle"] = src_handle
                        if tgt_handle:
                            extra_attrs["target_handle"] = tgt_handle
                        if edge_data.get("interface"):
                            extra_attrs["interface"] = edge_data["interface"]
                    self.add_edge(
                        src, tgt,
                        EdgeMetadata(
                            confidence=0.8,
                            source=EdgeSource.MANUAL,
                            edge_type=edge_label,
                        ),
                        **extra_attrs,
                    )
                    stats["edges_promoted"] += 1
            except Exception as e:
                stats["errors"].append(f"Edge {src}->{tgt}: {str(e)}")

        # Validate interfaces for all promoted devices
        all_subnets = self.store.list_subnets()
        all_zones = self.store.list_zones()
        for node in nodes:
            if node.get("type", "device") == "device":
                device_id = node.get("id", "")
                device_ifaces = self.store.list_interfaces(device_id=device_id)
                if device_ifaces:
                    device_obj = self.store.get_device(device_id)
                    device_vlan = device_obj.vlan_id if device_obj else 0
                    iface_errors = validate_device_interfaces(
                        device_id, device_ifaces, all_subnets, all_zones,
                        device_vlan_id=device_vlan,
                    )
                    for ie in iface_errors:
                        stats["errors"].append(ie["message"])

        return stats

    def apply_design(self, design_id: str, expected_live_hash: str | None = None) -> dict:
        """Apply planned nodes from a design to the live inventory.

        Performs TOCTOU check, re-validates conflicts, and applies transactionally.
        """
        import json

        # TOCTOU check
        current_hash = self.store.compute_live_hash()
        if expected_live_hash and current_hash != expected_live_hash:
            raise ValueError(
                "LIVE_DRIFT: Live inventory changed since diff was computed. "
                "Please re-run diff."
            )

        # Re-run conflict check
        diff = self.store.compute_design_diff(design_id)
        if not diff["can_apply"]:
            raise ValueError(
                f"CONFLICTS: {len(diff['conflicts'])} conflicts and "
                f"{len(diff['edge_errors'])} edge errors remain."
            )

        design = self.store.get_design(design_id)
        if not design:
            raise ValueError(f"Design {design_id} not found")

        snapshot = json.loads(design["snapshot_json"])
        planned_nodes = [n for n in snapshot.get("nodes", [])
                         if n.get("data", {}).get("_source") == "planned"]
        planned_edges = [e for e in snapshot.get("edges", [])
                         if e.get("data", {}).get("_source") == "planned"]

        stats = {"devices_added": 0, "edges_added": 0, "skipped": [], "errors": []}

        # Apply planned nodes as devices
        live_ids = {d.id for d in self.store.list_devices()}
        devices_to_add = []
        for node in planned_nodes:
            nid = node.get("id", "")
            data = node.get("data", {})
            if nid in live_ids:
                stats["skipped"].append(nid)
                continue

            dt_str = (data.get("deviceType") or "HOST").upper()
            try:
                dt = DeviceType[dt_str]
            except KeyError:
                dt = DeviceType.HOST

            device = Device(
                id=nid,
                name=data.get("label", nid),
                device_type=dt,
                management_ip=data.get("ip", ""),
                vendor=data.get("vendor", ""),
                location=data.get("location", ""),
                zone_id=data.get("zone", ""),
                vlan_id=_safe_int(data.get("vlan"), 0),
                description=data.get("description", ""),
            )
            devices_to_add.append(device)

        # Transactional apply
        try:
            for device in devices_to_add:
                self.store.add_device(device)
                self.add_device(device)
                stats["devices_added"] += 1

            for edge in planned_edges:
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                if src and tgt:
                    edge_data = edge.get("data", {})
                    label = edge_data.get("label", "connected_to") if edge_data else "connected_to"
                    self.add_edge(
                        src, tgt,
                        EdgeMetadata(
                            confidence=0.8,
                            source=EdgeSource.MANUAL,
                            edge_type=label,
                        ),
                    )
                    stats["edges_added"] += 1
        except Exception as e:
            stats["errors"].append(str(e))
            raise

        # Update design status
        self.store.update_design_status(design_id, "applied")
        stats["new_live_hash"] = self.store.compute_live_hash()
        return stats

    # ── Visual node types (skip zones, subnets, NACLs, etc.) ──
    VISUAL_NODE_TYPES = {"device"}  # VPCs and TGW are already device nodes in fixtures

    # ── Edge styling by type ──
    EDGE_STYLES = {
        "layer2_link":   {"stroke": "#22c55e", "strokeWidth": 3},                          # Bright green, thick
        "layer3_link":   {"stroke": "#22c55e", "strokeWidth": 3},                          # Same green — physical link
        "ha_peer":       {"stroke": "#f59e0b", "strokeWidth": 2, "strokeDasharray": "6,4"}, # Amber dashed
        "tunnel_link":   {"stroke": "#06b6d4", "strokeWidth": 3, "strokeDasharray": "10,5"}, # Cyan dashed, thick
        "routes_via":    {"stroke": "#64748b", "strokeWidth": 1, "opacity": 0.3},            # Very subtle
        "attached_to":   {"stroke": "#06b6d4", "strokeWidth": 3},                           # Cyan solid — cloud attach
        "load_balances": {"stroke": "#a855f7", "strokeWidth": 2},                           # Purple
        "mpls_path":     {"stroke": "#f59e0b", "strokeWidth": 4},                           # Amber, thickest — WAN
        "connected_to":  {"stroke": "#22c55e", "strokeWidth": 2},                           # Green
        "vpc_contains":  {"stroke": "#64748b", "strokeWidth": 1, "strokeDasharray": "3,3"}, # Subtle
    }

    GROUP_LABELS = {
        "onprem": "On-Premises DC",
        "aws": "AWS",
        "azure": "Azure",
        "oci": "Oracle Cloud",
        "gcp": "GCP",
        "branch": "Branch Offices",
    }

    # Group accent colors — distinct per cloud/site
    GROUP_ACCENTS = {
        "onprem": "#e09f3e",  # Amber
        "aws":    "#f59e0b",  # Orange
        "azure":  "#3b82f6",  # Blue
        "oci":    "#ef4444",  # Red
        "gcp":    "#10b981",  # Emerald
        "branch": "#8b5cf6",  # Violet
    }

    def _compute_topology_hash(self) -> str:
        """SHA-256 hash of topology structure + key attributes for change detection."""
        import hashlib, json
        nodes_data = sorted([
            (nid, data.get("node_type", ""), data.get("name", ""), data.get("management_ip", ""))
            for nid, data in self.graph.nodes(data=True)
        ])
        edges_data = sorted([
            (s, d, data.get("edge_type", ""), data.get("status", ""))
            for s, d, _, data in self.graph.edges(data=True, keys=True)
        ])
        content = json.dumps({"n": nodes_data, "e": edges_data}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_device_group(self, node_data: dict) -> str:
        """Classify a device into a site/cloud group for visual grouping."""
        location = (node_data.get("location", "") or "").lower()
        cloud = (node_data.get("cloud_provider", "") or "").lower()
        region = (node_data.get("region", "") or "").lower()
        name = (node_data.get("name", "") or "").lower()
        loc_or_region = location + " " + region  # Check both

        # AWS detection
        if cloud == "aws" or "us-east" in loc_or_region or "us-west" in loc_or_region or "aws" in name or "vpc-" in name or "tgw-" in name or "gwlb-" in name or "natgw-" in name or "igw-" in name or "csr-aws" in name:
            return "aws"
        # Azure detection
        if cloud == "azure" or "westeurope" in loc_or_region or "eastus" in loc_or_region or "azure" in name or "vwan-" in name or "vnet-" in name or "nva-azure" in name or "er-gw" in name:
            return "azure"
        # OCI detection
        if cloud == "oci" or "ashburn" in loc_or_region or "oracle" in loc_or_region or "oci" in name or "vcn-" in name or "drg-" in name:
            return "oci"
        # GCP detection
        if cloud == "gcp" or "gcp" in loc_or_region:
            return "gcp"
        # Branch
        if "branch" in location or "branch" in name:
            return "branch"
        return "onprem"

    def _get_device_status(self, device_id: str, metrics_store) -> str:
        """Derive device health status from latest metrics."""
        if not metrics_store:
            return "initializing"  # Monitoring not started yet
        cpu = metrics_store.get_latest_device_metric(device_id, "cpu_pct")
        if cpu is None:
            return "initializing"  # Not polled yet — monitoring warming up
        if cpu > 95:
            return "critical"
        if cpu > 80:
            return "degraded"
        return "healthy"

    def export_react_flow_graph(self, metrics_store=None) -> dict:
        """Convert KG nodes/edges to React Flow format with grouping, dedup, and caching."""
        global _topo_cache, _topo_cache_ts, _topo_cache_hash

        now = time.time()
        current_hash = self._compute_topology_hash()

        # Check cache: topology unchanged AND TTL not expired
        if (
            _topo_cache is not None
            and current_hash == _topo_cache_hash
            and (now - _topo_cache_ts) < _TOPO_CACHE_TTL
        ):
            # Even when cached, refresh device status (status changes faster than topology)
            if metrics_store:
                for node in _topo_cache["nodes"]:
                    if node.get("type") != "group":
                        entity_id = node["data"].get("entityId", node["id"])
                        node["data"]["status"] = self._get_device_status(entity_id, metrics_store)
            _topo_cache["exported_at"] = now
            return _topo_cache

        # ── Rebuild export ──
        rf_nodes: list[dict] = []
        rf_edges: list[dict] = []

        # ── Nodes: only visual types ──
        all_device_nodes: list[dict] = []

        for node_id, data in self.graph.nodes(data=True):
            ntype = data.get("node_type", "device")
            if ntype not in self.VISUAL_NODE_TYPES:
                continue

            data_dict = {
                "label": data.get("name", node_id),
                "entityId": node_id,
                "deviceType": data.get("device_type", "HOST"),
                "ip": data.get("management_ip") or data.get("cidr", ""),
                "vendor": data.get("vendor", ""),
                "role": data.get("role", ""),
                "group": self._get_device_group(data),
                "status": self._get_device_status(node_id, metrics_store),
                "haRole": data.get("ha_role", ""),
                "location": data.get("location", "") or data.get("site", ""),
                "osVersion": data.get("os_version", ""),
            }

            # Include interfaces for device nodes
            if ntype == "device":
                device_ifaces = self.store.list_interfaces(device_id=node_id)
                data_dict["interfaces"] = [
                    {
                        "id": iface.id,
                        "name": iface.name,
                        "ip": iface.ip,
                        "role": iface.role,
                        "zone": iface.zone_id,
                        "operStatus": iface.oper_status,
                        "adminStatus": iface.admin_status,
                    }
                    for iface in device_ifaces
                ]

            # Operational metrics from SNMP/vendor collectors
            if metrics_store and ntype == "device":
                cpu = metrics_store.get_latest_device_metric(node_id, "cpu_pct")
                memory = metrics_store.get_latest_device_metric(node_id, "memory_pct")
                data_dict["cpuPct"] = round(cpu, 1) if cpu is not None else None
                data_dict["memoryPct"] = round(memory, 1) if memory is not None else None

                # Firewall-specific
                if data.get("device_type") in ("firewall", "FIREWALL"):
                    sessions = metrics_store.get_latest_device_metric(node_id, "session_count")
                    session_max = metrics_store.get_latest_device_metric(node_id, "session_max")
                    data_dict["sessionCount"] = int(sessions) if sessions is not None else None
                    data_dict["sessionMax"] = int(session_max) if session_max is not None else None

                    threat_hits = metrics_store.get_latest_device_metric(node_id, "threat_hits_total")
                    data_dict["threatHits"] = int(threat_hits) if threat_hits is not None else None

                # Load balancer-specific
                if data.get("device_type") in ("load_balancer", "LOAD_BALANCER"):
                    ssl_tps = metrics_store.get_latest_device_metric(node_id, "ssl_tps")
                    data_dict["sslTps"] = int(ssl_tps) if ssl_tps is not None else None

                    # Find pool health from metrics
                    for metric_name in ["pool_web-app-pool_members_up", "pool_api-pool_members_up", "pool_aws-web-pool_members_up"]:
                        up = metrics_store.get_latest_device_metric(node_id, metric_name)
                        total_metric = metric_name.replace("_up", "_total")
                        total = metrics_store.get_latest_device_metric(node_id, total_metric)
                        if up is not None and total is not None:
                            data_dict["poolHealth"] = f"{int(up)}/{int(total)}"
                            break

                # Router-specific
                if data.get("device_type") in ("router", "ROUTER"):
                    bgp_peers = []
                    # Check for BGP peer metrics
                    for key in ["bgp_peer_10.255.0.2_state", "bgp_peer_169.254.100.2_state"]:
                        state = metrics_store.get_latest_device_metric(node_id, key)
                        if state is not None:
                            bgp_peers.append(state)
                    if bgp_peers:
                        up = sum(1 for p in bgp_peers if p == 1)
                        data_dict["bgpPeers"] = f"{up}/{len(bgp_peers)}"

                    route_count = metrics_store.get_latest_device_metric(node_id, "route_table_size_ipv4")
                    data_dict["routeCount"] = int(route_count) if route_count is not None else None

            node_entry = {
                "id": node_id,
                "type": ntype,
                "data": data_dict,
            }
            all_device_nodes.append(node_entry)

        # ── Group container nodes by site/cloud ──
        groups_found: dict[str, list] = {}
        for node in all_device_nodes:
            g = node["data"]["group"]
            groups_found.setdefault(g, []).append(node)

        # ── Rank helper for sorting within cloud groups ──
        ROLE_RANK = {
            "perimeter": 1, "core": 2, "distribution": 3,
            "access": 4, "edge": 3, "cloud_gateway": 5,
        }
        DEVICE_TYPE_RANK = {
            "FIREWALL": 2, "ROUTER": 3, "LOAD_BALANCER": 3, "SWITCH": 4,
            "PROXY": 3, "HOST": 6, "TRANSIT_GATEWAY": 5, "CLOUD_GATEWAY": 5,
            "NAT_GATEWAY": 5, "VIRTUAL_APPLIANCE": 4, "VPN_CONCENTRATOR": 3,
        }

        def _get_rank(node_data: dict, group: str = "") -> int:
            role = node_data.get("role", "")
            if group in ("aws", "azure", "oci", "gcp"):
                CLOUD_RANK = {
                    "cloud_gateway": 0, "core": 1, "distribution": 2,
                    "edge": 3, "access": 4,
                }
                if role and role in CLOUD_RANK:
                    return CLOUD_RANK[role]
            if role and role in ROLE_RANK:
                return ROLE_RANK[role]
            dt = node_data.get("deviceType", "HOST")
            return DEVICE_TYPE_RANK.get(dt, 5)

        # ══════════════════════════════════════════════════════════════
        # Radial Hub-Spoke Layout
        # ══════════════════════════════════════════════════════════════
        import math

        CENTER_X = 1200  # Canvas center
        CENTER_Y = 800
        INNER_RADIUS = 350   # Distribution devices
        OUTER_RADIUS = 900   # Cloud groups and branches
        NODE_W = 180
        NODE_H = 80

        # Angles for outer groups (degrees, math convention: 0=right, 90=up)
        # Y is negated below to convert to screen coords (Y-down)
        OUTER_ANGLES: dict[str, int] = {
            "aws": 0,           # Right
            "azure": 180,       # Left
            "oci": 240,         # Lower-left (math: 240° = lower-left)
            "gcp": 60,          # Upper-right
            "branch": 310,      # Lower-right (math: 310° = lower-right)
        }

        # ── Step 1: Classify on-prem devices into core/inner rings ──
        core_devices: list = []    # Core FW, core routers, perimeter FW
        inner_devices: list = []   # Distribution, edge, access, proxy

        onprem_nodes = groups_found.get("onprem", [])
        for node in onprem_nodes:
            role = node["data"].get("role", "")
            if role in ("core", "perimeter"):
                core_devices.append(node)
            else:
                inner_devices.append(node)

        # ── Step 2: Position CORE devices in a tight cluster at center ──
        core_cols = min(len(core_devices), 4)
        core_rows = math.ceil(len(core_devices) / max(core_cols, 1))
        for idx, node in enumerate(core_devices):
            col = idx % core_cols
            row = idx // core_cols
            node["position"] = {
                "x": int(CENTER_X - (core_cols * NODE_W) / 2 + col * (NODE_W + 20)),
                "y": int(CENTER_Y - (core_rows * NODE_H) / 2 + row * (NODE_H + 30)),
            }

        # ── Step 3: Position INNER ring devices around core ──
        if inner_devices:
            angle_step = 360 / len(inner_devices)
            for idx, node in enumerate(inner_devices):
                angle_rad = math.radians(idx * angle_step + 45)  # Start at 45°
                node["position"] = {
                    "x": int(CENTER_X + INNER_RADIUS * math.cos(angle_rad) - NODE_W / 2),
                    "y": int(CENTER_Y - INNER_RADIUS * math.sin(angle_rad) - NODE_H / 2),  # Negate sin for screen Y-down
                }

        # ── Step 4: Position OUTER groups (clouds + branches) ──
        outer_group_positions: dict[str, tuple[int, int]] = {}  # group_id → center (x, y)

        for group_id, group_nodes in groups_found.items():
            if group_id == "onprem":
                continue  # Already positioned above

            angle_deg = OUTER_ANGLES.get(group_id, 45)
            angle_rad = math.radians(angle_deg)

            # Group center position
            gx = int(CENTER_X + OUTER_RADIUS * math.cos(angle_rad))
            gy = int(CENTER_Y - OUTER_RADIUS * math.sin(angle_rad))  # Negate sin for screen Y-down
            outer_group_positions[group_id] = (gx, gy)

            # Position devices within this outer group in a small cluster
            n = len(group_nodes)
            cols = min(n, 3)
            rows = math.ceil(n / max(cols, 1))
            cluster_w = cols * (NODE_W + 20)
            cluster_h = rows * (NODE_H + 30)

            # Sort by rank within cloud group
            group_nodes.sort(key=lambda nd: (_get_rank(nd["data"], group_id), nd["data"].get("label", "")))

            for idx, node in enumerate(group_nodes):
                col = idx % cols
                row = idx // cols
                node["position"] = {
                    "x": int(gx - cluster_w / 2 + col * (NODE_W + 20)),
                    "y": int(gy - cluster_h / 2 + row * (NODE_H + 30)),
                }

        # ── Step 5: Create group label nodes (no containers — just floating labels) ──
        # On-prem: label above the core cluster
        rf_nodes.append({
            "id": "group-onprem",
            "type": "group",
            "data": {"label": self.GROUP_LABELS.get("onprem", "On-Premises DC")},
            "position": {"x": CENTER_X - 300, "y": CENTER_Y - 280},
            "style": {
                "width": 600, "height": 560,
                "backgroundColor": f"{self.GROUP_ACCENTS['onprem']}0A",
                "border": f"2px solid {self.GROUP_ACCENTS['onprem']}50",
                "borderRadius": 16,
                "padding": 10,
                "fontSize": 18, "fontWeight": 800,
                "color": f"{self.GROUP_ACCENTS['onprem']}CC",
                "letterSpacing": "0.06em",
                "textTransform": "uppercase",
            },
            "selectable": False, "draggable": False,
        })
        # Set on-prem devices as children of the group
        for node in core_devices + inner_devices:
            node["parentId"] = "group-onprem"
            # Convert absolute position to relative to group
            node["position"]["x"] -= (CENTER_X - 300)
            node["position"]["y"] -= (CENTER_Y - 280)

        # Outer group labels
        for group_id, (gx, gy) in outer_group_positions.items():
            group_nodes = groups_found.get(group_id, [])
            if not group_nodes:
                continue
            accent = self.GROUP_ACCENTS.get(group_id, "#3d3528")

            # Calculate cluster bounding box
            n = len(group_nodes)
            cols = min(n, 3)
            rows = math.ceil(n / max(cols, 1))
            cluster_w = max(cols * (NODE_W + 20) + 60, 300)
            cluster_h = max(rows * (NODE_H + 30) + 60, 200)

            rf_nodes.append({
                "id": f"group-{group_id}",
                "type": "group",
                "data": {"label": self.GROUP_LABELS.get(group_id, group_id)},
                "position": {"x": int(gx - cluster_w / 2), "y": int(gy - cluster_h / 2)},
                "style": {
                    "width": cluster_w, "height": cluster_h,
                    "backgroundColor": f"{accent}0A",
                    "border": f"2px solid {accent}50",
                    "borderRadius": 16,
                    "padding": 10,
                    "fontSize": 18, "fontWeight": 800,
                    "color": f"{accent}CC",
                    "letterSpacing": "0.06em",
                    "textTransform": "uppercase",
                },
                "selectable": False, "draggable": False,
            })

            # Set outer devices as children — convert to relative positions
            group_offset_x = int(gx - cluster_w / 2)
            group_offset_y = int(gy - cluster_h / 2)
            for node in group_nodes:
                node["parentId"] = f"group-{group_id}"
                node["position"]["x"] -= group_offset_x
                node["position"]["y"] -= group_offset_y

        rf_nodes.extend(all_device_nodes)

        # ── Step 6: Add environment label nodes above each group ──
        # These are custom "envLabel" nodes — large, prominent, with icon
        # Positioned above and centered on each group

        # On-prem label
        onprem_accent = self.GROUP_ACCENTS.get("onprem", "#e09f3e")
        rf_nodes.append({
            "id": "env-label-onprem",
            "type": "envLabel",
            "data": {
                "label": "On-Premises DC",
                "envType": "onprem",
                "accent": onprem_accent,
                "deviceCount": len(core_devices) + len(inner_devices),
            },
            "position": {"x": CENTER_X - 120, "y": CENTER_Y - 320},
            "selectable": False, "draggable": False,
        })

        # Outer group labels
        for group_id, (gx, gy) in outer_group_positions.items():
            group_nodes_list = groups_found.get(group_id, [])
            if not group_nodes_list:
                continue
            accent = self.GROUP_ACCENTS.get(group_id, "#3d3528")
            n = len(group_nodes_list)
            cols = min(n, 3)
            rows_count = math.ceil(n / max(cols, 1))
            cluster_h_val = max(rows_count * (NODE_H + 30) + 60, 200)

            rf_nodes.append({
                "id": f"env-label-{group_id}",
                "type": "envLabel",
                "data": {
                    "label": self.GROUP_LABELS.get(group_id, group_id),
                    "envType": group_id,
                    "accent": accent,
                    "deviceCount": n,
                },
                "position": {"x": gx - 100, "y": int(gy - cluster_h_val / 2 - 50)},
                "selectable": False, "draggable": False,
            })

        # ── Edges: deduplicate bidirectional, style by type ──
        # Build set of visual node IDs for filtering
        visual_node_ids = {n["id"] for n in all_device_nodes}

        seen_edges: set[tuple] = set()
        for src, dst, key, data in self.graph.edges(data=True, keys=True):
            # Skip edges between non-visual nodes
            if src not in visual_node_ids or dst not in visual_node_ids:
                continue

            edge_type = data.get("edge_type", "link")
            dedup_key = (min(src, dst), max(src, dst), edge_type)

            # Fix A: Ghost link — if both L2 and L3 exist, prefer L2
            l2_key = (min(src, dst), max(src, dst), "layer2_link")
            l3_key = (min(src, dst), max(src, dst), "layer3_link")
            if edge_type == "layer3_link" and l2_key in seen_edges:
                continue  # Skip L3 — L2 already covers this link

            if dedup_key in seen_edges:
                continue
            seen_edges.add(dedup_key)

            style = dict(self.EDGE_STYLES.get(edge_type, self.EDGE_STYLES["layer3_link"]))

            # Link status
            if data.get("status") == "DOWN":
                style["stroke"] = "#ef4444"
                style["strokeWidth"] = 4
                style["strokeDasharray"] = "6,3"

            # Build edge label from interface names
            src_iface = data.get("src_interface") or data.get("local_port", "")
            dst_iface = data.get("dst_interface") or data.get("remote_port", "")

            # Link utilization from interface metrics
            link_util = None
            link_speed = ""
            if metrics_store:
                src_iface_name = data.get("src_interface") or data.get("local_port", "")
                if src_iface_name and src:
                    util = metrics_store.get_latest_device_metric(src, f"iface_{src_iface_name}_utilization_pct")
                    if util is not None:
                        link_util = round(util, 0)

            # Get interface speed from topology store
            if src_iface:
                ifaces = self.store.list_interfaces(device_id=src)
                for iface in ifaces:
                    if iface.name == src_iface:
                        link_speed = iface.speed
                        break

            # Build edge label with operational data
            edge_label = ""
            if edge_type in ("mpls_path",):
                edge_label = f"MPLS"
                if link_speed:
                    edge_label += f" · {link_speed}"
            elif edge_type == "tunnel_link":
                ttype = data.get("tunnel_type", "GRE").upper()
                edge_label = ttype
                if data.get("status") == "DOWN":
                    edge_label += " DOWN"
            elif edge_type == "attached_to":
                edge_label = "TGW"
            elif src_iface and dst_iface:
                parts = []
                if link_speed:
                    parts.append(link_speed)
                if link_util is not None:
                    parts.append(f"{int(link_util)}%")
                edge_label = " · ".join(parts) if parts else ""
            elif edge_type == "ha_peer":
                edge_label = "HA"
            elif edge_type == "routes_via":
                edge_label = data.get("destination", "")

            # Adjust edge stroke based on utilization
            if link_util is not None and link_util > 0:
                # Scale width: 2px at 0%, 5px at 100%
                style["strokeWidth"] = max(2, min(6, 2 + link_util / 25))
                # Color shift: normal green → amber at high util → red at critical
                if link_util > 90:
                    style["stroke"] = "#ef4444"  # Red — critical
                elif link_util > 75:
                    style["stroke"] = "#f59e0b"  # Amber — warning

            # WAN links get larger, more prominent labels
            is_wan = edge_type in ("mpls_path", "tunnel_link", "attached_to")
            label_size = 10 if is_wan else 8
            label_fill = "#94a3b8" if is_wan else "#64748b"
            label_weight = 600 if is_wan else 400

            rf_edges.append({
                "id": f"e-{src}-{dst}-{edge_type}-{key}",
                "source": src,
                "target": dst,
                "type": "smoothstep",
                "label": edge_label,
                "labelStyle": {"fontSize": label_size, "fill": label_fill, "fontWeight": label_weight},
                "labelBgStyle": {"fill": "#1a1814", "fillOpacity": 0.8},
                "labelBgPadding": [4, 2],
                "data": {
                    "edgeType": edge_type,
                    "srcInterface": src_iface,
                    "dstInterface": dst_iface,
                    "protocol": data.get("protocol", ""),
                    "status": data.get("status", "up"),
                    "utilization": link_util,
                    "speed": link_speed,
                },
                "style": style,
                "animated": edge_type == "tunnel_link" and data.get("status", "UP") == "UP",
            })

        result = {
            "nodes": rf_nodes,
            "edges": rf_edges,
            "topology_version": current_hash,
            "exported_at": now,
            "device_count": len([n for n in rf_nodes if n.get("type") != "group"]),
            "edge_count": len(rf_edges),
            "groups": list(groups_found.keys()),
        }

        # Update cache
        _topo_cache = result
        _topo_cache_ts = now
        _topo_cache_hash = current_hash

        return result
