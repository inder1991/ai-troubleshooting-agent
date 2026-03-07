"""Tests for drift event management endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    device = Device(id="d1", name="Router1", vendor="cisco",
                    device_type=DeviceType.ROUTER, management_ip="10.0.0.1")
    store.add_device(device)
    # Create drift events
    store.upsert_drift_event("device", "d1", "config_drift", "hostname",
                              "Router1", "Router1-old", "warning")
    store.upsert_drift_event("device", "d1", "config_drift", "acl_count",
                              "10", "8", "critical")

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep
    orig = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig


class TestDriftResolution:
    def test_list_active_drifts(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["drifts"]) == 2

    def test_resolve_drift(self, store_and_client):
        store, client = store_and_client
        drifts = store.list_active_drift_events()
        event_id = drifts[0]["id"]
        resp = client.post(f"/api/v4/network/monitor/drift/{event_id}/resolve")
        assert resp.status_code == 200
        remaining = store.list_active_drift_events()
        assert len(remaining) == 1

    def test_resolve_nonexistent_drift(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/monitor/drift/nonexistent/resolve")
        assert resp.status_code == 200  # Idempotent

    def test_resolve_all_drifts(self, store_and_client):
        store, client = store_and_client
        resp = client.post("/api/v4/network/monitor/drift/resolve-all")
        assert resp.status_code == 200
        remaining = store.list_active_drift_events()
        assert len(remaining) == 0
