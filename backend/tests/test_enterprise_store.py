import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import (
    VPC, CloudProvider, VPCPeering, TransitGateway, RouteTable,
    VPNTunnel, TunnelType, DirectConnect, DirectConnectProvider,
    NACL, NACLRule, NACLDirection, PolicyAction,
    LoadBalancer, LBType, LBScheme, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone, ComplianceStandard,
)


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=str(tmp_path / "test.db"))


def test_vpc_crud(store):
    vpc = VPC(id="vpc-1", name="prod", cloud_provider=CloudProvider.AWS,
              cidr_blocks=["10.0.0.0/16"])
    store.add_vpc(vpc)
    result = store.get_vpc("vpc-1")
    assert result.name == "prod"
    assert result.cidr_blocks == ["10.0.0.0/16"]
    all_vpcs = store.list_vpcs()
    assert len(all_vpcs) == 1


def test_transit_gateway_crud(store):
    tgw = TransitGateway(id="tgw-1", name="hub", attached_vpc_ids=["vpc-1", "vpc-2"])
    store.add_transit_gateway(tgw)
    result = store.list_transit_gateways()
    assert len(result) == 1
    assert result[0].attached_vpc_ids == ["vpc-1", "vpc-2"]


def test_vpn_tunnel_crud(store):
    vpn = VPNTunnel(id="vpn-1", name="site-vpn", tunnel_type=TunnelType.IPSEC,
                    local_cidrs=["10.0.0.0/16"], remote_cidrs=["172.16.0.0/12"])
    store.add_vpn_tunnel(vpn)
    result = store.list_vpn_tunnels()
    assert len(result) == 1
    assert result[0].local_cidrs == ["10.0.0.0/16"]


def test_direct_connect_crud(store):
    dx = DirectConnect(id="dx-1", name="prod-dx", provider=DirectConnectProvider.AWS_DX,
                       bandwidth_mbps=10000)
    store.add_direct_connect(dx)
    result = store.list_direct_connects()
    assert result[0].bandwidth_mbps == 10000


def test_nacl_and_rules_crud(store):
    nacl = NACL(id="nacl-1", name="prod-nacl", vpc_id="vpc-1", subnet_ids=["s1"])
    store.add_nacl(nacl)
    r1 = NACLRule(id="nr-1", nacl_id="nacl-1", rule_number=100,
                  direction=NACLDirection.INBOUND, action=PolicyAction.ALLOW,
                  cidr="10.0.0.0/16", port_range_from=443, port_range_to=443)
    r2 = NACLRule(id="nr-2", nacl_id="nacl-1", rule_number=200,
                  direction=NACLDirection.INBOUND, action=PolicyAction.DENY)
    store.add_nacl_rule(r1)
    store.add_nacl_rule(r2)
    rules = store.list_nacl_rules("nacl-1")
    assert len(rules) == 2
    assert rules[0].rule_number == 100  # Ordered


def test_load_balancer_crud(store):
    lb = LoadBalancer(id="lb-1", name="api-lb", lb_type=LBType.ALB,
                      listeners=[{"port": 443, "protocol": "https"}])
    store.add_load_balancer(lb)
    tg = LBTargetGroup(id="tg-1", lb_id="lb-1", port=8080, target_ids=["d-1", "d-2"])
    store.add_lb_target_group(tg)
    lbs = store.list_load_balancers()
    assert lbs[0].listeners[0]["port"] == 443
    tgs = store.list_lb_target_groups(lb_id="lb-1")
    assert len(tgs[0].target_ids) == 2


def test_vlan_crud(store):
    vlan = VLAN(id="vlan-100", vlan_number=100, name="mgmt", trunk_ports=["ge-0/0/1"])
    store.add_vlan(vlan)
    result = store.list_vlans()
    assert result[0].vlan_number == 100


def test_mpls_crud(store):
    mpls = MPLSCircuit(id="mpls-1", name="wan", label=1000,
                       endpoints=["dc-east", "dc-west"])
    store.add_mpls_circuit(mpls)
    result = store.list_mpls_circuits()
    assert result[0].endpoints == ["dc-east", "dc-west"]


def test_compliance_zone_crud(store):
    cz = ComplianceZone(id="cz-1", name="CDE", standard=ComplianceStandard.PCI_DSS,
                        subnet_ids=["s1", "s2"], vpc_ids=["vpc-1"])
    store.add_compliance_zone(cz)
    result = store.list_compliance_zones()
    assert result[0].standard == ComplianceStandard.PCI_DSS
    assert len(result[0].subnet_ids) == 2


def test_vpc_peering_crud(store):
    p = VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2",
                   cidr_routes=["10.0.0.0/16"])
    store.add_vpc_peering(p)
    result = store.list_vpc_peerings()
    assert result[0].cidr_routes == ["10.0.0.0/16"]


def test_route_table_crud(store):
    rt = RouteTable(id="rt-1", vpc_id="vpc-1", name="main", is_main=True)
    store.add_route_table(rt)
    result = store.list_route_tables(vpc_id="vpc-1")
    assert result[0].is_main is True
