"""Tests for topology query endpoints."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import networkx as nx


@pytest.fixture
def kg_and_client():
    mock_kg = MagicMock()
    g = nx.DiGraph()
    g.add_node("r1", node_type="device", label="Router1")
    g.add_node("r2", node_type="device", label="Router2")
    g.add_node("r3", node_type="device", label="Router3")
    g.add_edge("r1", "r2", confidence=0.9, edge_type="connected_to")
    g.add_edge("r2", "r3", confidence=0.8, edge_type="connected_to")
    g.add_edge("r1", "r3", confidence=0.5, edge_type="routes_to")
    mock_kg.graph = g
    mock_kg.find_k_shortest_paths = MagicMock(return_value=[["r1", "r3"], ["r1", "r2", "r3"]])
    mock_kg.find_candidate_devices = MagicMock(return_value=[
        {"device_id": "r1", "name": "Router1", "ip": "10.0.0.1"},
    ])
    mock_kg.boost_edge_confidence = MagicMock()

    from src.api.main import app
    from src.api import topology_query_endpoints as tqe
    original = tqe._knowledge_graph
    tqe._knowledge_graph = mock_kg
    client = TestClient(app)
    yield mock_kg, client
    tqe._knowledge_graph = original


class TestPathFinding:
    def test_find_paths(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths?src=r1&dst=r3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["paths"]) == 2
        kg.find_k_shortest_paths.assert_called_once_with("r1", "r3", 3)

    def test_find_paths_with_k(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths?src=r1&dst=r3&k=1")
        assert resp.status_code == 200
        kg.find_k_shortest_paths.assert_called_with("r1", "r3", 1)

    def test_find_paths_missing_params(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/paths")
        assert resp.status_code == 422


class TestIPResolution:
    def test_resolve_ip(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.get("/api/v4/network/query/resolve-ip?ip=10.0.0.1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 1

    def test_resolve_ip_missing(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/resolve-ip")
        assert resp.status_code == 422


class TestDeviceNeighbors:
    def test_get_neighbors(self, kg_and_client):
        _, client = kg_and_client
        resp = client.get("/api/v4/network/query/neighbors/r1")
        assert resp.status_code == 200
        data = resp.json()
        assert "neighbors" in data

    def test_neighbors_not_found(self, kg_and_client):
        kg, client = kg_and_client
        kg.graph = nx.DiGraph()  # empty graph
        resp = client.get("/api/v4/network/query/neighbors/nonexistent")
        assert resp.status_code == 404


class TestEdgeConfidence:
    def test_boost_confidence(self, kg_and_client):
        kg, client = kg_and_client
        resp = client.post("/api/v4/network/query/boost-confidence", json={"src": "r1", "dst": "r2"})
        assert resp.status_code == 200
        kg.boost_edge_confidence.assert_called_once()
