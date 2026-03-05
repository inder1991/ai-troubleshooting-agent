"""Regression test: firewalls must appear in firewalls_in_path.

model_dump() keeps Python Enum objects which break JSON serialization
and can cause subtle bugs when node attributes are passed to code that
expects plain primitive types.  model_dump(mode="json") converts all
enums to their .value strings.
"""
import os
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet, Interface
from src.network.topology_store import TopologyStore
from src.agents.network.graph_pathfinder import graph_pathfinder


def _make_store_with_firewall(tmp_path):
    """Create a TopologyStore with a path: host-A -> firewall-1 -> host-B."""
    db_path = os.path.join(str(tmp_path), "test_fw.db")
    store = TopologyStore(db_path=db_path)
    # Devices
    host_a = Device(id="host-a", name="Host A", device_type=DeviceType.HOST, management_ip="10.0.1.10")
    fw = Device(id="fw-1", name="Firewall 1", device_type=DeviceType.FIREWALL, management_ip="10.0.1.1")
    host_b = Device(id="host-b", name="Host B", device_type=DeviceType.HOST, management_ip="10.0.2.10")
    store.add_device(host_a)
    store.add_device(fw)
    store.add_device(host_b)
    # Subnet
    subnet_a = Subnet(id="subnet-a", cidr="10.0.1.0/24")
    subnet_b = Subnet(id="subnet-b", cidr="10.0.2.0/24")
    store.add_subnet(subnet_a)
    store.add_subnet(subnet_b)
    # Interfaces
    store.add_interface(Interface(id="iface-a", device_id="host-a", name="eth0", ip="10.0.1.10"))
    store.add_interface(Interface(id="iface-fw-in", device_id="fw-1", name="eth0", ip="10.0.1.1"))
    store.add_interface(Interface(id="iface-fw-out", device_id="fw-1", name="eth1", ip="10.0.2.1"))
    store.add_interface(Interface(id="iface-b", device_id="host-b", name="eth0", ip="10.0.2.10"))
    return store


def test_firewalls_detected_in_path(tmp_path):
    """After model_dump(mode='json'), DeviceType.FIREWALL should match string comparison."""
    store = _make_store_with_firewall(tmp_path)
    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()

    # Verify the firewall node has device_type as a plain str, not an Enum instance.
    # type() is used instead of isinstance() because DeviceType inherits from str
    # and isinstance(DeviceType.FIREWALL, str) is True even for enum objects.
    fw_data = kg.graph.nodes.get("fw-1", {})
    assert fw_data.get("device_type") == "firewall", (
        f"Expected string 'firewall', got {fw_data.get('device_type')!r}"
    )
    assert type(fw_data.get("device_type")) is str, (
        f"Expected plain str, got {type(fw_data.get('device_type')).__name__}"
    )

    # Build manual edges for the path: host-a -> fw-1 -> host-b
    kg.graph.add_edge("host-a", "fw-1", edge_type="connected_to", confidence=0.9)
    kg.graph.add_edge("fw-1", "host-b", edge_type="connected_to", confidence=0.9)

    # Run pathfinder
    state = {"src_ip": "10.0.1.10", "dst_ip": "10.0.2.10"}
    result = graph_pathfinder(state, kg=kg)

    assert len(result["firewalls_in_path"]) > 0, (
        f"Expected at least 1 firewall, got {result['firewalls_in_path']}"
    )
    assert result["firewalls_in_path"][0]["device_id"] == "fw-1"


def test_enum_serialization_consistency(tmp_path):
    """All node types should store device_type as a plain str, not an Enum."""
    db_path = os.path.join(str(tmp_path), "test_enum.db")
    store = TopologyStore(db_path=db_path)
    store.add_device(Device(id="d1", name="Router", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="Switch", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))
    store.add_device(Device(id="d3", name="FW", device_type=DeviceType.FIREWALL, management_ip="10.0.0.3"))

    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()

    for node_id in ["d1", "d2", "d3"]:
        dt = kg.graph.nodes[node_id].get("device_type")
        assert type(dt) is str, (
            f"Node {node_id} device_type is {type(dt).__name__}, expected plain str (not Enum)"
        )
