"""PR-F — frontend↔backend contract regression tests.

Locks the Pydantic models that form the wire contract against the
TypeScript types the frontend relies on. When someone adds a field on
one side without updating the other, these tests fail with a diff.

The tests are deliberately source-level, not HTTP-level:
  · Fast — no app boot required.
  · Catch drift at merge time, not at runtime in prod.
  · Frontend ↔ backend equality is asserted against a snapshot set that
    ships with this test, not parsed live out of the TS file — the TS
    side moves in multiple PRs a day and importing it here would chain
    a node dependency on every pytest run. If the TS side changes, the
    developer updates both sides and the snapshot expectation here.
"""
from __future__ import annotations

from src.api.models import (
    BudgetTelemetry,
    StartSessionRequest,
    StartSessionResponse,
)


# ── /api/v4/session/start request ────────────────────────────────────
#
# Frontend-authored fields (TS `StartSessionRequest`, typed manually
# in frontend/src/types/index.ts). This is the contract the backend
# MUST accept without silently dropping fields.

_TS_START_REQUEST_FIELDS = {
    # Core app-diagnostic
    "service_name",
    "time_window",
    "trace_id",
    "namespace",
    "elk_index",
    "repo_url",
    "profile_id",
    "capability",
    "cluster_url",
    "scan_mode",
    "scope",
    # Auth
    "auth_method",
    "auth_token",
    "kubeconfig_content",
    "role",
    # Database diagnostics (PR-F fix — previously silently dropped)
    "focus",
    "database_type",
    "sampling_mode",
    "include_explain_plans",
    "parent_session_id",
    "table_filter",
    "extra",
}


def _backend_field_names(model_cls) -> set[str]:
    """Return every field name Pydantic will accept — primary name + aliases."""
    names: set[str] = set()
    for field_name, field in model_cls.model_fields.items():
        names.add(field_name)
        if field.alias:
            names.add(field.alias)
    return names


def test_start_session_request_accepts_every_typescript_field():
    """Frontend TS fields must all be settable on the backend model.

    Reads StartSessionRequest.model_fields + aliases; compares against
    the TS snapshot. If the frontend adds a field without adding it to
    the backend, this test fails.
    """
    backend = _backend_field_names(StartSessionRequest)
    missing = _TS_START_REQUEST_FIELDS - backend
    assert not missing, (
        "Frontend sends fields the backend model doesn't declare "
        f"(Pydantic will silently drop them): {sorted(missing)}"
    )


def test_start_session_request_db_fields_are_declared():
    """Explicit coverage for PR-F Bug — DB-diagnostics capability fields."""
    fields = StartSessionRequest.model_fields
    for f in (
        "focus",
        "database_type",
        "sampling_mode",
        "include_explain_plans",
        "parent_session_id",
        "table_filter",
    ):
        assert f in fields, f"expected {f!r} on StartSessionRequest"


def test_start_session_request_db_fields_accept_camelcase():
    """Frontend was sending camelCase aliases for these; accept both."""
    req = StartSessionRequest.model_validate({
        "service_name": "s",
        "time_window": "1h",
        "databaseType": "postgres",
        "samplingMode": "deep",
        "includeExplainPlans": True,
        "parentSessionId": "parent-1",
        "tableFilter": ["public.users"],
    })
    assert req.database_type == "postgres"
    assert req.sampling_mode == "deep"
    assert req.include_explain_plans is True
    assert req.parent_session_id == "parent-1"
    assert req.table_filter == ["public.users"]


# ── /api/v4/session/{id}/status response ─────────────────────────────
#
# Expected key set on the response body. The route currently returns a
# dict (not Response-model-typed), so we lock the key set here.

_TS_SESSION_STATUS_KEYS_REQUIRED = {
    "session_id",
    "service_name",
    "phase",
    "confidence",
    "findings_count",
    "token_usage",
    "breadcrumbs",
    "created_at",
    "updated_at",
    "pending_action",
}

