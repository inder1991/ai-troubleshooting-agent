"""Tests for bulk export endpoints."""
import csv
import io
import pytest

from src.network.models import Device, DeviceType, Subnet, Interface
from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="d1", name="Router1", vendor="cisco", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="Switch1", vendor="juniper", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))
    store.add_interface(Interface(id="i1", device_id="d1", name="eth0", ip="10.0.0.1"))
    store.add_interface(Interface(id="i2", device_id="d1", name="eth1", ip="10.0.1.1"))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", description="Office LAN"))

    from src.api.main import app
    from src.api import export_endpoints
    original = export_endpoints._topology_store
    export_endpoints._topology_store = store

    from starlette.testclient import TestClient
    client = TestClient(app)
    yield store, client
    export_endpoints._topology_store = original


class TestDeviceExport:
    def test_export_devices_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/devices?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Router1"

    def test_export_devices_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/devices?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "Router1"


class TestSubnetExport:
    def test_export_subnets_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/subnets?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_export_subnets_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/subnets?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


class TestInterfaceExport:
    def test_export_interfaces_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/interfaces?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_export_interfaces_csv(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/interfaces?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


class TestAlertRulesExport:
    def test_export_alert_rules_json(self, store_and_client):
        _, client = store_and_client
        resp = client.get("/api/v4/network/export/alert-rules?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
