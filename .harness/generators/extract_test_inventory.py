#!/usr/bin/env python3
"""Generator — backend test inventory.

Walks backend/tests/**/*.py and counts per file: total `def test_*`
functions and Hypothesis tests (functions with @given decorator).

Output: .harness/generated/test_inventory.json
Schema: .harness/schemas/generated/test_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty list (backend/tests may be absent).
  Malformed input  — skip unparseable file silently.
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


def _is_given(dec: ast.AST) -> bool:
    if isinstance(dec, ast.Name) and dec.id == "given":
        return True
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "given":
        return True
    return False


def _scan(root: Path) -> list[dict]:
    """Walk backend/tests under root."""
    tests_root = root / "backend" / "tests"
    if not tests_root.exists():
        return []
    out: list[dict] = []
    for path in iter_python_files(tests_root, exclude=("__pycache__",)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        test_count = 0
        hypo_count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_count += 1
                    if any(_is_given(d) for d in node.decorator_list):
                        hypo_count += 1
        if test_count == 0:
            continue
        out.append({
            "path": str(path.relative_to(root)),
            "test_count": test_count,
            "hypothesis_count": hypo_count,
        })
    out.sort(key=lambda e: e["path"])
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"files": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("test_inventory", payload)
    print(f"[INFO] wrote {len(payload['files'])} test files → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
