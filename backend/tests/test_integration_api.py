"""Tests for V5 integration CRUD API endpoints."""

import pytest
import os
import tempfile
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_store():
    """Reset integration store for each test."""
    import src.api.routes_v5 as rv5
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    rv5._db_path = tmp_path
    rv5._integration_store = None
    yield
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


def _make_integration_payload(**overrides):
    base = {
        "name": "Test Cluster",
        "cluster_type": "openshift",
        "cluster_url": "https://api.test:6443",
        "auth_method": "token",
        "auth_data": "sha256~test",
    }
    base.update(overrides)
    return base


class TestIntegrationAPI:
    def test_add_integration(self, client):
        resp = client.post("/api/v5/integrations", json=_make_integration_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Cluster"
        assert "id" in data
        assert data["cluster_type"] == "openshift"
        assert data["status"] == "active"

    def test_list_integrations(self, client):
        client.post("/api/v5/integrations", json=_make_integration_payload(name="A"))
        client.post("/api/v5/integrations", json=_make_integration_payload(name="B"))
        resp = client.get("/api/v5/integrations")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_integrations_empty(self, client):
        resp = client.get("/api/v5/integrations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_integration(self, client):
        add = client.post("/api/v5/integrations", json=_make_integration_payload(name="Get Test"))
        iid = add.json()["id"]
        resp = client.get(f"/api/v5/integrations/{iid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"

    def test_update_integration(self, client):
        add = client.post("/api/v5/integrations", json=_make_integration_payload(name="Original"))
        iid = add.json()["id"]
        updated_payload = _make_integration_payload(name="Updated")
        resp = client.put(f"/api/v5/integrations/{iid}", json=updated_payload)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["id"] == iid

    def test_delete_integration(self, client):
        add = client.post("/api/v5/integrations", json=_make_integration_payload(name="Del Test"))
        iid = add.json()["id"]
        del_resp = client.delete(f"/api/v5/integrations/{iid}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"
        assert client.get(f"/api/v5/integrations/{iid}").status_code == 404

    def test_get_nonexistent(self, client):
        assert client.get("/api/v5/integrations/fake-id").status_code == 404

    def test_delete_nonexistent(self, client):
        assert client.delete("/api/v5/integrations/fake-id").status_code == 404

    def test_update_nonexistent(self, client):
        resp = client.put("/api/v5/integrations/fake-id", json=_make_integration_payload())
        assert resp.status_code == 404

    def test_add_with_optional_urls(self, client):
        payload = _make_integration_payload(
            prometheus_url="http://prom:9090",
            elasticsearch_url="http://es:9200",
        )
        resp = client.post("/api/v5/integrations", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["prometheus_url"] == "http://prom:9090"
        assert data["elasticsearch_url"] == "http://es:9200"
