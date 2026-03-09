"""Tests for OID MIB Registry — Task 21."""
import pytest


class TestMIBRegistryLookup:
    """Test lookup_oid function."""

    def test_lookup_known_oid_sysdescr(self):
        from src.network.collectors.mib_registry import lookup_oid
        result = lookup_oid("1.3.6.1.2.1.1.1.0")
        assert result is not None
        assert result["name"] == "sysDescr"
        assert result["module"] == "SNMPv2-MIB"

    def test_lookup_known_oid_sysuptime(self):
        from src.network.collectors.mib_registry import lookup_oid
        result = lookup_oid("1.3.6.1.2.1.1.3.0")
        assert result is not None
        assert result["name"] == "sysUpTime"

    def test_lookup_unknown_oid_returns_none(self):
        from src.network.collectors.mib_registry import lookup_oid
        result = lookup_oid("99.99.99.99.99")
        assert result is None

    def test_lookup_returns_description(self):
        from src.network.collectors.mib_registry import lookup_oid
        result = lookup_oid("1.3.6.1.2.1.1.1.0")
        assert "description" in result
        assert len(result["description"]) > 0

    def test_lookup_cisco_enterprise_oid(self):
        """Enterprise OIDs from Cisco should be in the registry."""
        from src.network.collectors.mib_registry import lookup_oid, MIB_REGISTRY
        # Find any Cisco OID in the registry
        cisco_oids = [
            oid for oid, info in MIB_REGISTRY.items()
            if "cisco" in info.get("module", "").lower()
            or "cisco" in info.get("description", "").lower()
            or "cisco" in info.get("name", "").lower()
            or oid.startswith("1.3.6.1.4.1.9.")
        ]
        assert len(cisco_oids) > 0, "Expected at least one Cisco enterprise OID"

    def test_lookup_juniper_enterprise_oid(self):
        """Enterprise OIDs from Juniper should be in the registry."""
        from src.network.collectors.mib_registry import MIB_REGISTRY
        juniper_oids = [
            oid for oid, info in MIB_REGISTRY.items()
            if oid.startswith("1.3.6.1.4.1.2636.")
        ]
        assert len(juniper_oids) > 0, "Expected at least one Juniper enterprise OID"

    def test_lookup_paloalto_enterprise_oid(self):
        """Enterprise OIDs from Palo Alto should be in the registry."""
        from src.network.collectors.mib_registry import MIB_REGISTRY
        paloalto_oids = [
            oid for oid, info in MIB_REGISTRY.items()
            if oid.startswith("1.3.6.1.4.1.25461.")
        ]
        assert len(paloalto_oids) > 0, "Expected at least one Palo Alto enterprise OID"


class TestMIBRegistrySize:
    """Ensure the registry has 200+ entries."""

    def test_registry_has_200_plus_entries(self):
        from src.network.collectors.mib_registry import MIB_REGISTRY
        assert len(MIB_REGISTRY) >= 200, f"Expected 200+ OIDs, got {len(MIB_REGISTRY)}"


class TestBatchLookup:
    """Test batch_lookup function."""

    def test_batch_lookup_all_known(self):
        from src.network.collectors.mib_registry import batch_lookup
        oids = ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.3.0"]
        result = batch_lookup(oids)
        assert len(result) == 2
        assert "1.3.6.1.2.1.1.1.0" in result
        assert result["1.3.6.1.2.1.1.1.0"]["name"] == "sysDescr"

    def test_batch_lookup_mixed_known_unknown(self):
        from src.network.collectors.mib_registry import batch_lookup
        oids = ["1.3.6.1.2.1.1.1.0", "99.99.99"]
        result = batch_lookup(oids)
        assert "1.3.6.1.2.1.1.1.0" in result
        assert "99.99.99" not in result

    def test_batch_lookup_all_unknown(self):
        from src.network.collectors.mib_registry import batch_lookup
        result = batch_lookup(["99.99.99", "88.88.88"])
        assert len(result) == 0

    def test_batch_lookup_empty_list(self):
        from src.network.collectors.mib_registry import batch_lookup
        result = batch_lookup([])
        assert result == {}


class TestSearchOIDs:
    """Test search_oids function."""

    def test_search_by_name(self):
        from src.network.collectors.mib_registry import search_oids
        results = search_oids("sysDescr")
        assert len(results) >= 1
        assert any(r["name"] == "sysDescr" for r in results)

    def test_search_by_description(self):
        from src.network.collectors.mib_registry import search_oids
        results = search_oids("uptime")
        assert len(results) >= 1

    def test_search_case_insensitive(self):
        from src.network.collectors.mib_registry import search_oids
        results_lower = search_oids("sysdescr")
        results_upper = search_oids("SYSDESCR")
        assert len(results_lower) >= 1
        assert len(results_lower) == len(results_upper)

    def test_search_no_results(self):
        from src.network.collectors.mib_registry import search_oids
        results = search_oids("zzz_nonexistent_xyzzy")
        assert results == []

    def test_search_cpu(self):
        from src.network.collectors.mib_registry import search_oids
        results = search_oids("cpu")
        assert len(results) >= 1

    def test_search_returns_oid_field(self):
        from src.network.collectors.mib_registry import search_oids
        results = search_oids("sysDescr")
        assert "oid" in results[0]


class TestMIBEndpoints:
    """Test the MIB REST API endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from src.api.collector_endpoints import collector_router
        app = FastAPI()
        app.include_router(collector_router)
        return TestClient(app)

    def test_mib_lookup_known(self, client):
        resp = client.get("/api/collector/mib/lookup", params={"oid": "1.3.6.1.2.1.1.1.0"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "sysDescr"

    def test_mib_lookup_unknown(self, client):
        resp = client.get("/api/collector/mib/lookup", params={"oid": "99.99.99"})
        assert resp.status_code == 404

    def test_mib_batch(self, client):
        resp = client.post(
            "/api/collector/mib/batch",
            json={"oids": ["1.3.6.1.2.1.1.1.0", "99.99.99"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "1.3.6.1.2.1.1.1.0" in data["results"]
        assert "99.99.99" not in data["results"]

    def test_mib_search(self, client):
        resp = client.get("/api/collector/mib/search", params={"q": "cpu"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_mib_search_empty_query(self, client):
        resp = client.get("/api/collector/mib/search", params={"q": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
