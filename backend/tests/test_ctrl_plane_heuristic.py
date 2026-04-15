"""Tests for ctrl_plane_agent heuristic additions."""

import pytest
from src.agents.cluster.ctrl_plane_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_operator_progressing_detected():
    data = {
        "cluster_operators": [
            {"name": "kube-apiserver", "degraded": False, "available": True, "progressing": True},
        ],
        "api_health": {"status": "ok"},
        "events": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("progressing" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_scc_privileged_non_system():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "security_context_constraints": [
            {"name": "my-scc", "allowPrivilegedContainer": True, "users": ["system:serviceaccount:production:default"]},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("scc" in d.lower() or "privileged" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_mcp_mismatch_detected():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "machine_config_pools": [
            {"name": "worker", "degraded": False, "machineCount": 6, "updatedMachineCount": 4},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("mismatch" in d.lower() or "updating" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_etcd_pod_not_running():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "etcd_pods": [
            {"name": "etcd-master-0", "namespace": "openshift-etcd", "status": "CrashLoopBackOff", "restarts": 5},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    etcd_anomalies = [d for d in descs if "etcd" in d.lower()]
    assert len(etcd_anomalies) > 0
    for d in etcd_anomalies:
        assert severities[d] in ("high", "critical")


@pytest.mark.asyncio
async def test_webhook_fail_external_detected():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "webhooks": [
            {
                "name": "external-validator",
                "failure_policy": "Fail",
                "timeout_seconds": 30,
                "client_config": {"url": "https://external.example.com/validate"},
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("webhook" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_webhook_high_timeout():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "webhooks": [
            {
                "name": "slow-webhook",
                "failure_policy": "Ignore",
                "timeout_seconds": 15,
                "client_config": {"service": {"name": "svc", "namespace": "ns"}},
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("timeout" in d.lower() or "webhook" in d.lower() for d in descs)
