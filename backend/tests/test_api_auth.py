"""Tests for API key authentication middleware."""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from starlette.testclient import TestClient


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_client(api_keys: str | None = None):
    """Build a fresh app + TestClient with the given API_KEYS env var.

    The env patch is kept alive for the lifetime of the client.
    """
    env_patch = {}
    if api_keys is not None:
        env_patch["API_KEYS"] = api_keys
    else:
        # Ensure API_KEYS is absent
        env_patch["API_KEYS"] = ""

    patcher = patch.dict(os.environ, env_patch)
    patcher.start()

    from src.api.main import create_app
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    return client, patcher


# ═══════════════════════════════════════════════════════════════════
# 1. Auth disabled when API_KEYS is not set
# ═══════════════════════════════════════════════════════════════════

class TestAuthDisabled:
    def test_no_api_keys_env_allows_all(self):
        """When API_KEYS is unset, requests pass without a key."""
        client, patcher = _make_client(api_keys=None)
        try:
            resp = client.get("/metrics")
            assert resp.status_code == 200
        finally:
            patcher.stop()

    def test_empty_api_keys_env_allows_all(self):
        """When API_KEYS is empty string, auth is disabled."""
        client, patcher = _make_client(api_keys="")
        try:
            resp = client.get("/metrics")
            assert resp.status_code == 200
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# 2. Valid key passes
# ═══════════════════════════════════════════════════════════════════

class TestAuthEnabled:
    def test_valid_key_passes(self):
        """A valid X-API-Key header is accepted."""
        client, patcher = _make_client(api_keys="secret-key-1,secret-key-2")
        try:
            resp = client.get("/metrics", headers={"X-API-Key": "secret-key-1"})
            assert resp.status_code == 200
        finally:
            patcher.stop()

    def test_second_valid_key_passes(self):
        """All comma-separated keys are accepted."""
        client, patcher = _make_client(api_keys="key-a,key-b")
        try:
            resp = client.get("/metrics", headers={"X-API-Key": "key-b"})
            assert resp.status_code == 200
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# 3. Invalid / missing key returns 401
# ═══════════════════════════════════════════════════════════════════

class TestAuthRejects:
    def test_missing_key_returns_401(self):
        """No X-API-Key header returns 401."""
        client, patcher = _make_client(api_keys="my-secret")
        try:
            resp = client.get("/api/collector/devices")
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid or missing API key"
        finally:
            patcher.stop()

    def test_wrong_key_returns_401(self):
        """An incorrect X-API-Key returns 401."""
        client, patcher = _make_client(api_keys="correct-key")
        try:
            resp = client.get("/api/collector/devices", headers={"X-API-Key": "wrong-key"})
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid or missing API key"
        finally:
            patcher.stop()


# ═══════════════════════════════════════════════════════════════════
# 4. Health / docs endpoints bypass auth
# ═══════════════════════════════════════════════════════════════════

class TestExemptPaths:
    """Paths like /health, /docs, /openapi.json bypass auth even when keys are set."""

    @pytest.fixture
    def secured_client(self):
        client, patcher = _make_client(api_keys="test-key")
        yield client
        patcher.stop()

    def test_health_bypasses_auth(self, secured_client):
        """GET /health does not require a key."""
        resp = secured_client.get("/health")
        assert resp.status_code != 401

    def test_health_ready_bypasses_auth(self, secured_client):
        resp = secured_client.get("/health/ready")
        assert resp.status_code != 401

    def test_health_live_bypasses_auth(self, secured_client):
        resp = secured_client.get("/health/live")
        assert resp.status_code != 401

    def test_metrics_bypasses_auth(self, secured_client):
        resp = secured_client.get("/metrics")
        assert resp.status_code != 401

    def test_docs_bypasses_auth(self, secured_client):
        resp = secured_client.get("/docs")
        assert resp.status_code != 401

    def test_openapi_json_bypasses_auth(self, secured_client):
        resp = secured_client.get("/openapi.json")
        assert resp.status_code != 401

    def test_non_exempt_path_requires_auth(self, secured_client):
        """A non-exempt path returns 401 without a key."""
        # Use /api/collector/devices which is a real endpoint on the app
        resp = secured_client.get("/api/collector/devices")
        assert resp.status_code == 401
