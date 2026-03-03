"""Tests for network data models and topology store."""
import os
import tempfile
import pytest
from src.network.models import (
    Device, DeviceType, Interface, Subnet, Zone, Workload,
    Route, NATRule, NATDirection, FirewallRule, PolicyAction,
    Flow, DiagnosisStatus, Trace, TraceMethod, TraceHop, HopStatus,
    FlowVerdict, VerdictMatchType,
    EdgeMetadata, EdgeSource,
    AdapterHealth, AdapterHealthStatus, FirewallVendor,
    PolicyVerdict, AdapterConfig, IdentityStage,
    NetworkDiagnosticState,
)
from src.network.topology_store import TopologyStore


class TestModels:
    def test_device_defaults(self):
        d = Device(id="r1", name="Router1")
        assert d.device_type == DeviceType.HOST
        assert d.vendor == ""

    def test_device_type_enum(self):
        d = Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL)
        assert d.device_type.value == "firewall"

    def test_interface_model(self):
        i = Interface(id="eth0", device_id="r1", ip="10.0.0.1")
        assert i.status == "up"
        assert i.vrf == ""

    def test_subnet_model(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1")
        assert s.vlan_id == 0

    def test_zone_model(self):
        z = Zone(id="z1", name="trust", security_level=100)
        assert z.firewall_id == ""

    def test_workload_ips_list(self):
        w = Workload(id="w1", name="api", ips=["10.0.1.1", "10.0.1.2"])
        assert len(w.ips) == 2

    def test_route_defaults(self):
        r = Route(id="rt1", device_id="r1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1")
        assert r.protocol == "static"
        assert r.metric == 0

    def test_nat_rule_direction(self):
        n = NATRule(id="nat1", device_id="fw1", direction=NATDirection.DNAT)
        assert n.direction.value == "dnat"

    def test_firewall_rule_lists(self):
        fr = FirewallRule(
            id="fr1", device_id="fw1",
            src_ips=["10.0.0.0/8"], dst_ips=["172.16.0.0/12"],
            ports=[443, 8443], action=PolicyAction.ALLOW,
        )
        assert len(fr.ports) == 2
        assert fr.action == PolicyAction.ALLOW

    def test_flow_defaults(self):
        f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443)
        assert f.diagnosis_status == DiagnosisStatus.RUNNING
        assert f.confidence == 0.0

    def test_trace_hop_optional_device(self):
        h = TraceHop(id="h1", trace_id="t1", hop_number=1, ip="10.0.0.1")
        assert h.device_id is None
        assert h.status == HopStatus.RESPONDED

    def test_edge_metadata_defaults(self):
        e = EdgeMetadata()
        assert e.confidence == 0.5
        assert e.source == EdgeSource.MANUAL

    def test_adapter_health(self):
        ah = AdapterHealth(vendor=FirewallVendor.PALO_ALTO, status=AdapterHealthStatus.CONNECTED)
        assert ah.snapshot_age_seconds == 0.0

    def test_identity_stage(self):
        s = IdentityStage(stage="original", ip="10.0.0.1", port=443)
        assert s.device_id is None

    def test_network_diagnostic_state_defaults(self):
        state = NetworkDiagnosticState()
        assert state.resolution_status == "pending"
        assert state.diagnosis_status == "running"
        assert state.routing_loop_detected is False
        assert state.ambiguous_candidates == []

    def test_verdict_match_type_values(self):
        assert VerdictMatchType.EXACT.value == "exact"
        assert VerdictMatchType.IMPLICIT_DENY.value == "implicit_deny"
        assert VerdictMatchType.SHADOWED.value == "shadowed"

    def test_policy_verdict(self):
        pv = PolicyVerdict(action=PolicyAction.ALLOW, confidence=0.95, match_type=VerdictMatchType.EXACT)
        assert pv.rule_id == ""


class TestTopologyStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "test_network.db")
        return TopologyStore(db_path=db_path)

    def test_device_crud(self, store):
        d = Device(id="r1", name="Router1", device_type=DeviceType.ROUTER)
        store.add_device(d)
        fetched = store.get_device("r1")
        assert fetched is not None
        assert fetched.name == "Router1"
        assert fetched.device_type == DeviceType.ROUTER

        devices = store.list_devices()
        assert len(devices) == 1

        store.delete_device("r1")
        assert store.get_device("r1") is None

    def test_device_upsert(self, store):
        d1 = Device(id="r1", name="Router1")
        store.add_device(d1)
        d2 = Device(id="r1", name="Router1-Updated")
        store.add_device(d2)
        fetched = store.get_device("r1")
        assert fetched.name == "Router1-Updated"

    def test_subnet_crud(self, store):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1")
        store.add_subnet(s)
        subnets = store.list_subnets()
        assert len(subnets) == 1
        assert subnets[0].cidr == "10.0.0.0/24"

    def test_interface_crud(self, store):
        store.add_device(Device(id="r1", name="Router1"))
        iface = Interface(id="eth0", device_id="r1", ip="10.0.0.1")
        store.add_interface(iface)
        interfaces = store.list_interfaces(device_id="r1")
        assert len(interfaces) == 1
        found = store.find_interface_by_ip("10.0.0.1")
        assert found is not None
        assert found.device_id == "r1"

    def test_zone_crud(self, store):
        z = Zone(id="z1", name="trust", security_level=100)
        store.add_zone(z)
        zones = store.list_zones()
        assert len(zones) == 1

    def test_route_crud(self, store):
        store.add_device(Device(id="r1", name="Router1"))
        r = Route(id="rt1", device_id="r1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1")
        store.add_route(r)
        routes = store.list_routes(device_id="r1")
        assert len(routes) == 1

    def test_bulk_routes(self, store):
        store.add_device(Device(id="r1", name="Router1"))
        routes = [
            Route(id=f"rt{i}", device_id="r1", destination_cidr=f"10.{i}.0.0/16", next_hop="10.0.0.1")
            for i in range(100)
        ]
        store.bulk_add_routes(routes)
        fetched = store.list_routes(device_id="r1")
        assert len(fetched) == 100

    def test_nat_rule_crud(self, store):
        store.add_device(Device(id="fw1", name="Firewall1"))
        nr = NATRule(id="nat1", device_id="fw1", original_src="10.0.0.0/24",
                     translated_src="203.0.113.1", direction=NATDirection.SNAT)
        store.add_nat_rule(nr)
        rules = store.list_nat_rules(device_id="fw1")
        assert len(rules) == 1
        assert rules[0].direction == NATDirection.SNAT

    def test_firewall_rule_json_lists(self, store):
        store.add_device(Device(id="fw1", name="Firewall1"))
        fr = FirewallRule(
            id="fr1", device_id="fw1", rule_name="allow-web",
            src_ips=["10.0.0.0/8"], dst_ips=["172.16.0.0/12"],
            ports=[80, 443], action=PolicyAction.ALLOW, logged=True, order=1,
        )
        store.add_firewall_rule(fr)
        rules = store.list_firewall_rules(device_id="fw1")
        assert len(rules) == 1
        assert rules[0].src_ips == ["10.0.0.0/8"]
        assert rules[0].ports == [80, 443]
        assert rules[0].logged is True

    def test_workload_crud(self, store):
        wl = Workload(id="w1", name="api-server", ips=["10.0.1.1", "10.0.1.2"])
        store.add_workload(wl)
        workloads = store.list_workloads()
        assert len(workloads) == 1
        assert workloads[0].ips == ["10.0.1.1", "10.0.1.2"]

    def test_flow_crud(self, store):
        f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443, session_id="sess1")
        store.add_flow(f)
        fetched = store.get_flow("f1")
        assert fetched is not None
        assert fetched.diagnosis_status == DiagnosisStatus.RUNNING

        store.update_flow_status("f1", "complete", 0.95)
        updated = store.get_flow("f1")
        assert updated.diagnosis_status == DiagnosisStatus.COMPLETE
        assert updated.confidence == 0.95

    def test_find_recent_flow(self, store):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443,
                 timestamp=now)
        store.add_flow(f)
        found = store.find_recent_flow("10.0.0.1", "10.0.1.1", 443)
        assert found is not None
        assert found.id == "f1"

        not_found = store.find_recent_flow("10.0.0.1", "10.0.1.1", 8080)
        assert not_found is None

        # Old flow should not be found within 60s window
        old = Flow(id="f2", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=8080,
                   timestamp="2020-01-01T00:00:00+00:00")
        store.add_flow(old)
        not_recent = store.find_recent_flow("10.0.0.1", "10.0.1.1", 8080)
        assert not_recent is None

    def test_trace_and_hops(self, store):
        store.add_flow(Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443))
        t = Trace(id="t1", flow_id="f1", src="10.0.0.1", dst="10.0.1.1",
                  method=TraceMethod.ICMP, hop_count=3)
        store.add_trace(t)
        h1 = TraceHop(id="h1", trace_id="t1", hop_number=1, ip="10.0.0.1", rtt_ms=1.2)
        h2 = TraceHop(id="h2", trace_id="t1", hop_number=2, ip="10.0.0.254", rtt_ms=2.5)
        store.add_trace_hop(h1)
        store.add_trace_hop(h2)

    def test_flow_verdict_crud(self, store):
        store.add_flow(Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443))
        v = FlowVerdict(id="v1", flow_id="f1", firewall_id="fw1",
                        action=PolicyAction.ALLOW, confidence=0.95,
                        match_type=VerdictMatchType.EXACT)
        store.add_flow_verdict(v)

    def test_adapter_config_crud(self, store):
        cfg = AdapterConfig(vendor=FirewallVendor.PALO_ALTO,
                           api_endpoint="https://panorama.example.com",
                           api_key="secret123",
                           extra_config={"vsys": "vsys1"})
        store.save_adapter_config(cfg)
        fetched = store.get_adapter_config("palo_alto")
        assert fetched is not None
        assert fetched.api_endpoint == "https://panorama.example.com"
        assert fetched.extra_config["vsys"] == "vsys1"

    def test_diagram_snapshot(self, store):
        snap_id = store.save_diagram_snapshot('{"nodes": []}', "initial")
        assert snap_id is not None
        assert snap_id > 0


def test_device_has_zone_vlan_description():
    from src.network.models import Device, DeviceType
    d = Device(
        id="d1", name="fw-01", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", zone_id="pci", vlan_id=100,
        description="PCI firewall",
    )
    assert d.zone_id == "pci"
    assert d.vlan_id == 100
    assert d.description == "PCI firewall"


def test_device_store_roundtrip(tmp_path):
    import os
    from src.network.topology_store import TopologyStore
    from src.network.models import Device, DeviceType
    store = TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))
    d = Device(
        id="d1", name="fw-01", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", zone_id="pci", vlan_id=100,
        description="PCI firewall",
    )
    store.add_device(d)
    loaded = store.get_device("d1")
    assert loaded is not None
    assert loaded.zone_id == "pci"
    assert loaded.vlan_id == 100
    assert loaded.description == "PCI firewall"

    # Also verify list_devices returns the enriched fields
    all_devices = store.list_devices()
    assert len(all_devices) == 1
    assert all_devices[0].zone_id == "pci"
    assert all_devices[0].vlan_id == 100
    assert all_devices[0].description == "PCI firewall"
