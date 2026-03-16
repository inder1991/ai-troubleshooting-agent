"""Tests for the v5 topology API export logic.

Tests the pure helper functions (classify_group, compute_rank,
recommend_algorithm) and the full build_topology_export pipeline
using an ephemeral SQLite store.
"""

from __future__ import annotations

import pytest

from src.api.topology_v5 import (
    build_topology_export,
    classify_group,
    compute_rank,
    recommend_algorithm,
    GROUP_META,
    _compute_topology_version,
)
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.models import Device as PD, DeviceType


# ── classify_group ────────────────────────────────────────────────────────


class TestClassifyGroup:
    def test_onprem_default(self):
        assert classify_group({"site_id": "dc-east", "hostname": "rtr-01"}) == "onprem"

    def test_aws_site_id(self):
        assert classify_group({"site_id": "aws-us-east-1", "hostname": "vpc-prod"}) == "aws"

    def test_aws_hostname(self):
        assert classify_group({"site_id": "", "hostname": "tgw-main"}) == "aws"

    def test_aws_cloud_provider(self):
        assert classify_group({"site_id": "", "hostname": "router1", "cloud_provider": "aws"}) == "aws"

    def test_azure_site_id(self):
        assert classify_group({"site_id": "azure-westeurope", "hostname": "fw-01"}) == "azure"

    def test_azure_hostname(self):
        assert classify_group({"site_id": "", "hostname": "vwan-hub"}) == "azure"

    def test_azure_cloud_provider(self):
        assert classify_group({"site_id": "", "hostname": "nva-azure-fw"}) == "azure"

    def test_oci_site_id(self):
        assert classify_group({"site_id": "oci-ashburn", "hostname": "drg-core"}) == "oci"

    def test_oci_hostname(self):
        assert classify_group({"site_id": "", "hostname": "vcn-prod"}) == "oci"

    def test_oci_cloud_provider(self):
        assert classify_group({"site_id": "", "hostname": "fw1", "cloud_provider": "oci"}) == "oci"

    def test_gcp_cloud_provider(self):
        assert classify_group({"site_id": "", "hostname": "vm-01", "cloud_provider": "gcp"}) == "gcp"

    def test_gcp_in_region(self):
        assert classify_group({"site_id": "", "hostname": "fw-01", "region": "gcp-us-central1"}) == "gcp"

    def test_branch(self):
        assert classify_group({"site_id": "branch-nyc", "hostname": "br-sw-01"}) == "branch"

    def test_branch_hostname(self):
        assert classify_group({"site_id": "", "hostname": "branch-router"}) == "branch"

    def test_empty_data_defaults_onprem(self):
        assert classify_group({}) == "onprem"

    def test_none_values_default_onprem(self):
        assert classify_group({"site_id": None, "hostname": None}) == "onprem"


# ── compute_rank ──────────────────────────────────────────────────────────


class TestComputeRank:
    def test_core_role(self):
        assert compute_rank("ROUTER", "core") == 1

    def test_perimeter_role(self):
        assert compute_rank("FIREWALL", "perimeter") == 1

    def test_distribution_role(self):
        assert compute_rank("SWITCH", "distribution") == 2

    def test_access_role(self):
        assert compute_rank("SWITCH", "access") == 3

    def test_edge_role(self):
        assert compute_rank("ROUTER", "edge") == 3

    def test_no_role_router(self):
        """Router with no role gets rank 1 from device_type fallback."""
        assert compute_rank("router", "") == 1

    def test_no_role_switch(self):
        """Switch with no role gets rank 2 from device_type fallback."""
        assert compute_rank("switch", "") == 2

    def test_no_role_host(self):
        assert compute_rank("host", "") == 4

    def test_no_role_firewall(self):
        assert compute_rank("firewall", "") == 1

    def test_unknown_type_default_rank(self):
        assert compute_rank("unknown_thing", "") == 3

    def test_role_takes_priority_over_type(self):
        """Role-based rank overrides device_type fallback."""
        # Host device with core role should get rank 1 (role wins)
        assert compute_rank("host", "core") == 1

    def test_case_insensitive_role(self):
        assert compute_rank("SWITCH", "Core") == 1


# ── recommend_algorithm ───────────────────────────────────────────────────


class TestRecommendAlgorithm:
    def test_small_topology(self):
        assert recommend_algorithm(10) == "force_directed"

    def test_medium_topology(self):
        assert recommend_algorithm(49) == "force_directed"

    def test_boundary_50(self):
        assert recommend_algorithm(50) == "hierarchical"

    def test_large_topology(self):
        assert recommend_algorithm(150) == "hierarchical"

    def test_very_large_topology(self):
        assert recommend_algorithm(500) == "hierarchical"

    def test_zero_nodes(self):
        assert recommend_algorithm(0) == "force_directed"


# ── _compute_topology_version ─────────────────────────────────────────────


class TestTopologyVersion:
    def test_deterministic(self):
        v1 = _compute_topology_version(["a", "b"], ["e1"])
        v2 = _compute_topology_version(["a", "b"], ["e1"])
        assert v1 == v2

    def test_order_independent(self):
        v1 = _compute_topology_version(["b", "a"], ["e2", "e1"])
        v2 = _compute_topology_version(["a", "b"], ["e1", "e2"])
        assert v1 == v2

    def test_different_inputs(self):
        v1 = _compute_topology_version(["a"], ["e1"])
        v2 = _compute_topology_version(["a", "b"], ["e1"])
        assert v1 != v2

    def test_length_16(self):
        v = _compute_topology_version(["x"], ["y"])
        assert len(v) == 16


