"""Tests for ASN-to-Name Registry — Task 65."""
import pytest


class TestASNLookup:
    def test_lookup_known_asn_cloudflare(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(13335)
        assert result is not None
        assert result["name"] == "Cloudflare"
        assert result["country"] == "US"

    def test_lookup_known_asn_google(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(15169)
        assert result is not None
        assert result["name"] == "Google"

    def test_lookup_known_asn_amazon(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(16509)
        assert result is not None
        assert result["name"] == "Amazon"

    def test_lookup_known_asn_facebook(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(32934)
        assert result is not None
        assert result["name"] == "Facebook"

    def test_lookup_unknown_asn_returns_none(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(999999999)
        assert result is None

    def test_lookup_returns_country(self):
        from src.network.asn_registry import lookup_asn
        result = lookup_asn(13335)
        assert "country" in result


class TestASNBatchLookup:
    def test_batch_lookup_all_known(self):
        from src.network.asn_registry import batch_lookup_asn
        result = batch_lookup_asn([13335, 15169])
        assert len(result) == 2
        assert 13335 in result
        assert 15169 in result
        assert result[13335]["name"] == "Cloudflare"

    def test_batch_lookup_mixed_known_unknown(self):
        from src.network.asn_registry import batch_lookup_asn
        result = batch_lookup_asn([13335, 999999999])
        assert 13335 in result
        assert 999999999 not in result

    def test_batch_lookup_empty_list(self):
        from src.network.asn_registry import batch_lookup_asn
        result = batch_lookup_asn([])
        assert result == {}


class TestASNRegistrySize:
    def test_registry_has_200_plus_entries(self):
        from src.network.asn_registry import ASN_REGISTRY
        assert len(ASN_REGISTRY) >= 200, f"Expected 200+ ASNs, got {len(ASN_REGISTRY)}"


class TestASNEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.api.flow_endpoints import flow_router
        app = FastAPI()
        app.include_router(flow_router)
        return TestClient(app)

    def test_endpoint_returns_json(self, client):
        resp = client.get("/api/v4/network/flows/asn/lookup", params={"asn": 13335})
        assert resp.status_code == 200
        data = resp.json()
        assert data["asn"] == 13335
        assert data["name"] == "Cloudflare"
        assert data["country"] == "US"

    def test_endpoint_unknown_asn(self, client):
        resp = client.get("/api/v4/network/flows/asn/lookup", params={"asn": 999999999})
        assert resp.status_code == 404

    def test_endpoint_requires_asn_param(self, client):
        resp = client.get("/api/v4/network/flows/asn/lookup")
        assert resp.status_code == 422  # validation error
