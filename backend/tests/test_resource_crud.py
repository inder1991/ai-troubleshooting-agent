"""Tests for core resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="d1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))

    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestSubnetCRUD:
    def test_create_subnet(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/subnets", json={
            "id": "sub1", "cidr": "10.0.0.0/24", "description": "Test subnet"
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "sub1"

    def test_create_subnet_invalid_cidr(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/subnets", json={
            "id": "sub1", "cidr": "not-a-cidr"
        })
        assert resp.status_code == 422

    def test_list_subnets(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Subnet
        store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
        resp = client.get("/api/v4/network/resources/subnets")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestInterfaceCRUD:
    def test_create_interface(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/interfaces", json={
            "id": "if1", "device_id": "d1", "name": "eth0", "ip": "10.0.0.1"
        })
        assert resp.status_code == 201

    def test_list_interfaces(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Interface
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0"))
        resp = client.get("/api/v4/network/resources/interfaces")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_interfaces_filter_by_device(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Interface
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0"))
        store.add_device(Device(id="d2", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))
        store.add_interface(Interface(id="if2", device_id="d2", name="eth1"))
        resp = client.get("/api/v4/network/resources/interfaces?device_id=d1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "d1"


class TestRouteCRUD:
    def test_create_route(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/routes", json={
            "id": "rt1", "device_id": "d1", "destination_cidr": "0.0.0.0/0",
            "next_hop": "10.0.0.1", "protocol": "static"
        })
        assert resp.status_code == 201

    def test_list_routes(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Route
        store.add_route(Route(id="rt1", device_id="d1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1"))
        resp = client.get("/api/v4/network/resources/routes")
        assert resp.status_code == 200

    def test_list_routes_filter_by_device(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Route
        store.add_route(Route(id="rt1", device_id="d1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1"))
        store.add_device(Device(id="d2", name="Switch1", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))
        store.add_route(Route(id="rt2", device_id="d2", destination_cidr="192.168.0.0/16", next_hop="10.0.0.2"))
        resp = client.get("/api/v4/network/resources/routes?device_id=d1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "d1"


class TestZoneCRUD:
    def test_create_zone(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/zones", json={
            "id": "z1", "name": "DMZ", "security_level": 50
        })
        assert resp.status_code == 201

    def test_list_zones(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Zone
        store.add_zone(Zone(id="z1", name="DMZ"))
        resp = client.get("/api/v4/network/resources/zones")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
