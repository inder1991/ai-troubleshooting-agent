"""Network Knowledge Graph -- NetworkX MultiDiGraph with confidence-weighted edges."""
import networkx as nx
from typing import Optional
from datetime import datetime, timezone
from .models import (
    Device, Subnet, Zone, Interface, EdgeMetadata, EdgeSource, Route,
    VPC, TransitGateway, VPNTunnel, DirectConnect, NACL, LoadBalancer,
    LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone, VPCPeering,
)
from .topology_store import TopologyStore
from .ip_resolver import IPResolver


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
        self.ip_resolver.load_subnets([s.model_dump() for s in subnets])

        # Load devices
        for d in self.store.list_devices():
            self.graph.add_node(d.id, **d.model_dump(), node_type="device")
            if d.management_ip:
                self._device_index[d.management_ip] = d.id

        # Load subnets
        for s in subnets:
            self.graph.add_node(s.id, **s.model_dump(), node_type="subnet")

        # Load zones
        for z in self.store.list_zones():
            self.graph.add_node(z.id, **z.model_dump(), node_type="zone")

        # Load interfaces and create edges (device -> subnet via interface)
        for d in self.store.list_devices():
            for iface in self.store.list_interfaces(device_id=d.id):
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
            self.graph.add_node(vpc.id, **vpc.model_dump(), node_type="vpc")
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
            self.graph.add_node(tgw.id, **tgw.model_dump(), node_type="transit_gateway")
            for vpc_id in tgw.attached_vpc_ids:
                self.graph.add_edge(vpc_id, tgw.id, edge_type="attached_to",
                                    confidence=0.95, source=EdgeSource.API.value)
                self.graph.add_edge(tgw.id, vpc_id, edge_type="attached_to",
                                    confidence=0.95, source=EdgeSource.API.value)

        # Load VPN Tunnels
        for vpn in self.store.list_vpn_tunnels():
            self.graph.add_node(vpn.id, **vpn.model_dump(), node_type="vpn_tunnel")
            if vpn.local_gateway_id:
                self.graph.add_edge(vpn.local_gateway_id, vpn.id, edge_type="tunnel_to",
                                    confidence=0.9, source=EdgeSource.API.value)
                self.graph.add_edge(vpn.id, vpn.local_gateway_id, edge_type="tunnel_to",
                                    confidence=0.9, source=EdgeSource.API.value)

        # Load Direct Connects
        for dx in self.store.list_direct_connects():
            self.graph.add_node(dx.id, **dx.model_dump(), node_type="direct_connect")

        # Load NACLs
        for nacl in self.store.list_nacls():
            self.graph.add_node(nacl.id, **nacl.model_dump(), node_type="nacl")
            for sid in nacl.subnet_ids:
                self.graph.add_edge(nacl.id, sid, edge_type="nacl_guards",
                                    confidence=1.0, source=EdgeSource.API.value)

        # Load Load Balancers
        for lb in self.store.list_load_balancers():
            self.graph.add_node(lb.id, **lb.model_dump(), node_type="load_balancer")
            for tg in self.store.list_lb_target_groups(lb_id=lb.id):
                for target_id in tg.target_ids:
                    self.graph.add_edge(lb.id, target_id, edge_type="load_balances",
                                        confidence=0.9, source=EdgeSource.API.value,
                                        port=tg.port, protocol=tg.protocol)

        # Load VLANs
        for vlan in self.store.list_vlans():
            self.graph.add_node(vlan.id, **vlan.model_dump(), node_type="vlan")

        # Load MPLS Circuits
        for mpls in self.store.list_mpls_circuits():
            self.graph.add_node(mpls.id, **mpls.model_dump(), node_type="mpls")
            # Connect endpoints
            endpoints = mpls.endpoints
            for i in range(len(endpoints) - 1):
                self.graph.add_edge(endpoints[i], endpoints[i + 1],
                                    edge_type="mpls_path", confidence=0.95,
                                    source=EdgeSource.API.value, label=mpls.label)

        # Load Compliance Zones
        for cz in self.store.list_compliance_zones():
            self.graph.add_node(cz.id, **cz.model_dump(), node_type="compliance_zone")

    def add_device(self, device: Device) -> None:
        self.store.add_device(device)
        self.graph.add_node(device.id, **device.model_dump(), node_type="device")
        if device.management_ip:
            self._device_index[device.management_ip] = device.id

    def add_subnet(self, subnet: Subnet) -> None:
        self.store.add_subnet(subnet)
        self.graph.add_node(subnet.id, **subnet.model_dump(), node_type="subnet")
        # Rebuild resolver
        subnets = self.store.list_subnets()
        self.ip_resolver.load_subnets([s.model_dump() for s in subnets])

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
            "device": device.model_dump() if device else None,
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
        """Boost confidence on a verified edge."""
        if self.graph.has_edge(src_id, dst_id):
            for key in self.graph[src_id][dst_id]:
                current = self.graph[src_id][dst_id][key].get("confidence", 0.5)
                new_conf = min(1.0, current + boost)
                self.graph[src_id][dst_id][key]["confidence"] = new_conf
                self.graph[src_id][dst_id][key]["last_verified_at"] = \
                    datetime.now(timezone.utc).isoformat()

    @property
    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self.graph.number_of_edges()

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
        }

        for i, (node_id, data) in enumerate(self.graph.nodes(data=True)):
            ntype = data.get("node_type", "device")
            rf_type = node_type_map.get(ntype, "device")
            rf_nodes.append({
                "id": node_id,
                "type": rf_type,
                "position": {"x": (i % 6) * ROW_WIDTH, "y": (i // 6) * COL_HEIGHT},
                "data": {
                    "label": data.get("name", node_id),
                    "entityId": node_id,
                    "deviceType": data.get("device_type", "HOST"),
                    "ip": data.get("management_ip") or data.get("cidr", ""),
                },
            })

        for u, v, edata in self.graph.edges(data=True):
            rf_edges.append({
                "id": f"e-{u}-{v}-{edata.get('edge_type', 'default')}",
                "source": u,
                "target": v,
                "label": edata.get("edge_type", ""),
                "animated": edata.get("confidence", 0) < 0.8,
            })

        return {"nodes": rf_nodes, "edges": rf_edges}
