"""Tests for enterprise hybrid network entity models."""
import pytest
from src.network.models import (
    # New enums
    CloudProvider,
    TunnelType,
    DirectConnectProvider,
    LBType,
    LBScheme,
    ComplianceStandard,
    NACLDirection,
    ConnectivityStatus,
    # Extended enum
    DeviceType,
    # Existing enum used by NACLRule
    PolicyAction,
    # New models
    VPC,
    RouteTable,
    VPCPeering,
    TransitGateway,
    VPNTunnel,
    DirectConnect,
    NACL,
    NACLRule,
    LoadBalancer,
    LBTargetGroup,
    VLAN,
    MPLSCircuit,
    ComplianceZone,
)


# ── Enum Tests ──


class TestCloudProvider:
    def test_values(self):
        assert CloudProvider.AWS == "aws"
        assert CloudProvider.AZURE == "azure"
        assert CloudProvider.GCP == "gcp"
        assert CloudProvider.OCI == "oci"

    def test_member_count(self):
        assert len(CloudProvider) == 4


class TestTunnelType:
    def test_values(self):
        assert TunnelType.IPSEC == "ipsec"
        assert TunnelType.GRE == "gre"
        assert TunnelType.SSL == "ssl"

    def test_member_count(self):
        assert len(TunnelType) == 3


class TestDirectConnectProvider:
    def test_values(self):
        assert DirectConnectProvider.AWS_DX == "aws_dx"
        assert DirectConnectProvider.AZURE_ER == "azure_er"
        assert DirectConnectProvider.OCI_FC == "oci_fc"

    def test_member_count(self):
        assert len(DirectConnectProvider) == 3


class TestLBType:
    def test_values(self):
        assert LBType.ALB == "alb"
        assert LBType.NLB == "nlb"
        assert LBType.AZURE_LB == "azure_lb"
        assert LBType.HAPROXY == "haproxy"

    def test_member_count(self):
        assert len(LBType) == 4


class TestLBScheme:
    def test_values(self):
        assert LBScheme.INTERNET_FACING == "internet_facing"
        assert LBScheme.INTERNAL == "internal"

    def test_member_count(self):
        assert len(LBScheme) == 2


class TestComplianceStandard:
    def test_values(self):
        assert ComplianceStandard.PCI_DSS == "pci_dss"
        assert ComplianceStandard.SOC2 == "soc2"
        assert ComplianceStandard.HIPAA == "hipaa"
        assert ComplianceStandard.CUSTOM == "custom"

    def test_member_count(self):
        assert len(ComplianceStandard) == 4


class TestNACLDirection:
    def test_values(self):
        assert NACLDirection.INBOUND == "inbound"
        assert NACLDirection.OUTBOUND == "outbound"

    def test_member_count(self):
        assert len(NACLDirection) == 2


class TestConnectivityStatus:
    def test_values(self):
        assert ConnectivityStatus.UP == "up"
        assert ConnectivityStatus.DOWN == "down"
        assert ConnectivityStatus.DEGRADED == "degraded"

    def test_member_count(self):
        assert len(ConnectivityStatus) == 3


class TestDeviceTypeExtensions:
    """Verify the new members added to DeviceType."""

    def test_new_members_exist(self):
        assert DeviceType.VPC == "vpc"
        assert DeviceType.TRANSIT_GATEWAY == "transit_gateway"
        assert DeviceType.LOAD_BALANCER == "load_balancer"
        assert DeviceType.VPN_GATEWAY == "vpn_gateway"
        assert DeviceType.DIRECT_CONNECT == "direct_connect"
        assert DeviceType.NACL == "nacl"

    def test_original_members_intact(self):
        assert DeviceType.ROUTER == "router"
        assert DeviceType.SWITCH == "switch"
        assert DeviceType.FIREWALL == "firewall"
        assert DeviceType.PROXY == "proxy"
        assert DeviceType.GATEWAY == "gateway"
        assert DeviceType.HOST == "host"

    def test_total_member_count(self):
        assert len(DeviceType) == 12


# ── Model Tests ──


