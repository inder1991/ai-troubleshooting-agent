"""Tests for multi-instance adapter registry, topology store CRUD, API endpoints, and Panorama discovery."""
import os
import sys
import json
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.network.adapters.registry import AdapterRegistry
from src.network.adapters.base import FirewallAdapter
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import (
    FirewallVendor, AdapterInstance, AdapterConfig, AdapterHealth, AdapterHealthStatus,
)
from src.network.topology_store import TopologyStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_adapter(vendor: FirewallVendor = FirewallVendor.PALO_ALTO) -> MockFirewallAdapter:
    return MockFirewallAdapter(vendor=vendor, api_endpoint="https://test.example.com", api_key="key123")


def _make_instance(label="Test PA", vendor=FirewallVendor.PALO_ALTO, **kw) -> AdapterInstance:
    return AdapterInstance(label=label, vendor=vendor, api_endpoint="https://pa.example.com", **kw)


def _temp_store() -> TopologyStore:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return TopologyStore(db_path=path)


# ===========================================================================
# TestAdapterRegistry
# ===========================================================================

class TestAdapterRegistry:
    def test_register_and_get_by_instance(self):
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter)
        assert reg.get_by_instance("inst-1") is adapter
        assert reg.get_by_instance("nonexistent") is None

    def test_get_by_device(self):
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter, device_ids=["fw-node-1", "fw-node-2"])
        assert reg.get_by_device("fw-node-1") is adapter
        assert reg.get_by_device("fw-node-2") is adapter
        assert reg.get_by_device("unknown") is None

    def test_remove(self):
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter, device_ids=["fw-1"])
        reg.remove("inst-1")
        assert reg.get_by_instance("inst-1") is None
        assert reg.get_by_device("fw-1") is None

    def test_bind_and_unbind_device(self):
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter)
        reg.bind_device("dev-A", "inst-1")
        assert reg.get_by_device("dev-A") is adapter
        reg.unbind_device("dev-A")
        assert reg.get_by_device("dev-A") is None

    def test_backward_compat_get(self):
        """The .get() method tries device_id first, then instance_id."""
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter, device_ids=["dev-1"])
        # By device_id
        assert reg.get("dev-1") is adapter
        # By instance_id
        assert reg.get("inst-1") is adapter
        # Not found
        assert reg.get("missing") is None
        assert reg.get("missing", "default") == "default"

    def test_contains(self):
        reg = AdapterRegistry()
        adapter = _make_mock_adapter()
        reg.register("inst-1", adapter, device_ids=["dev-1"])
        assert "inst-1" in reg
        assert "dev-1" in reg
        assert "nope" not in reg

    def test_len_and_items(self):
        reg = AdapterRegistry()
        reg.register("a", _make_mock_adapter())
        reg.register("b", _make_mock_adapter())
        assert len(reg) == 2
        assert set(dict(reg.items()).keys()) == {"a", "b"}

    def test_all_instances_and_device_bindings(self):
        reg = AdapterRegistry()
        a1 = _make_mock_adapter()
        a2 = _make_mock_adapter(vendor=FirewallVendor.AWS_SG)
        reg.register("inst-1", a1, device_ids=["d1"])
        reg.register("inst-2", a2, device_ids=["d2", "d3"])
        assert len(reg.all_instances()) == 2
        assert reg.device_bindings() == {"d1": "inst-1", "d2": "inst-2", "d3": "inst-2"}


# ===========================================================================
# TestTopologyStoreAdapterInstances
# ===========================================================================

