"""Shared helpers for .harness/generators/ scripts.

Every generator writes a deterministic `.harness/generated/<name>.json`
file via `write_generated(name, payload)`. Output is sorted-keys +
2-space indent + trailing newline so re-running the generator with
no source changes produces a byte-identical file (verified by
`make harness` followed by `git diff --stat .harness/generated/`).

Helpers also include source-walk iterators (`iter_python_files`,
`iter_tsx_files`) so each generator can stay short.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = REPO_ROOT / ".harness" / "generated"


def write_generated(name: str, payload: Any) -> Path:
    """Write `payload` (JSON-serializable) to .harness/generated/<name>.json
    with sort_keys=True, indent=2, trailing newline. Idempotent + deterministic.

    H-4: generated files are auto-derived; they are NEVER hand-edited.
    Returns the path written.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GENERATED_DIR / f"{name}.json"
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return out_path


def iter_python_files(root: Path, exclude: tuple[str, ...] = ()) -> Iterable[Path]:
    """Yield .py files under root, sorted, deterministic, skipping any path
    whose string repr contains any token in `exclude`."""
    for path in sorted(root.rglob("*.py")):
        virtual = str(path)
        if any(token in virtual for token in exclude):
            continue
        yield path


def iter_tsx_files(root: Path, exclude: tuple[str, ...] = ()) -> Iterable[Path]:
    """Yield .ts/.tsx/.js/.jsx files under root, sorted, deterministic."""
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        for path in sorted(root.rglob(f"*{ext}")):
            virtual = str(path)
            if any(token in virtual for token in exclude):
                continue
            yield path