class TestVPC:
    def test_minimal(self):
        vpc = VPC(id="vpc-1", name="prod-vpc")
        assert vpc.id == "vpc-1"
        assert vpc.name == "prod-vpc"

    def test_defaults(self):
        vpc = VPC(id="vpc-1", name="prod-vpc")
        assert vpc.cloud_provider == CloudProvider.AWS
        assert vpc.region == ""
        assert vpc.cidr_blocks == []
        assert vpc.account_id == ""
        assert vpc.compliance_zone == ""

    def test_full(self):
        vpc = VPC(
            id="vpc-1",
            name="prod-vpc",
            cloud_provider=CloudProvider.AZURE,
            region="eastus",
            cidr_blocks=["10.0.0.0/16", "10.1.0.0/16"],
            account_id="acc-123",
            compliance_zone="pci",
        )
        assert vpc.cloud_provider == CloudProvider.AZURE
        assert vpc.region == "eastus"
        assert len(vpc.cidr_blocks) == 2
        assert vpc.account_id == "acc-123"
        assert vpc.compliance_zone == "pci"

    def test_cidr_blocks_list_independence(self):
        """Each instance should get its own list."""
        v1 = VPC(id="v1", name="a")
        v2 = VPC(id="v2", name="b")
        v1.cidr_blocks.append("10.0.0.0/16")
        assert v2.cidr_blocks == []


class TestRouteTable:
    def test_minimal(self):
        rt = RouteTable(id="rt-1", vpc_id="vpc-1")
        assert rt.id == "rt-1"
        assert rt.vpc_id == "vpc-1"

    def test_defaults(self):
        rt = RouteTable(id="rt-1", vpc_id="vpc-1")
        assert rt.name == ""
        assert rt.is_main is False

    def test_main_route_table(self):
        rt = RouteTable(id="rt-1", vpc_id="vpc-1", is_main=True, name="main")
        assert rt.is_main is True
        assert rt.name == "main"


class TestVPCPeering:
    def test_minimal(self):
        p = VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2")
        assert p.id == "pcx-1"
        assert p.requester_vpc_id == "vpc-1"
        assert p.accepter_vpc_id == "vpc-2"

    def test_defaults(self):
        p = VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2")
        assert p.status == "active"
        assert p.cidr_routes == []

    def test_with_cidr_routes(self):
        p = VPCPeering(
            id="pcx-1",
            requester_vpc_id="vpc-1",
            accepter_vpc_id="vpc-2",
            cidr_routes=["10.0.0.0/16", "10.1.0.0/16"],
        )
        assert len(p.cidr_routes) == 2


class TestTransitGateway:
    def test_minimal(self):
        tgw = TransitGateway(id="tgw-1", name="central-tgw")
        assert tgw.id == "tgw-1"
        assert tgw.name == "central-tgw"

    def test_defaults(self):
        tgw = TransitGateway(id="tgw-1", name="central-tgw")
        assert tgw.cloud_provider == CloudProvider.AWS
        assert tgw.region == ""
        assert tgw.attached_vpc_ids == []
        assert tgw.route_table_id == ""

    def test_full(self):
        tgw = TransitGateway(
            id="tgw-1",
            name="central-tgw",
            cloud_provider=CloudProvider.GCP,
            region="us-central1",
            attached_vpc_ids=["vpc-1", "vpc-2", "vpc-3"],
            route_table_id="rt-tgw-1",
        )
        assert tgw.cloud_provider == CloudProvider.GCP
        assert len(tgw.attached_vpc_ids) == 3


