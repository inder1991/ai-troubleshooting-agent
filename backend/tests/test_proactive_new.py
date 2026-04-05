"""Tests for 4 new proactive checks."""

from src.agents.cluster.proactive_analyzer import (
    _check_dns_replica,
    _check_webhook_risk,
    _check_pv_reclaim_delete,
    _check_ingress_spof,
)


def test_dns_zero_replicas_critical():
    data = [{"name": "dns-default", "namespace": "openshift-dns", "replicas_desired": 2, "replicas_ready": 0}]
    findings = _check_dns_replica(data)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_dns_single_replica_high():
    data = [{"name": "coredns", "namespace": "kube-system", "replicas_desired": 2, "replicas_ready": 1}]
    findings = _check_dns_replica(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_dns_healthy_no_findings():
    data = [{"name": "coredns", "namespace": "kube-system", "replicas_desired": 2, "replicas_ready": 2}]
    findings = _check_dns_replica(data)
    assert len(findings) == 0


def test_webhook_fail_external():
    data = [
        {
            "name": "external-validator",
            "failure_policy": "Fail",
            "client_config": {"url": "https://external.example.com/validate"},
            "timeout_seconds": 10,
        },
    ]
    findings = _check_webhook_risk(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_webhook_ignore_no_finding():
    data = [
        {
            "name": "safe-webhook",
            "failure_policy": "Ignore",
            "client_config": {"url": "https://external.example.com/validate"},
            "timeout_seconds": 5,
        },
    ]
    findings = _check_webhook_risk(data)
    assert len(findings) == 0


def test_pv_reclaim_delete_on_stateful():
    data = [
        {
            "name": "data-pvc",
            "namespace": "production",
            "reclaim_policy": "Delete",
            "owner_kind": "StatefulSet",
            "storage_class": "gp2",
        },
    ]
    findings = _check_pv_reclaim_delete(data)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_pv_retain_no_finding():
    data = [
        {
            "name": "data-pvc",
            "namespace": "production",
            "reclaim_policy": "Retain",
            "owner_kind": "StatefulSet",
            "storage_class": "gp2",
        },
    ]
    findings = _check_pv_reclaim_delete(data)
    assert len(findings) == 0


def test_ingress_single_replica():
    data = [{"name": "router-default", "namespace": "openshift-ingress", "replicas_desired": 1, "replicas_ready": 1}]
    findings = _check_ingress_spof(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_ingress_multi_replica_no_finding():
    data = [{"name": "router-default", "namespace": "openshift-ingress", "replicas_desired": 3, "replicas_ready": 3}]
    findings = _check_ingress_spof(data)
    assert len(findings) == 0