_TS_SESSION_STATUS_KEYS_OPTIONAL = {
    "incident_id",
    "agents_completed",
    "coverage_gaps",
    "budget",                    # PR-F fix — now emitted
    "self_consistency",
    "winner_critic_dissent",
    "capability",
    "investigation_mode",
    "related_sessions",
    "data_completeness",
    "diagnosis_stop_reason",
    "signature_match",
    "winning_agents",
}


def test_session_status_source_emits_required_keys():
    """Source-level grep — the /status route builds a dict whose
    literal key set covers every required frontend field.
    """
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src" / "api" / "routes_v4.py"
    body = src.read_text()
    # Find the get_session_status function body by offset; then assert
    # every required key appears as a quoted dict literal in the route
    # (good enough — the route assembles the dict inline).
    start = body.find('"/session/{session_id}/status"')
    assert start != -1
    end = body.find('@router_v4.get("/session/{session_id}/findings")')
    assert end != -1
    route = body[start:end]
    for key in _TS_SESSION_STATUS_KEYS_REQUIRED:
        assert f'"{key}"' in route, (
            f"/status route doesn't emit required frontend key {key!r}"
        )


def test_session_status_source_emits_budget_key():
    """PR-F — budget MUST be emitted so the FreshnessRow cost clause
    has something to render. Regression guard."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src" / "api" / "routes_v4.py"
    body = src.read_text()
    assert '"budget"' in body
    # And it must use the BudgetTelemetry translator, not the raw
    # SessionBudget.to_dict() which has a completely different shape.
    assert "BudgetTelemetry.from_session_budget" in body


# ── BudgetTelemetry shape ─────────────────────────────────────────────


def test_budget_telemetry_matches_typescript_shape():
    """Frontend type is { tool_calls_used, tool_calls_max, llm_usd_used,
    llm_usd_max }. Test locks the Pydantic model key set to that shape.
    """
    expected = {"tool_calls_used", "tool_calls_max", "llm_usd_used", "llm_usd_max"}
    actual = set(BudgetTelemetry.model_fields.keys())
    assert actual == expected, f"BudgetTelemetry drift: {actual ^ expected}"


def test_budget_telemetry_from_session_budget_roundtrip():
    """Translator rejects None cleanly and zeros produce an empty shape."""
    t = BudgetTelemetry.from_session_budget(None)
    assert t.tool_calls_used == 0
    assert t.tool_calls_max == 0
    assert t.llm_usd_used == 0.0
    assert t.llm_usd_max == 0.0


def test_budget_telemetry_from_session_budget_real():
    from src.utils.llm_budget import get_budget_for_mode
    budget = get_budget_for_mode("standard")
    budget.record(input_tokens=100_000, output_tokens=10_000, latency_ms=5000)
    budget.record(input_tokens=50_000, output_tokens=5_000, latency_ms=2500)

    t = BudgetTelemetry.from_session_budget(budget)
    assert t.tool_calls_max == budget.max_llm_calls
    assert t.tool_calls_used == 2
    # 150_000 tokens × $3 / 1M ≈ $0.45
    assert 0.40 < t.llm_usd_used < 0.50
    assert t.llm_usd_max == round(budget.max_tokens_input * 3.0 / 1_000_000.0, 4)


def test_budget_telemetry_from_session_budget_malformed():
    """Translator must not raise on objects missing expected attributes."""
    class _Junk:
        pass
    t = BudgetTelemetry.from_session_budget(_Junk())
    assert isinstance(t, BudgetTelemetry)
    assert t.tool_calls_used == 0


# ── StartSessionResponse shape ───────────────────────────────────────


_TS_START_RESPONSE_FIELDS = {
    "session_id",
    "incident_id",
    "status",
    "message",
    "service_name",
    "created_at",
    "capability",
}


def test_start_session_response_matches_typescript_shape():
    backend = _backend_field_names(StartSessionResponse)
    missing = _TS_START_RESPONSE_FIELDS - backend
    assert not missing, (
        f"StartSessionResponse missing fields expected by frontend: {sorted(missing)}"
    )
