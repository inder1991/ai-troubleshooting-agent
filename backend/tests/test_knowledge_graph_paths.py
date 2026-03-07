"""Tests for KnowledgeGraph path-finding, edge operations, and exports."""
import os
import pytest
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Subnet, Zone, Interface, Route, EdgeMetadata, EdgeSource,
)


class TestKnowledgeGraphPaths:
    """Path-finding tests using confidence-weighted dual cost model."""

    @pytest.fixture
    def store(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "test_kg_paths.db")
        return TopologyStore(db_path=db_path)

    @pytest.fixture
    def graph(self, store):
        return NetworkKnowledgeGraph(store)

    def _seed_linear(self, store):
        """Seed a linear topology: r1 -> fw1 -> sw1 with route edges."""
        store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_device(Device(id="sw1", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.1.1"))

        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1"))
        store.add_subnet(Subnet(id="s2", cidr="10.0.1.0/24", gateway_ip="10.0.1.1"))

        store.add_zone(Zone(id="z1", name="trust"))

        store.add_interface(Interface(id="r1-eth0", device_id="r1", name="eth0", ip="10.0.0.1"))
        store.add_interface(Interface(id="fw1-eth0", device_id="fw1", name="eth0", ip="10.0.0.2"))
        store.add_interface(Interface(id="fw1-eth1", device_id="fw1", name="eth1", ip="10.0.1.2"))
        store.add_interface(Interface(id="sw1-eth0", device_id="sw1", name="eth0", ip="10.0.1.1"))

        # Routes: r1 -> fw1 -> sw1
        store.add_route(Route(id="rt1", device_id="r1", destination_cidr="10.0.1.0/24", next_hop="10.0.0.2"))
        store.add_route(Route(id="rt2", device_id="fw1", destination_cidr="10.0.1.0/24", next_hop="10.0.1.1"))

    def _seed_diamond(self, store):
        """Seed a diamond topology: A -> B -> D and A -> C -> D (two paths)."""
        store.add_device(Device(id="A", name="DevA", device_type=DeviceType.ROUTER, management_ip="10.1.0.1"))
        store.add_device(Device(id="B", name="DevB", device_type=DeviceType.ROUTER, management_ip="10.1.0.2"))
        store.add_device(Device(id="C", name="DevC", device_type=DeviceType.ROUTER, management_ip="10.1.0.3"))
        store.add_device(Device(id="D", name="DevD", device_type=DeviceType.ROUTER, management_ip="10.1.0.4"))

        store.add_subnet(Subnet(id="sd", cidr="10.1.0.0/24", gateway_ip="10.1.0.1"))

        store.add_interface(Interface(id="A-e0", device_id="A", name="eth0", ip="10.1.0.1"))
        store.add_interface(Interface(id="B-e0", device_id="B", name="eth0", ip="10.1.0.2"))
        store.add_interface(Interface(id="C-e0", device_id="C", name="eth0", ip="10.1.0.3"))
        store.add_interface(Interface(id="D-e0", device_id="D", name="eth0", ip="10.1.0.4"))

    # ── 1. Basic path finding ──

    def test_basic_path_through_route_edges(self, store, graph):
        """A path r1 -> fw1 -> sw1 should be found after building route edges."""
        self._seed_linear(store)
        graph.load_from_store()
        graph.build_route_edges("10.0.0.1", "10.0.1.1")

        paths = graph.find_k_shortest_paths("r1", "sw1", k=3)
        assert len(paths) >= 1
        # First path should start at r1 and end at sw1
        assert paths[0][0] == "r1"
        assert paths[0][-1] == "sw1"

    def test_no_path_between_disconnected_nodes(self, graph):
        """Two isolated devices with no edges should return no paths."""
        graph.add_device(Device(id="iso1", name="Isolated1"))
        graph.add_device(Device(id="iso2", name="Isolated2"))
        paths = graph.find_k_shortest_paths("iso1", "iso2")
        assert paths == []

    def test_missing_node_returns_empty(self, graph):
        """Querying paths for nodes not in the graph returns empty list."""
        paths = graph.find_k_shortest_paths("ghost1", "ghost2")
        assert paths == []

    def test_single_hop_path(self, graph):
        """Direct edge A -> B should produce a single two-node path."""
        graph.add_device(Device(id="p", name="P"))
        graph.add_device(Device(id="q", name="Q"))
        graph.add_edge("p", "q", EdgeMetadata(confidence=0.9, source=EdgeSource.MANUAL, edge_type="connected_to"))

        paths = graph.find_k_shortest_paths("p", "q", k=3)
        assert len(paths) == 1
        assert paths[0] == ["p", "q"]

    def test_k_limit_caps_results(self, store, graph):
        """With a diamond topology (2 distinct paths), k=1 should return only 1."""
        self._seed_diamond(store)
        graph.load_from_store()
        # Manually add edges for two independent paths: A->B->D and A->C->D
        graph.add_edge("A", "B", EdgeMetadata(confidence=0.9, source=EdgeSource.MANUAL, edge_type="connected_to"))
        graph.add_edge("B", "D", EdgeMetadata(confidence=0.9, source=EdgeSource.MANUAL, edge_type="connected_to"))
        graph.add_edge("A", "C", EdgeMetadata(confidence=0.8, source=EdgeSource.MANUAL, edge_type="connected_to"))
        graph.add_edge("C", "D", EdgeMetadata(confidence=0.8, source=EdgeSource.MANUAL, edge_type="connected_to"))

        paths_k1 = graph.find_k_shortest_paths("A", "D", k=1)
        assert len(paths_k1) == 1

        paths_k2 = graph.find_k_shortest_paths("A", "D", k=2)
        assert len(paths_k2) == 2

    def test_path_prefers_higher_confidence(self, graph):
        """The shortest path (lowest cost) should use the higher-confidence edge."""
        graph.add_device(Device(id="x", name="X"))
        graph.add_device(Device(id="y", name="Y"))
        graph.add_device(Device(id="z", name="Z"))
        # Direct path x -> z with low confidence (high cost)
        graph.add_edge("x", "z", EdgeMetadata(confidence=0.3, source=EdgeSource.MANUAL, edge_type="connected_to"))
        # Indirect path x -> y -> z with high confidence (low cost)
        graph.add_edge("x", "y", EdgeMetadata(confidence=0.95, source=EdgeSource.MANUAL, edge_type="connected_to"))
        graph.add_edge("y", "z", EdgeMetadata(confidence=0.95, source=EdgeSource.MANUAL, edge_type="connected_to"))

        paths = graph.find_k_shortest_paths("x", "z", k=2)
        assert len(paths) == 2
        # First path should be x -> y -> z (lower total cost despite more hops)
        assert paths[0] == ["x", "y", "z"]
        # Second path is the direct low-confidence x -> z
        assert paths[1] == ["x", "z"]

    # ── 2. Edge confidence operations ──

    def test_boost_edge_confidence(self, store, graph):
        """Boosting an edge should increase its confidence value."""
        self._seed_linear(store)
        graph.load_from_store()
        graph.build_route_edges("10.0.0.1", "10.0.1.1")

        assert graph.graph.has_edge("r1", "fw1"), "Route edge r1->fw1 should exist"
        # Read original confidence
        orig = None
        for key in graph.graph["r1"]["fw1"]:
            orig = graph.graph["r1"]["fw1"][key].get("confidence", 0.5)
            break

        graph.boost_edge_confidence("r1", "fw1", boost=0.1)

        for key in graph.graph["r1"]["fw1"]:
            new_conf = graph.graph["r1"]["fw1"][key]["confidence"]
            assert new_conf == pytest.approx(min(1.0, orig + 0.1))
            break

    def test_boost_caps_at_one(self, graph):
        """Boosting an edge already at 0.98 by 0.1 should cap at 1.0."""
        graph.add_device(Device(id="h1", name="H1"))
        graph.add_device(Device(id="h2", name="H2"))
        graph.add_edge("h1", "h2", EdgeMetadata(confidence=0.98, source=EdgeSource.MANUAL, edge_type="connected_to"))

        graph.boost_edge_confidence("h1", "h2", boost=0.1)

        for key in graph.graph["h1"]["h2"]:
            assert graph.graph["h1"]["h2"][key]["confidence"] == 1.0
            break

    def test_boost_nonexistent_edge_is_noop(self, graph):
        """Boosting an edge that doesn't exist should not raise."""
        graph.add_device(Device(id="n1", name="N1"))
        graph.add_device(Device(id="n2", name="N2"))
        # No edge between n1 and n2
        graph.boost_edge_confidence("n1", "n2", boost=0.1)
        # Nothing should have changed, no error raised

    # ── 3. React Flow export ──

    def test_export_react_flow_has_nodes_and_edges(self, store, graph):
        """Exported React Flow dict should contain nodes and edges lists."""
        self._seed_linear(store)
        graph.load_from_store()

        rf = graph.export_react_flow_graph()
        assert "nodes" in rf
        assert "edges" in rf
        assert isinstance(rf["nodes"], list)
        assert isinstance(rf["edges"], list)
        assert len(rf["nodes"]) > 0
        assert len(rf["edges"]) > 0

    def test_export_react_flow_node_structure(self, store, graph):
        """Each React Flow node should have id, type, data, and position keys."""
        self._seed_linear(store)
        graph.load_from_store()

        rf = graph.export_react_flow_graph()
        for node in rf["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "data" in node
            assert "position" in node
            assert "label" in node["data"]

    def test_export_react_flow_edge_structure(self, store, graph):
        """Each React Flow edge should have id, source, target keys."""
        self._seed_linear(store)
        graph.load_from_store()

        rf = graph.export_react_flow_graph()
        for edge in rf["edges"]:
            assert "id" in edge
            assert "source" in edge
            assert "target" in edge
            assert "data" in edge

    # ── 4. Candidate devices ──

    def test_find_candidate_devices_in_subnet(self, store, graph):
        """Querying a subnet IP should return all devices with interfaces in that subnet."""
        self._seed_linear(store)
        graph.load_from_store()
        # 10.0.0.0/24 has r1 (10.0.0.1) and fw1 (10.0.0.2)
        candidates = graph.find_candidate_devices("10.0.0.50")
        assert len(candidates) == 2
        device_ids = {c["device_id"] for c in candidates}
        assert "r1" in device_ids
        assert "fw1" in device_ids
        # Each candidate should have expected keys
        for c in candidates:
            assert "device_name" in c
            assert "interface_ip" in c
            assert "interface_name" in c

    def test_find_candidate_devices_no_subnet(self, store, graph):
        """IP not in any known subnet returns empty candidates."""
        self._seed_linear(store)
        graph.load_from_store()
        candidates = graph.find_candidate_devices("192.168.99.99")
        assert candidates == []

    # ── 5. Load from store ──

    def test_load_from_store_populates_graph(self, store, graph):
        """Loading from store should populate nodes from devices, subnets, and zones."""
        self._seed_linear(store)
        graph.load_from_store()
        # 3 devices + 2 subnets + 1 zone = 6 nodes
        assert graph.node_count == 6
        # Interfaces create device -> subnet edges
        assert graph.edge_count > 0

    def test_load_from_store_indexes_ips(self, store, graph):
        """After load, device IPs should be findable via the internal index."""
        self._seed_linear(store)
        graph.load_from_store()
        assert graph.find_device_by_ip("10.0.0.1") == "r1"
        assert graph.find_device_by_ip("10.0.0.2") == "fw1"
        # Interface IP should also resolve
        assert graph.find_device_by_ip("10.0.1.2") == "fw1"

    # ── 6. Build route edges ──

    def test_build_route_edges_creates_routes_to(self, store, graph):
        """build_route_edges should add routes_to edges between devices."""
        self._seed_linear(store)
        graph.load_from_store()
        edges_before = graph.edge_count
        graph.build_route_edges("10.0.0.1", "10.0.1.1")
        assert graph.edge_count > edges_before
        # r1 -> fw1 route edge should exist
        assert graph.graph.has_edge("r1", "fw1")

    def test_build_route_edges_has_route_metadata(self, store, graph):
        """Route edges should carry destination, next_hop, and confidence metadata."""
        self._seed_linear(store)
        graph.load_from_store()
        graph.build_route_edges("10.0.0.1", "10.0.1.1")

        found_route_edge = False
        for key in graph.graph["r1"]["fw1"]:
            edata = graph.graph["r1"]["fw1"][key]
            if edata.get("edge_type") == "routes_to":
                found_route_edge = True
                assert edata["destination"] == "10.0.1.0/24"
                assert edata["next_hop"] == "10.0.0.2"
                assert edata["confidence"] == 0.85
                assert edata["source"] == "api"
                break
        assert found_route_edge, "Should have a routes_to edge from r1 to fw1"