class TestVPNTunnel:
    def test_minimal(self):
        vpn = VPNTunnel(id="vpn-1", name="site-to-site")
        assert vpn.id == "vpn-1"
        assert vpn.name == "site-to-site"

    def test_defaults(self):
        vpn = VPNTunnel(id="vpn-1", name="site-to-site")
        assert vpn.tunnel_type == TunnelType.IPSEC
        assert vpn.local_gateway_id == ""
        assert vpn.remote_gateway_ip == ""
        assert vpn.local_cidrs == []
        assert vpn.remote_cidrs == []
        assert vpn.encryption == "AES-256-GCM"
        assert vpn.ike_version == "IKEv2"
        assert vpn.status == ConnectivityStatus.UP

    def test_full(self):
        vpn = VPNTunnel(
            id="vpn-1",
            name="gre-tunnel",
            tunnel_type=TunnelType.GRE,
            local_gateway_id="gw-1",
            remote_gateway_ip="203.0.113.1",
            local_cidrs=["10.0.0.0/16"],
            remote_cidrs=["172.16.0.0/12"],
            encryption="AES-128-CBC",
            ike_version="IKEv1",
            status=ConnectivityStatus.DEGRADED,
        )
        assert vpn.tunnel_type == TunnelType.GRE
        assert vpn.status == ConnectivityStatus.DEGRADED
        assert vpn.remote_gateway_ip == "203.0.113.1"

    def test_down_status(self):
        vpn = VPNTunnel(id="vpn-d", name="down-tunnel", status=ConnectivityStatus.DOWN)
        assert vpn.status == ConnectivityStatus.DOWN


class TestDirectConnect:
    def test_minimal(self):
        dc = DirectConnect(id="dx-1", name="aws-dx-east")
        assert dc.id == "dx-1"
        assert dc.name == "aws-dx-east"

    def test_defaults(self):
        dc = DirectConnect(id="dx-1", name="aws-dx-east")
        assert dc.provider == DirectConnectProvider.AWS_DX
        assert dc.bandwidth_mbps == 1000
        assert dc.location == ""
        assert dc.vlan_id == 0
        assert dc.bgp_asn == 0
        assert dc.status == ConnectivityStatus.UP

    def test_full(self):
        dc = DirectConnect(
            id="er-1",
            name="azure-er-west",
            provider=DirectConnectProvider.AZURE_ER,
            bandwidth_mbps=10000,
            location="Equinix-DC2",
            vlan_id=100,
            bgp_asn=65000,
            status=ConnectivityStatus.UP,
        )
        assert dc.provider == DirectConnectProvider.AZURE_ER
        assert dc.bandwidth_mbps == 10000
        assert dc.vlan_id == 100
        assert dc.bgp_asn == 65000


class TestNACL:
    def test_minimal(self):
        nacl = NACL(id="nacl-1", name="web-tier-nacl")
        assert nacl.id == "nacl-1"
        assert nacl.name == "web-tier-nacl"

    def test_defaults(self):
        nacl = NACL(id="nacl-1", name="web-tier-nacl")
        assert nacl.vpc_id == ""
        assert nacl.subnet_ids == []
        assert nacl.is_default is False

    def test_with_subnets(self):
        nacl = NACL(
            id="nacl-1",
            name="default",
            vpc_id="vpc-1",
            subnet_ids=["sub-1", "sub-2"],
            is_default=True,
        )
        assert nacl.is_default is True
        assert len(nacl.subnet_ids) == 2

    def test_subnet_list_independence(self):
        n1 = NACL(id="n1", name="a")
        n2 = NACL(id="n2", name="b")
        n1.subnet_ids.append("sub-x")
        assert n2.subnet_ids == []


class TestNACLRule:
    def test_minimal(self):
        rule = NACLRule(id="nr-1", nacl_id="nacl-1")
        assert rule.id == "nr-1"
        assert rule.nacl_id == "nacl-1"

    def test_defaults(self):
        rule = NACLRule(id="nr-1", nacl_id="nacl-1")
        assert rule.direction == NACLDirection.INBOUND
        assert rule.rule_number == 100
        assert rule.protocol == "tcp"
        assert rule.cidr == "0.0.0.0/0"
        assert rule.port_range_from == 0
        assert rule.port_range_to == 65535
        assert rule.action == PolicyAction.ALLOW

    def test_deny_rule(self):
        rule = NACLRule(
            id="nr-2",
            nacl_id="nacl-1",
            direction=NACLDirection.OUTBOUND,
            rule_number=200,
            protocol="udp",
            cidr="192.168.0.0/16",
            port_range_from=443,
            port_range_to=443,
            action=PolicyAction.DENY,
        )
        assert rule.direction == NACLDirection.OUTBOUND
        assert rule.rule_number == 200
        assert rule.protocol == "udp"
        assert rule.cidr == "192.168.0.0/16"
        assert rule.port_range_from == 443
        assert rule.port_range_to == 443
        assert rule.action == PolicyAction.DENY


