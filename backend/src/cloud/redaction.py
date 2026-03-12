"""Sensitive data redaction and JSON compression utilities."""
from __future__ import annotations

import gzip
import json
from typing import Any

_REDACT_KEYS = frozenset({
    "Password", "Secret", "PrivateKey", "AccessKey", "SecretKey",
    "Token", "Credential", "AuthToken", "ConnectionString",
})

_REDACTED = "***REDACTED***"


def redact_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Deep-redact sensitive fields. Returns new dict."""
    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: _REDACTED if any(s in k for s in _REDACT_KEYS) else _walk(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj
    return _walk(raw)


def compress_raw(raw: dict[str, Any]) -> bytes:
    """Gzip-compress raw JSON dict to bytes for BLOB storage."""
    return gzip.compress(
        json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
    )


def decompress_raw(blob: bytes) -> dict[str, Any]:
    """Decompress gzip BLOB back to dict."""
    return json.loads(gzip.decompress(blob).decode("utf-8"))


def make_raw_preview(raw: dict[str, Any], max_len: int = 512) -> str:
    """First N chars of JSON for quick display."""
    text = json.dumps(raw, sort_keys=True, default=str)
    return text[:max_len]
