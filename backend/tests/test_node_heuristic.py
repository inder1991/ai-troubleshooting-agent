"""Tests for node_agent heuristic additions."""

import pytest
from src.agents.cluster.node_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_init_container_stuck():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [],
        "pods": [
            {
                "name": "app-pod",
                "namespace": "production",
                "init_containers": [
                    {"name": "init-db", "state": "waiting", "reason": "CrashLoopBackOff"},
                ],
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("init" in d.lower() and ("stuck" in d.lower() or "crash" in d.lower()) for d in descs)


@pytest.mark.asyncio
async def test_probe_misconfiguration():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [],
        "pods": [
            {
                "name": "slow-start-pod",
                "namespace": "production",
                "status": "Running",
                "ready": False,
                "running_not_ready_minutes": 10,
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("probe" in d.lower() or "not ready" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_mount_failure_event():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [
            {"type": "Warning", "reason": "FailedMount", "object": "pod/app-pod", "message": "MountVolume.SetUp failed for volume config-vol"},
        ],
        "pods": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("mount" in d.lower() or "failedmount" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_quota_blocking_event():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [
            {"type": "Warning", "reason": "FailedCreate", "object": "replicaset/app-rs",
             "message": "Error creating: pods is forbidden: exceeded quota: compute-quota"},
        ],
        "pods": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("quota" in d.lower() for d in descs)
