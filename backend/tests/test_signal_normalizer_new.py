"""Tests for 8 new signal extraction rules in signal_normalizer."""

import pytest
from src.agents.cluster.signal_normalizer import extract_signals


def _make_report(domain: str, desc: str, ref: str = "test/ref") -> list[dict]:
    return [{"domain": domain, "status": "SUCCESS", "anomalies": [
        {"description": desc, "evidence_ref": ref, "severity": "high"},
    ]}]


def test_operator_degraded_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Operator kube-apiserver is degraded and unavailable"))
    types = {s.signal_type for s in signals}
    assert "OPERATOR_DEGRADED" in types


def test_operator_progressing_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Operator monitoring is progressing with upgrade"))
    types = {s.signal_type for s in signals}
    assert "OPERATOR_PROGRESSING" in types


def test_init_container_stuck_signal():
    signals = extract_signals(_make_report("node", "Init container init-db is stuck waiting with crash"))
    types = {s.signal_type for s in signals}
    assert "INIT_CONTAINER_STUCK" in types


def test_webhook_failure_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Webhook validation.example.com failed with timeout"))
    types = {s.signal_type for s in signals}
    assert "WEBHOOK_FAILURE" in types


def test_mount_failure_signal():
    signals = extract_signals(_make_report("node", "FailedMount: MountVolume.SetUp failed for volume config"))
    types = {s.signal_type for s in signals}
    assert "MOUNT_FAILURE" in types


def test_pdb_blocking_signal():
    signals = extract_signals(_make_report("node", "PDB my-pdb blocking evictions, disruptionsAllowed is 0"))
    types = {s.signal_type for s in signals}
    assert "PDB_BLOCKING" in types


def test_quota_exceeded_signal():
    signals = extract_signals(_make_report("node", "ResourceQuota exceeded, pods blocked from creation"))
    types = {s.signal_type for s in signals}
    assert "QUOTA_EXCEEDED" in types


def test_probe_misconfigured_signal():
    signals = extract_signals(_make_report("node", "Pod is Running but probe failing, not ready for 10 minutes"))
    types = {s.signal_type for s in signals}
    assert "PROBE_MISCONFIGURED" in types
