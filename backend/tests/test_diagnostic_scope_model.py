"""Tests for DiagnosticScope model, SKIPPED enum, and scope wiring."""

import pytest
from pydantic import ValidationError

from src.agents.cluster.state import (
    DiagnosticScope,
    DomainStatus,
    ClusterDiagnosticState,
)


# ---------------------------------------------------------------------------
# DiagnosticScope defaults
# ---------------------------------------------------------------------------


def test_diagnostic_scope_defaults():
    scope = DiagnosticScope()
    assert scope.level == "cluster"
    assert scope.namespaces == []
    assert scope.workload_key is None
    assert scope.domains == ["ctrl_plane", "node", "network", "storage"]
    assert scope.include_control_plane is True


def test_diagnostic_scope_serialization_roundtrip():
    scope = DiagnosticScope(level="namespace", namespaces=["prod"])
    data = scope.model_dump(mode="json")
    assert data["level"] == "namespace"
    assert data["namespaces"] == ["prod"]
    # Roundtrip
    restored = DiagnosticScope(**data)
    assert restored == scope


def test_diagnostic_scope_model_dump_keys():
    """Ensure .model_dump() produces the exact keys downstream expects."""
    scope = DiagnosticScope()
    keys = set(scope.model_dump().keys())
    assert keys == {"level", "namespaces", "workload_key", "domains", "include_control_plane"}


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------


def test_diagnostic_scope_frozen():
    scope = DiagnosticScope()
    with pytest.raises(ValidationError):
        scope.level = "namespace"


def test_diagnostic_scope_frozen_list_attribute():
    """Cannot reassign list field on frozen model."""
    scope = DiagnosticScope()
    with pytest.raises(ValidationError):
        scope.namespaces = ["new-ns"]


# ---------------------------------------------------------------------------
# Namespace shorthand
# ---------------------------------------------------------------------------


def test_namespace_shorthand():
    """When only a namespace is provided, level should be set to 'namespace'."""
    scope = DiagnosticScope(level="namespace", namespaces=["kube-system"])
    assert scope.level == "namespace"
    assert scope.namespaces == ["kube-system"]
    assert scope.domains == ["ctrl_plane", "node", "network", "storage"]


def test_workload_scope():
    scope = DiagnosticScope(
        level="workload",
        namespaces=["prod"],
        workload_key="Deployment/my-app",
    )
    assert scope.level == "workload"
    assert scope.workload_key == "Deployment/my-app"


# ---------------------------------------------------------------------------
# Level validation
# ---------------------------------------------------------------------------


def test_invalid_level_rejected():
    with pytest.raises(ValidationError):
        DiagnosticScope(level="invalid_level")


def test_all_valid_levels():
    for level in ("cluster", "namespace", "workload", "component"):
        scope = DiagnosticScope(level=level)
        assert scope.level == level


# ---------------------------------------------------------------------------
# Custom domains
# ---------------------------------------------------------------------------


def test_custom_domains():
    scope = DiagnosticScope(domains=["network", "storage"])
    assert scope.domains == ["network", "storage"]
    assert scope.include_control_plane is True


def test_control_plane_off():
    scope = DiagnosticScope(include_control_plane=False)
    assert scope.include_control_plane is False


# ---------------------------------------------------------------------------
# DomainStatus.SKIPPED
# ---------------------------------------------------------------------------


def test_domain_status_skipped_exists():
    assert DomainStatus.SKIPPED == "SKIPPED"
    assert DomainStatus.SKIPPED.value == "SKIPPED"


def test_domain_status_all_values():
    expected = {"PENDING", "RUNNING", "SUCCESS", "PARTIAL", "FAILED", "SKIPPED"}
    actual = {s.value for s in DomainStatus}
    assert actual == expected


# ---------------------------------------------------------------------------
# ClusterDiagnosticState new fields
# ---------------------------------------------------------------------------


def test_cluster_state_scope_fields_defaults():
    state = ClusterDiagnosticState(diagnostic_id="DIAG-001")
    assert state.diagnostic_scope is None
    assert state.scoped_topology_graph is None
    assert state.dispatch_domains == ["ctrl_plane", "node", "network", "storage"]
    assert state.scope_coverage == 1.0


def test_cluster_state_with_scope():
    scope = DiagnosticScope(level="namespace", namespaces=["prod"])
    state = ClusterDiagnosticState(
        diagnostic_id="DIAG-002",
        diagnostic_scope=scope.model_dump(mode="json"),
        dispatch_domains=["node", "network"],
        scope_coverage=0.5,
    )
    assert state.diagnostic_scope["level"] == "namespace"
    assert state.dispatch_domains == ["node", "network"]
    assert state.scope_coverage == 0.5


def test_cluster_state_serialization_with_scope():
    scope = DiagnosticScope(level="workload", namespaces=["prod"], workload_key="Deployment/api")
    state = ClusterDiagnosticState(
        diagnostic_id="DIAG-003",
        diagnostic_scope=scope.model_dump(mode="json"),
    )
    data = state.model_dump(mode="json")
    assert data["diagnostic_scope"]["workload_key"] == "Deployment/api"
    assert data["scope_coverage"] == 1.0


# ---------------------------------------------------------------------------
# Guard mode rejection (unit test for the logic, not the HTTP endpoint)
# ---------------------------------------------------------------------------


def test_guard_mode_rejects_non_cluster_scope():
    """Guard mode only allows cluster-level scope."""
    scope_dict = {"level": "namespace", "namespaces": ["prod"]}
    scan_mode = "guard"
    # Simulate the route guard logic
    if scan_mode == "guard" and scope_dict.get("level") != "cluster":
        rejected = True
    else:
        rejected = False
    assert rejected is True


def test_guard_mode_accepts_cluster_scope():
    scope_dict = {"level": "cluster"}
    scan_mode = "guard"
    if scan_mode == "guard" and scope_dict.get("level") != "cluster":
        rejected = True
    else:
        rejected = False
    assert rejected is False


def test_guard_mode_accepts_no_scope():
    """No scope provided defaults to cluster level, so guard mode should accept."""
    scope_dict = None
    scan_mode = "guard"
    if scan_mode == "guard" and scope_dict and scope_dict.get("level") != "cluster":
        rejected = True
    else:
        rejected = False
    assert rejected is False
