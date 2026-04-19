"""PR-J — /readyz LLM credential check."""
from __future__ import annotations

import pytest

from src.api.health import _check_llm_credential


def test_empty_env_reports_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert _check_llm_credential().startswith("error:")
    assert "not set" in _check_llm_credential()


def test_whitespace_only_env_reports_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert "not set" in _check_llm_credential()


def test_placeholder_env_reports_error(monkeypatch):
    for val in ("REPLACE_ME", "replace_with_real_key", "TODO", "xxx", "<set>"):
        monkeypatch.setenv("ANTHROPIC_API_KEY", val)
        assert "placeholder" in _check_llm_credential(), (
            f"expected {val!r} to be flagged as placeholder"
        )


def test_real_looking_key_reports_ok(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-abcDEF1234567890")
    assert _check_llm_credential() == "ok"


def test_credential_presence_does_not_leak_value(monkeypatch, caplog):
    """Regression guard — credential checker must never log the value."""
    secret = "sk-ant-do-not-log-this-secret-value"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    import logging
    with caplog.at_level(logging.DEBUG):
        _check_llm_credential()
    combined = " ".join(r.getMessage() for r in caplog.records)
    assert secret not in combined