class TestTopologyStoreAdapterInstances:
    def test_save_and_get(self):
        store = _temp_store()
        inst = _make_instance()
        store.save_adapter_instance(inst)
        loaded = store.get_adapter_instance(inst.instance_id)
        assert loaded is not None
        assert loaded.label == "Test PA"
        assert loaded.vendor == FirewallVendor.PALO_ALTO
        assert loaded.created_at != ""
        assert loaded.updated_at != ""

    def test_list_all(self):
        store = _temp_store()
        store.save_adapter_instance(_make_instance(label="A"))
        store.save_adapter_instance(_make_instance(label="B", vendor=FirewallVendor.AWS_SG))
        all_instances = store.list_adapter_instances()
        assert len(all_instances) == 2

    def test_list_by_vendor(self):
        store = _temp_store()
        store.save_adapter_instance(_make_instance(label="PA-1"))
        store.save_adapter_instance(_make_instance(label="PA-2"))
        store.save_adapter_instance(_make_instance(label="AWS-1", vendor=FirewallVendor.AWS_SG))
        pa_instances = store.list_adapter_instances_by_vendor("palo_alto")
        assert len(pa_instances) == 2

    def test_update_preserves_created_at(self):
        store = _temp_store()
        inst = _make_instance()
        store.save_adapter_instance(inst)
        first = store.get_adapter_instance(inst.instance_id)
        created_at_1 = first.created_at

        # Update
        inst.label = "Updated"
        store.save_adapter_instance(inst)
        second = store.get_adapter_instance(inst.instance_id)
        assert second.label == "Updated"
        assert second.created_at == created_at_1  # preserved

    def test_delete_cascades_bindings(self):
        store = _temp_store()
        inst = _make_instance()
        store.save_adapter_instance(inst)
        store.save_device_binding("dev-1", inst.instance_id)
        store.save_device_binding("dev-2", inst.instance_id)
        assert len(store.list_device_bindings_for_instance(inst.instance_id)) == 2

        store.delete_adapter_instance(inst.instance_id)
        assert store.get_adapter_instance(inst.instance_id) is None
        assert len(store.list_device_bindings_for_instance(inst.instance_id)) == 0

    def test_device_bindings(self):
        store = _temp_store()
        store.save_device_binding("dev-A", "inst-1")
        store.save_device_binding("dev-B", "inst-1")
        store.save_device_binding("dev-C", "inst-2")

        all_bindings = store.list_device_bindings()
        assert len(all_bindings) == 3

        inst1_bindings = store.list_device_bindings_for_instance("inst-1")
        assert set(inst1_bindings) == {"dev-A", "dev-B"}

        store.delete_device_binding("dev-A")
        assert len(store.list_device_bindings_for_instance("inst-1")) == 1

    def test_migration_from_old_table(self):
        store = _temp_store()
        # Insert into old adapter_configs table
        config = AdapterConfig(
            vendor=FirewallVendor.PALO_ALTO,
            api_endpoint="https://old-panorama.example.com",
            api_key="old-key",
            extra_config={"device_group": "DG1"},
        )
        store.save_adapter_config(config)

        # Force re-migration
        store._migrate_adapter_configs()

        instances = store.list_adapter_instances()
        assert len(instances) >= 1
        migrated = [i for i in instances if i.api_endpoint == "https://old-panorama.example.com"]
        assert len(migrated) == 1
        assert migrated[0].vendor == FirewallVendor.PALO_ALTO

    def test_migration_idempotent(self):
        store = _temp_store()
        config = AdapterConfig(
            vendor=FirewallVendor.PALO_ALTO,
            api_endpoint="https://panorama.example.com",
            api_key="key",
        )
        store.save_adapter_config(config)
        store._migrate_adapter_configs()
        count_1 = len(store.list_adapter_instances())
        store._migrate_adapter_configs()
        count_2 = len(store.list_adapter_instances())
        assert count_1 == count_2  # no duplicates


# ===========================================================================
# TestAdapterInstanceEndpoints
# ===========================================================================

