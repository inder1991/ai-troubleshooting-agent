"""Tests for device search and network statistics endpoints."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Interface, Subnet
from src.api.search_endpoints import search_router, init_search_endpoints


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(
        id="r1", name="core-router-1", device_type=DeviceType.ROUTER,
        vendor="cisco", location="us-east",
    ))
    store.add_device(Device(
        id="r2", name="edge-router-2", device_type=DeviceType.ROUTER,
        vendor="juniper", location="us-west",
    ))
    store.add_device(Device(
        id="fw1", name="palo-fw-1", device_type=DeviceType.FIREWALL,
        vendor="palo_alto", location="us-east",
    ))
    store.add_device(Device(
        id="sw1", name="access-switch-1", device_type=DeviceType.SWITCH,
        vendor="cisco", location="eu-west",
    ))
    store.add_interface(Interface(id="if1", device_id="r1", name="eth0"))
    store.add_interface(Interface(id="if2", device_id="r1", name="eth1"))
    store.add_interface(Interface(id="if3", device_id="fw1", name="eth0"))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
    store.add_subnet(Subnet(id="sub2", cidr="10.0.1.0/24"))

    init_search_endpoints(store)

    app = FastAPI()
    app.include_router(search_router)
    client = TestClient(app)
    return store, client


class TestDeviceSearch:
    def test_search_by_name(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"name": "router"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2
        names = {d["name"] for d in data["devices"]}
        assert "core-router-1" in names
        assert "edge-router-2" in names

    def test_search_by_type(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"device_type": "firewall"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["id"] == "fw1"

    def test_search_by_vendor(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"vendor": "cisco"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2
        ids = {d["id"] for d in data["devices"]}
        assert ids == {"r1", "sw1"}

    def test_search_by_location(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"location": "us-east"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2
        ids = {d["id"] for d in data["devices"]}
        assert ids == {"r1", "fw1"}

    def test_combined_filters(self, store_and_client):
        _, client = store_and_client
        resp = client.get(
            "/api/v4/network/search/devices",
            params={"vendor": "cisco", "location": "us-east"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["id"] == "r1"

    def test_pagination(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2
        assert data["total"] >= 4  # 4 devices total

    def test_pagination_offset(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"limit": 2, "offset": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 2
        assert data["total"] == 4

    def test_no_results(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices", params={"name": "nonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 0
        assert data["total"] == 0

    def test_no_filters_returns_all(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["devices"]) == 4
        assert data["total"] == 4


class TestStats:
    def test_get_stats(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/search/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 4
        assert data["total_interfaces"] == 3
        assert data["total_subnets"] == 2
        # by_type
        assert data["by_type"]["router"] == 2
        assert data["by_type"]["firewall"] == 1
        assert data["by_type"]["switch"] == 1
        # by_vendor
        assert data["by_vendor"]["cisco"] == 2
        assert data["by_vendor"]["juniper"] == 1
        assert data["by_vendor"]["palo_alto"] == 1

    def test_stats_empty_store(self, tmp_path):
        store = TopologyStore(str(tmp_path / "empty.db"))
        init_search_endpoints(store)
        app = FastAPI()
        app.include_router(search_router)
        client = TestClient(app)
        resp = client.get("/api/v4/network/search/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 0
        assert data["total_interfaces"] == 0
        assert data["total_subnets"] == 0
        assert data["by_type"] == {}
        assert data["by_vendor"] == {}
