"""Tests for traceroute probe and hop attributor."""
import os
import pytest
from src.agents.network.traceroute_probe import make_manual_trace, traceroute_probe
from src.agents.network.hop_attributor import hop_attributor
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet, Interface


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))

@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


class TestManualTrace:
    def test_basic_trace(self):
        result = make_manual_trace([
            {"ip": "10.0.0.1", "rtt_ms": 1.0},
            {"ip": "10.0.0.2", "rtt_ms": 2.0},
            {"ip": "10.0.1.1", "rtt_ms": 3.0},
        ])
        assert result["trace_method"] == "manual"
        assert len(result["trace_hops"]) == 3
        assert result["routing_loop_detected"] is False
        assert result["traced_path"]["hop_count"] == 3

    def test_loop_detection(self):
        result = make_manual_trace([
            {"ip": "10.0.0.1", "rtt_ms": 1.0},
            {"ip": "10.0.0.2", "rtt_ms": 2.0},
            {"ip": "10.0.0.1", "rtt_ms": 3.0},  # Loop!
        ])
        assert result["routing_loop_detected"] is True

    def test_timeout_hops(self):
        result = make_manual_trace([
            {"ip": "10.0.0.1", "rtt_ms": 1.0},
            {"ip": "", "rtt_ms": 0, "status": "timeout"},
            {"ip": "10.0.1.1", "rtt_ms": 3.0},
        ])
        assert len(result["trace_hops"]) == 3
        assert result["trace_hops"][1]["status"] == "timeout"

    def test_empty_trace(self):
        result = make_manual_trace([])
        assert len(result["trace_hops"]) == 0
        assert result["routing_loop_detected"] is False


class TestTracerouteProbe:
    def test_no_dst_ip(self):
        result = traceroute_probe({"dst_ip": ""})
        assert result["trace_method"] == "unavailable"

    def test_missing_dst_ip(self):
        result = traceroute_probe({})
        assert result["trace_method"] == "unavailable"


class TestHopAttributor:
    def _seed(self, store):
        store.add_device(Device(id="r1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        store.add_device(Device(id="fw1", name="Firewall1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        store.add_interface(Interface(id="r1-e0", device_id="r1", name="eth0", ip="10.0.0.1"))
        store.add_interface(Interface(id="fw1-e0", device_id="fw1", name="eth0", ip="10.0.0.2"))

    def test_direct_attribution(self, store, kg):
        self._seed(store)
        kg.load_from_store()
        trace = make_manual_trace([
            {"ip": "10.0.0.1", "rtt_ms": 1.0},
            {"ip": "10.0.0.2", "rtt_ms": 2.0},
        ])
        state = {**trace}
        result = hop_attributor(state, kg=kg)
        assert result["trace_hops"][0]["device_id"] == "r1"
        assert result["trace_hops"][0]["attribution_confidence"] == 1.0
        assert result["trace_hops"][1]["device_id"] == "fw1"

    def test_candidate_attribution(self, store, kg):
        self._seed(store)
        kg.load_from_store()
        trace = make_manual_trace([{"ip": "10.0.0.50", "rtt_ms": 1.0}])
        state = {**trace}
        result = hop_attributor(state, kg=kg)
        # 10.0.0.50 is in subnet but not a known device IP
        assert result["trace_hops"][0].get("candidate_devices") is not None
        assert result["trace_hops"][0]["attribution_confidence"] < 1.0

    def test_no_match(self, store, kg):
        kg.load_from_store()
        trace = make_manual_trace([{"ip": "192.168.99.1", "rtt_ms": 1.0}])
        state = {**trace}
        result = hop_attributor(state, kg=kg)
        assert result["trace_hops"][0]["attribution_confidence"] == 0.0

    def test_empty_hops(self, store, kg):
        result = hop_attributor({"trace_hops": []}, kg=kg)
        assert result["trace_hops"] == []
