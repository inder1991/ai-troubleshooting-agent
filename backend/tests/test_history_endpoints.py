"""Tests for device status and metric history endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    # Seed devices so foreign-key-like references are valid
    store.add_device(Device(id="d1", name="Router1", vendor="cisco", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="Switch1", vendor="juniper", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))

    # Seed device statuses
    store.upsert_device_status("d1", "up", 5.0, 0.0, "icmp")
    store.upsert_device_status("d2", "degraded", 150.0, 0.05, "icmp")

    # Seed metric history
    store.append_metric("device", "d1", "latency_ms", 5.0)
    store.append_metric("device", "d1", "latency_ms", 6.0)
    store.append_metric("device", "d1", "latency_ms", 7.0)

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep

    orig_store = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig_store


class TestDeviceStatusList:
    def test_list_device_statuses(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/device-statuses")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    def test_list_device_statuses_pagination(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/device-statuses?offset=0&limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2

    def test_list_device_statuses_offset(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/device-statuses?offset=1&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2

    def test_list_device_statuses_empty_when_no_store(self):
        """Endpoint returns empty list when topology store is not set."""
        from src.api.main import app
        import src.api.monitor_endpoints as mon_ep

        orig = mon_ep._topology_store
        mon_ep._topology_store = None
        client = TestClient(app)
        try:
            resp = client.get("/api/v4/network/monitor/device-statuses")
            assert resp.status_code == 200
            data = resp.json()
            assert data["items"] == []
            assert data["total"] == 0
        finally:
            mon_ep._topology_store = orig


class TestMetricHistory:
    def test_query_metric_history(self, store_and_client):
        _, client = store_and_client
        resp = client.get(
            "/api/v4/network/monitor/metric-history"
            "?entity_type=device&entity_id=d1&metric_name=latency_ms"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_query_metric_history_with_since(self, store_and_client):
        _, client = store_and_client
        # Use a far-future date so no results match
        resp = client.get(
            "/api/v4/network/monitor/metric-history"
            "?entity_type=device&entity_id=d1&metric_name=latency_ms"
            "&since=2099-01-01T00:00:00"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 0

    def test_query_metric_history_with_past_since(self, store_and_client):
        _, client = store_and_client
        # Use a past date so all results match
        resp = client.get(
            "/api/v4/network/monitor/metric-history"
            "?entity_type=device&entity_id=d1&metric_name=latency_ms"
            "&since=2000-01-01T00:00:00"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_query_metric_history_missing_params(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/metric-history")
        assert resp.status_code == 422  # validation error — missing required params

    def test_query_metric_history_empty_when_no_store(self):
        """Endpoint returns empty list when topology store is not set."""
        from src.api.main import app
        import src.api.monitor_endpoints as mon_ep

        orig = mon_ep._topology_store
        mon_ep._topology_store = None
        client = TestClient(app)
        try:
            resp = client.get(
                "/api/v4/network/monitor/metric-history"
                "?entity_type=device&entity_id=d1&metric_name=latency_ms"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data == []
        finally:
            mon_ep._topology_store = orig
