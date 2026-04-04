"""Tests for the v5 topology overview endpoint.

Validates environment summaries and WAN connection aggregation
from build_topology_overview().
"""

from __future__ import annotations

import pytest

from src.api.topology_v5 import build_topology_overview, GROUP_META
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def seeded_repo(tmp_path):
    """Repo with two devices in different groups + a neighbor link between them."""
    db_path = str(tmp_path / "topo.db")
    store = TopologyStore(db_path=db_path)
    repo = SQLiteRepository(store)

    # On-prem router
    store.add_device(PD(
        id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1", vendor="cisco", role="core",
    ))
    # AWS cloud gateway (location triggers AWS classification)
    store.add_device(PD(
        id="csr-01", name="csr-aws-01", device_type=DeviceType.ROUTER,
        management_ip="10.10.0.1", vendor="cisco", role="cloud_gateway",
        location="us-east-1",
    ))
    # Cross-group neighbor link
    store.upsert_neighbor_link(
        link_id="l1", device_id="rtr-01", local_interface="Gi0/0",
        remote_device="csr-01", remote_interface="Gi0/0",
        protocol="bgp", confidence=0.9,
    )

    return repo


@pytest.fixture()
def empty_repo(tmp_path):
    """Repo with no devices."""
    db_path = str(tmp_path / "empty.db")
    store = TopologyStore(db_path=db_path)
    return SQLiteRepository(store)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestTopologyOverview:
    def test_returns_environments(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        assert "environments" in result
        assert len(result["environments"]) >= 1

    def test_environment_has_required_fields(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        for env in result["environments"]:
            assert "id" in env
            assert "label" in env
            assert "accent" in env
            assert "device_count" in env
            assert "health_summary" in env

    def test_wan_connections_detected(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        assert "wan_connections" in result
        assert len(result["wan_connections"]) >= 1

    def test_wan_connection_has_fields(self, seeded_repo):
        result = build_topology_overview(seeded_repo)
        for wan in result["wan_connections"]:
            assert "source" in wan
            assert "target" in wan
            assert "connection_types" in wan
            assert "status" in wan

    def test_empty_topology(self, empty_repo):
        result = build_topology_overview(empty_repo)
        assert result["environments"] == []
        assert result["wan_connections"] == []
