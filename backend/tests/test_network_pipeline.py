"""Tests for network pipeline nodes: input_resolver, graph_pathfinder."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet, Interface, Route, Zone
from src.agents.network.input_resolver import input_resolver
from src.agents.network.graph_pathfinder import graph_pathfinder


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


def seed_topology(store):
    """Create: Router(10.0.0.1) -> Firewall(10.0.0.2, 10.0.1.2) -> Switch(10.0.1.1)"""
    store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
    store.add_device(Device(id="sw1", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.1.1"))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1"))
    store.add_subnet(Subnet(id="s2", cidr="10.0.1.0/24", gateway_ip="10.0.1.1"))
    store.add_interface(Interface(id="r1-e0", device_id="r1", name="eth0", ip="10.0.0.1"))
    store.add_interface(Interface(id="fw1-e0", device_id="fw1", name="eth0", ip="10.0.0.2"))
    store.add_interface(Interface(id="fw1-e1", device_id="fw1", name="eth1", ip="10.0.1.2"))
    store.add_interface(Interface(id="sw1-e0", device_id="sw1", name="eth0", ip="10.0.1.1"))
    store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.1.0/24", next_hop="10.0.0.2"))
    store.add_route(Route(id="rt2", device_id="fw1", destination_cidr="10.0.1.0/24", next_hop="10.0.1.1"))


class TestInputResolver:
    def test_resolved(self, store, kg):
        seed_topology(store)
        kg.load_from_store()
        state = {"src_ip": "10.0.0.1", "dst_ip": "10.0.1.1"}
        result = input_resolver(state, kg=kg)
        assert result["resolution_status"] == "resolved"
        assert result["src_device"] is not None
        assert result["dst_device"] is not None

    def test_ambiguous(self, store, kg):
        seed_topology(store)
        kg.load_from_store()
        # 10.0.0.50 is in s1 but no device has that IP -> ambiguous (multiple candidates in subnet)
        state = {"src_ip": "10.0.0.50", "dst_ip": "10.0.1.1"}
        result = input_resolver(state, kg=kg)
        assert result["resolution_status"] == "ambiguous"
        assert len(result["ambiguous_candidates"]) > 0

    def test_failed(self, store, kg):
        kg.load_from_store()  # empty topology
        state = {"src_ip": "192.168.99.1", "dst_ip": "192.168.99.2"}
        result = input_resolver(state, kg=kg)
        assert result["resolution_status"] == "failed"

    def test_subnet_resolved_no_device(self, store, kg):
        seed_topology(store)
        kg.load_from_store()
        # Unknown IP but in known subnet, only 1 candidate
        # Add a host with unique subnet
        store.add_subnet(Subnet(id="s3", cidr="172.16.0.0/24"))
        store.add_device(Device(id="h1", name="Host1", management_ip="172.16.0.10"))
        store.add_interface(Interface(id="h1-e0", device_id="h1", name="eth0", ip="172.16.0.10"))
        kg.load_from_store()
        state = {"src_ip": "172.16.0.10", "dst_ip": "10.0.1.1"}
        result = input_resolver(state, kg=kg)
        assert result["resolution_status"] == "resolved"


class TestGraphPathfinder:
    def test_path_found(self, store, kg):
        seed_topology(store)
        kg.load_from_store()
        state = {"src_ip": "10.0.0.1", "dst_ip": "10.0.1.1"}
        result = graph_pathfinder(state, kg=kg)
        assert len(result["candidate_paths"]) >= 1
        assert result["candidate_paths"][0]["hops"][0] == "r1"

    def test_firewalls_identified(self, store, kg):
        seed_topology(store)
        kg.load_from_store()
        state = {"src_ip": "10.0.0.1", "dst_ip": "10.0.1.1"}
        result = graph_pathfinder(state, kg=kg)
        fw_ids = [f["device_id"] for f in result["firewalls_in_path"]]
        assert "fw1" in fw_ids

    def test_no_path(self, store, kg):
        store.add_device(Device(id="isolated", name="Isolated", management_ip="192.168.1.1"))
        store.add_device(Device(id="other", name="Other", management_ip="192.168.2.1"))
        store.add_interface(Interface(id="i1", device_id="isolated", name="eth0", ip="192.168.1.1"))
        store.add_interface(Interface(id="i2", device_id="other", name="eth0", ip="192.168.2.1"))
        store.add_subnet(Subnet(id="s1", cidr="192.168.1.0/24"))
        store.add_subnet(Subnet(id="s2", cidr="192.168.2.0/24"))
        kg.load_from_store()
        state = {"src_ip": "192.168.1.1", "dst_ip": "192.168.2.1"}
        result = graph_pathfinder(state, kg=kg)
        assert result["diagnosis_status"] == "no_path_known"

    def test_no_device_ids(self, store, kg):
        kg.load_from_store()
        state = {"src_ip": "99.99.99.1", "dst_ip": "99.99.99.2"}
        result = graph_pathfinder(state, kg=kg)
        assert result["diagnosis_status"] == "no_path_known"
