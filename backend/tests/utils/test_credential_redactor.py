"""Credential redactor — unit tests.

Locks the contract for PR-A's redact-before-log pattern. Any future
regression that reintroduces raw API keys into logs fails these tests.
"""
from __future__ import annotations

import pytest

from src.utils.credential_redactor import redact_for_logging, redact_string


# ── Anthropic sk-ant- keys ───────────────────────────────────────────


def test_redacts_anthropic_api_key_inline():
    text = "call failed with api_key=sk-ant-abc123DEFghi456_example_long_token"
    out = redact_string(text)
    # The important invariant: no part of the raw key appears in the
    # output. Either redactor path (sk-ant pattern OR api_key assignment
    # pattern) may catch it — we don't care which, only that it's gone.
    assert "sk-ant-abc123" not in out
    assert "abc123DEF" not in out
    assert "<redacted>" in out


def test_redacts_anthropic_key_even_when_embedded_in_url():
    text = "https://api.anthropic.com?api_key=sk-ant-DEADBEEF12345678deadbeef"
    out = redact_string(text)
    assert "DEADBEEF" not in out


def test_redacts_multiple_keys_in_one_string():
    text = "primary=sk-ant-AAAAAAAA1111 secondary=sk-ant-BBBBBBBB2222"
    out = redact_string(text)
    assert "AAAAAAAA" not in out
    assert "BBBBBBBB" not in out
    # At least two redaction markers present — either through sk-ant or
    # generic key/value patterns.
    assert out.count("<redacted>") >= 2


# ── Generic sk-* (OpenAI-style) ──────────────────────────────────────


def test_redacts_generic_sk_key():
    text = "OpenAI key: sk-1234567890abcdefghij1234567890"
    out = redact_string(text)
    assert "1234567890abcdef" not in out
    assert "sk-<redacted>" in out


def test_does_not_redact_sk_prefix_of_ordinary_words():
    """Plain English strings that happen to contain 'sk-' (short) are untouched."""
    assert redact_string("sk-based model") == "sk-based model"
    assert redact_string("risk-level") == "risk-level"


# ── HTTP headers ─────────────────────────────────────────────────────


def test_redacts_bearer_token():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def"
    out = redact_string(text)
    # The critical invariant — the raw token never survives. Either
    # the Bearer pattern or the Authorization pattern (or both) catch
    # it; we don't care which.
    assert "eyJ" not in out
    assert "<redacted>" in out


def test_redacts_bearer_case_insensitive():
    assert "<redacted>" in redact_string("authorization: BEARER mytoken123456")


def test_redacts_authorization_header():
    text = "authorization: sk-somelongvalue12345678"
    out = redact_string(text)
    assert "sk-somelongvalue" not in out
    assert "authorization: <redacted>" in out


def test_redacts_x_api_key_header():
    text = "x-api-key: abcdef123456"
    out = redact_string(text)
    assert "abcdef" not in out


# ── URL / form / JSON assignments ────────────────────────────────────


def test_redacts_api_key_assignment():
    assert "secret123" not in redact_string("api_key=secret123")
    assert "secret123" not in redact_string("api-key: secret123")
    assert "secret123" not in redact_string('{"api_key": "secret123"}')


def test_redacts_generic_password_secret_token_keys():
    for key in ("password", "secret", "token"):
        text = f"{key}=mysecretvalue"
        out = redact_string(text)
        assert "mysecretvalue" not in out
        assert f"{key}=<redacted>" in out


# ── Dict / mapping handling ──────────────────────────────────────────


def test_redacts_sensitive_keys_in_dict_even_when_value_has_no_pattern():
    value = {"authorization": "literally anything at all", "other": "fine"}
    out = redact_for_logging(value)
    assert out["authorization"] == "<redacted>"
    assert out["other"] == "fine"


def test_redacts_nested_dict_values():
    value = {"request": {"headers": {"x-api-key": "abcd"}, "body": "sk-ant-AAAAAAAA1111"}}
    out = redact_for_logging(value)
    assert out["request"]["headers"]["x-api-key"] == "<redacted>"
    assert "AAAAAAAA" not in out["request"]["body"]


def test_preserves_non_sensitive_structure():
    value = {"status": 400, "agent_name": "log_agent", "count": 42}
    assert redact_for_logging(value) == value


# ── Exception path (the real failure mode from the audit) ────────────


def test_redacts_exception_message():
    class _Err(Exception):
        def __str__(self):
            return "auth failed: authorization: Bearer sk-ant-DEADBEEF1234567890deadbeef"

    out = redact_for_logging(_Err())
    assert "sk-ant-DEADBEEF" not in out
    assert "DEADBEEF" not in out


def test_redacts_exception_with_json_body():
    class _Err(Exception):
        def __str__(self):
            return '{"error": {"message": "bad key", "key": "sk-ant-XYZ1234567890abcdefXY"}}'

    out = redact_for_logging(_Err())
    assert "XYZ1234567890" not in out


# ── List + tuple ─────────────────────────────────────────────────────


def test_redacts_list_items():
    value = ["ok", "authorization: Bearer sk-ant-AAAAAAAA1111"]
    out = redact_for_logging(value)
    assert out[0] == "ok"
    assert "AAAAAAAA" not in out[1]
    assert isinstance(out, list)


def test_redacts_tuple_items():
    value = ("ok", "x-api-key: secret_val_12")
    out = redact_for_logging(value)
    assert out[0] == "ok"
    assert "secret_val_12" not in out[1]
    assert isinstance(out, tuple)


# ── Idempotence + safety ─────────────────────────────────────────────


def test_redact_string_is_idempotent():
    text = "api_key=sk-ant-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert redact_string(redact_string(text)) == redact_string(text)


def test_empty_and_none_inputs():
    assert redact_string("") == ""
    assert redact_for_logging(None) is None
    # Non-string primitives pass through unchanged so log records
    # preserve their type (e.g. status codes stay numeric).
    assert redact_for_logging(123) == 123
    assert redact_for_logging(True) is True


def test_benign_text_passes_through_unchanged():
    text = "log_agent found 3 patterns on checkout-service"
    assert redact_string(text) == text
