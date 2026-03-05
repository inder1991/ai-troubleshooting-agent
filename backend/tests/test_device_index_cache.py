"""Regression test: _device_index must be cleared on reload."""
import os
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Interface
from src.network.topology_store import TopologyStore


def test_cache_cleared_on_reload(tmp_path):
    """After deleting a device and reloading, find_device_by_ip should return None."""
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    store.add_device(Device(id="d1", name="Host1", device_type=DeviceType.HOST, management_ip="10.0.0.1"))
    store.add_interface(Interface(id="i1", device_id="d1", name="eth0", ip="10.0.0.1"))

    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()
    assert kg.find_device_by_ip("10.0.0.1") == "d1"

    # Delete device from store
    store.delete_device("d1")
    kg.load_from_store()

    # After reload, the old IP should NOT resolve
    assert kg.find_device_by_ip("10.0.0.1") is None, (
        "Stale cache: IP still resolves to deleted device"
    )


def test_promote_updates_interface_cache(tmp_path):
    """Interfaces added via promote_from_canvas should update _device_index."""
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    kg = NetworkKnowledgeGraph(store)

    nodes = [{
        "id": "dev-x",
        "type": "device",
        "data": {
            "label": "DevX",
            "deviceType": "HOST",
            "ip": "10.0.0.5",
            "interfaces": [
                {"id": "iface-x1", "name": "eth0", "ip": "192.168.1.10", "role": "inside"},
            ],
        },
    }]
    kg.promote_from_canvas(nodes, [])

    # Management IP should resolve
    assert kg.find_device_by_ip("10.0.0.5") == "dev-x"
    # Interface IP should also resolve (this is the bug -- currently it doesn't)
    assert kg.find_device_by_ip("192.168.1.10") == "dev-x", (
        "Interface IP not cached after promote"
    )
