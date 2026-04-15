"""JSON-Schema validator wrapper — returns a structured issue list instead
of raising on the first error, so callers (catalog UI, workflow builder input
form, future executor) can surface all problems at once.

Phase 1 Task 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str


def _format_path(absolute_path) -> str:
    out = "$"
    for p in absolute_path:
        out += f".{p}" if isinstance(p, str) else f"[{p}]"
    return out


def validate_against(payload: Any, schema: dict[str, Any]) -> list[ValidationIssue]:
    validator = Draft202012Validator(schema)
    issues: list[ValidationIssue] = []
    for err in validator.iter_errors(payload):
        issues.append(
            ValidationIssue(path=_format_path(err.absolute_path), message=err.message)
        )
    return issues
