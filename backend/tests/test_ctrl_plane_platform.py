"""Tests for platform-layer ctrl_plane_agent heuristic checks."""

import pytest
from src.agents.cluster.ctrl_plane_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_cluster_version_upgrade_stuck():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.3",
            "conditions": [
                {"type": "Available", "status": "True"},
                {"type": "Progressing", "status": "True", "message": "Working towards 4.14.3"},
                {"type": "Failing", "status": "False"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("cluster" in d.lower() and "version" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_cluster_version_failing():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.3",
            "conditions": [
                {"type": "Available", "status": "True"},
                {"type": "Progressing", "status": "True"},
                {"type": "Failing", "status": "True", "message": "Unable to apply 4.14.3"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    failing = [a for a in result["anomalies"] if "failing" in a["description"].lower() or "cluster" in a["description"].lower()]
    assert len(failing) > 0
    assert any(a["severity"] == "critical" for a in failing)


@pytest.mark.asyncio
async def test_cluster_version_available_false():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.2",
            "conditions": [
                {"type": "Available", "status": "False", "message": "Cluster not available"},
                {"type": "Progressing", "status": "False"},
                {"type": "Failing", "status": "False"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    severities = [a["severity"] for a in result["anomalies"]]
    assert "critical" in severities


@pytest.mark.asyncio
async def test_olm_subscription_not_at_latest():
    data = {
        "subscriptions": [
            {"name": "jaeger", "state": "UpgradePending", "currentCSV": "v1.51", "installedCSV": "v1.47"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("subscription" in d and "jaeger" in d for d in descs)


@pytest.mark.asyncio
async def test_olm_csv_failed():
    data = {
        "csvs": [
            {"name": "jaeger-operator.v1.51.0", "phase": "Failed", "reason": "ComponentFailed", "message": "deploy failed"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("clusterserviceversion" in d or "csv" in d.split() for d in descs)


@pytest.mark.asyncio
async def test_olm_install_plan_requires_approval():
    data = {
        "install_plans": [
            {"name": "install-abc", "approval": "Manual", "approved": False, "phase": "RequiresApproval", "csv_names": ["op.v1"]},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("installplan" in d or "install plan" in d for d in descs)
    plan_anomalies = [a for a in result["anomalies"] if "installplan" in a["description"].lower() or "install plan" in a["description"].lower()]
    assert all(a["severity"] == "low" for a in plan_anomalies)


@pytest.mark.asyncio
async def test_machine_not_running():
    data = {
        "machines": [
            {"name": "worker-2", "phase": "Failed", "node_ref": "", "conditions": []},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("machine" in d and "worker-2" in d for d in descs)
    assert result["anomalies"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_machine_provisioned_no_node_ref():
    data = {
        "machines": [
            {"name": "worker-3", "phase": "Provisioned", "node_ref": "", "conditions": []},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("machine" in d and "node" in d for d in descs)
    assert result["anomalies"][0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_proxy_misconfigured_no_noproxy():
    data = {
        "proxy_config": {
            "httpProxy": "http://proxy.corp:3128",
            "httpsProxy": "http://proxy.corp:3128",
            "noProxy": "",
            "trustedCA": "",
        },
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("proxy" in d for d in descs)
