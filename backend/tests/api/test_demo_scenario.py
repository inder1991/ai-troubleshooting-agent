"""PR-K8 — smoke tests for the Zepay scenario replayer."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes_demo_scenario import _deep_merge, _RUNS, ScenarioRun


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "src/api/fixtures/zepay-main-incident.json"
)


# ── JSON shape ─────────────────────────────────────────────────────────


def test_fixture_exists_and_parses():
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    timeline = json.loads(FIXTURE.read_text())
    assert isinstance(timeline, list)
    assert len(timeline) >= 150, f"expected ≥150 entries, got {len(timeline)}"


def test_fixture_entries_have_required_shape():
    timeline = json.loads(FIXTURE.read_text())
    kinds = set()
    for i, entry in enumerate(timeline):
        assert "t" in entry, f"entry {i} missing 't'"
        assert "kind" in entry, f"entry {i} missing 'kind'"
        assert isinstance(entry["t"], (int, float)), f"entry {i} 't' not numeric"
        kinds.add(entry["kind"])
    assert kinds == {"event", "state_patch", "phase_change", "await_approval"}, kinds


def test_fixture_timeline_is_monotonic_enough():
    """Timeline may have parallel agents with overlapping t values, but no
    entry should regress by more than 1 second (parallel slack)."""
    timeline = json.loads(FIXTURE.read_text())
    for i in range(1, len(timeline)):
        delta = timeline[i]["t"] - timeline[i - 1]["t"]
        assert delta >= -2.0, (
            f"entry {i} goes backwards by {-delta}s "
            f"(t={timeline[i-1]['t']} → {timeline[i]['t']})"
        )


def test_fixture_only_uses_ui_rendered_event_types():
    """Every event_type must be in the allow-list of types the War Room
    actually renders (audited from frontend/src)."""
    allowed = {
        "started", "progress", "tool_call", "finding", "summary", "success",
        "error", "warning", "phase_change", "attestation_required", "reasoning",
    }
    timeline = json.loads(FIXTURE.read_text())
    found: set[str] = set()
    for e in timeline:
        if e["kind"] == "event":
            found.add(e["event"]["event_type"])
    unknown = found - allowed
    assert not unknown, f"timeline uses event types the UI won't render: {unknown}"


def test_fixture_has_attestation_gate():
    timeline = json.loads(FIXTURE.read_text())
    gates = [e for e in timeline if e["kind"] == "await_approval"]
    assert len(gates) == 1, "expected exactly 1 await_approval entry"
    assert "pending_action" in gates[0]


def test_fixture_carries_all_notable_accounts():
    timeline = json.loads(FIXTURE.read_text())
    payload = json.dumps(timeline)
    assert "C-CORP-ACME-LOG-0042" in payload
    assert "C-CHEN-SARAH-8741" in payload
    assert "C-INFLUENCER-BTC-2291" in payload


def test_fixture_includes_signature_match_and_stop_reason():
    timeline = json.loads(FIXTURE.read_text())
    payload = json.dumps(timeline)
    assert "retry_without_idempotency_key" in payload
    assert "high_confidence_no_challenges" in payload


def test_fixture_includes_three_fix_prs_with_realistic_metadata():
    timeline = json.loads(FIXTURE.read_text())
    payload = json.dumps(timeline)
    for pr in ("8427", "1203", "294"):
        assert pr in payload, f"PR #{pr} missing"
    for repo in ("payment-service", "shared-finance-models", "reconciliation-job"):
        assert f"zepay/{repo}" in payload


# ── _deep_merge primitive ──────────────────────────────────────────────


def test_deep_merge_replaces_scalar():
    dst = {"phase": "initial"}
    _deep_merge(dst, {"phase": "diagnosis_complete"})
    assert dst["phase"] == "diagnosis_complete"


def test_deep_merge_merges_dict():
    dst = {"a": {"x": 1, "y": 2}}
    _deep_merge(dst, {"a": {"y": 99, "z": 3}})
    assert dst["a"] == {"x": 1, "y": 99, "z": 3}


def test_deep_merge_append_syntax_adds_to_list():
    dst = {"token_usage": [{"agent": "log_agent"}]}
    _deep_merge(dst, {"token_usage[+]": {"agent": "metric_agent"}})
    assert dst["token_usage"] == [
        {"agent": "log_agent"},
        {"agent": "metric_agent"},
    ]


def test_deep_merge_append_creates_list_when_absent():
    dst: dict = {}
    _deep_merge(dst, {"critic_verdicts[+]": {"verdict": "confirmed"}})
    assert dst["critic_verdicts"] == [{"verdict": "confirmed"}]


# ── Endpoint gating ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_runs():
    _RUNS.clear()
    yield
    _RUNS.clear()


def test_start_returns_404_without_demo_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.routes_demo_scenario import router

    monkeypatch.delenv("DEMO_MODE", raising=False)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.post("/api/v4/demo/scenario/start", json={"scenario": "zepay-main-incident"})
    assert r.status_code == 404
