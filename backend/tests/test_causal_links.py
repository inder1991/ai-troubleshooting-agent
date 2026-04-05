"""Tests for 5 new causal link types in CONSTRAINED_LINK_TYPES."""

from src.agents.cluster.synthesizer import CONSTRAINED_LINK_TYPES


def test_operator_degraded_rescheduling_link():
    assert "operator_degraded -> workload_rescheduling" in CONSTRAINED_LINK_TYPES


def test_quota_exceeded_scheduling_link():
    assert "quota_exceeded -> scheduling_failure" in CONSTRAINED_LINK_TYPES


def test_webhook_failure_pod_blocked_link():
    assert "webhook_failure -> pod_creation_blocked" in CONSTRAINED_LINK_TYPES


def test_mount_failure_crash_link():
    assert "mount_failure -> container_crash" in CONSTRAINED_LINK_TYPES


def test_probe_failure_service_link():
    assert "probe_failure -> service_degradation" in CONSTRAINED_LINK_TYPES
