"""Tests for interface validation endpoint."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType, Interface, Subnet, Zone


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
    # Valid interface
    store.add_interface(Interface(id="if1", device_id="fw1", name="eth0", ip="10.0.0.1", subnet_id="sub1", zone_id="z1"))
    # Invalid: IP outside subnet
    store.add_interface(Interface(id="if2", device_id="fw1", name="eth1", ip="192.168.1.1", subnet_id="sub1", zone_id="z2"))
    store.add_zone(Zone(id="z1", name="Inside"))
    store.add_zone(Zone(id="z2", name="Outside"))

    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestValidationEndpoint:
    def test_validate_device(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/resources/validate/fw1")
        assert resp.status_code == 200
        data = resp.json()
        assert "errors" in data
        assert "device_id" in data
        # Should find rule 29 violation (IP outside subnet)
        assert any(e["rule"] == 29 for e in data["errors"])

    def test_validate_unknown_device(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/resources/validate/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["errors"] == []

    def test_validate_bulk(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/validate/bulk", json={"device_ids": ["fw1"]})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "fw1"

    def test_validate_bulk_empty(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/validate/bulk", json={"device_ids": []})
        assert resp.status_code == 200
        assert resp.json() == []
