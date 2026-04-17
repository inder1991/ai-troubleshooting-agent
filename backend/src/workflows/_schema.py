"""Shared schema-version check for persisted workflow dataclasses."""
from __future__ import annotations

from typing import Any


def _check_schema_version(d: dict[str, Any], expected: int, cls_name: str) -> None:
    # Default to ``expected`` for unversioned dicts so existing v1 payloads
    # written before this field existed still load. Phase-0 grace window only.
    version = d.get("schema_version", expected)
    if version != expected:
        raise ValueError(
            f"unsupported schema_version for {cls_name}: got {version!r}, expected {expected}"
        )
