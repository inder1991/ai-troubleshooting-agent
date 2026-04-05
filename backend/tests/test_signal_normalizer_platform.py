"""Tests for platform-layer signal extraction rules."""

from src.agents.cluster.signal_normalizer import extract_signals


def _make_report(desc: str) -> list[dict]:
    return [{
        "domain": "ctrl_plane",
        "status": "SUCCESS",
        "anomalies": [{"description": desc, "evidence_ref": "test/ref", "severity": "high"}],
    }]


def test_cluster_upgrade_stuck_signal():
    signals = extract_signals(_make_report("ClusterVersion upgrade failing: unable to apply 4.14.3"))
    types = [s.signal_type for s in signals]
    assert "CLUSTER_UPGRADE_STUCK" in types


def test_cluster_upgrade_progressing_signal():
    signals = extract_signals(_make_report("Cluster version upgrade progressing to 4.14.3"))
    types = [s.signal_type for s in signals]
    assert "CLUSTER_UPGRADE_STUCK" in types


def test_olm_subscription_failure_signal():
    signals = extract_signals(_make_report("OLM Subscription jaeger state is UpgradePending"))
    types = [s.signal_type for s in signals]
    assert "OLM_SUBSCRIPTION_FAILURE" in types


def test_olm_csv_failure_signal():
    signals = extract_signals(_make_report("ClusterServiceVersion jaeger-operator.v1.51 phase is Failed"))
    types = [s.signal_type for s in signals]
    assert "OLM_CSV_FAILURE" in types


def test_machine_failure_signal():
    signals = extract_signals(_make_report("Machine worker-2 is not running (phase: Failed)"))
    types = [s.signal_type for s in signals]
    assert "MACHINE_FAILURE" in types


def test_proxy_misconfigured_signal():
    signals = extract_signals(_make_report("Proxy misconfigured — noProxy is empty, traffic may be blocked"))
    types = [s.signal_type for s in signals]
    assert "PROXY_MISCONFIGURED" in types