# ── build_topology_export (integration with ephemeral store) ──────────────


class TestBuildTopologyExport:
    @pytest.fixture()
    def repo(self, tmp_path):
        store = TopologyStore(str(tmp_path / "test.db"))
        return SQLiteRepository(store)

    def test_empty_topology(self, repo):
        result = build_topology_export(repo)
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["groups"] == []
        assert result["device_count"] == 0
        assert result["edge_count"] == 0
        assert "topology_version" in result
        assert result["layout_hints"]["algorithm"] == "force_directed"

    def test_single_device(self, repo):
        repo._store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1", vendor="cisco", role="core",
        ))
        result = build_topology_export(repo)
        assert result["device_count"] == 1
        assert result["edge_count"] == 0
        assert len(result["nodes"]) == 1

        node = result["nodes"][0]
        assert node["id"] == "rtr-01"
        assert node["hostname"] == "rtr-01"
        assert node["vendor"] == "cisco"
        assert node["device_type"] == "ROUTER"
        assert node["group"] == "onprem"
        assert node["rank"] == 1
        assert node["status"] == "healthy"
        assert node["confidence"] == 0.9
        assert node["ha_role"] is None
        assert node["metrics"] == {}

    def test_groups_populated(self, repo):
        repo._store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1", vendor="cisco", role="core",
        ))
        repo._store.add_device(PD(
            id="vpc-01", name="vpc-prod", device_type=DeviceType.VPC,
            management_ip="", vendor="aws", cloud_provider="aws",
        ))
        result = build_topology_export(repo)
        assert result["device_count"] == 2
        assert len(result["groups"]) == 2

        group_ids = {g["id"] for g in result["groups"]}
        assert "onprem" in group_ids
        assert "aws" in group_ids

        aws_group = next(g for g in result["groups"] if g["id"] == "aws")
        assert aws_group["label"] == "AWS"
        assert aws_group["accent"] == "#f59e0b"
        assert aws_group["device_count"] == 1

    def test_edges_from_neighbor_links(self, repo):
        store = repo._store
        store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1", vendor="cisco",
        ))
        store.add_device(PD(
            id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
            management_ip="10.0.0.2", vendor="cisco",
        ))
        store.upsert_neighbor_link(
            link_id="link-1",
            device_id="rtr-01",
            local_interface="Gi0/0",
            remote_device="sw-01",
            remote_interface="Gi0/48",
            protocol="lldp",
            confidence=0.95,
        )
        result = build_topology_export(repo)
        assert result["edge_count"] == 1
        edge = result["edges"][0]
        assert edge["source"] == "rtr-01"
        assert edge["target"] == "sw-01"
        assert edge["source_interface"] == "rtr-01:Gi0/0"
        assert edge["target_interface"] == "sw-01:Gi0/48"
        assert edge["edge_type"] == "physical"
        assert edge["protocol"] == "lldp"
        assert edge["confidence"] == 0.95

    def test_edges_dedup(self, repo):
        """Bidirectional LLDP links should be deduplicated."""
        store = repo._store
        store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1",
        ))
        store.add_device(PD(
            id="sw-01", name="sw-01", device_type=DeviceType.SWITCH,
            management_ip="10.0.0.2",
        ))
        # Forward link
        store.upsert_neighbor_link(
            link_id="link-1", device_id="rtr-01",
            local_interface="Gi0/0", remote_device="sw-01",
            remote_interface="Gi0/48", protocol="lldp",
        )
        # Reverse link
        store.upsert_neighbor_link(
            link_id="link-2", device_id="sw-01",
            local_interface="Gi0/48", remote_device="rtr-01",
            remote_interface="Gi0/0", protocol="lldp",
        )
        result = build_topology_export(repo)
        assert result["edge_count"] == 1

    def test_site_id_filter(self, repo):
        store = repo._store
        store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1", site_id="dc-east",
        ))
        store.add_device(PD(
            id="rtr-02", name="rtr-02", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.2", site_id="dc-west",
        ))
        result = build_topology_export(repo, site_id="dc-east")
        assert result["device_count"] == 1
        assert result["nodes"][0]["id"] == "rtr-01"

    def test_layout_hints_present(self, repo):
        result = build_topology_export(repo)
        assert "layout_hints" in result
        assert result["layout_hints"]["grouping"] == "site"
        assert result["layout_hints"]["algorithm"] in ("force_directed", "hierarchical")

    def test_topology_version_changes(self, repo):
        store = repo._store
        v1 = build_topology_export(repo)["topology_version"]

        store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1",
        ))
        v2 = build_topology_export(repo)["topology_version"]
        assert v1 != v2

    def test_no_pixel_positions(self, repo):
        """Ensure no position/x/y fields leak into the export."""
        store = repo._store
        store.add_device(PD(
            id="rtr-01", name="rtr-01", device_type=DeviceType.ROUTER,
            management_ip="10.0.0.1",
        ))
        result = build_topology_export(repo)
        node = result["nodes"][0]
        assert "x" not in node
        assert "y" not in node
        assert "position" not in node

    def test_ha_role_populated(self, repo):
        store = repo._store
        store.add_device(PD(
            id="fw-01", name="fw-01", device_type=DeviceType.FIREWALL,
            management_ip="10.0.0.1", ha_role="active",
        ))
        result = build_topology_export(repo)
        assert result["nodes"][0]["ha_role"] == "active"

    def test_response_structure_keys(self, repo):
        result = build_topology_export(repo)
        expected_keys = {"nodes", "edges", "groups", "layout_hints", "topology_version", "device_count", "edge_count"}
        assert set(result.keys()) == expected_keys
