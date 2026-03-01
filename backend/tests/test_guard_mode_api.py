"""Tests for guard mode API: scan_mode parameter and findings endpoint."""

import uuid
import pytest
from src.api.models import StartSessionRequest


# ── Model tests ──────────────────────────────────────────────────────────


def test_start_session_request_default_scan_mode():
    """Default scan_mode is 'diagnostic'."""
    req = StartSessionRequest(serviceName="test")
    assert req.scan_mode == "diagnostic"


def test_start_session_request_guard_scan_mode():
    """scan_mode='guard' is accepted."""
    req = StartSessionRequest(serviceName="test", scan_mode="guard")
    assert req.scan_mode == "guard"


def test_start_session_request_alias():
    """scanMode alias works."""
    req = StartSessionRequest(serviceName="test", scanMode="guard")
    assert req.scan_mode == "guard"


# ── Findings endpoint tests ─────────────────────────────────────────────


from src.api.routes_v4 import sessions, get_findings


@pytest.fixture
def guard_session_id():
    """Create a valid UUID4 session ID and clean up after test."""
    sid = str(uuid.uuid4())
    yield sid
    sessions.pop(sid, None)


@pytest.fixture
def diagnostic_session_id():
    """Create a valid UUID4 session ID and clean up after test."""
    sid = str(uuid.uuid4())
    yield sid
    sessions.pop(sid, None)


@pytest.mark.asyncio
async def test_guard_findings_returns_scan_result(guard_session_id):
    """Guard mode findings returns guard_scan_result."""
    sid = guard_session_id
    sessions[sid] = {
        "capability": "cluster_diagnostics",
        "scan_mode": "guard",
        "state": {
            "guard_scan_result": {
                "overall_health": "DEGRADED",
                "risk_score": 0.65,
                "current_risks": [{"category": "compute", "severity": "warning"}],
            },
        },
        "created_at": "2026-03-01T00:00:00+00:00",
    }
    result = await get_findings(sid)
    assert result["scan_mode"] == "guard"
    assert "guard_scan_result" in result
    assert result["guard_scan_result"]["overall_health"] == "DEGRADED"


@pytest.mark.asyncio
async def test_diagnostic_findings_includes_scan_mode(diagnostic_session_id):
    """Diagnostic mode findings includes scan_mode field."""
    sid = diagnostic_session_id
    sessions[sid] = {
        "capability": "cluster_diagnostics",
        "scan_mode": "diagnostic",
        "state": {
            "platform": "openshift",
            "platform_version": "4.14",
            "data_completeness": 0.8,
            "causal_chains": [],
            "uncorrelated_findings": [],
            "domain_reports": [],
            "health_report": {
                "platform_health": "HEALTHY",
                "blast_radius": {},
                "remediation": {},
                "execution_metadata": {"blocked_count": 2},
            },
        },
        "created_at": "2026-03-01T00:00:00+00:00",
    }
    result = await get_findings(sid)
    assert result.get("scan_mode") == "diagnostic"
    assert result["platform_health"] == "HEALTHY"
    assert "guard_scan_result" not in result


@pytest.mark.asyncio
async def test_guard_findings_without_result_returns_pending(guard_session_id):
    """Guard mode session without guard_scan_result returns PENDING."""
    sid = guard_session_id
    sessions[sid] = {
        "capability": "cluster_diagnostics",
        "scan_mode": "guard",
        "state": {},
        "created_at": "2026-03-01T00:00:00+00:00",
    }
    result = await get_findings(sid)
    # Falls through to pending branch since no guard_scan_result and state is empty dict
    assert result["session_id"] == sid
    assert result.get("platform_health") == "PENDING"
    assert result["findings"] == []
