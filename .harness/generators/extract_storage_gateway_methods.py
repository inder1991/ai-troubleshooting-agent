#!/usr/bin/env python3
"""Generator — backend StorageGateway method inventory.

AST-walks backend/src/storage/gateway.py, finds the StorageGateway class
body, and emits per public method: name, kind (write/read), args (with
annotations), return type, audited (true if body calls self._audit),
timed (true if @timed_query decorator).

Output: .harness/generated/storage_gateway_methods.json
Schema: .harness/schemas/generated/storage_gateway_methods.schema.json

H-25:
  Missing input    — exit 0 with empty list (file may not exist).
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

from _common import write_generated  # noqa: E402

WRITE_PREFIXES = ("create_", "update_", "delete_", "upsert_", "merge_", "set_", "save_", "insert_")


def _ann_str(ann: ast.AST | None) -> str:
    return "" if ann is None else ast.unparse(ann)


def _has_timed_query(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "timed_query":
            return True
        if isinstance(d, ast.Name) and d.id == "timed_query":
            return True
    return False


def _calls_self_audit(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for sub in ast.walk(fn):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "_audit"
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "self"
        ):
            return True
    return False


def _scan(root: Path) -> list[dict]:
    """Find StorageGateway class methods under root."""
    candidates = [
        root / "backend" / "src" / "storage" / "gateway.py",
        root / "backend" / "storage" / "gateway.py",
    ]
    gw = next((c for c in candidates if c.exists()), None)
    if gw is None:
        return []
    try:
        tree = ast.parse(gw.read_text(encoding="utf-8"), filename=str(gw))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    out: list[dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "StorageGateway"):
            continue
        for member in node.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if member.name.startswith("_"):
                continue
            kind = "write" if member.name.startswith(WRITE_PREFIXES) else "read"
            args = []
            for arg in member.args.args:
                if arg.arg == "self":
                    continue
                args.append({"name": arg.arg, "type": _ann_str(arg.annotation)})
            out.append({
                "name": member.name,
                "kind": kind,
                "args": args,
                "return_type": _ann_str(member.returns),
                "audited": _calls_self_audit(member),
                "timed": _has_timed_query(member),
            })
    out.sort(key=lambda e: e["name"])
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"methods": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("storage_gateway_methods", payload)
    print(f"[INFO] wrote {len(payload['methods'])} methods → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
