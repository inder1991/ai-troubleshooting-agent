"""Tests for bulk create and delete operations."""
import pytest
from fastapi.testclient import TestClient
from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestBulkCreate:
    def test_bulk_create_devices(self, store_and_client):
        store, client = store_and_client
        devices = [{"id": f"d{i}", "name": f"Device{i}", "device_type": "host"} for i in range(5)]
        resp = client.post("/api/v4/network/resources/devices/bulk", json=devices)
        assert resp.status_code == 201
        assert resp.json()["created"] == 5

    def test_bulk_create_subnets(self, store_and_client):
        _, client = store_and_client
        subnets = [{"id": f"sub{i}", "cidr": f"10.{i}.0.0/24"} for i in range(3)]
        resp = client.post("/api/v4/network/resources/subnets/bulk", json=subnets)
        assert resp.status_code == 201
        assert resp.json()["created"] == 3

    def test_bulk_create_interfaces(self, store_and_client):
        store, client = store_and_client
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        ifaces = [{"id": f"if{i}", "device_id": "d1", "name": f"eth{i}"} for i in range(3)]
        resp = client.post("/api/v4/network/resources/interfaces/bulk", json=ifaces)
        assert resp.status_code == 201
        assert resp.json()["created"] == 3

    def test_bulk_create_routes(self, store_and_client):
        store, client = store_and_client
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        routes = [{"id": f"rt{i}", "device_id": "d1", "destination_cidr": f"10.{i}.0.0/24", "next_hop": "10.0.0.1"} for i in range(5)]
        resp = client.post("/api/v4/network/resources/routes/bulk", json=routes)
        assert resp.status_code == 201
        assert resp.json()["created"] == 5


class TestBulkDelete:
    def test_bulk_delete_devices(self, store_and_client):
        store, client = store_and_client
        for i in range(3):
            store.add_device(Device(id=f"d{i}", name=f"D{i}", device_type=DeviceType.HOST))
        resp = client.request("DELETE", "/api/v4/network/resources/devices/bulk", json={"ids": ["d0", "d1"]})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    def test_bulk_delete_empty(self, store_and_client):
        _, client = store_and_client
        resp = client.request("DELETE", "/api/v4/network/resources/devices/bulk", json={"ids": []})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0
