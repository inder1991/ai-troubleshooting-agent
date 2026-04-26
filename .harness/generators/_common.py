"""Shared helpers for .harness/generators/ scripts.

Every generator writes to .harness/generated/<name>.json with a
versioned schema header and sorted keys for byte-deterministic output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_generated(target: Path, schema_version: int, payload: dict[str, Any]) -> None:
    """Write `payload` to `target` with a versioned schema envelope.

    Output is sorted-keys + 2-space indent + trailing newline so
    re-running the generator with no source changes is byte-identical.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {"$schema_version": schema_version, **payload}
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    )
