"""Tests for platform-layer failure patterns."""

from src.agents.cluster.failure_patterns import match_patterns
from src.agents.cluster.state import NormalizedSignal


def _signal(signal_type: str, resource_key: str = "test/ref") -> dict:
    return NormalizedSignal(
        signal_id="t1", signal_type=signal_type,
        resource_key=resource_key, source_domain="ctrl_plane",
        reliability=0.9, timestamp="2026-01-01T00:00:00Z",
    ).model_dump(mode="json")


def test_cluster_upgrade_failure_pattern():
    signals = [_signal("CLUSTER_UPGRADE_STUCK")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "CLUSTER_UPGRADE_FAILURE" in ids


def test_olm_operator_install_failure_pattern():
    signals = [_signal("OLM_SUBSCRIPTION_FAILURE"), _signal("OLM_CSV_FAILURE")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "OLM_OPERATOR_INSTALL_FAILURE" in ids


def test_olm_upgrade_stuck_pattern():
    signals = [_signal("OLM_SUBSCRIPTION_FAILURE"), _signal("OLM_INSTALLPLAN_STUCK")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "OLM_UPGRADE_STUCK" in ids


def test_machine_provisioning_failure_pattern():
    signals = [_signal("MACHINE_FAILURE"), _signal("NODE_NOT_READY")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "MACHINE_PROVISIONING_FAILURE" in ids


def test_proxy_blocks_image_pull_pattern():
    signals = [_signal("PROXY_MISCONFIGURED"), _signal("IMAGE_PULL_BACKOFF")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "PROXY_BLOCKS_IMAGE_PULL" in ids


def test_machine_node_mismatch_pattern():
    signals = [_signal("MACHINE_FAILURE")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "MACHINE_NODE_MISMATCH" in ids
