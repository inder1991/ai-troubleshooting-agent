"""Tests for cloud API endpoints."""
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.cloud.api.router import create_cloud_router
from src.cloud.cloud_store import CloudStore


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


@pytest.fixture
def app(tmp_db):
    store = CloudStore(db_path=tmp_db)
    router = create_cloud_router(store)
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestAccountEndpoints:
    def test_list_accounts_empty(self, client):
        resp = client.get("/api/v4/cloud/accounts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_account(self, client):
        resp = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws",
            "display_name": "Production AWS",
            "credential_handle": "ref-001",
            "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "aws"
        assert "account_id" in data

    def test_get_account(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.get(f"/api/v4/cloud/accounts/{account_id}")
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Test"

    def test_delete_account(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.delete(f"/api/v4/cloud/accounts/{account_id}")
        assert resp.status_code == 200

    def test_get_account_not_found(self, client):
        resp = client.get("/api/v4/cloud/accounts/nonexistent")
        assert resp.status_code == 404

    def test_create_account_fields(self, client):
        resp = client.post("/api/v4/cloud/accounts", json={
            "provider": "gcp",
            "display_name": "GCP Staging",
            "credential_handle": "ref-gcp",
            "auth_method": "service_account",
            "regions": ["us-central1", "europe-west1"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "gcp"
        assert data["display_name"] == "GCP Staging"
        assert data["auth_method"] == "service_account"
        assert data["regions"] == ["us-central1", "europe-west1"]
        assert data["sync_enabled"] is True
        assert data["last_sync_status"] == "never"
        assert data["consecutive_failures"] == 0

    def test_list_accounts_after_create(self, client):
        client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Acct A",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        client.post("/api/v4/cloud/accounts", json={
            "provider": "gcp", "display_name": "Acct B",
            "credential_handle": "ref2", "auth_method": "service_account",
            "regions": ["us-central1"],
        })
        resp = client.get("/api/v4/cloud/accounts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_delete_then_get_returns_404(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "DeleteMe",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        client.delete(f"/api/v4/cloud/accounts/{account_id}")
        resp = client.get(f"/api/v4/cloud/accounts/{account_id}")
        assert resp.status_code == 404


class TestResourceEndpoints:
    def test_list_resources_empty(self, client):
        resp = client.get("/api/v4/cloud/resources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_resource_not_found(self, client):
        resp = client.get("/api/v4/cloud/resources/nonexistent")
        assert resp.status_code == 404


class TestSyncEndpoints:
    def test_list_sync_jobs_empty(self, client):
        resp = client.get("/api/v4/cloud/sync/jobs")
        assert resp.status_code == 200

    def test_trigger_sync_account_not_found(self, client):
        resp = client.post("/api/v4/cloud/accounts/nonexistent/sync", json={
            "tiers": [1, 2],
        })
        assert resp.status_code == 404

    def test_trigger_sync_success(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.post(f"/api/v4/cloud/accounts/{account_id}/sync", json={
            "tiers": [1],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_health_check_not_found(self, client):
        resp = client.post("/api/v4/cloud/accounts/nonexistent/health")
        assert resp.status_code == 404

    def test_health_check_success(self, client):
        create = client.post("/api/v4/cloud/accounts", json={
            "provider": "aws", "display_name": "Test",
            "credential_handle": "ref", "auth_method": "iam_role",
            "regions": ["us-east-1"],
        })
        account_id = create.json()["account_id"]
        resp = client.post(f"/api/v4/cloud/accounts/{account_id}/health")
        assert resp.status_code == 200
        assert "status" in resp.json()
