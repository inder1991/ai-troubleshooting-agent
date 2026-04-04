import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_webhook_accepts_firing_alert_and_schedules_session():
    """Webhook must accept a firing Alertmanager payload and return session_id."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "firing",
                         "labels": {"namespace": "production", "workload": "order-service",
                                    "severity": "warning", "alertname": "HighRestartRate"},
                         "annotations": {"summary": "High restart rate"}}],
            "groupLabels": {"namespace": "production"},
            "commonLabels": {"severity": "warning", "namespace": "production",
                              "workload": "order-service"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "scheduled"
    assert "session_id" in body
    assert body["delay_seconds"] >= 0
    assert "scope" in body


@pytest.mark.asyncio
async def test_webhook_ignores_resolved_alerts():
    """Webhook must return status=ignored for resolved alerts."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "resolved",
                         "labels": {"namespace": "production", "severity": "warning"},
                         "annotations": {}}],
            "groupLabels": {},
            "commonLabels": {"severity": "warning"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_ignores_info_severity():
    """Webhook must return status=ignored for severity=info."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "firing",
                         "labels": {"namespace": "default", "severity": "info"},
                         "annotations": {}}],
            "groupLabels": {},
            "commonLabels": {"severity": "info"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_scope_derivation_workload_level():
    """When workload + namespace labels present, scope level must be workload."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope(
        {"namespace": "prod", "workload": "my-app", "severity": "critical"}
    )
    assert scope["level"] == "workload"
    assert scope["namespaces"] == ["prod"]
    assert scan_mode == "comprehensive"


def test_scope_derivation_namespace_level():
    """When only namespace label, scope must be namespace."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope({"namespace": "staging", "severity": "warning"})
    assert scope["level"] == "namespace"
    assert scan_mode == "diagnostic"


def test_scope_derivation_cluster_level():
    """When no namespace label, scope must be cluster."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope({"severity": "critical"})
    assert scope["level"] == "cluster"


@pytest.mark.asyncio
async def test_webhook_deduplicates_same_target():
    """Second firing alert for same target within dedup window returns deduplicated."""
    import time
    from src.api.routes_alerts import _active_alert_sessions
    from src.api.main import app

    # Clear any existing state
    _active_alert_sessions.clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "firing",
                         "labels": {"namespace": "dedup-test", "workload": "dedup-svc",
                                    "severity": "warning", "alertname": "TestAlert"},
                         "annotations": {}}],
            "groupLabels": {},
            "commonLabels": {"namespace": "dedup-test", "workload": "dedup-svc", "severity": "warning"},
            "commonAnnotations": {},
        }
        resp1 = await client.post("/api/v5/alerts/webhook", json=payload)
        resp2 = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp1.status_code == 200
    assert resp1.json()["status"] == "scheduled"
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "deduplicated"
    assert resp2.json()["session_id"] == resp1.json()["session_id"]
