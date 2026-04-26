"""Q16 gamma + Q13 — secret redaction in log output.

Pattern catalogue mirrors .harness/security_policy.yaml's transport
log_redaction patterns. Single source of truth lives in security_policy.yaml;
this module is the runtime applier for backend logs."""

from __future__ import annotations

import re
from typing import Pattern

# Q13 — pattern set. Keep in sync with security_policy.yaml.
_PATTERNS: list[tuple[str, Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    (
        "generic_secret",
        re.compile(
            r"(?i)(api[_-]?key|secret|password|token)[\"']?\s*[:=]\s*[\"']([^\"']{8,})[\"']",
        ),
    ),
]


def redact_secrets(text: str) -> str:
    """Replace any matched secret with [REDACTED]. Idempotent."""
    if not isinstance(text, str):
        return text
    for _name, pattern in _PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text
