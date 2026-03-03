"""Tests for reachability matrix."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, Subnet, Interface, DeviceType, Zone
from src.agents.network.reachability_matrix import compute_reachability_matrix


@pytest.fixture
def populated_kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    kg = NetworkKnowledgeGraph(store)
    # Add zones
    store.add_zone(Zone(id="zone-pci", name="PCI", security_level=5))
    store.add_zone(Zone(id="zone-dev", name="DEV", security_level=1))
    # Add devices
    store.add_device(Device(id="d1", name="pci-server", zone_id="zone-pci",
                           management_ip="10.0.1.1", device_type=DeviceType.HOST))
    store.add_device(Device(id="d2", name="dev-server", zone_id="zone-dev",
                           management_ip="10.0.2.1", device_type=DeviceType.HOST))
    kg.load_from_store()
    return kg


def test_matrix_returns_grid(populated_kg):
    result = compute_reachability_matrix(populated_kg, ["zone-pci", "zone-dev"])
    assert "matrix" in result
    assert len(result["matrix"]) > 0