class TestLoadBalancer:
    def test_minimal(self):
        lb = LoadBalancer(id="lb-1", name="web-alb")
        assert lb.id == "lb-1"
        assert lb.name == "web-alb"

    def test_defaults(self):
        lb = LoadBalancer(id="lb-1", name="web-alb")
        assert lb.lb_type == LBType.ALB
        assert lb.scheme == LBScheme.INTERNAL
        assert lb.vpc_id == ""
        assert lb.listeners == []
        assert lb.health_check_path == "/health"

    def test_full(self):
        lb = LoadBalancer(
            id="lb-2",
            name="api-nlb",
            lb_type=LBType.NLB,
            scheme=LBScheme.INTERNET_FACING,
            vpc_id="vpc-1",
            listeners=[{"port": 443, "protocol": "TLS"}],
            health_check_path="/api/health",
        )
        assert lb.lb_type == LBType.NLB
        assert lb.scheme == LBScheme.INTERNET_FACING
        assert len(lb.listeners) == 1
        assert lb.listeners[0]["port"] == 443

    def test_listeners_list_independence(self):
        lb1 = LoadBalancer(id="lb1", name="a")
        lb2 = LoadBalancer(id="lb2", name="b")
        lb1.listeners.append({"port": 80})
        assert lb2.listeners == []


class TestLBTargetGroup:
    def test_minimal(self):
        tg = LBTargetGroup(id="tg-1", lb_id="lb-1")
        assert tg.id == "tg-1"
        assert tg.lb_id == "lb-1"

    def test_defaults(self):
        tg = LBTargetGroup(id="tg-1", lb_id="lb-1")
        assert tg.name == ""
        assert tg.protocol == "tcp"
        assert tg.port == 80
        assert tg.target_ids == []
        assert tg.health_status == "healthy"

    def test_full(self):
        tg = LBTargetGroup(
            id="tg-1",
            lb_id="lb-1",
            name="api-targets",
            protocol="https",
            port=8443,
            target_ids=["i-1", "i-2", "i-3"],
            health_status="unhealthy",
        )
        assert tg.name == "api-targets"
        assert tg.port == 8443
        assert len(tg.target_ids) == 3
        assert tg.health_status == "unhealthy"


class TestVLAN:
    def test_minimal(self):
        vlan = VLAN(id="vlan-1", vlan_number=100)
        assert vlan.id == "vlan-1"
        assert vlan.vlan_number == 100

    def test_defaults(self):
        vlan = VLAN(id="vlan-1", vlan_number=100)
        assert vlan.name == ""
        assert vlan.trunk_ports == []
        assert vlan.access_ports == []
        assert vlan.site == ""

    def test_full(self):
        vlan = VLAN(
            id="vlan-1",
            vlan_number=200,
            name="management",
            trunk_ports=["Gi0/1", "Gi0/2"],
            access_ports=["Fa0/1"],
            site="dc-east",
        )
        assert vlan.vlan_number == 200
        assert len(vlan.trunk_ports) == 2
        assert len(vlan.access_ports) == 1
        assert vlan.site == "dc-east"


class TestMPLSCircuit:
    def test_minimal(self):
        mpls = MPLSCircuit(id="mpls-1", name="wan-core")
        assert mpls.id == "mpls-1"
        assert mpls.name == "wan-core"

    def test_defaults(self):
        mpls = MPLSCircuit(id="mpls-1", name="wan-core")
        assert mpls.label == 0
        assert mpls.provider == ""
        assert mpls.bandwidth_mbps == 100
        assert mpls.endpoints == []
        assert mpls.qos_class == ""

    def test_full(self):
        mpls = MPLSCircuit(
            id="mpls-1",
            name="wan-core",
            label=1024,
            provider="AT&T",
            bandwidth_mbps=10000,
            endpoints=["pe-east", "pe-west"],
            qos_class="EF",
        )
        assert mpls.label == 1024
        assert mpls.provider == "AT&T"
        assert mpls.bandwidth_mbps == 10000
        assert len(mpls.endpoints) == 2
        assert mpls.qos_class == "EF"


