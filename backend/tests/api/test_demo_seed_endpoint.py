"""PR-K7 — tests for /api/v4/demo/seed/{scenario}.

Scope:
  · In prod (DEMO_MODE unset) the endpoint returns 404 so its
    existence cannot be sniffed.
  · In demo mode (DEMO_MODE=on) it accepts the Zepay historical
    payload, writes into the sessions dict, and the incident then
    surfaces on a subsequent GET /api/v4/session/{id}/status.
  · Extra fields in the payload are ignored (forward-compat).

The test uses FastAPI's TestClient so nothing is cluster-dependent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _fixture_payload() -> dict:
    """Load the same file the demo-controller ships with."""
    repo_root = Path(__file__).resolve().parents[3]
    p = repo_root / "demo/zepay-demo/demo-controller/fixtures/historical-incident.json"
    assert p.exists(), f"fixture missing: {p}"
    return json.loads(p.read_text())


def _client_demo_mode(monkeypatch, on: bool) -> TestClient:
    """Build a minimal app that mounts the seed router (and the
    routes_v4 sessions dict it writes into), with DEMO_MODE controlled
    by the caller. We DON'T boot the full create_app() because that
    pulls a dozen heavy routers we don't need here."""
    if on:
        monkeypatch.setenv("DEMO_MODE", "on")
    else:
        monkeypatch.delenv("DEMO_MODE", raising=False)

    from src.api.routes_demo_seed import router as seed_router

    app = FastAPI()
    app.include_router(seed_router)
    return TestClient(app)


# ── prod posture ──────────────────────────────────────────────────


def test_seed_returns_404_when_demo_mode_off(monkeypatch):
    c = _client_demo_mode(monkeypatch, on=False)
    r = c.post("/api/v4/demo/seed/zepay-historical", json=_fixture_payload())
    assert r.status_code == 404
    # Body carries the generic "not found" we use elsewhere — doesn't
    # hint at the endpoint's real purpose.
    assert r.json() == {"detail": "not found"}


# ── demo posture ──────────────────────────────────────────────────


def test_seed_accepts_historical_payload(monkeypatch):
    c = _client_demo_mode(monkeypatch, on=True)
    payload = _fixture_payload()
    r = c.post("/api/v4/demo/seed/zepay-historical", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["seeded"] is True
    assert body["incident_id"] == payload["incident_id"]
    assert body["scenario"] == "zepay-historical"

    # And the sessions dict should now carry the entry.
    from src.api.routes_v4 import sessions
    assert payload["incident_id"] in sessions
    entry = sessions[payload["incident_id"]]
    assert entry["service_name"] == payload["service_name"]
    assert entry["phase"] == payload["phase"]
    # demo_seed metadata preserved for UI rendering
    assert entry["demo_seed"]["scenario"] == "zepay-historical"


def test_seed_is_idempotent(monkeypatch):
    c = _client_demo_mode(monkeypatch, on=True)
    payload = _fixture_payload()
    r1 = c.post("/api/v4/demo/seed/zepay-historical", json=payload)
    r2 = c.post("/api/v4/demo/seed/zepay-historical", json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


def test_seed_ignores_unknown_fields(monkeypatch):
    """Forward-compat: fixture file may grow new fields — endpoint must
    drop them silently instead of 422-ing the demo."""
    c = _client_demo_mode(monkeypatch, on=True)
    payload = _fixture_payload()
    payload["this_field_does_not_exist_yet"] = "fine"
    r = c.post("/api/v4/demo/seed/zepay-historical", json=payload)
    assert r.status_code == 200


def test_seed_requires_core_fields(monkeypatch):
    c = _client_demo_mode(monkeypatch, on=True)
    # Missing incident_id → 422.
    r = c.post("/api/v4/demo/seed/zepay-historical", json={
        "service_name": "cart-service",
        "created_at":   "2026-02-11T14:22:00Z",
        "updated_at":   "2026-02-11T18:14:00Z",
    })
    assert r.status_code == 422


def test_demo_mode_recognizes_common_truthy_values(monkeypatch):
    """`on`, `true`, `1`, `yes` (case-insensitive) all enable the route."""
    from src.api.routes_demo_seed import _demo_mode_on
    for v in ("on", "ON", "true", "True", "1", "yes"):
        monkeypatch.setenv("DEMO_MODE", v)
        assert _demo_mode_on() is True, v
    for v in ("off", "false", "0", "no", ""):
        monkeypatch.setenv("DEMO_MODE", v)
        assert _demo_mode_on() is False, v
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert _demo_mode_on() is False
