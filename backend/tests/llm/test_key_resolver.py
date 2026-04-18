"""Resolver precedence + env-var rendering for the multi-key Anthropic story."""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

from src.llm.key_resolver import (
    DEFAULT_ENV_VAR,
    MissingKeyError,
    NAMED_ENV_PREFIX,
    _normalize,
    available_named_keys,
    key_for,
)


@contextmanager
def _env(**kv: str):
    """Set/unset env vars for the duration of a test, then restore."""
    original = {k: os.environ.get(k) for k in kv}
    try:
        for k, v in kv.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ─── _normalize ──────────────────────────────────────────────────────────────


def test_normalize_simple():
    assert _normalize("premium") == "ANTHROPIC_API_KEY_PREMIUM"


def test_normalize_kebab():
    assert _normalize("billing-team-a") == "ANTHROPIC_API_KEY_BILLING_TEAM_A"


def test_normalize_already_snake():
    assert _normalize("Cheap_Models") == "ANTHROPIC_API_KEY_CHEAP_MODELS"


def test_normalize_strips_whitespace():
    assert _normalize("  premium  ") == "ANTHROPIC_API_KEY_PREMIUM"


# ─── key_for() — resolver semantics ──────────────────────────────────────────


def test_default_when_no_name(monkeypatch):
    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    assert key_for() == "sk-default"
    assert key_for(None) == "sk-default"
    assert key_for("") == "sk-default"


def test_named_overrides_default(monkeypatch):
    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}PREMIUM", "sk-premium")
    assert key_for("premium") == "sk-premium"
    # Default still wins when no name given.
    assert key_for() == "sk-default"


def test_named_falls_back_to_default_when_name_unmapped(monkeypatch):
    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    # No PREMIUM env var set — must fall back rather than crash.
    monkeypatch.delenv(f"{NAMED_ENV_PREFIX}PREMIUM", raising=False)
    assert key_for("premium") == "sk-default"


def test_empty_named_var_falls_back(monkeypatch):
    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}PREMIUM", "   ")  # whitespace-only
    assert key_for("premium") == "sk-default"


def test_missing_default_raises_when_no_named_works(monkeypatch):
    monkeypatch.delenv(DEFAULT_ENV_VAR, raising=False)
    monkeypatch.delenv(f"{NAMED_ENV_PREFIX}PREMIUM", raising=False)
    with pytest.raises(MissingKeyError) as e:
        key_for("premium")
    assert "ANTHROPIC_API_KEY" in str(e.value)


def test_missing_default_with_no_name_raises(monkeypatch):
    monkeypatch.delenv(DEFAULT_ENV_VAR, raising=False)
    with pytest.raises(MissingKeyError):
        key_for()


def test_kebab_name_resolves(monkeypatch):
    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}BILLING_TEAM_A", "sk-team-a")
    assert key_for("billing-team-a") == "sk-team-a"


# ─── available_named_keys() — Settings UI helper ─────────────────────────────


def test_lists_named_keys_only(monkeypatch):
    # Wipe any pre-existing ANTHROPIC_API_KEY_* env vars in test runner shell
    for k in list(os.environ):
        if k.startswith(NAMED_ENV_PREFIX) and k != DEFAULT_ENV_VAR:
            monkeypatch.delenv(k, raising=False)

    monkeypatch.setenv(DEFAULT_ENV_VAR, "sk-default")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}PREMIUM", "sk-1")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}CHEAP", "sk-2")
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}EMPTY", "")  # empty = excluded

    names = available_named_keys()
    assert names == ["cheap", "premium"]  # sorted, lowercased, no default, no empty


def test_underscores_become_kebab_in_listing(monkeypatch):
    for k in list(os.environ):
        if k.startswith(NAMED_ENV_PREFIX) and k != DEFAULT_ENV_VAR:
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv(f"{NAMED_ENV_PREFIX}BILLING_TEAM_A", "sk-x")
    assert available_named_keys() == ["billing-team-a"]
