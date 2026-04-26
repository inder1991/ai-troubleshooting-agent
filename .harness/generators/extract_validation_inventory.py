#!/usr/bin/env python3
"""Generator — Pydantic boundary model inventory.

Walks backend/src/models/{api,agent}/**/*.py, parses each pydantic class,
records: kind (api/agent), class name, model_config kwargs (extra,
frozen), each field name + type annotation + Field() ge/le/min_length/
max_length kwargs.

Output: .harness/generated/validation_inventory.json
Schema: .harness/schemas/generated/validation_inventory.schema.json

H-25:
  Missing input    — exit 0 with empty list.
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

CONFIG_KEYS = {"extra", "frozen", "strict", "validate_assignment"}
FIELD_BOUND_KEYS = {"ge", "le", "gt", "lt", "min_length", "max_length"}


def _config_kwargs(cls: ast.ClassDef) -> dict:
    out: dict = {}
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
            and isinstance(stmt.value, ast.Call)
        ):
            for kw in stmt.value.keywords:
                if kw.arg in CONFIG_KEYS and isinstance(kw.value, ast.Constant):
                    out[kw.arg] = kw.value.value
    return out


def _field_meta(stmt: ast.AnnAssign) -> dict:
    name = stmt.target.id if isinstance(stmt.target, ast.Name) else "?"
    type_str = ast.unparse(stmt.annotation) if stmt.annotation is not None else "?"
    field_meta: dict = {"name": name, "type": type_str}
    if (
        isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == "Field"
    ):
        for kw in stmt.value.keywords:
            if kw.arg in FIELD_BOUND_KEYS and isinstance(kw.value, ast.Constant):
                field_meta[kw.arg] = kw.value.value
    return field_meta


def _scan(root: Path) -> list[dict]:
    """Walk backend/src/models/{api,agent} and backend/models/{api,agent}."""
    out: list[dict] = []
    for sub in ("api", "agent"):
        for base in (
            root / "backend" / "src" / "models" / sub,
            root / "backend" / "models" / sub,
        ):
            if not base.exists():
                continue
            for path in iter_python_files(base, exclude=("__pycache__",)):
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                except (OSError, UnicodeDecodeError, SyntaxError):
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ClassDef):
                        continue
                    fields = [
                        _field_meta(s) for s in node.body
                        if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
                    ]
                    out.append({
                        "kind": sub,
                        "class": node.name,
                        "config": _config_kwargs(node),
                        "fields": fields,
                        "file": str(path.relative_to(root)),
                    })
    out.sort(key=lambda e: (e["file"], e["class"]))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"models": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("validation_inventory", payload)
    print(f"[INFO] wrote {len(payload['models'])} models → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
