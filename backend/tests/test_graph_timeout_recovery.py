import pytest


def test_build_partial_health_report_from_domain_reports():
    """_build_partial_health_report must return a ClusterHealthReport-like dict from partial state."""
    from src.agents.cluster.graph import _build_partial_health_report

    partial_state = {
        "domain_reports": [
            {"domain": "ctrl_plane", "status": "SUCCESS", "confidence": 80,
             "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001",
                             "description": "DNS degraded", "evidence_ref": "op/dns",
                             "severity": "high", "evidence_sources": []}],
             "ruled_out": [], "evidence_refs": [], "truncation_flags": {},
             "token_usage": 0, "duration_ms": 0},
            {"domain": "node", "status": "FAILED", "confidence": 0,
             "anomalies": [], "ruled_out": [], "evidence_refs": [],
             "truncation_flags": {}, "token_usage": 0, "duration_ms": 0},
        ],
        "proactive_findings": [],
        "data_completeness": 0.4,
        "namespaces": ["default"],
        "platform": "kubernetes",
        "platform_version": "1.29.0",
        "diagnostic_id": "test-diag",
    }

    report = _build_partial_health_report(partial_state)

    assert report is not None
    assert report.get("status") == "PARTIAL_TIMEOUT"
    # With a FAILED domain, health must be UNKNOWN or DEGRADED — not HEALTHY
    assert report.get("overall_status") not in ("HEALTHY",)
    # All anomalies from completed domains should be in uncorrelated_findings
    assert any(f.get("anomaly_id") == "cp-001"
               for f in report.get("uncorrelated_findings", []))
    # No remediation steps (synthesis didn't complete)
    assert report.get("remediation", {}).get("immediate", []) == []


def test_build_partial_health_report_empty_state():
    """_build_partial_health_report must not crash on empty state."""
    from src.agents.cluster.graph import _build_partial_health_report

    report = _build_partial_health_report({})
    assert report is not None
    assert report.get("status") == "PARTIAL_TIMEOUT"
    assert report.get("overall_status") == "UNKNOWN"
