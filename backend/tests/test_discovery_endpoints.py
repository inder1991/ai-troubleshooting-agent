"""Tests for /api/v4/network/discovery endpoints."""
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def client(store, kg):
    with patch("src.api.discovery_endpoints._get_topology_store", return_value=store), \
         patch("src.api.discovery_endpoints._get_discovery_engine", return_value=None):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


@pytest.fixture
def mock_engine():
    """A mocked DiscoveryEngine."""
    engine = MagicMock()
    engine.probe_known_subnets = AsyncMock(return_value=[
        {"ip": "10.0.0.50", "mac": "", "hostname": "new-host",
         "discovered_via": "probe", "source_device_id": ""},
    ])
    engine.reverse_dns = AsyncMock(return_value="resolved.example.com")
    return engine


@pytest.fixture
def client_with_engine(store, kg, mock_engine):
    """Client with a mocked DiscoveryEngine available."""
    with patch("src.api.discovery_endpoints._get_topology_store", return_value=store), \
         patch("src.api.discovery_endpoints._get_discovery_engine", return_value=mock_engine):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


class TestCandidatesEndpoint:
    def test_list_empty(self, client):
        resp = client.get("/api/v4/network/discovery/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["candidates"] == []

    def test_list_with_candidates(self, client, store):
        store.upsert_discovery_candidate("10.0.0.99", "aa:bb:cc:dd:ee:ff",
                                         "printer", "probe", "")
        store.upsert_discovery_candidate("10.0.0.100", "", "cam-01",
                                         "adapter_neighbor", "sw1")
        resp = client.get("/api/v4/network/discovery/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 2
        ips = {c["ip"] for c in data["candidates"]}
        assert "10.0.0.99" in ips
        assert "10.0.0.100" in ips

    def test_dismissed_not_listed(self, client, store):
        store.upsert_discovery_candidate("10.0.0.99", "", "", "probe", "")
        store.dismiss_candidate("10.0.0.99")
        resp = client.get("/api/v4/network/discovery/candidates")
        assert resp.status_code == 200
        assert len(resp.json()["candidates"]) == 0


class TestScanEndpoint:
    def test_scan_returns_503_when_no_engine(self, client):
        resp = client.post("/api/v4/network/discovery/scan")
        assert resp.status_code == 503
        assert "not available" in resp.json()["detail"].lower()

    def test_scan_triggers_probe(self, client_with_engine, store):
        resp = client_with_engine.post("/api/v4/network/discovery/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert len(data["new_candidates"]) == 1
        assert data["new_candidates"][0]["ip"] == "10.0.0.50"


class TestReverseDnsEndpoint:
    def test_reverse_dns_returns_503_when_no_engine(self, client):
        resp = client.post("/api/v4/network/discovery/reverse-dns",
                           json={"ip": "10.0.0.1"})
        assert resp.status_code == 503

    def test_reverse_dns_resolves(self, client_with_engine):
        resp = client_with_engine.post("/api/v4/network/discovery/reverse-dns",
                                       json={"ip": "10.0.0.1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip"] == "10.0.0.1"
        assert data["hostname"] == "resolved.example.com"

    def test_reverse_dns_requires_ip(self, client_with_engine):
        resp = client_with_engine.post("/api/v4/network/discovery/reverse-dns",
                                       json={})
        assert resp.status_code == 422
