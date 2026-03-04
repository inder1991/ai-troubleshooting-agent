"""Tests for /api/v4/network/monitor endpoints."""
import os
import pytest
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.adapters.registry import AdapterRegistry


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def client(store, kg):
    from src.network.monitor import NetworkMonitor
    registry = AdapterRegistry()
    monitor = NetworkMonitor(store, kg, registry)

    with patch("src.api.monitor_endpoints._get_monitor", return_value=monitor), \
         patch("src.api.monitor_endpoints._get_topology_store", return_value=store), \
         patch("src.api.monitor_endpoints._get_knowledge_graph", return_value=kg):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


class TestSnapshotEndpoint:
    def test_snapshot_returns_empty(self, client):
        resp = client.get("/api/v4/network/monitor/snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert "devices" in data
        assert "links" in data
        assert "drifts" in data
        assert "candidates" in data

    def test_snapshot_returns_device_status(self, client, store):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        resp = client.get("/api/v4/network/monitor/snapshot")
        assert len(resp.json()["devices"]) == 1


class TestDriftEndpoint:
    def test_drift_list(self, client, store):
        store.upsert_drift_event("route", "rt1", "missing", "cidr", "10.0.0.0/8", "", "warning")
        resp = client.get("/api/v4/network/monitor/drift")
        assert resp.status_code == 200
        assert len(resp.json()["drifts"]) == 1


class TestDeviceHistory:
    def test_device_history(self, client, store):
        store.append_metric("device", "d1", "latency_ms", 5.0)
        resp = client.get("/api/v4/network/monitor/device/d1/history?period=24h")
        assert resp.status_code == 200
        assert len(resp.json()["history"]) >= 1


class TestDiscoveryPromote:
    def test_promote_candidate(self, client, store, kg):
        store.upsert_discovery_candidate("10.0.0.99", "", "printer", "probe", "")
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        resp = client.post("/api/v4/network/monitor/discover/10.0.0.99/promote", json={
            "name": "printer-1",
            "device_type": "HOST",
        })
        assert resp.status_code == 200
        assert resp.json()["device_id"]

    def test_dismiss_candidate(self, client, store):
        store.upsert_discovery_candidate("10.0.0.99", "", "", "probe", "")
        resp = client.post("/api/v4/network/monitor/discover/10.0.0.99/dismiss")
        assert resp.status_code == 200
        assert len(store.list_discovery_candidates()) == 0
