"""Sprint H.0b Story 9 — secret redaction processor (Q16 γ + Q13)."""

from __future__ import annotations


def test_redactor_replaces_aws_key() -> None:
    from src.observability._redactor import redact_secrets
    out = redact_secrets("AWS_KEY=AKIAIOSFODNN7EXAMPLE in config")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED]" in out


def test_redactor_replaces_jwt() -> None:
    from src.observability._redactor import redact_secrets
    jwt = "eyJ0eXAi.eyJzdWIi.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    out = redact_secrets(f"token={jwt}")
    assert jwt not in out
    assert "[REDACTED]" in out


def test_redactor_no_op_on_clean_text() -> None:
    from src.observability._redactor import redact_secrets
    out = redact_secrets("nothing sensitive here")
    assert out == "nothing sensitive here"
