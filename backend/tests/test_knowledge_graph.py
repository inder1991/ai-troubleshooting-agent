"""Tests for Network Knowledge Graph and IP Resolver."""
import os
import pytest
from src.network.ip_resolver import IPResolver
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Subnet, Zone, Interface, Route, EdgeMetadata, EdgeSource,
)


class TestIPResolver:
    def test_load_and_resolve(self):
        resolver = IPResolver()
        resolver.load_subnets([
            {"cidr": "10.0.0.0/24", "id": "s1", "gateway_ip": "10.0.0.1"},
            {"cidr": "10.0.1.0/24", "id": "s2", "gateway_ip": "10.0.1.1"},
            {"cidr": "10.0.0.0/16", "id": "s3", "gateway_ip": "10.0.0.1"},
        ])
        # Longest prefix match
        result = resolver.resolve("10.0.0.50")
        assert result is not None
        assert result["id"] == "s1"  # /24 is more specific than /16

    def test_no_match(self):
        resolver = IPResolver()
        resolver.load_subnets([{"cidr": "10.0.0.0/24", "id": "s1"}])
        assert resolver.resolve("192.168.1.1") is None

    def test_get_prefix(self):
        resolver = IPResolver()
        resolver.load_subnets([{"cidr": "10.0.0.0/24", "id": "s1"}])
        assert resolver.get_prefix("10.0.0.50") == "10.0.0.0/24"
        assert resolver.get_prefix("192.168.1.1") is None

    def test_count(self):
        resolver = IPResolver()
        resolver.load_subnets([
            {"cidr": "10.0.0.0/24", "id": "s1"},
            {"cidr": "10.0.1.0/24", "id": "s2"},
        ])
        assert resolver.count == 2

    def test_reload_clears_old(self):
        resolver = IPResolver()
        resolver.load_subnets([{"cidr": "10.0.0.0/24", "id": "s1"}])
        assert resolver.count == 1
        resolver.load_subnets([{"cidr": "192.168.0.0/16", "id": "s2"}])
        assert resolver.count == 1
        assert resolver.resolve("10.0.0.1") is None
        assert resolver.resolve("192.168.1.1") is not None


class TestNetworkKnowledgeGraph:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "test_network.db")
        return TopologyStore(db_path=db_path)

    @pytest.fixture
    def graph(self, store):
        return NetworkKnowledgeGraph(store)

    def _seed_topology(self, store):
        """Seed a basic topology: 3 devices, 2 subnets, interfaces, routes."""
        store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_device(Device(id="sw1", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.1.1"))

        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1"))
        store.add_subnet(Subnet(id="s2", cidr="10.0.1.0/24", gateway_ip="10.0.1.1"))

        store.add_zone(Zone(id="z1", name="trust"))
        store.add_zone(Zone(id="z2", name="untrust"))

        store.add_interface(Interface(id="r1-eth0", device_id="r1", name="eth0", ip="10.0.0.1"))
        store.add_interface(Interface(id="fw1-eth0", device_id="fw1", name="eth0", ip="10.0.0.2"))
        store.add_interface(Interface(id="fw1-eth1", device_id="fw1", name="eth1", ip="10.0.1.2"))
        store.add_interface(Interface(id="sw1-eth0", device_id="sw1", name="eth0", ip="10.0.1.1"))

        # Routes: r1 -> fw1 -> sw1
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.1.0/24", next_hop="10.0.0.2"))
        store.add_route(Route(id="rt2", device_id="fw1", destination_cidr="10.0.1.0/24", next_hop="10.0.1.1"))

    def test_load_from_store(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        # 3 devices + 2 subnets + 2 zones = 7 nodes
        assert graph.node_count == 7
        # Interfaces create device->subnet edges
        assert graph.edge_count > 0

    def test_add_device_and_subnet(self, graph):
        graph.add_device(Device(id="r2", name="Router2", management_ip="172.16.0.1"))
        graph.add_subnet(Subnet(id="s3", cidr="172.16.0.0/24"))
        assert graph.node_count == 2
        assert "r2" in graph.graph
        assert "s3" in graph.graph

    def test_resolve_ip(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        result = graph.resolve_ip("10.0.0.1")
        assert result["ip"] == "10.0.0.1"
        assert result["subnet"] is not None
        assert result["device_id"] == "r1"

    def test_resolve_ip_no_device(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        result = graph.resolve_ip("10.0.0.99")
        assert result["subnet"] is not None  # In 10.0.0.0/24
        assert result["device_id"] is None

    def test_find_device_by_ip(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        assert graph.find_device_by_ip("10.0.0.1") == "r1"
        assert graph.find_device_by_ip("10.0.0.2") == "fw1"
        assert graph.find_device_by_ip("192.168.99.99") is None

    def test_find_candidate_devices(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        # 10.0.0.0/24 has r1 (10.0.0.1) and fw1 (10.0.0.2)
        candidates = graph.find_candidate_devices("10.0.0.50")
        assert len(candidates) == 2
        device_ids = {c["device_id"] for c in candidates}
        assert "r1" in device_ids
        assert "fw1" in device_ids

    def test_build_route_edges(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        initial_edges = graph.edge_count
        graph.build_route_edges("10.0.0.1", "10.0.1.1")
        # Should add route edges: r1->fw1, fw1->sw1
        assert graph.edge_count > initial_edges

    def test_k_shortest_paths(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        graph.build_route_edges("10.0.0.1", "10.0.1.1")
        paths = graph.find_k_shortest_paths("r1", "sw1", k=3)
        assert len(paths) >= 1
        assert paths[0][0] == "r1"
        assert paths[0][-1] == "sw1"

    def test_k_shortest_paths_no_path(self, store, graph):
        graph.add_device(Device(id="isolated1", name="Isolated"))
        graph.add_device(Device(id="isolated2", name="Isolated2"))
        paths = graph.find_k_shortest_paths("isolated1", "isolated2")
        assert paths == []

    def test_k_shortest_paths_missing_node(self, graph):
        paths = graph.find_k_shortest_paths("nonexistent1", "nonexistent2")
        assert paths == []

    def test_boost_edge_confidence(self, store, graph):
        self._seed_topology(store)
        graph.load_from_store()
        graph.build_route_edges("10.0.0.1", "10.0.1.1")
        # Find an edge r1->fw1
        if graph.graph.has_edge("r1", "fw1"):
            old_conf = None
            for key in graph.graph["r1"]["fw1"]:
                old_conf = graph.graph["r1"]["fw1"][key].get("confidence", 0.5)
                break
            graph.boost_edge_confidence("r1", "fw1", boost=0.1)
            for key in graph.graph["r1"]["fw1"]:
                new_conf = graph.graph["r1"]["fw1"][key].get("confidence")
                assert new_conf > old_conf
                break

    def test_add_edge_with_metadata(self, graph):
        graph.add_device(Device(id="a", name="A"))
        graph.add_device(Device(id="b", name="B"))
        meta = EdgeMetadata(confidence=0.7, source=EdgeSource.TRACEROUTE, edge_type="routes_to")
        graph.add_edge("a", "b", meta)
        assert graph.edge_count == 1
        edge_data = list(graph.graph["a"]["b"].values())[0]
        assert edge_data["confidence"] == 0.7
        assert edge_data["source"] == "traceroute"

    def test_node_and_edge_counts(self, graph):
        assert graph.node_count == 0
        assert graph.edge_count == 0
        graph.add_device(Device(id="x", name="X"))
        assert graph.node_count == 1
