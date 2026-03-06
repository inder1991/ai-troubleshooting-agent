"""Tests for DNS monitoring API endpoints."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock influxdb_client before importing
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDNSConfigEndpoints:
    def test_get_dns_config(self, client):
        resp = client.get("/api/v4/dns/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "servers" in data
        assert "watched_hostnames" in data
        assert "enabled" in data

    def test_update_dns_config(self, client):
        config = {
            "servers": [{"id": "dns-1", "name": "Google", "ip": "8.8.8.8"}],
            "watched_hostnames": [
                {"hostname": "api.example.com", "record_type": "A",
                 "expected_values": ["10.0.0.1"], "critical": True},
            ],
            "query_timeout": 5.0,
            "enabled": True,
        }
        resp = client.put("/api/v4/dns/config", json=config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["servers"][0]["ip"] == "8.8.8.8"

    def test_add_dns_server(self, client):
        server = {"id": "dns-new", "name": "Cloudflare", "ip": "1.1.1.1"}
        resp = client.post("/api/v4/dns/servers", json=server)
        assert resp.status_code == 200

    def test_remove_dns_server(self, client):
        server = {"id": "dns-del", "name": "ToDelete", "ip": "9.9.9.9"}
        client.post("/api/v4/dns/servers", json=server)
        resp = client.delete("/api/v4/dns/servers/dns-del")
        assert resp.status_code == 200

    def test_add_watched_hostname(self, client):
        hostname = {"hostname": "new.example.com", "record_type": "A", "critical": False}
        resp = client.post("/api/v4/dns/hostnames", json=hostname)
        assert resp.status_code == 200

    def test_remove_watched_hostname(self, client):
        hostname = {"hostname": "remove.example.com", "record_type": "A"}
        client.post("/api/v4/dns/hostnames", json=hostname)
        resp = client.delete("/api/v4/dns/hostnames/remove.example.com")
        assert resp.status_code == 200


class TestDNSQueryEndpoints:
    def test_query_dns_now(self, client):
        resp = client.post("/api/v4/dns/query", json={
            "hostname": "example.com", "record_type": "A", "server_ip": "8.8.8.8",
        })
        assert resp.status_code in (200, 500)

    def test_get_dns_metrics(self, client):
        resp = client.get("/api/v4/dns/metrics", params={"range": "1h"})
        assert resp.status_code == 200

    def test_get_dns_nxdomain_counts(self, client):
        resp = client.get("/api/v4/dns/nxdomain")
        assert resp.status_code == 200
