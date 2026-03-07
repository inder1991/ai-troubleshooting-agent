"""Tests for offset/limit pagination on TopologyStore list methods and API endpoints."""
import os
import pytest
from unittest.mock import patch

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_pagination.db")
    return TopologyStore(db_path=db_path)


def _make_device(i: int) -> Device:
    return Device(
        id=f"dev-{i:03d}",
        name=f"Device-{i}",
        device_type=DeviceType.HOST,
        management_ip=f"10.0.{i // 256}.{i % 256}",
    )


def _seed_devices(store: TopologyStore, n: int = 25):
    """Insert *n* devices into the store."""
    for i in range(n):
        store.add_device(_make_device(i))


def _seed_device_statuses(store: TopologyStore, n: int = 25):
    """Insert *n* device statuses (devices must already exist)."""
    for i in range(n):
        store.upsert_device_status(f"dev-{i:03d}", "up", float(i), 0.0, "icmp")


# ---------------------------------------------------------------------------
# list_devices pagination
# ---------------------------------------------------------------------------

class TestListDevicesPagination:
    def test_no_args_returns_all(self, store):
        """list_devices() with no args returns all devices (backwards compat)."""
        _seed_devices(store, 25)
        devices = store.list_devices()
        assert len(devices) == 25

    def test_limit_returns_exact_count(self, store):
        """list_devices(limit=10) returns exactly 10 items."""
        _seed_devices(store, 25)
        devices = store.list_devices(limit=10)
        assert len(devices) == 10

    def test_offset_and_limit_returns_page_2(self, store):
        """list_devices(offset=10, limit=10) returns second page."""
        _seed_devices(store, 25)
        page1 = store.list_devices(offset=0, limit=10)
        page2 = store.list_devices(offset=10, limit=10)
        assert len(page2) == 10
        # Pages must not overlap
        page1_ids = {d.id for d in page1}
        page2_ids = {d.id for d in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_offset_past_end_returns_empty(self, store):
        """list_devices(offset=100, limit=10) returns empty when past end."""
        _seed_devices(store, 25)
        devices = store.list_devices(offset=100, limit=10)
        assert devices == []

    def test_last_partial_page(self, store):
        """When offset+limit exceeds total, return remaining items."""
        _seed_devices(store, 25)
        devices = store.list_devices(offset=20, limit=10)
        assert len(devices) == 5


# ---------------------------------------------------------------------------
# list_device_statuses pagination
# ---------------------------------------------------------------------------

class TestListDeviceStatusesPagination:
    def test_limit_returns_exact_count(self, store):
        """list_device_statuses(limit=5) returns exactly 5 items."""
        _seed_devices(store, 25)
        _seed_device_statuses(store, 25)
        statuses = store.list_device_statuses(limit=5)
        assert len(statuses) == 5

    def test_offset_returns_remaining(self, store):
        """list_device_statuses(offset=20, limit=10) returns remaining items."""
        _seed_devices(store, 25)
        _seed_device_statuses(store, 25)
        statuses = store.list_device_statuses(offset=20, limit=10)
        assert len(statuses) == 5

    def test_no_args_returns_all(self, store):
        """list_device_statuses() with no args returns all (backwards compat)."""
        _seed_devices(store, 25)
        _seed_device_statuses(store, 25)
        statuses = store.list_device_statuses()
        assert len(statuses) == 25


# ---------------------------------------------------------------------------
# count methods
# ---------------------------------------------------------------------------

class TestCountMethods:
    def test_count_devices(self, store):
        """count_devices() returns total count."""
        _seed_devices(store, 17)
        assert store.count_devices() == 17

    def test_count_devices_empty(self, store):
        """count_devices() returns 0 on empty table."""
        assert store.count_devices() == 0

    def test_count_device_statuses(self, store):
        """count_device_statuses() returns total count."""
        _seed_devices(store, 12)
        _seed_device_statuses(store, 12)
        assert store.count_device_statuses() == 12

    def test_count_device_statuses_empty(self, store):
        """count_device_statuses() returns 0 on empty table."""
        assert store.count_device_statuses() == 0


# ---------------------------------------------------------------------------
# API endpoint — GET /api/v4/network/monitor/devices
# ---------------------------------------------------------------------------

@pytest.fixture
def api_store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_api_pagination.db")
    s = TopologyStore(db_path=db_path)
    _seed_devices(s, 25)
    _seed_device_statuses(s, 25)
    return s


@pytest.fixture
def client(api_store):
    from src.network.knowledge_graph import NetworkKnowledgeGraph
    from src.network.adapters.registry import AdapterRegistry
    from src.network.monitor import NetworkMonitor

    kg = NetworkKnowledgeGraph(api_store)
    registry = AdapterRegistry()
    monitor = NetworkMonitor(api_store, kg, registry)

    with patch("src.api.monitor_endpoints._get_monitor", return_value=monitor), \
         patch("src.api.monitor_endpoints._get_topology_store", return_value=api_store), \
         patch("src.api.monitor_endpoints._get_knowledge_graph", return_value=kg):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


class TestDevicesEndpoint:
    def test_default_pagination(self, client):
        """GET /devices with defaults returns paginated envelope."""
        resp = client.get("/api/v4/network/monitor/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert data["total"] == 25
        assert data["offset"] == 0
        assert len(data["items"]) == 25  # default limit=100 > 25 items

    def test_with_limit(self, client):
        """GET /devices?limit=5 returns exactly 5 items."""
        resp = client.get("/api/v4/network/monitor/devices?limit=5")
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["total"] == 25
        assert data["limit"] == 5

    def test_with_offset_and_limit(self, client):
        """GET /devices?offset=20&limit=10 returns remaining items."""
        resp = client.get("/api/v4/network/monitor/devices?offset=20&limit=10")
        data = resp.json()
        assert len(data["items"]) == 5
        assert data["total"] == 25
        assert data["offset"] == 20

    def test_limit_capped_at_500(self, client):
        """Requesting limit > 500 is capped to 500."""
        resp = client.get("/api/v4/network/monitor/devices?limit=1000")
        data = resp.json()
        assert data["limit"] == 500

    def test_snapshot_still_returns_all(self, client):
        """The existing snapshot endpoint is not affected by pagination."""
        resp = client.get("/api/v4/network/monitor/snapshot")
        assert resp.status_code == 200
        # Snapshot should still work (may have different format)
        data = resp.json()
        assert "devices" in data
