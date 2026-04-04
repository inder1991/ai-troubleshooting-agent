"""Tests for the V5 topology group filter feature.

Fixture: 2 devices in different groups + a neighbor link between them.
Tests verify group filtering returns only in-group devices/edges and
includes wan_exits for cross-group connections.
"""

from __future__ import annotations

import pytest

from src.api.topology_v5 import build_topology_export
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType


@pytest.fixture()
def repo(tmp_path):
    """Two devices in different groups with a neighbor link between them."""
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)

    # On-prem router
    store.add_device(PD(
        id="rtr-dc-edge-01",
        name="rtr-dc-edge-01",
        device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
        vendor="cisco",
        role="core",
        site_id="dc-east",
    ))

    # AWS cloud router
    store.add_device(PD(
        id="csr-aws-01",
        name="csr-aws-01",
        device_type=DeviceType.ROUTER,
        management_ip="10.1.0.1",
        vendor="cisco",
        role="cloud_gateway",
        cloud_provider="aws",
    ))

    # Cross-group neighbor link (BGP peering between on-prem and AWS)
    store.upsert_neighbor_link(
        link_id="rtr-dc-edge-01:Gi0/1--csr-aws-01:Gi0/0",
        device_id="rtr-dc-edge-01",
        local_interface="Gi0/1",
        remote_device="csr-aws-01",
        remote_interface="Gi0/0",
        protocol="bgp",
        confidence=0.95,
    )

    return repo


def _device_ids(result: dict) -> set[str]:
    """Extract device node IDs from result (skip group/label nodes)."""
    return {n["id"] for n in result["nodes"] if n.get("type") == "device"}


class TestGroupFilter:
    def test_filter_onprem_only(self, repo):
        """group='onprem' returns only on-prem devices."""
        result = build_topology_export(repo, group="onprem")
        ids = _device_ids(result)
        assert "rtr-dc-edge-01" in ids
        assert "csr-aws-01" not in ids
        assert result["device_count"] == 1

    def test_filter_aws_only(self, repo):
        """group='aws' returns only AWS devices."""
        result = build_topology_export(repo, group="aws")
        ids = _device_ids(result)
        assert "csr-aws-01" in ids
        assert "rtr-dc-edge-01" not in ids
        assert result["device_count"] == 1

    def test_no_filter_returns_all(self, repo):
        """No group param returns all devices."""
        result = build_topology_export(repo)
        ids = _device_ids(result)
        assert "rtr-dc-edge-01" in ids
        assert "csr-aws-01" in ids
        assert result["device_count"] == 2

    def test_filter_returns_intra_group_edges_only(self, repo):
        """When filtering by group, edges should only connect devices within that group."""
        result = build_topology_export(repo, group="onprem")
        # The cross-group edge (onprem <-> aws) should NOT appear in edges
        # because the other endpoint (csr-aws-01) is not in the onprem group
        for edge in result["edges"]:
            assert edge["source"] in _device_ids(result), \
                f"Edge source {edge['source']} not in filtered device set"
            assert edge["target"] in _device_ids(result), \
                f"Edge target {edge['target']} not in filtered device set"

    def test_filter_includes_wan_exits(self, repo):
        """Filtered result includes wan_exits for cross-group connections."""
        result = build_topology_export(repo, group="onprem")
        assert "wan_exits" in result
        assert len(result["wan_exits"]) >= 1

        wan_exit = result["wan_exits"][0]
        assert wan_exit["target_group"] == "aws"
        assert wan_exit["target_group_label"] == "AWS"
        assert wan_exit["target_group_accent"] == "#f59e0b"
        assert wan_exit["source_device"] == "rtr-dc-edge-01"
        assert wan_exit["target_device"] == "csr-aws-01"
        assert wan_exit["connection_type"] == "bgp"
