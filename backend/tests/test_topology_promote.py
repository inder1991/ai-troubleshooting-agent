"""Tests for canvas-to-KG promotion."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    return NetworkKnowledgeGraph(store)


def test_promote_adds_devices_to_kg(kg):
    canvas_nodes = [
        {
            "id": "device-fw-01",
            "type": "device",
            "data": {
                "label": "fw-01",
                "deviceType": "firewall",
                "ip": "10.0.0.1",
                "vendor": "Palo Alto",
                "zone": "dmz",
                "vlan": 100,
            },
        },
    ]
    canvas_edges = [
        {"source": "device-fw-01", "target": "device-rtr-01"},
    ]
    result = kg.promote_from_canvas(canvas_nodes, canvas_edges)
    assert result["devices_promoted"] >= 1
    assert kg.node_count >= 1
