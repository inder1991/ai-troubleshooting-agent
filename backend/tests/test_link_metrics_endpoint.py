"""Tests for link metrics endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.upsert_link_metric("r1", "r2", 5.0, 1_000_000_000, 0.001, 0.45)
    store.upsert_link_metric("r2", "r1", 6.0, 1_000_000_000, 0.002, 0.30)

    from src.api.main import app
    import src.api.monitor_endpoints as mon_ep
    orig = mon_ep._topology_store
    mon_ep._topology_store = store
    client = TestClient(app)
    yield store, client
    mon_ep._topology_store = orig


class TestLinkMetrics:
    def test_list_all_link_metrics(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_filter_by_src(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics?src_id=r1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["src_device_id"] == "r1"

    def test_filter_by_dst(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/monitor/link-metrics?dst_id=r1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["dst_device_id"] == "r1"

    def test_empty_when_no_store(self):
        from src.api.main import app
        import src.api.monitor_endpoints as mon_ep
        orig = mon_ep._topology_store
        mon_ep._topology_store = None
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/monitor/link-metrics")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            mon_ep._topology_store = orig
