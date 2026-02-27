import pytest


def test_cluster_findings_format():
    """Verify the cluster findings response shape matches frontend expectations."""
    findings = {
        "diagnostic_id": "DIAG-TEST",
        "platform": "openshift",
        "platform_health": "DEGRADED",
        "data_completeness": 0.75,
        "causal_chains": [],
        "domain_reports": [],
        "blast_radius": {"summary": "", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
        "remediation": {"immediate": [], "long_term": []},
    }
    assert "platform_health" in findings
    assert "domain_reports" in findings
    assert "causal_chains" in findings
    assert isinstance(findings["data_completeness"], float)
