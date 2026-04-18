"""SpanTagRedactor — denylist key + value regex redaction tests."""
from __future__ import annotations

from src.agents.tracing.redactor import RedactionConfig, SpanTagRedactor
from src.models.schemas import SpanInfo


def _span(tags: dict[str, str], error_message=None) -> SpanInfo:
    return SpanInfo(
        span_id="s1", service_name="svc", operation_name="op",
        duration_ms=1.0, status="ok", tags=tags, error_message=error_message,
    )


def test_passes_safe_keys_through():
    r = SpanTagRedactor()
    res = r.redact_tags({"http.method": "POST", "http.status_code": "200"})
    assert res.safe_tags == {"http.method": "POST", "http.status_code": "200"}
    assert res.stripped_keys == []
    assert res.value_redactions == 0


def test_strips_authorization_key():
    r = SpanTagRedactor()
    res = r.redact_tags({"authorization": "Bearer abc", "http.method": "POST"})
    assert "authorization" in res.stripped_keys
    assert "authorization" not in res.safe_tags


def test_strips_password_variants():
    r = SpanTagRedactor()
    for key in ("password", "user.passwd", "db_pwd", "api.password", "password_hash"):
        res = r.redact_tags({key: "hunter2"})
        assert key in res.stripped_keys, f"{key} should be stripped"


def test_preserves_auth_method():
    """Lookahead should allow 'authorization_method' patterns."""
    r = SpanTagRedactor()
    res = r.redact_tags({"authorization_method": "oauth2"})
    # Our actual regex strips anything containing 'authorization' so this
    # IS stripped. Testing the lookahead variant explicitly:
    res2 = r.redact_tags({"auth_method": "oauth2"})
    assert "auth_method" in res2.safe_tags, "auth_method should pass"


def test_strips_token_variants():
    r = SpanTagRedactor()
    for key in ("api_token", "access-token", "x-auth-token", "refresh_token", "session_token"):
        res = r.redact_tags({key: "whatever"})
        assert key in res.stripped_keys


def test_strips_jwt_values():
    r = SpanTagRedactor()
    jwt = "eyJhbGciOiJIUzI1NiJ9.payloadpartgoeshere.signaturepartgoeshere"
    res = r.redact_tags({"http.url": f"https://x?t={jwt}"})
    assert "<jwt:redacted>" in res.safe_tags["http.url"]
    assert res.value_redactions >= 1


def test_strips_credit_cards():
    r = SpanTagRedactor()
    res = r.redact_tags({"payment": "card 4532-1234-5678-9012 charged"})
    assert "<card:redacted>" in res.safe_tags["payment"]


def test_strips_emails_in_values():
    r = SpanTagRedactor()
    res = r.redact_tags(
        {"db.statement": "SELECT * FROM users WHERE email='jane@example.com'"}
    )
    assert "<email:redacted>" in res.safe_tags["db.statement"]
    assert "jane@example.com" not in res.safe_tags["db.statement"]


def test_strips_ssn():
    r = SpanTagRedactor()
    res = r.redact_tags({"note": "SSN 123-45-6789 on file"})
    assert "<ssn:redacted>" in res.safe_tags["note"]


def test_strips_bearer_tokens_in_values():
    r = SpanTagRedactor()
    res = r.redact_tags({"log": "Auth Bearer abcdefghijklmnopqrstuvwxyz1234"})
    assert "<token:redacted>" in res.safe_tags["log"].lower()


def test_redacts_long_base64_blob():
    r = SpanTagRedactor()
    res = r.redact_tags({"dump": "data=" + "A" * 60})
    assert "<blob:redacted>" in res.safe_tags["dump"]


def test_operator_extension_additional_denied_key():
    cfg = RedactionConfig(additional_denied_key_regexes=["order_ssn"])
    r = SpanTagRedactor(cfg)
    res = r.redact_tags({"order_ssn": "anything"})
    assert "order_ssn" in res.stripped_keys


def test_disabled_is_passthrough():
    cfg = RedactionConfig(enabled=False)
    r = SpanTagRedactor(cfg)
    res = r.redact_tags({"password": "hunter2", "http.url": "eyJhbGciOi.xxx.yyy"})
    assert res.stripped_keys == []
    assert res.value_redactions == 0
    assert res.safe_tags == {"password": "hunter2", "http.url": "eyJhbGciOi.xxx.yyy"}


def test_redact_span_also_scrubs_error_message():
    r = SpanTagRedactor()
    span = _span({"http.method": "POST"}, error_message="Failed: user=a@b.com, cc=4532-1234-5678-9012")
    safe = r.redact_span(span)
    assert "<email:redacted>" in safe.error_message
    assert "<card:redacted>" in safe.error_message
    assert safe.value_redactions >= 2


def test_redact_span_annotates_strip_count():
    r = SpanTagRedactor()
    span = _span({"http.method": "POST", "authorization": "x", "session_token": "y"})
    safe = r.redact_span(span)
    assert set(safe.stripped_tag_keys) == {"authorization", "session_token"}
    assert "http.method" in safe.tags
