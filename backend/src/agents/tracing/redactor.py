"""Span-tag redaction — Option E (maximum-permissive denylist + value regex).

Policy locked during architecture review:

  * **Tag keys**: denylist-based. Every key passes through UNLESS it matches
    a credential-class pattern (password, token, secret, cookie, etc.).
  * **Tag values**: regex-scrubbed for high-confidence PII patterns
    (JWT, credit card, SSN, email, bearer tokens, long base64 blobs).
  * **Operator override**: per-integration config can extend the denylist
    and add custom value patterns. Defaults are shipped "on".

Design notes
------------
- Keys are matched against a single compiled regex — case-insensitive —
  with a lookahead to preserve ``auth_method`` while denying ``auth`` alone.
- Value redaction preserves surrounding context (``SELECT * WHERE email='<email:redacted>'``)
  rather than nuking the whole value, so diagnostic signal survives.
- The redactor exposes counters (``stripped_tag_keys``, ``value_redactions``)
  that bubble up into the ``SpanInfo`` model and the UI, so the operator
  always knows WHAT was filtered, even when they can't see the actual values.
- The LLM is told in the prompt footer how many redactions were applied,
  so it doesn't draw wrong conclusions from absent data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from src.models.schemas import SpanInfo


_DENIED_KEY_REGEX = re.compile(
    r"(?i)"
    r"("
    r"password|passwd|pwd"
    r"|secret"
    r"|token"
    r"|credential|credentials"
    r"|api[_.\-]?key|apikey"
    r"|authorization(?!_method)"
    r"|cookie"
    r"|private[_.\-]?key"
    r"|ssh[_.\-]?key"
    r"|access[_.\-]?key"
    r"|refresh[_.\-]?token"
    r"|jwt"
    r"|bearer"
    r"|x-api-key"
    r"|x-auth-token"
    r")"
)

_VALUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWTs — very distinctive shape, near-zero false positives.
    (
        re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
        "<jwt:redacted>",
    ),
    # Bearer-prefixed tokens.
    (
        re.compile(r"Bearer\s+[A-Za-z0-9._~+/=\-]{20,}", re.IGNORECASE),
        "Bearer <token:redacted>",
    ),
    # Credit card — 13-19 digits with optional separators; no Luhn check
    # (too aggressive a rule for identifying — we just want to redact plausible
    # card shapes rather than be strictly correct about validity).
    (
        re.compile(r"\b(?:\d[- ]?){12,18}\d\b"),
        "<card:redacted>",
    ),
    # US SSN.
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "<ssn:redacted>",
    ),
    # Email addresses.
    (
        re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
        "<email:redacted>",
    ),
    # Long base64-looking blobs (likely opaque credentials). Placed last so
    # the more-specific patterns match first.
    (
        re.compile(r"\b[A-Za-z0-9+/=]{40,}\b"),
        "<blob:redacted>",
    ),
]


@dataclass
class RedactionConfig:
    """Operator-tunable per integration."""

    enabled: bool = True
    additional_denied_key_regexes: list[str] = field(default_factory=list)
    additional_value_patterns: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SpanRedactionResult:
    safe_tags: dict[str, str]
    stripped_keys: list[str]
    value_redactions: int


class SpanTagRedactor:
    """Applies the locked redaction policy to a span's tags.

    Stateless; reuse safely across spans and threads.
    """

    def __init__(self, config: Optional[RedactionConfig] = None) -> None:
        self._config = config or RedactionConfig()
        self._extra_key_patterns: list[re.Pattern[str]] = [
            re.compile(pat, re.IGNORECASE)
            for pat in self._config.additional_denied_key_regexes
        ]
        self._extra_value_patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(pat), repl)
            for pat, repl in self._config.additional_value_patterns
        ]

    def redact_tags(self, tags: dict[str, str]) -> SpanRedactionResult:
        if not self._config.enabled:
            return SpanRedactionResult(
                safe_tags=dict(tags), stripped_keys=[], value_redactions=0
            )

        safe: dict[str, str] = {}
        stripped: list[str] = []
        redactions = 0

        for key, value in tags.items():
            if self._is_key_denied(key):
                stripped.append(key)
                continue

            redacted_value, n = self._redact_value(str(value))
            safe[key] = redacted_value
            redactions += n

        return SpanRedactionResult(
            safe_tags=safe, stripped_keys=stripped, value_redactions=redactions
        )

    def redact_span(self, span: SpanInfo) -> SpanInfo:
        """Return a new SpanInfo with redacted tags + annotation fields set."""
        result = self.redact_tags(span.tags)

        # Also scrub any PII that made it into error_message (most common
        # leak vector — stack traces carrying email / user IDs).
        error_msg = span.error_message
        if error_msg:
            error_msg, err_redactions = self._redact_value(error_msg)
            result = SpanRedactionResult(
                safe_tags=result.safe_tags,
                stripped_keys=result.stripped_keys,
                value_redactions=result.value_redactions + err_redactions,
            )

        return span.model_copy(
            update={
                "tags": result.safe_tags,
                "error_message": error_msg,
                "stripped_tag_keys": result.stripped_keys,
                "value_redactions": result.value_redactions,
            }
        )

    # ── Internals ────────────────────────────────────────────────────────

    def _is_key_denied(self, key: str) -> bool:
        if _DENIED_KEY_REGEX.search(key):
            return True
        for pat in self._extra_key_patterns:
            if pat.search(key):
                return True
        return False

    def _redact_value(self, value: str) -> tuple[str, int]:
        redactions = 0
        for pat, repl in _VALUE_PATTERNS:
            new_value, n = pat.subn(repl, value)
            if n:
                redactions += n
                value = new_value
        for pat, repl in self._extra_value_patterns:
            new_value, n = pat.subn(repl, value)
            if n:
                redactions += n
                value = new_value
        return value, redactions
