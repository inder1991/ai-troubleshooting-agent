"""Tests for platform-layer proactive checks."""

from src.agents.cluster.proactive_analyzer import (
    PROACTIVE_CHECKS, _EVALUATORS,
)


def test_cluster_version_check_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "cluster_version_check" in ids
    assert "cluster_version_check" in _EVALUATORS


def test_olm_subscription_health_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "olm_subscription_health" in ids
    assert "olm_subscription_health" in _EVALUATORS


def test_machine_health_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "machine_health" in ids
    assert "machine_health" in _EVALUATORS


def test_proxy_config_check_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "proxy_config_check" in ids
    assert "proxy_config_check" in _EVALUATORS


def test_cluster_version_check_failing():
    evaluator = _EVALUATORS["cluster_version_check"]
    data = [{
        "conditions": [
            {"type": "Available", "status": "True"},
            {"type": "Failing", "status": "True", "message": "Unable to apply"},
        ],
        "version": "4.14.2",
        "desired": "4.14.3",
    }]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "critical"


def test_cluster_version_check_progressing():
    evaluator = _EVALUATORS["cluster_version_check"]
    data = [{
        "conditions": [
            {"type": "Available", "status": "True"},
            {"type": "Progressing", "status": "True"},
            {"type": "Failing", "status": "False"},
        ],
        "version": "4.14.2",
        "desired": "4.14.3",
    }]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"


def test_olm_subscription_health_upgrade_failed():
    evaluator = _EVALUATORS["olm_subscription_health"]
    data = [{"name": "jaeger", "namespace": "ns", "state": "UpgradeFailed", "currentCSV": "v2", "installedCSV": "v1"}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "critical"


def test_olm_subscription_health_csv_mismatch():
    evaluator = _EVALUATORS["olm_subscription_health"]
    data = [{"name": "jaeger", "namespace": "ns", "state": "UpgradePending", "currentCSV": "v2", "installedCSV": "v1"}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"


def test_machine_health_failed():
    evaluator = _EVALUATORS["machine_health"]
    data = [{"name": "worker-2", "phase": "Failed"}]
    findings = evaluator(data)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_machine_health_not_running():
    evaluator = _EVALUATORS["machine_health"]
    data = [{"name": "worker-3", "phase": "Provisioning"}]
    findings = evaluator(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_proxy_config_no_noproxy():
    evaluator = _EVALUATORS["proxy_config_check"]
    data = [{"httpProxy": "http://proxy:3128", "httpsProxy": "", "noProxy": "", "trustedCA": ""}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "medium"


def test_proxy_config_no_trusted_ca():
    evaluator = _EVALUATORS["proxy_config_check"]
    data = [{"httpProxy": "", "httpsProxy": "http://proxy:3128", "noProxy": ".svc", "trustedCA": ""}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"
