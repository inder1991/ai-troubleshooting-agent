import pytest
from src.agents.cluster.guard_formatter import (
    guard_formatter, _extract_current_risks, _compute_overall_health,
    _compute_risk_score, _compute_delta,
)
from src.agents.cluster.state import CurrentRisk, GuardScanResult


def _state_with_anomalies():
    return {
        "diagnostic_id": "test",
        "scan_mode": "guard",
        "platform": "openshift",
        "platform_version": "4.14",
        "domain_reports": [
            {
                "domain": "ctrl_plane", "status": "SUCCESS", "confidence": 80,
                "anomalies": [
                    {"domain": "ctrl_plane", "anomaly_id": "cp-1", "description": "DNS operator degraded", "evidence_ref": "ev-1", "severity": "critical"},
                ],
                "ruled_out": [], "evidence_refs": [], "truncation_flags": {}, "duration_ms": 500,
            }
        ],
        "issue_clusters": [],
        "health_report": {"remediation": {"immediate": [], "long_term": [{"description": "Increase etcd disk", "effort_estimate": "1 week"}]}},
        "previous_scan": None,
    }


@pytest.mark.asyncio
async def test_guard_mode_produces_result():
    result = await guard_formatter(_state_with_anomalies(), {})
    assert "guard_scan_result" in result
    gsr = result["guard_scan_result"]
    assert gsr["overall_health"] == "CRITICAL"
    assert len(gsr["current_risks"]) > 0


@pytest.mark.asyncio
async def test_diagnostic_mode_is_noop():
    state = {"scan_mode": "diagnostic", "diagnostic_id": "test"}
    result = await guard_formatter(state, {})
    assert "guard_scan_result" not in result


@pytest.mark.asyncio
async def test_no_scan_mode_defaults_to_noop():
    state = {"diagnostic_id": "test"}
    result = await guard_formatter(state, {})
    assert "guard_scan_result" not in result


@pytest.mark.asyncio
async def test_predictive_risks_from_remediation():
    result = await guard_formatter(_state_with_anomalies(), {})
    gsr = result["guard_scan_result"]
    assert len(gsr["predictive_risks"]) > 0


@pytest.mark.asyncio
async def test_delta_first_scan_is_empty():
    result = await guard_formatter(_state_with_anomalies(), {})
    delta = result["guard_scan_result"]["delta"]
    assert delta["new_risks"] == []
    assert delta["resolved_risks"] == []
    assert delta["previous_scan_id"] is None


@pytest.mark.asyncio
async def test_delta_detects_new_risks():
    state = _state_with_anomalies()
    state["previous_scan"] = {
        "scan_id": "gs-prev",
        "scanned_at": "2026-03-01T00:00:00Z",
        "current_risks": [],  # no risks before
    }
    result = await guard_formatter(state, {})
    delta = result["guard_scan_result"]["delta"]
    assert len(delta["new_risks"]) > 0


def test_overall_health_critical():
    risks = [CurrentRisk(category="operator", severity="critical", description="x")]
    assert _compute_overall_health(risks) == "CRITICAL"


def test_overall_health_healthy():
    assert _compute_overall_health([]) == "HEALTHY"


def test_risk_score_bounded():
    risks = [CurrentRisk(category="x", severity="critical") for _ in range(10)]
    score = _compute_risk_score(risks, [])
    assert score <= 1.0