class TestAdapterInstanceEndpoints:
    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create a TestClient with a fresh store for each test."""
        from fastapi.testclient import TestClient
        from src.api.main import create_app
        from src.api import network_endpoints

        # Use a temp DB
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._temp_path = path
        temp_store = TopologyStore(db_path=path)

        # Patch the module-level singletons
        network_endpoints._topology_store = temp_store
        network_endpoints._adapter_registry = AdapterRegistry()

        app = create_app()
        self.client = TestClient(app)
        yield
        os.unlink(path)

    def test_create_and_list(self):
        # Create
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "Test PA",
            "vendor": "palo_alto",
            "api_endpoint": "https://pa.test.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        instance_id = data["instance_id"]

        # List
        resp = self.client.get("/api/v4/network/adapters")
        assert resp.status_code == 200
        adapters = resp.json()["adapters"]
        assert len(adapters) == 1
        assert adapters[0]["label"] == "Test PA"
        # API key should be stripped
        assert "api_key" not in adapters[0]

    def test_get_instance(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "Get Test",
            "vendor": "aws_sg",
        })
        iid = resp.json()["instance_id"]

        resp = self.client.get(f"/api/v4/network/adapters/{iid}")
        assert resp.status_code == 200
        assert resp.json()["label"] == "Get Test"

    def test_update_instance(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "Before",
            "vendor": "palo_alto",
        })
        iid = resp.json()["instance_id"]

        resp = self.client.put(f"/api/v4/network/adapters/{iid}", json={
            "label": "After",
        })
        assert resp.status_code == 200

        resp = self.client.get(f"/api/v4/network/adapters/{iid}")
        assert resp.json()["label"] == "After"

    def test_delete_instance(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "ToDelete",
            "vendor": "palo_alto",
        })
        iid = resp.json()["instance_id"]

        resp = self.client.delete(f"/api/v4/network/adapters/{iid}")
        assert resp.status_code == 200

        resp = self.client.get(f"/api/v4/network/adapters/{iid}")
        assert resp.status_code == 404

    def test_test_connection(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "TestConn",
            "vendor": "palo_alto",
            "api_endpoint": "https://unreachable.test",
        })
        iid = resp.json()["instance_id"]

        resp = self.client.post(f"/api/v4/network/adapters/{iid}/test")
        assert resp.status_code == 200
        # Mock adapter should respond with some status

    def test_test_new(self):
        resp = self.client.post("/api/v4/network/adapters/test-new", json={
            "label": "Unsaved",
            "vendor": "palo_alto",
            "api_endpoint": "https://test.example.com",
        })
        assert resp.status_code == 200

    def test_bind_devices(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "BindTest",
            "vendor": "palo_alto",
        })
        iid = resp.json()["instance_id"]

        resp = self.client.post(f"/api/v4/network/adapters/{iid}/bind", json={
            "device_ids": ["fw-node-1", "fw-node-2"],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "bound"

    def test_invalid_vendor(self):
        resp = self.client.post("/api/v4/network/adapters", json={
            "label": "Bad",
            "vendor": "nonexistent_vendor",
        })
        assert resp.status_code == 400

    def test_not_found(self):
        resp = self.client.get("/api/v4/network/adapters/nonexistent-id")
        assert resp.status_code == 404


# ===========================================================================
# TestPanoramaDiscover
# ===========================================================================

class TestPanoramaDiscover:
    @pytest.mark.asyncio
    async def test_discover_standalone_returns_empty(self):
        """Standalone firewalls have no device groups."""
        from src.network.adapters.panorama_adapter import PanoramaAdapter, HAS_PANOS
        if not HAS_PANOS:
            pytest.skip("pan-os-python not installed")

        adapter = PanoramaAdapter(
            hostname="10.0.0.1", api_key="testkey", device_group="", vsys="vsys1",
        )
        # Standalone — should not attempt Panorama DG fetch
        # We mock _connect to return a non-Panorama object
        mock_fw = MagicMock()
        mock_fw.__class__ = type("Firewall", (), {})
        adapter._panos_device = mock_fw

        result = await adapter.discover_device_groups()
        assert result == []

    @pytest.mark.asyncio
    async def test_discover_with_mock_panorama(self):
        """When panos is available, discover should query Panorama for DGs."""
        from src.network.adapters.panorama_adapter import PanoramaAdapter, HAS_PANOS
        if not HAS_PANOS:
            pytest.skip("pan-os-python not installed")

        import panos.panorama

        adapter = PanoramaAdapter(
            hostname="panorama.test", api_key="key", device_group="DG1",
        )

        mock_panorama = MagicMock(spec=panos.panorama.Panorama)
        adapter._panos_device = mock_panorama

        mock_dg = MagicMock()
        mock_dg.name = "DeviceGroup-A"
        mock_dg.children = []

        with patch("panos.panorama.DeviceGroup.refreshall", return_value=[mock_dg]):
            result = await adapter.discover_device_groups()
            assert len(result) == 1
            assert result[0]["name"] == "DeviceGroup-A"


# ===========================================================================
# Run with: python3 -m pytest backend/tests/test_adapter_registry.py -v
# ===========================================================================
