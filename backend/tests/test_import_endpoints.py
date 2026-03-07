"""Tests for bulk device import endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    from src.api.main import app
    from src.api import export_endpoints

    original = export_endpoints._topology_store
    export_endpoints._topology_store = store
    client = TestClient(app)
    yield store, client
    export_endpoints._topology_store = original


class TestDeviceImport:
    def test_import_devices(self, store_and_client):
        store, client = store_and_client
        devices = [
            {
                "id": "d1",
                "name": "Router1",
                "vendor": "cisco",
                "device_type": "router",
                "management_ip": "10.0.0.1",
            },
            {
                "id": "d2",
                "name": "Switch1",
                "vendor": "juniper",
                "device_type": "switch",
                "management_ip": "10.0.0.2",
            },
        ]
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2

        # Verify devices exist in the store
        stored = store.list_devices()
        assert len(stored) == 2

    def test_import_updates_existing(self, store_and_client):
        store, client = store_and_client
        devices = [
            {
                "id": "d1",
                "name": "Router1",
                "vendor": "cisco",
                "device_type": "router",
                "management_ip": "10.0.0.1",
            }
        ]
        client.post("/api/v4/network/export/devices/import", json=devices)

        # Import again with updated name
        devices[0]["name"] = "Router1-Updated"
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        assert resp.status_code == 200

        stored = store.list_devices()
        assert len(stored) == 1
        assert stored[0].name == "Router1-Updated"

    def test_import_empty_list(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/export/devices/import", json=[])
        assert resp.status_code == 200
        assert resp.json()["imported"] == 0

    def test_import_invalid_device_type(self, store_and_client):
        _, client = store_and_client
        devices = [
            {
                "id": "d1",
                "name": "Bad",
                "vendor": "x",
                "device_type": "INVALID",
                "management_ip": "1.2.3.4",
            }
        ]
        resp = client.post("/api/v4/network/export/devices/import", json=devices)
        # Should handle gracefully -- defaults to HOST
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1
