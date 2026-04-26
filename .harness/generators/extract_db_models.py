#!/usr/bin/env python3
"""Generator — backend SQLModel db models inventory.

AST-walks backend/src/models/db/*.py, identifies `class X(SQLModel, table=True)`
classes, and emits per class: class_name, table_name (from __tablename__),
fields (each with name, type, primary_key, max_length when extractable),
file path.

Output: .harness/generated/db_models.json
Schema: .harness/schemas/generated/db_models.schema.json

H-25:
  Missing input    — exit 0 with empty list.
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


def _is_table_class(cls: ast.ClassDef) -> bool:
    """True if class extends SQLModel AND has table=True keyword."""
    has_sqlmodel = any(
        (isinstance(b, ast.Name) and b.id == "SQLModel")
        for b in cls.bases
    )
    has_table_true = any(
        isinstance(kw.value, ast.Constant) and kw.arg == "table" and kw.value.value is True
        for kw in cls.keywords
    )
    return has_sqlmodel and has_table_true


def _ann_str(ann: ast.AST | None) -> str:
    return "" if ann is None else ast.unparse(ann)


def _field_info(node: ast.AnnAssign) -> dict | None:
    if not isinstance(node.target, ast.Name):
        return None
    name = node.target.id
    type_str = _ann_str(node.annotation)
    pk = False
    max_length: int | None = None
    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "Field":
        for kw in node.value.keywords:
            if kw.arg == "primary_key" and isinstance(kw.value, ast.Constant):
                pk = bool(kw.value.value)
            elif kw.arg == "max_length" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, int):
                    max_length = kw.value.value
    return {"name": name, "type": type_str, "primary_key": pk, "max_length": max_length}


def _table_name(cls: ast.ClassDef) -> str:
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__tablename__"
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            return stmt.value.value
    return cls.name.lower()


def _scan(root: Path) -> list[dict]:
    """Walk backend/src/models/db (or backend/models/db) under root."""
    candidates = [root / "backend" / "src" / "models" / "db", root / "backend" / "models" / "db"]
    db_root = next((c for c in candidates if c.exists()), None)
    if db_root is None:
        return []
    out: list[dict] = []
    for path in iter_python_files(db_root, exclude=("__pycache__",)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ClassDef) and _is_table_class(node)):
                continue
            fields: list[dict] = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    info = _field_info(stmt)
                    if info is not None:
                        fields.append(info)
            out.append({
                "class_name": node.name,
                "table_name": _table_name(node),
                "fields": fields,
                "file": str(path.relative_to(root)),
            })
    out.sort(key=lambda e: (e["file"], e["class_name"]))
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
    out_path = write_generated("db_models", payload)
    print(f"[INFO] wrote {len(payload['models'])} models → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
