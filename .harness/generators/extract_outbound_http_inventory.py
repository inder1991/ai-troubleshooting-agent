#!/usr/bin/env python3
"""Generator — outbound HTTP callsite inventory.

Walks backend/src/**/*.py, finds httpx.AsyncClient(...).get|post|put|patch|
delete|request(...) calls, records {file, line, url_arg, retry_decorated,
timeout_explicit}. retry_decorated is true when the enclosing function
has a @with_retry decorator.

Output: .harness/generated/outbound_http_inventory.json
Schema: .harness/schemas/generated/outbound_http_inventory.schema.json

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

HTTP_VERBS = {"get", "post", "put", "patch", "delete", "request"}


def _is_httpx_call(node: ast.AST) -> bool:
    """True if node is a Call to .get/.post/etc on something that mentions httpx."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in HTTP_VERBS:
        return False
    return True


def _has_with_retry(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        if isinstance(d, ast.Name) and d.id == "with_retry":
            return True
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "with_retry":
            return True
        if isinstance(d, ast.Attribute) and d.attr == "with_retry":
            return True
    return False


def _has_timeout_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "timeout" for kw in call.keywords)


def _url_arg(call: ast.Call) -> str:
    if not call.args:
        return ""
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    try:
        return ast.unparse(arg)[:200]
    except Exception:  # noqa: BLE001 — best-effort serialization
        return "?"


def _scan(root: Path) -> list[dict]:
    """Walk backend/src/**/*.py, find httpx-style calls."""
    spine = root / "backend" / "src"
    if not spine.exists():
        return []
    out: list[dict] = []
    for path in iter_python_files(spine, exclude=("__pycache__", "/venv/", ".venv", "tests")):
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        if "httpx" not in text:
            continue
        # Walk functions; for each call inside, check decorators.
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            retry = _has_with_retry(fn)
            for node in ast.walk(fn):
                if not _is_httpx_call(node):
                    continue
                out.append({
                    "file": str(path.relative_to(root)),
                    "line": node.lineno,
                    "url": _url_arg(node),
                    "verb": node.func.attr.upper() if isinstance(node.func, ast.Attribute) else "",
                    "retry_decorated": retry,
                    "timeout_explicit": _has_timeout_kwarg(node),
                })
    out.sort(key=lambda e: (e["file"], e["line"]))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"callsites": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("outbound_http_inventory", payload)
    print(f"[INFO] wrote outbound_http_inventory ({len(payload['callsites'])} callsites) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
