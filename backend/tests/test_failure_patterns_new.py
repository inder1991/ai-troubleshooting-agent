"""Tests for 8 new failure patterns."""

from src.agents.cluster.failure_patterns import match_patterns, FAILURE_PATTERNS


def _make_signals(*signal_types: str) -> list[dict]:
    return [{"signal_id": f"s{i}", "signal_type": st, "resource_key": f"test/{st.lower()}",
             "source_domain": "test", "raw_value": None, "reliability": 0.8,
             "timestamp": "2026-04-05T00:00:00Z", "namespace": "test"}
            for i, st in enumerate(signal_types)]


def test_operator_scaled_down():
    signals = _make_signals("OPERATOR_DEGRADED")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "OPERATOR_SCALED_DOWN" in ids


def test_operator_upgrade_stuck():
    signals = _make_signals("OPERATOR_PROGRESSING")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "OPERATOR_UPGRADE_STUCK" in ids


def test_etcd_quorum_loss():
    signals = _make_signals("OPERATOR_DEGRADED", "NODE_NOT_READY")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "ETCD_QUORUM_LOSS" in ids


def test_webhook_blocking():
    signals = _make_signals("WEBHOOK_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "WEBHOOK_BLOCKING" in ids


def test_init_container_stuck_pattern():
    signals = _make_signals("INIT_CONTAINER_STUCK")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "INIT_CONTAINER_STUCK_PATTERN" in ids


def test_config_mount_failure():
    signals = _make_signals("MOUNT_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "CONFIG_MOUNT_FAILURE" in ids


def test_netpol_blocks_dns():
    signals = _make_signals("NETPOL_EMPTY_INGRESS", "DNS_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "NETPOL_BLOCKS_DNS" in ids


def test_quota_scheduling_failure():
    signals = _make_signals("QUOTA_EXCEEDED", "FAILED_SCHEDULING")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "QUOTA_SCHEDULING_FAILURE" in ids
