"""Tests for Bulk Device Actions — Task 57."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


@pytest.fixture
def mock_store():
    """Create a mock InstanceStore with test devices."""
    store = MagicMock()
    # In-memory device store
    devices = {}

    def make_device(did, tags=None):
        d = MagicMock()
        d.device_id = did
        d.tags = list(tags or [])
        d.management_ip = f"10.0.0.{did[-1]}"
        d.ping_config = MagicMock()
        return d

    devices["dev-1"] = make_device("dev-1", tags=["prod", "dc1"])
    devices["dev-2"] = make_device("dev-2", tags=["staging", "dc2"])
    devices["dev-3"] = make_device("dev-3", tags=["prod", "dc1"])

    def get_device(did):
        return devices.get(did)

    def delete_device(did):
        if did in devices:
            del devices[did]
            return True
        return False

    def upsert_device(device):
        devices[device.device_id] = device

    store.get_device = get_device
    store.delete_device = delete_device
    store.upsert_device = upsert_device
    store.list_devices = lambda: list(devices.values())
    store._devices = devices  # expose for test assertions
    return store


@pytest.fixture
def client(mock_store):
    """Create test client with mocked collector store."""
    import src.api.collector_endpoints as ep

    # Patch the module-level singleton
    original_store = ep._instance_store
    ep._instance_store = mock_store

    app = FastAPI()
    app.include_router(ep.collector_router)
    tc = TestClient(app)
    yield tc

    ep._instance_store = original_store


class TestBulkDelete:
    def test_bulk_delete_removes_devices(self, client, mock_store):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1", "dev-2"], "action": "delete"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "delete"
        assert data["results"]["dev-1"]["success"] is True
        assert data["results"]["dev-2"]["success"] is True
        # Devices should be removed
        assert "dev-1" not in mock_store._devices
        assert "dev-2" not in mock_store._devices
        assert "dev-3" in mock_store._devices

    def test_bulk_delete_nonexistent_device(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["no-such-device"], "action": "delete"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["no-such-device"]["success"] is False


class TestBulkAddTag:
    def test_bulk_add_tag(self, client, mock_store):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1", "dev-2"], "action": "add_tag", "tag": "critical"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["dev-1"]["success"] is True
        assert "critical" in data["results"]["dev-1"]["tags"]
        assert data["results"]["dev-2"]["success"] is True
        assert "critical" in data["results"]["dev-2"]["tags"]

    def test_bulk_add_tag_idempotent(self, client, mock_store):
        """Adding a tag that already exists should not duplicate it."""
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1"], "action": "add_tag", "tag": "prod"},
        )
        assert resp.status_code == 200
        tags = resp.json()["results"]["dev-1"]["tags"]
        assert tags.count("prod") == 1

    def test_bulk_add_tag_missing_tag_field(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1"], "action": "add_tag"},
        )
        assert resp.status_code == 400

    def test_bulk_add_tag_nonexistent_device(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["no-such-device"], "action": "add_tag", "tag": "x"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"]["no-such-device"]["success"] is False


class TestBulkRemoveTag:
    def test_bulk_remove_tag(self, client, mock_store):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1", "dev-3"], "action": "remove_tag", "tag": "dc1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["dev-1"]["success"] is True
        assert "dc1" not in data["results"]["dev-1"]["tags"]
        assert data["results"]["dev-3"]["success"] is True
        assert "dc1" not in data["results"]["dev-3"]["tags"]

    def test_bulk_remove_tag_not_present(self, client):
        """Removing a tag that doesn't exist should succeed without error."""
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1"], "action": "remove_tag", "tag": "nonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"]["dev-1"]["success"] is True

    def test_bulk_remove_tag_missing_tag_field(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1"], "action": "remove_tag"},
        )
        assert resp.status_code == 400


class TestBulkActionValidation:
    def test_invalid_action_returns_400(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1"], "action": "reboot"},
        )
        assert resp.status_code == 400
        assert "Invalid action" in resp.json()["detail"]

    def test_empty_device_ids_returns_400(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": [], "action": "delete"},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_response_includes_device_count(self, client):
        resp = client.post(
            "/api/collector/devices/bulk-action",
            json={"device_ids": ["dev-1", "dev-2"], "action": "delete"},
        )
        assert resp.status_code == 200
        assert resp.json()["device_count"] == 2
