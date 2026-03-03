"""Tests for diagnosis writeback and confidence persistence."""
import os
import tempfile
import pytest
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Subnet, Interface, EdgeMetadata, EdgeSource,
)


@pytest.fixture
def temp_store():
    """Create a TopologyStore backed by a temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = TopologyStore(db_path=path)
    yield store
    os.unlink(path)


@pytest.fixture
def kg(temp_store):
    """Create a NetworkKnowledgeGraph backed by the temp store."""
    graph = NetworkKnowledgeGraph(store=temp_store)
    return graph


def _seed_device_subnet_edge(kg):
    """Helper: create a device connected to a subnet via an interface.
    This edge survives load_from_store() because it is rebuilt from interfaces.
    Returns (device_id, subnet_id) for the created edge.
    """
    subnet = Subnet(id="subnet-1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1")
    kg.store.add_subnet(subnet)

    d1 = Device(id="dev-a", name="A", device_type=DeviceType.HOST, management_ip="10.0.0.10")
    kg.add_device(d1)

    iface1 = Interface(id="iface-a", device_id="dev-a", name="eth0", ip="10.0.0.10")
    kg.store.add_interface(iface1)

    # Rebuild the graph so the device->subnet edge is created
    kg.load_from_store()
    return "dev-a", "subnet-1"


class TestBoostPersistsToSQLite:
    def test_boost_persists_to_sqlite(self, kg, temp_store):
        """Boost confidence, clear the graph, reload -- confidence must survive."""
        src, dst = _seed_device_subnet_edge(kg)

        # The initial device->subnet edge has confidence=0.9 (from load_from_store)
        assert kg.graph.has_edge(src, dst)
        initial = kg.graph[src][dst][0]["confidence"]
        assert initial == pytest.approx(0.9)

        # Boost
        kg.boost_edge_confidence(src, dst, boost=0.05)
        boosted = kg.graph[src][dst][0]["confidence"]
        assert boosted == pytest.approx(0.95)

        # Verify persisted in SQLite
        rows = temp_store.list_edge_confidences()
        assert len(rows) == 1
        assert rows[0]["src_id"] == src
        assert rows[0]["dst_id"] == dst
        assert rows[0]["confidence"] == pytest.approx(0.95)
        assert rows[0]["source"] == "diagnosis"
        assert rows[0]["last_verified_at"] != ""

        # Clear graph completely and reload
        kg.graph.clear()
        kg._device_index.clear()
        assert kg.graph.number_of_edges() == 0

        kg.load_from_store()

        # Edge must exist and confidence must be restored from SQLite (0.95, not default 0.9)
        assert kg.graph.has_edge(src, dst)
        restored = kg.graph[src][dst][0]["confidence"]
        assert restored == pytest.approx(0.95)


class TestWritebackCreatesNewDevices:
    def test_writeback_creates_new_devices(self, kg):
        """Unknown hops should become new devices in the graph."""
        hops = [
            {"ip": "192.168.1.1", "rtt_ms": 1.0, "status": "responded"},
            {"ip": "192.168.1.2", "rtt_ms": 2.0, "status": "responded"},
            {"ip": "192.168.1.3", "device_name": "known-router", "rtt_ms": 3.0, "status": "responded"},
        ]
        added = kg.writeback_discovered_hops(hops)
        assert added == 3

        # Each hop should have produced a device node
        assert kg.graph.has_node("device-discovered-192-168-1-1")
        assert kg.graph.has_node("device-discovered-192-168-1-2")
        assert kg.graph.has_node("device-discovered-192-168-1-3")

        # Verify the custom name was used
        node_data = kg.graph.nodes["device-discovered-192-168-1-3"]
        assert node_data["name"] == "known-router"

        # Devices should also be persisted in SQLite
        devices = kg.store.list_devices()
        device_ids = [d.id for d in devices]
        assert "device-discovered-192-168-1-1" in device_ids
        assert "device-discovered-192-168-1-2" in device_ids
        assert "device-discovered-192-168-1-3" in device_ids


class TestWritebackCreatesEdges:
    def test_writeback_creates_edges(self, kg):
        """Sequential hops should produce routes_to edges."""
        hops = [
            {"ip": "10.0.0.1", "rtt_ms": 1.0, "status": "responded"},
            {"ip": "10.0.0.2", "rtt_ms": 2.0, "status": "responded"},
            {"ip": "10.0.0.3", "rtt_ms": 3.0, "status": "responded"},
        ]
        kg.writeback_discovered_hops(hops)

        dev1 = "device-discovered-10-0-0-1"
        dev2 = "device-discovered-10-0-0-2"
        dev3 = "device-discovered-10-0-0-3"

        # Check edges between consecutive hops
        assert kg.graph.has_edge(dev1, dev2)
        assert kg.graph.has_edge(dev2, dev3)
        # No edge skipping a hop
        assert not kg.graph.has_edge(dev1, dev3)

        # Verify edge metadata
        edge_data = kg.graph[dev1][dev2][0]
        assert edge_data["confidence"] == pytest.approx(0.7)
        assert edge_data["source"] == EdgeSource.DIAGNOSIS.value
        assert edge_data["edge_type"] == "routes_to"


class TestWritebackSkipsStarHops:
    def test_writeback_skips_star_hops(self, kg):
        """Timeout hops ('*') should be ignored completely."""
        hops = [
            {"ip": "10.0.0.1", "rtt_ms": 1.0, "status": "responded"},
            {"ip": "*", "rtt_ms": 0, "status": "timeout"},
            {"ip": "", "rtt_ms": 0, "status": "timeout"},
            {"ip": "10.0.0.4", "rtt_ms": 4.0, "status": "responded"},
        ]
        added = kg.writeback_discovered_hops(hops)
        assert added == 2  # Only 10.0.0.1 and 10.0.0.4

        dev1 = "device-discovered-10-0-0-1"
        dev4 = "device-discovered-10-0-0-4"

        # Despite the gap, an edge should connect the two real hops
        assert kg.graph.has_edge(dev1, dev4)


class TestLoadFromStoreRestoresConfidence:
    def test_load_from_store_restores_confidence(self, kg, temp_store):
        """Persisted confidence should override default after load_from_store."""
        src, dst = _seed_device_subnet_edge(kg)

        # The default confidence from load_from_store is 0.9
        assert kg.graph[src][dst][0]["confidence"] == pytest.approx(0.9)

        # Manually persist a different confidence value to SQLite
        temp_store.save_edge_confidence(src, dst, 0.99, "diagnosis")

        # Reload from store -- the persisted 0.99 should override the default 0.9
        kg.load_from_store()

        assert kg.graph.has_edge(src, dst)
        restored = kg.graph[src][dst][0]["confidence"]
        assert restored == pytest.approx(0.99)
