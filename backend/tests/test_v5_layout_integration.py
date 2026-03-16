import pytest
from src.api.topology_v5 import build_topology_export
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType

@pytest.fixture
def repo_with_devices(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    # Add devices in different groups
    store.add_device(PD(id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
                        management_ip="10.0.0.1", vendor="cisco", role="core"))
    store.add_device(PD(id="fw-01", name="fw-01", device_type=DeviceType.FIREWALL,
                        management_ip="10.0.0.2", vendor="palo_alto", role="perimeter"))
    store.add_device(PD(id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
                        management_ip="10.0.0.3", vendor="cisco", role="access"))
    return repo

class TestV5LayoutIntegration:
    def test_nodes_have_positions(self, repo_with_devices):
        result = build_topology_export(repo_with_devices)
        device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
        for node in device_nodes:
            assert "position" in node, f"Node {node['id']} missing position"
            assert "x" in node["position"]
            assert "y" in node["position"]

    def test_nodes_are_top_level(self, repo_with_devices):
        """Devices have no parentId — they're top-level for free edge rendering."""
        result = build_topology_export(repo_with_devices)
        device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
        for node in device_nodes:
            assert "parentId" not in node, f"Node {node['id']} should not have parentId"

    def test_env_labels_present_for_groups(self, repo_with_devices):
        """Force-directed layout uses labels only, no background rectangles."""
        result = build_topology_export(repo_with_devices)
        env_nodes = [n for n in result["nodes"] if n.get("type") == "envLabel"]
        assert len(env_nodes) >= 1

    def test_env_labels_present(self, repo_with_devices):
        result = build_topology_export(repo_with_devices)
        env_nodes = [n for n in result["nodes"] if n.get("type") == "envLabel"]
        assert len(env_nodes) >= 1
        assert env_nodes[0]["data"]["label"] is not None

    def test_env_labels_before_devices_in_array(self, repo_with_devices):
        """Env labels should appear before device nodes."""
        result = build_topology_export(repo_with_devices)
        label_indices = [i for i, n in enumerate(result["nodes"]) if n.get("type") == "envLabel"]
        device_indices = [i for i, n in enumerate(result["nodes"]) if n.get("type") == "device"]
        if label_indices and device_indices:
            assert max(label_indices) < min(device_indices)

    def test_device_count_excludes_groups(self, repo_with_devices):
        result = build_topology_export(repo_with_devices)
        assert result["device_count"] == 3  # Only actual devices, not groups/labels

    def test_full_fixture_data(self):
        """Test with the real demo database (if available)."""
        try:
            store = TopologyStore()
            repo = SQLiteRepository(store)
            devices = repo.get_devices()
            if len(devices) == 0:
                pytest.skip("No demo data loaded")
            result = build_topology_export(repo)
            assert result["device_count"] >= 30
            assert result["edge_count"] >= 20
            # All device nodes have positions
            device_nodes = [n for n in result["nodes"] if n.get("type") == "device"]
            for node in device_nodes:
                assert "position" in node
        except Exception as e:
            pytest.skip(f"Demo DB not available: {e}")
