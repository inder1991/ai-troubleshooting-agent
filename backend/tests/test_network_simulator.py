"""Unit tests for NetworkSimulator."""
import json
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.simulation.network_simulator import (
    NetworkSimulator, SimulatedTopology, PacketSpec, ConnectivityResult,
)
from src.network.models import Device, DeviceType


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def simulator(store, kg):
    return NetworkSimulator(store, kg)


def _sim_topo(nodes, edges, routes=None, fw_rules=None):
    return SimulatedTopology(
        nodes=nodes, edges=edges,
        routes=routes or [], firewall_rules=fw_rules or [],
    )


def _node(id, label, dtype="host", ip="", zone="", source="live"):
    return {"id": id, "data": {"label": label, "deviceType": dtype, "ip": ip, "zone": zone, "_source": source}}


def _edge(src, tgt, label="connected_to"):
    return {"id": f"e-{src}-{tgt}", "source": src, "target": tgt, "data": {"label": label}}


class TestConnectivity:
    def test_reachable(self, simulator):
        topo = _sim_topo(
            [_node("a", "A"), _node("b", "B"), _node("c", "C")],
            [_edge("a", "b"), _edge("b", "c")],
        )
        result = simulator.simulate_connectivity(topo, "a", "c")
        assert result.reachable is True
        assert result.path == ["a", "b", "c"]

    def test_unreachable(self, simulator):
        topo = _sim_topo(
            [_node("a", "A"), _node("b", "B")],
            [],
        )
        result = simulator.simulate_connectivity(topo, "a", "b")
        assert result.reachable is False

    def test_blocked_by_firewall(self, simulator):
        topo = _sim_topo(
            [_node("a", "A"), _node("fw", "FW", dtype="firewall"), _node("b", "B")],
            [_edge("a", "fw"), _edge("fw", "b")],
            fw_rules=[{"device_id": "fw", "action": "deny", "protocol": "any", "description": "block all"}],
        )
        result = simulator.simulate_connectivity(topo, "a", "b")
        assert result.reachable is False
        assert "fw" in (result.blocked_by or "")


class TestFirewallPolicy:
    def test_allow(self, simulator):
        topo = _sim_topo(
            [_node("a", "A", ip="10.0.0.1"), _node("fw", "FW", dtype="firewall", ip="10.0.0.2"), _node("b", "B", ip="10.0.0.3")],
            [_edge("a", "fw"), _edge("fw", "b")],
            fw_rules=[{"device_id": "fw", "action": "allow", "protocol": "tcp", "dst_port": "80", "src_ip": "any", "dst_ip": "any", "id": "r1", "description": "allow http"}],
        )
        packet = PacketSpec(src_ip="10.0.0.1", dst_ip="10.0.0.3", port=80, protocol="tcp")
        result = simulator.simulate_firewall_policy(topo, packet)
        assert result.allowed is True

    def test_deny(self, simulator):
        topo = _sim_topo(
            [_node("a", "A", ip="10.0.0.1"), _node("fw", "FW", dtype="firewall", ip="10.0.0.2"), _node("b", "B", ip="10.0.0.3")],
            [_edge("a", "fw"), _edge("fw", "b")],
            fw_rules=[{"device_id": "fw", "action": "deny", "protocol": "tcp", "dst_port": "80", "src_ip": "any", "dst_ip": "any", "id": "r1", "description": "block http"}],
        )
        packet = PacketSpec(src_ip="10.0.0.1", dst_ip="10.0.0.3", port=80, protocol="tcp")
        result = simulator.simulate_firewall_policy(topo, packet)
        assert result.allowed is False


class TestIntegrityChecks:
    def test_duplicate_ip(self, simulator):
        topo = _sim_topo(
            [_node("a", "A", ip="10.0.0.1"), _node("b", "B", ip="10.0.0.1")],
            [],
        )
        issues = simulator.detect_integrity_issues(topo)
        assert any(i.type == "duplicate_ip" for i in issues)

    def test_zone_violation(self, simulator):
        topo = _sim_topo(
            [_node("a", "A", dtype="host", zone="dmz"), _node("b", "B", dtype="host", zone="core")],
            [_edge("a", "b")],
        )
        issues = simulator.detect_integrity_issues(topo)
        assert any(i.type == "zone_violation" for i in issues)

    def test_routing_loop(self, simulator):
        """Cycle in route graph is detected."""
        topo = _sim_topo(
            [_node("r1", "R1", dtype="router"), _node("r2", "R2", dtype="router"), _node("r3", "R3", dtype="router")],
            [_edge("r1", "r2"), _edge("r2", "r3"), _edge("r3", "r1")],
            routes=[
                {"device_id": "r1", "next_hop_device": "r2"},
                {"device_id": "r2", "next_hop_device": "r3"},
                {"device_id": "r3", "next_hop_device": "r1"},
            ],
        )
        issues = simulator.detect_integrity_issues(topo)
        assert any(i.type == "routing_loop" for i in issues)

    def test_isolated_subnet(self, simulator):
        """Subnet unreachable from any gateway is flagged."""
        topo = _sim_topo(
            [
                _node("gw", "Gateway", dtype="router"),
                _node("sub-a", "SubnetA", dtype="subnet"),
                _node("sub-b", "SubnetB", dtype="subnet"),  # isolated
            ],
            [_edge("gw", "sub-a")],  # sub-b has no edges to gateway
        )
        issues = simulator.detect_integrity_issues(topo)
        isolated = [i for i in issues if i.type == "isolated_subnet"]
        assert len(isolated) == 1
        assert "SubnetB" in isolated[0].description

    def test_missing_gateway(self, simulator):
        """Subnet connected only to non-gateway devices is flagged."""
        topo = _sim_topo(
            [
                _node("sub-1", "Subnet1", dtype="subnet"),
                _node("host-1", "Host1", dtype="host"),
            ],
            [_edge("sub-1", "host-1")],
        )
        issues = simulator.detect_integrity_issues(topo)
        assert any(i.type == "missing_gateway" for i in issues)

    def test_no_issues_clean_topology(self, simulator):
        topo = _sim_topo(
            [_node("a", "A", ip="10.0.0.1"), _node("b", "B", ip="10.0.0.2")],
            [_edge("a", "b")],
        )
        issues = simulator.detect_integrity_issues(topo)
        assert len(issues) == 0


class TestBuildSimulatedTopology:
    def test_merges_live_and_planned(self, store, kg, simulator):
        store.add_device(Device(id="live-1", name="live-1", device_type=DeviceType.HOST, management_ip="10.0.0.1"))
        snap = json.dumps({
            "nodes": [{"id": "planned-1", "data": {"label": "planned-1", "deviceType": "host", "_source": "planned"}}],
            "edges": [],
        })
        store.create_design("d1", "test", snapshot_json=snap)
        topo = simulator.build_simulated_topology("d1")
        ids = {n["id"] for n in topo.nodes}
        assert "live-1" in ids
        assert "planned-1" in ids
