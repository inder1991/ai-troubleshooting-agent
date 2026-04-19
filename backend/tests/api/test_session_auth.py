"""Session-ownership enforcement — unit tests.

Locks the PR-A contract:
  * When SESSION_OWNERSHIP_CHECK=off, enforce_session_owner is a no-op
    regardless of who's calling — zero behavior change for single-tenant
    deployments.
  * When =on, a caller whose extracted owner_id differs from the
    session's recorded owner_id gets a 403.
  * Backfill tolerance — sessions created before ownership tracking
    existed (no owner_id field) are never blocked.
"""
from __future__ import annotations

import os
from typing import Any, Dict

import pytest
from fastapi import HTTPException

from src.api import session_auth as sa


class _FakeRequest:
    """Minimal Request-compatible shim for unit tests."""

    def __init__(self, headers: Dict[str, str] | None = None, state: Dict[str, Any] | None = None) -> None:
        self.headers = headers or {}
        self.state = type("_S", (), state or {})()


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Start every test with the feature flag OFF."""
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "off")
    yield


# ── extract_owner_id ────────────────────────────────────────────────


def test_extract_returns_anonymous_when_no_signal():
    assert sa.extract_owner_id(_FakeRequest()) == "anonymous"


def test_extract_uses_header_when_present():
    req = _FakeRequest(headers={sa.SESSION_OWNER_HEADER: "user-42"})
    assert sa.extract_owner_id(req) == "user-42"


def test_extract_strips_whitespace_from_header():
    req = _FakeRequest(headers={sa.SESSION_OWNER_HEADER: "  user-42  "})
    assert sa.extract_owner_id(req) == "user-42"


def test_extract_prefers_request_state_over_header():
    req = _FakeRequest(
        headers={sa.SESSION_OWNER_HEADER: "header-user"},
        state={"owner_id": "state-user"},
    )
    assert sa.extract_owner_id(req) == "state-user"


def test_extract_ignores_empty_state_owner_id():
    req = _FakeRequest(
        headers={sa.SESSION_OWNER_HEADER: "header-user"},
        state={"owner_id": ""},
    )
    assert sa.extract_owner_id(req) == "header-user"


# ── ownership_check_enabled ─────────────────────────────────────────


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("SESSION_OWNERSHIP_CHECK", raising=False)
    assert sa.ownership_check_enabled() is False


def test_flag_on_when_env_is_on(monkeypatch):
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "on")
    assert sa.ownership_check_enabled() is True


def test_flag_case_insensitive(monkeypatch):
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "ON")
    assert sa.ownership_check_enabled() is True


# ── enforce_session_owner ───────────────────────────────────────────


def test_enforce_noop_when_flag_off():
    """With the flag off, any caller can touch any session."""
    sa.enforce_session_owner(
        session={"owner_id": "alice"},
        request=_FakeRequest(headers={sa.SESSION_OWNER_HEADER: "eve"}),
    )  # no raise


def test_enforce_noop_when_session_none():
    sa.enforce_session_owner(session=None, request=_FakeRequest())  # no raise


def test_enforce_noop_when_legacy_session_no_owner_id(monkeypatch):
    """A session persisted before ownership tracking existed still works
    when the flag is turned on mid-flight — we don't break in-flight work."""
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "on")
    sa.enforce_session_owner(
        session={"service_name": "svc"},  # no owner_id key
        request=_FakeRequest(headers={sa.SESSION_OWNER_HEADER: "anyone"}),
    )  # no raise


def test_enforce_allows_matching_owner(monkeypatch):
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "on")
    sa.enforce_session_owner(
        session={"owner_id": "alice"},
        request=_FakeRequest(headers={sa.SESSION_OWNER_HEADER: "alice"}),
    )


def test_enforce_blocks_mismatched_owner(monkeypatch):
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "on")
    with pytest.raises(HTTPException) as exc_info:
        sa.enforce_session_owner(
            session={"owner_id": "alice"},
            request=_FakeRequest(headers={sa.SESSION_OWNER_HEADER: "eve"}),
        )
    assert exc_info.value.status_code == 403
    assert "access" in exc_info.value.detail.lower()


def test_enforce_blocks_anonymous_when_owner_is_known(monkeypatch):
    """With the flag on, an anonymous caller can't touch an owned
    session — even if the flag is new and the owner was recorded
    before the caller arrived."""
    monkeypatch.setenv("SESSION_OWNERSHIP_CHECK", "on")
    with pytest.raises(HTTPException) as exc_info:
        sa.enforce_session_owner(
            session={"owner_id": "alice"},
            request=_FakeRequest(),  # no header, no state → anonymous
        )
    assert exc_info.value.status_code == 403
