"""Tests for HA group validation endpoint — GET /api/v4/network/ha-groups/{group_id}/validate."""
import os
import pytest
from unittest.mock import patch

from starlette.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import (
    Device, DeviceType, Subnet, HAGroup, HAMode,
)
from src.network.adapters.registry import AdapterRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test_ha_val.db")
    return TopologyStore(db_path=db_path)


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def client(store, kg):
    """TestClient with patched singletons pointing to test fixtures."""
    registry = AdapterRegistry()
    with patch("src.api.network_endpoints._topology_store", store), \
         patch("src.api.network_endpoints._knowledge_graph", kg), \
         patch("src.api.network_endpoints._adapter_registry", registry), \
         patch("src.api.network_endpoints._network_sessions", {}):
        from src.api.main import create_app
        app = create_app()
        with TestClient(app) as c:
            yield c


def _seed_ha_topology(store: TopologyStore):
    """Create two firewalls in the same subnet for a valid HA pair."""
    store.add_device(Device(
        id="fw1", name="Firewall-A", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1",
    ))
    store.add_device(Device(
        id="fw2", name="Firewall-B", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.2",
    ))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.254"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHAGroupValidationEndpoint:
    """GET /api/v4/network/ha-groups/{group_id}/validate"""

    def test_valid_ha_group_returns_valid_true(self, store, client):
        """A well-formed active-passive HA group with matching device types
        and same subnet should return valid=true, errors=[]."""
        _seed_ha_topology(store)
        group = HAGroup(
            id="ha1", name="fw-pair",
            ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["fw1", "fw2"],
            virtual_ips=["10.0.0.100"],
            active_member_id="fw1",
        )
        store.add_ha_group(group)

        resp = client.get("/api/v4/network/ha-groups/ha1/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["group_id"] == "ha1"
        assert body["valid"] is True
        assert body["errors"] == []

    def test_nonexistent_group_returns_404(self, client):
        """Requesting validation for a group that does not exist should 404."""
        resp = client.get("/api/v4/network/ha-groups/no-such-group/validate")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_mixed_device_types_returns_errors(self, store, client):
        """HA group with members of different device types should fail validation."""
        store.add_device(Device(
            id="fw1", name="Firewall-A", device_type=DeviceType.FIREWALL,
            management_ip="10.0.0.1",
        ))
        store.add_device(Device(
            id="r1", name="Router-A", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.2",
        ))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.254"))

        group = HAGroup(
            id="ha-mixed", name="mixed-pair",
            ha_mode=HAMode.ACTIVE_ACTIVE,
            member_ids=["fw1", "r1"],
        )
        store.add_ha_group(group)

        resp = client.get("/api/v4/network/ha-groups/ha-mixed/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("same device type" in e for e in body["errors"])

    def test_missing_active_member_returns_errors(self, store, client):
        """Active-passive group without an active member should fail validation."""
        _seed_ha_topology(store)
        group = HAGroup(
            id="ha-no-active", name="no-active",
            ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["fw1", "fw2"],
            # active_member_id intentionally omitted (defaults to "")
        )
        store.add_ha_group(group)

        resp = client.get("/api/v4/network/ha-groups/ha-no-active/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert any("active member" in e.lower() for e in body["errors"])

    def test_get_ha_group_by_id_still_works(self, store, client):
        """Ensure the plain GET /ha-groups/{group_id} endpoint is not broken
        by the new /validate sub-route."""
        _seed_ha_topology(store)
        group = HAGroup(
            id="ha-plain", name="plain",
            ha_mode=HAMode.ACTIVE_ACTIVE,
            member_ids=["fw1", "fw2"],
        )
        store.add_ha_group(group)

        resp = client.get("/api/v4/network/ha-groups/ha-plain")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ha_group"]["id"] == "ha-plain"
