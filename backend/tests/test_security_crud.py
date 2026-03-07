"""Tests for security & infrastructure resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))

    from src.api.main import app
    from src.api import security_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


# ── Firewall Rule CRUD ────────────────────────────────────────────────


class TestFirewallRuleCRUD:
    def test_create_firewall_rule(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/firewall-rules", json={
            "id": "fwr1",
            "device_id": "fw1",
            "rule_name": "allow-web",
            "src_zone": "inside",
            "dst_zone": "outside",
            "src_ips": ["10.0.0.0/24"],
            "dst_ips": ["0.0.0.0/0"],
            "ports": [80, 443],
            "protocol": "tcp",
            "action": "allow",
            "logged": True,
            "order": 10,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "fwr1"
        assert data["rule_name"] == "allow-web"
        assert data["ports"] == [80, 443]

    def test_list_firewall_rules(self, store_and_client):
        store, client = store_and_client
        from src.network.models import FirewallRule, PolicyAction
        store.add_firewall_rule(FirewallRule(
            id="fwr1", device_id="fw1", rule_name="allow-web",
            action=PolicyAction.ALLOW, ports=[80, 443],
        ))
        resp = client.get("/api/v4/network/security/firewall-rules")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_firewall_rules_filter_by_device(self, store_and_client):
        store, client = store_and_client
        from src.network.models import FirewallRule, PolicyAction
        store.add_firewall_rule(FirewallRule(id="fwr1", device_id="fw1", action=PolicyAction.DENY))
        store.add_device(Device(id="fw2", name="Firewall2", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_firewall_rule(FirewallRule(id="fwr2", device_id="fw2", action=PolicyAction.ALLOW))
        resp = client.get("/api/v4/network/security/firewall-rules?device_id=fw1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "fw1"


# ── NAT Rule CRUD ────────────────────────────────────────────────────


class TestNATRuleCRUD:
    def test_create_nat_rule(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/nat-rules", json={
            "id": "nat1",
            "device_id": "fw1",
            "original_src": "10.0.1.5",
            "translated_src": "203.0.113.10",
            "direction": "snat",
            "description": "Outbound SNAT",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "nat1"
        assert data["direction"] == "snat"

    def test_list_nat_rules(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NATRule
        store.add_nat_rule(NATRule(id="nat1", device_id="fw1"))
        resp = client.get("/api/v4/network/security/nat-rules")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_nat_rules_filter_by_device(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NATRule
        store.add_nat_rule(NATRule(id="nat1", device_id="fw1"))
        store.add_device(Device(id="fw2", name="Firewall2", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_nat_rule(NATRule(id="nat2", device_id="fw2"))
        resp = client.get("/api/v4/network/security/nat-rules?device_id=fw1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "fw1"


# ── NACL CRUD ────────────────────────────────────────────────────────


class TestNACLCRUD:
    def test_create_nacl(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/nacls", json={
            "id": "nacl1",
            "name": "prod-nacl",
            "vpc_id": "vpc1",
            "subnet_ids": ["sub1", "sub2"],
            "is_default": False,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "nacl1"
        assert data["name"] == "prod-nacl"
        assert data["subnet_ids"] == ["sub1", "sub2"]

    def test_list_nacls(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NACL
        store.add_nacl(NACL(id="nacl1", name="prod-nacl", vpc_id="vpc1"))
        resp = client.get("/api/v4/network/security/nacls")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_nacls_filter_by_vpc(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NACL
        store.add_nacl(NACL(id="nacl1", name="prod-nacl", vpc_id="vpc1"))
        store.add_nacl(NACL(id="nacl2", name="dev-nacl", vpc_id="vpc2"))
        resp = client.get("/api/v4/network/security/nacls?vpc_id=vpc1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["vpc_id"] == "vpc1"


# ── NACL Rule CRUD ───────────────────────────────────────────────────


class TestNACLRuleCRUD:
    def test_create_nacl_rule(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NACL
        store.add_nacl(NACL(id="nacl1", name="prod-nacl"))
        resp = client.post("/api/v4/network/security/nacl-rules", json={
            "id": "nr1",
            "nacl_id": "nacl1",
            "direction": "inbound",
            "rule_number": 100,
            "protocol": "tcp",
            "cidr": "10.0.0.0/8",
            "port_range_from": 443,
            "port_range_to": 443,
            "action": "allow",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "nr1"
        assert data["rule_number"] == 100

    def test_list_nacl_rules(self, store_and_client):
        store, client = store_and_client
        from src.network.models import NACL, NACLRule
        store.add_nacl(NACL(id="nacl1", name="prod-nacl"))
        store.add_nacl_rule(NACLRule(id="nr1", nacl_id="nacl1", rule_number=100))
        store.add_nacl_rule(NACLRule(id="nr2", nacl_id="nacl1", rule_number=200))
        resp = client.get("/api/v4/network/security/nacl-rules?nacl_id=nacl1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be ordered by rule_number
        assert data[0]["rule_number"] <= data[1]["rule_number"]

    def test_list_nacl_rules_requires_nacl_id(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/security/nacl-rules")
        assert resp.status_code == 422


# ── Load Balancer CRUD ───────────────────────────────────────────────


class TestLoadBalancerCRUD:
    def test_create_load_balancer(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/load-balancers", json={
            "id": "lb1",
            "name": "prod-alb",
            "lb_type": "alb",
            "scheme": "internet_facing",
            "vpc_id": "vpc1",
            "listeners": [{"port": 443, "protocol": "https"}],
            "health_check_path": "/healthz",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "lb1"
        assert data["lb_type"] == "alb"
        assert data["scheme"] == "internet_facing"

    def test_list_load_balancers(self, store_and_client):
        store, client = store_and_client
        from src.network.models import LoadBalancer
        store.add_load_balancer(LoadBalancer(id="lb1", name="prod-alb"))
        resp = client.get("/api/v4/network/security/load-balancers")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── LB Target Group CRUD ────────────────────────────────────────────


class TestLBTargetGroupCRUD:
    def test_create_lb_target_group(self, store_and_client):
        store, client = store_and_client
        from src.network.models import LoadBalancer
        store.add_load_balancer(LoadBalancer(id="lb1", name="prod-alb"))
        resp = client.post("/api/v4/network/security/lb-target-groups", json={
            "id": "tg1",
            "lb_id": "lb1",
            "name": "web-targets",
            "protocol": "tcp",
            "port": 80,
            "target_ids": ["i-001", "i-002"],
            "health_status": "healthy",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "tg1"
        assert data["target_ids"] == ["i-001", "i-002"]

    def test_list_lb_target_groups(self, store_and_client):
        store, client = store_and_client
        from src.network.models import LoadBalancer, LBTargetGroup
        store.add_load_balancer(LoadBalancer(id="lb1", name="prod-alb"))
        store.add_lb_target_group(LBTargetGroup(id="tg1", lb_id="lb1", name="web"))
        resp = client.get("/api/v4/network/security/lb-target-groups")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_lb_target_groups_filter_by_lb(self, store_and_client):
        store, client = store_and_client
        from src.network.models import LoadBalancer, LBTargetGroup
        store.add_load_balancer(LoadBalancer(id="lb1", name="prod-alb"))
        store.add_load_balancer(LoadBalancer(id="lb2", name="dev-alb"))
        store.add_lb_target_group(LBTargetGroup(id="tg1", lb_id="lb1", name="web"))
        store.add_lb_target_group(LBTargetGroup(id="tg2", lb_id="lb2", name="api"))
        resp = client.get("/api/v4/network/security/lb-target-groups?lb_id=lb1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["lb_id"] == "lb1"


# ── VLAN CRUD ────────────────────────────────────────────────────────


class TestVLANCRUD:
    def test_create_vlan(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/vlans", json={
            "id": "vlan100",
            "vlan_number": 100,
            "name": "Management",
            "trunk_ports": ["Gi0/1", "Gi0/2"],
            "access_ports": ["Fa0/1"],
            "site": "DC-East",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "vlan100"
        assert data["vlan_number"] == 100
        assert data["trunk_ports"] == ["Gi0/1", "Gi0/2"]

    def test_list_vlans(self, store_and_client):
        store, client = store_and_client
        from src.network.models import VLAN
        store.add_vlan(VLAN(id="vlan100", vlan_number=100, name="Mgmt"))
        resp = client.get("/api/v4/network/security/vlans")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── MPLS Circuit CRUD ───────────────────────────────────────────────


class TestMPLSCircuitCRUD:
    def test_create_mpls_circuit(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/mpls-circuits", json={
            "id": "mpls1",
            "name": "NYC-LAX",
            "label": 1001,
            "provider": "AT&T",
            "bandwidth_mbps": 500,
            "endpoints": ["rtr-nyc", "rtr-lax"],
            "qos_class": "EF",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "mpls1"
        assert data["label"] == 1001
        assert data["endpoints"] == ["rtr-nyc", "rtr-lax"]

    def test_list_mpls_circuits(self, store_and_client):
        store, client = store_and_client
        from src.network.models import MPLSCircuit
        store.add_mpls_circuit(MPLSCircuit(id="mpls1", name="NYC-LAX", label=1001))
        resp = client.get("/api/v4/network/security/mpls-circuits")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


# ── Compliance Zone CRUD ─────────────────────────────────────────────


class TestComplianceZoneCRUD:
    def test_create_compliance_zone(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/compliance-zones", json={
            "id": "cz1",
            "name": "PCI Segment",
            "standard": "pci_dss",
            "description": "PCI DSS cardholder data environment",
            "subnet_ids": ["sub1", "sub2"],
            "vpc_ids": ["vpc1"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "cz1"
        assert data["standard"] == "pci_dss"
        assert data["subnet_ids"] == ["sub1", "sub2"]

    def test_list_compliance_zones(self, store_and_client):
        store, client = store_and_client
        from src.network.models import ComplianceZone
        store.add_compliance_zone(ComplianceZone(id="cz1", name="PCI Segment"))
        resp = client.get("/api/v4/network/security/compliance-zones")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