class TestComplianceZone:
    def test_minimal(self):
        cz = ComplianceZone(id="cz-1", name="pci-zone")
        assert cz.id == "cz-1"
        assert cz.name == "pci-zone"

    def test_defaults(self):
        cz = ComplianceZone(id="cz-1", name="pci-zone")
        assert cz.standard == ComplianceStandard.PCI_DSS
        assert cz.description == ""
        assert cz.subnet_ids == []
        assert cz.vpc_ids == []

    def test_full(self):
        cz = ComplianceZone(
            id="cz-2",
            name="hipaa-zone",
            standard=ComplianceStandard.HIPAA,
            description="PHI data processing zone",
            subnet_ids=["sub-1", "sub-2"],
            vpc_ids=["vpc-1"],
        )
        assert cz.standard == ComplianceStandard.HIPAA
        assert cz.description == "PHI data processing zone"
        assert len(cz.subnet_ids) == 2
        assert len(cz.vpc_ids) == 1

    def test_list_independence(self):
        cz1 = ComplianceZone(id="cz1", name="a")
        cz2 = ComplianceZone(id="cz2", name="b")
        cz1.subnet_ids.append("sub-x")
        cz1.vpc_ids.append("vpc-x")
        assert cz2.subnet_ids == []
        assert cz2.vpc_ids == []


# ── Serialization round-trip tests ──


class TestModelSerialization:
    def test_vpc_roundtrip(self):
        vpc = VPC(
            id="vpc-1",
            name="prod",
            cloud_provider=CloudProvider.GCP,
            cidr_blocks=["10.0.0.0/8"],
        )
        data = vpc.model_dump()
        restored = VPC(**data)
        assert restored == vpc
        assert restored.cloud_provider == CloudProvider.GCP

    def test_vpn_tunnel_roundtrip(self):
        vpn = VPNTunnel(
            id="vpn-1",
            name="tun",
            tunnel_type=TunnelType.GRE,
            status=ConnectivityStatus.DEGRADED,
        )
        data = vpn.model_dump()
        restored = VPNTunnel(**data)
        assert restored == vpn

    def test_nacl_rule_roundtrip(self):
        rule = NACLRule(
            id="nr-1",
            nacl_id="nacl-1",
            direction=NACLDirection.OUTBOUND,
            action=PolicyAction.DENY,
        )
        data = rule.model_dump()
        restored = NACLRule(**data)
        assert restored == rule

    def test_load_balancer_roundtrip(self):
        lb = LoadBalancer(
            id="lb-1",
            name="web",
            lb_type=LBType.HAPROXY,
            scheme=LBScheme.INTERNET_FACING,
            listeners=[{"port": 80, "protocol": "HTTP"}],
        )
        data = lb.model_dump()
        restored = LoadBalancer(**data)
        assert restored == lb
        assert restored.listeners[0]["port"] == 80

    def test_compliance_zone_json(self):
        cz = ComplianceZone(
            id="cz-1",
            name="soc2",
            standard=ComplianceStandard.SOC2,
        )
        json_str = cz.model_dump_json()
        assert '"soc2"' in json_str


# ── Validation / edge-case tests ──


class TestValidationEdgeCases:
    def test_vpc_missing_required_field_raises(self):
        with pytest.raises(Exception):
            VPC(id="vpc-1")  # missing name

    def test_route_table_missing_vpc_id_raises(self):
        with pytest.raises(Exception):
            RouteTable(id="rt-1")  # missing vpc_id

    def test_vpc_peering_missing_fields_raises(self):
        with pytest.raises(Exception):
            VPCPeering(id="pcx-1")  # missing requester/accepter

    def test_vlan_missing_number_raises(self):
        with pytest.raises(Exception):
            VLAN(id="vlan-1")  # missing vlan_number

    def test_enum_from_string(self):
        """Enums can be constructed from string values."""
        assert CloudProvider("aws") == CloudProvider.AWS
        assert TunnelType("gre") == TunnelType.GRE
        assert ConnectivityStatus("degraded") == ConnectivityStatus.DEGRADED
        assert LBType("haproxy") == LBType.HAPROXY
        assert ComplianceStandard("hipaa") == ComplianceStandard.HIPAA

    def test_invalid_enum_raises(self):
        with pytest.raises(ValueError):
            CloudProvider("digitalocean")
