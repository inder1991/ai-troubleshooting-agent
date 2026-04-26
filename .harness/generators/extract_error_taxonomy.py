#!/usr/bin/env python3
"""Generator — backend error taxonomy.

AST-walks backend/src/errors/**/*.py (or backend/src/exceptions/**/*.py)
and emits, per public exception class: name, parent class names,
docstring (truncated to 200 chars). Also lists `Result*` type aliases.

Output: .harness/generated/error_taxonomy.json
Schema: .harness/schemas/generated/error_taxonomy.schema.json

H-25:
  Missing input    — exit 0 with empty arrays.
  Malformed input  — skip silently.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/generators"))

from _common import iter_python_files, write_generated  # noqa: E402

EXCEPTION_BASES = {"Exception", "BaseException", "RuntimeError", "ValueError", "TypeError"}


def _is_exception_class(cls: ast.ClassDef) -> bool:
    """True if any base name ends in 'Error' / 'Exception' or is a known exception type."""
    for b in cls.bases:
        name = b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else "")
        if not name:
            continue
        if name.endswith("Error") or name.endswith("Exception") or name in EXCEPTION_BASES:
            return True
    return False


def _scan(root: Path) -> dict:
    """Walk backend/src/errors and backend/src/exceptions."""
    out_classes: list[dict] = []
    out_results: list[dict] = []
    for sub in ("errors", "exceptions"):
        base = root / "backend" / "src" / sub
        if not base.exists():
            continue
        for path in iter_python_files(base, exclude=("__pycache__",)):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_") and _is_exception_class(node):
                    parents = [
                        b.id if isinstance(b, ast.Name) else (b.attr if isinstance(b, ast.Attribute) else "?")
                        for b in node.bases
                    ]
                    doc = ast.get_docstring(node, clean=False) or ""
                    out_classes.append({
                        "name": node.name,
                        "parents": parents,
                        "doc": doc.strip()[:200],
                        "file": str(path.relative_to(root)),
                    })
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                    if name.startswith("Result") or name.endswith("Result"):
                        out_results.append({
                            "name": name,
                            "value": ast.unparse(node.value)[:200],
                            "file": str(path.relative_to(root)),
                        })
    out_classes.sort(key=lambda e: (e["file"], e["name"]))
    out_results.sort(key=lambda e: (e["file"], e["name"]))
    return {"exception_classes": out_classes, "result_aliases": out_results}


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = _scan(args.root)
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("error_taxonomy", payload)
    print(f"[INFO] wrote error_taxonomy ({len(payload['exception_classes'])} classes) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
