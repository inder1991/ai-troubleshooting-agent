"""Tests for platform-layer causal link types."""

from src.agents.cluster.synthesizer import CONSTRAINED_LINK_TYPES


def test_cluster_upgrade_to_operator_degraded():
    assert "cluster_upgrade_stuck -> operator_degraded" in CONSTRAINED_LINK_TYPES


def test_olm_failure_to_operator_degraded():
    assert "olm_failure -> operator_degraded" in CONSTRAINED_LINK_TYPES


def test_machine_failure_to_node_not_ready():
    assert "machine_failure -> node_not_ready" in CONSTRAINED_LINK_TYPES


def test_proxy_misconfigured_to_image_pull_failure():
    assert "proxy_misconfigured -> image_pull_failure" in CONSTRAINED_LINK_TYPES
