"""Credential redactor — strips secrets from strings + dicts before logging.

Problem this exists to solve (PR-A / Bug #4 from SDET audit):

The Anthropic SDK's exception types — APIStatusError, APIError, etc. —
sometimes carry the full request envelope in their ``.body`` attribute
or in stringified form. When we call ``logger.error(..., extra={"extra": str(e)})``
from the LLM client, that string can contain the raw Authorization
header with the live API key. If logs are shipped to a third-party
sink (Datadog, Grafana Cloud, or a customer-visible log dashboard),
the secret leaks.

This module provides a single ``redact_for_logging`` entry point that
every ``logger.exception``/``logger.error`` site near LLM calls should
run its ``str(e)`` through before handing it to the log line. The
redactor is conservative — it prefers to over-redact (replace more
tokens) than under-redact (miss a secret).

Patterns redacted:

  * ``sk-ant-*`` — Anthropic API keys (canonical form)
  * ``sk-*`` — OpenAI / generic SK-style keys (match the common prefix
    but leave legitimate text like "sk-based" alone via the dash +
    alphanumeric-run rule)
  * ``Bearer <token>`` — HTTP Authorization header values
  * ``authorization: <value>`` — header literals (case-insensitive)
  * ``x-api-key: <value>`` — Anthropic header form (case-insensitive)
  * ``api_key=<value>`` / ``api-key=<value>`` — query-string / form form
  * ``password=<value>`` / ``secret=<value>`` / ``token=<value>`` — generic

Unit tested at ``tests/utils/test_credential_redactor.py``.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

__all__ = ["redact_for_logging", "redact_string"]

# Each pattern is (compiled_regex, replacement). Order matters — the
# Anthropic-specific prefixes run first so we don't accidentally catch
# their prefix inside the generic "sk-*" rule.
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # Anthropic API keys — canonical form is sk-ant-... with ~100+
    # base64-ish characters. We match aggressively; anything that
    # starts with "sk-ant-" followed by >=10 word chars or dashes.
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "sk-ant-<redacted>"),
    # OpenAI / generic sk-* keys. Restrict to >=20 characters after
    # "sk-" to avoid catching legitimate words like "sk-based-model".
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "sk-<redacted>"),
    # HTTP Bearer token
    (re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]+", re.IGNORECASE),
     "Bearer <redacted>"),
    # Header-line form: Authorization: <anything>\n   (case-insensitive)
    (re.compile(r"(?i)\bauthorization\s*[:=]\s*[^\s\n,'\"]+"),
     "authorization: <redacted>"),
    # x-api-key header form
    (re.compile(r"(?i)\bx-api-key\s*[:=]\s*[^\s\n,'\"]+"),
     "x-api-key: <redacted>"),
    # api_key / api-key assignment (URL, form, JSON).
    # Matches both `api_key=value` and `"api_key": "value"` (JSON) —
    # the optional closing quote before `:` is the key bit.
    (re.compile(r"(?i)\bapi[-_]?key['\"]?\s*[:=]\s*['\"]?[^\s'\"&,\}\n]+['\"]?"),
     "api_key=<redacted>"),
    # Generic password / secret / token assignment (same tolerance).
    (re.compile(
        r"(?i)\b(password|secret|token)['\"]?\s*[:=]\s*['\"]?[^\s'\"&,\}\n]+['\"]?"),
     r"\1=<redacted>"),
]


def redact_string(text: str) -> str:
    """Apply every redaction pattern to a string. Safe on non-str inputs."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def redact_for_logging(value: Any) -> Any:
    """Redact a value for safe logging.

    * str → redacted str
    * dict → recursively redacted dict (keys preserved; suspicious keys'
      values are blanket-replaced regardless of content)
    * list/tuple → recursively redacted
    * Exception → ``redact_string(str(exc))``
    * everything else → str(value) with redactions applied

    Blanket-replacement for suspicious keys catches credentials that
    wouldn't match any pattern (e.g. a weird-format proprietary key).
    """
    if value is None:
        return None
    if isinstance(value, BaseException):
        return redact_string(str(value))
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_sensitive_key(k):
                out[k] = "<redacted>"
            else:
                out[k] = redact_for_logging(v)
        return out
    if isinstance(value, (list, tuple)):
        redacted = [redact_for_logging(v) for v in value]
        return redacted if isinstance(value, list) else tuple(redacted)
    # Non-string primitives (int / float / bool) pass through unchanged —
    # they can't carry a credential and coercing them to strings loses
    # information (e.g. 400 vs "400").
    if isinstance(value, (int, float, bool)):
        return value
    # Fallback for anything else — coerce to string and redact.
    return redact_string(str(value))


_SENSITIVE_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)^(authorization|x-api-key)$"),
    re.compile(r"(?i)api[-_]?key"),
    re.compile(r"(?i)(password|secret|token)"),
    re.compile(r"(?i)bearer"),
)


def _is_sensitive_key(key: str) -> bool:
    return any(p.search(key) for p in _SENSITIVE_KEY_PATTERNS)
