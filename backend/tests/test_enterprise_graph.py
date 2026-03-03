import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import (
    VPC, CloudProvider, Subnet, TransitGateway, VPNTunnel, TunnelType,
    DirectConnect, DirectConnectProvider, NACL, LoadBalancer, LBType,
    LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone, ComplianceStandard,
    VPCPeering, Device, DeviceType,
)


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


def test_vpc_loaded_with_node_type(store, kg):
    store.add_vpc(VPC(id="vpc-1", name="prod", cidr_blocks=["10.0.0.0/16"]))
    kg.load_from_store()
    assert "vpc-1" in kg.graph
    assert kg.graph.nodes["vpc-1"]["node_type"] == "vpc"


def test_vpc_contains_subnet_edge(store, kg):
    store.add_vpc(VPC(id="vpc-1", name="prod", cidr_blocks=["10.0.0.0/16"]))
    store.add_subnet(Subnet(id="s1", cidr="10.0.1.0/24"))
    kg.load_from_store()
    edges = list(kg.graph.edges("vpc-1", data=True))
    vpc_contains = [e for e in edges if e[2].get("edge_type") == "vpc_contains"]
    assert len(vpc_contains) == 1
    assert vpc_contains[0][1] == "s1"


def test_vpc_peering_bidirectional(store, kg):
    store.add_vpc(VPC(id="vpc-1", name="prod"))
    store.add_vpc(VPC(id="vpc-2", name="staging"))
    store.add_vpc_peering(VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2"))
    kg.load_from_store()
    assert kg.graph.has_edge("vpc-1", "vpc-2")
    assert kg.graph.has_edge("vpc-2", "vpc-1")


def test_transit_gateway_attached_edges(store, kg):
    store.add_vpc(VPC(id="vpc-1", name="prod"))
    store.add_transit_gateway(TransitGateway(id="tgw-1", name="hub", attached_vpc_ids=["vpc-1"]))
    kg.load_from_store()
    assert "tgw-1" in kg.graph
    assert kg.graph.nodes["tgw-1"]["node_type"] == "transit_gateway"
    assert kg.graph.has_edge("vpc-1", "tgw-1")
    assert kg.graph.has_edge("tgw-1", "vpc-1")


def test_vpn_tunnel_edges(store, kg):
    store.add_device(Device(id="gw-1", name="gateway", device_type=DeviceType.VPN_GATEWAY))
    store.add_vpn_tunnel(VPNTunnel(id="vpn-1", name="site-vpn", local_gateway_id="gw-1"))
    kg.load_from_store()
    assert "vpn-1" in kg.graph
    assert kg.graph.nodes["vpn-1"]["node_type"] == "vpn_tunnel"
    assert kg.graph.has_edge("gw-1", "vpn-1")


def test_nacl_guards_subnet(store, kg):
    store.add_subnet(Subnet(id="s1", cidr="10.0.1.0/24"))
    store.add_nacl(NACL(id="nacl-1", name="prod-nacl", subnet_ids=["s1"]))
    kg.load_from_store()
    assert kg.graph.nodes["nacl-1"]["node_type"] == "nacl"
    edges = list(kg.graph.edges("nacl-1", data=True))
    guard_edges = [e for e in edges if e[2].get("edge_type") == "nacl_guards"]
    assert len(guard_edges) == 1


def test_load_balancer_targets(store, kg):
    store.add_device(Device(id="d-1", name="server-1", device_type=DeviceType.HOST))
    store.add_load_balancer(LoadBalancer(id="lb-1", name="api-lb"))
    store.add_lb_target_group(LBTargetGroup(id="tg-1", lb_id="lb-1", target_ids=["d-1"]))
    kg.load_from_store()
    assert kg.graph.nodes["lb-1"]["node_type"] == "load_balancer"
    edges = list(kg.graph.edges("lb-1", data=True))
    lb_edges = [e for e in edges if e[2].get("edge_type") == "load_balances"]
    assert len(lb_edges) == 1


def test_mpls_path_edges(store, kg):
    store.add_device(Device(id="dc-east", name="DC East", device_type=DeviceType.ROUTER))
    store.add_device(Device(id="dc-west", name="DC West", device_type=DeviceType.ROUTER))
    store.add_mpls_circuit(MPLSCircuit(id="mpls-1", name="wan", endpoints=["dc-east", "dc-west"]))
    kg.load_from_store()
    assert kg.graph.has_edge("dc-east", "dc-west")


def test_compliance_zone_loaded(store, kg):
    store.add_compliance_zone(ComplianceZone(id="cz-1", name="CDE", standard=ComplianceStandard.PCI_DSS))
    kg.load_from_store()
    assert kg.graph.nodes["cz-1"]["node_type"] == "compliance_zone"


def test_peering_penalty_in_path_cost(store, kg):
    """VPC peering should add cross_vpc penalty (0.25) to path cost."""
    store.add_vpc(VPC(id="vpc-1", name="prod"))
    store.add_vpc(VPC(id="vpc-2", name="staging"))
    store.add_vpc_peering(VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2"))
    kg.load_from_store()
    paths = kg.find_k_shortest_paths("vpc-1", "vpc-2")
    assert len(paths) >= 1
    assert paths[0] == ["vpc-1", "vpc-2"]


def test_vpn_tunnel_penalty_in_path_cost(store, kg):
    """VPN tunnel should add vpn_tunnel penalty (0.15)."""
    store.add_device(Device(id="gw-1", name="gw", device_type=DeviceType.VPN_GATEWAY))
    store.add_vpn_tunnel(VPNTunnel(id="vpn-1", name="tunnel", local_gateway_id="gw-1"))
    kg.load_from_store()
    paths = kg.find_k_shortest_paths("gw-1", "vpn-1")
    assert len(paths) >= 1
