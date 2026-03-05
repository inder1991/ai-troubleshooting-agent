"""Network Knowledge Graph -- NetworkX MultiDiGraph with confidence-weighted edges."""
import networkx as nx
from typing import Optional
from datetime import datetime, timezone
from .models import (
    Device, DeviceType, Subnet, Zone, Interface, EdgeMetadata, EdgeSource, Route,
    VPC, TransitGateway, VPNTunnel, DirectConnect, NACL, LoadBalancer,
    LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone, VPCPeering,
)
from .topology_store import TopologyStore
from .ip_resolver import IPResolver
from .interface_validation import validate_device_interfaces


def _safe_int(val, default: int = 0) -> int:
    """Safely convert to int, returning default on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


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
                    self._device_index[iface.ip] = d.id
                # Find which subnet this interface IP belongs to
                subnet_meta = self.ip_resolver.resolve(iface.ip)
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

        # Load VPCs
        for vpc in self.store.list_vpcs():
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

        # Load Transit Gateways
        for tgw in self.store.list_transit_gateways():
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
                    self.graph.add_edge(lb.id, target_id, edge_type="load_balances",
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

    def find_k_shortest_paths(
        self, src_id: str, dst_id: str, k: int = 3
    ) -> list[list[str]]:
        """Find K shortest paths using confidence-weighted dual cost model.
        cost = (1 - confidence) + topology_penalty
        """
        if src_id not in self.graph or dst_id not in self.graph:
            return []

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
            paths = list(nx.shortest_simple_paths(cost_graph, src_id, dst_id, weight="weight"))
            return paths[:k]
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

    def export_react_flow_graph(self) -> dict:
        """Convert KG nodes/edges to React Flow format for canvas rendering."""
        rf_nodes = []
        rf_edges = []
        ROW_WIDTH = 250
        COL_HEIGHT = 150

        node_type_map = {
            "device": "device",
            "subnet": "subnet",
            "vpc": "vpc",
            "compliance_zone": "compliance_zone",
            "availability_zone": "availability_zone",
            "auto_scaling_group": "auto_scaling_group",
        }

        # Separate nodes by type for hierarchical positioning
        vpc_nodes = []
        container_nodes = []  # AZ, subnet
        device_nodes = []

        for node_id, data in self.graph.nodes(data=True):
            ntype = data.get("node_type", "device")
            rf_type = node_type_map.get(ntype, "device")
            data_dict = {
                "label": data.get("name", node_id),
                "entityId": node_id,
                "deviceType": data.get("device_type", "HOST"),
                "ip": data.get("management_ip") or data.get("cidr", ""),
                "vendor": data.get("vendor", ""),
                "zone": data.get("zone_id", ""),
                "vlan": data.get("vlan_id", 0),
                "description": data.get("description", ""),
                "location": data.get("location", "") or data.get("site", ""),
                "status": "healthy",
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
                        "subnetId": iface.subnet_id,
                    }
                    for iface in device_ifaces
                ]

            node_entry = {
                "id": node_id,
                "type": rf_type,
                "data": data_dict,
            }

            if ntype == "vpc":
                vpc_nodes.append(node_entry)
            elif ntype in ("subnet", "availability_zone", "auto_scaling_group", "compliance_zone"):
                container_nodes.append(node_entry)
            else:
                device_nodes.append(node_entry)

        # Hierarchical positioning
        vpc_x = 0
        for vi, vpc_node in enumerate(vpc_nodes):
            vpc_node["position"] = {"x": vpc_x, "y": 0}
            vpc_node["style"] = {"width": 800, "height": 500}
            vpc_x += 900

        # Place containers in grid inside their VPC region
        for ci, cn in enumerate(container_nodes):
            cn["position"] = {"x": 50 + (ci % 3) * ROW_WIDTH, "y": 50 + (ci // 3) * COL_HEIGHT}
            cn["style"] = {"width": 220, "height": 180}

        # Place devices
        for di, dn in enumerate(device_nodes):
            dn["position"] = {"x": (di % 6) * ROW_WIDTH, "y": 600 + (di // 6) * COL_HEIGHT}

        rf_nodes = vpc_nodes + container_nodes + device_nodes

        for u, v, edata in self.graph.edges(data=True):
            edge_type = edata.get("edge_type", "connected_to")
            rf_edges.append({
                "id": f"e-{u}-{v}-{edge_type}",
                "source": u,
                "target": v,
                "type": "labeled",
                "data": {
                    "label": edge_type,
                    "interface": edata.get("interface", ""),
                },
                "animated": edata.get("confidence", 0) < 0.8,
            })

        return {"nodes": rf_nodes, "edges": rf_edges}
