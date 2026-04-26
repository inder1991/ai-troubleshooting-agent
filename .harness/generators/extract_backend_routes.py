#!/usr/bin/env python3
"""Generator — backend FastAPI routes inventory.

Walks backend/src/api/**/*.py, parses each `@router.<verb>("path")`
decorator on functions/async functions, extracts handler name, body type
annotation (named `payload` or `body`), return annotation, and the
auth/rate-limit/csrf dependencies (Depends(...) / @limiter.limit /
CsrfProtect annotation).

Output: .harness/generated/backend_routes.json
Schema: .harness/schemas/generated/backend_routes.schema.json

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


def _route_info(dec: ast.AST) -> tuple[str, str] | None:
    """Return (method, path) if dec is `@<router|app>.<verb>(\"...\")`, else None."""
    if not isinstance(dec, ast.Call):
        return None
    if not (isinstance(dec.func, ast.Attribute) and isinstance(dec.func.value, ast.Name)):
        return None
    if dec.func.value.id not in {"router", "app"}:
        return None
    verb = dec.func.attr.upper()
    if verb not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return None
    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
        return verb, dec.args[0].value
    return None


def _depends_callee(default: ast.AST | None) -> str | None:
    if (
        isinstance(default, ast.Call)
        and isinstance(default.func, ast.Name)
        and default.func.id == "Depends"
        and default.args
        and isinstance(default.args[0], ast.Name)
    ):
        return default.args[0].id
    return None


def _has_rate_limit(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "limiter"
        and d.func.attr == "limit"
        for d in fn.decorator_list
    )


def _ann_str(ann: ast.AST | None) -> str | None:
    return None if ann is None else ast.unparse(ann)


def _scan(root: Path) -> list[dict]:
    """Walk backend/src/api or backend/api under root; return route entries."""
    candidates = [root / "backend" / "src" / "api", root / "backend" / "api"]
    api_root = next((c for c in candidates if c.exists()), None)
    if api_root is None:
        return []
    out: list[dict] = []
    for path in iter_python_files(api_root, exclude=("__pycache__",)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                info = _route_info(dec)
                if info is None:
                    continue
                method, route_path = info
                auth_dep = None
                request_type = None
                csrf_dep = False
                pos_args = node.args.args
                defaults = [None] * (len(pos_args) - len(node.args.defaults)) + list(node.args.defaults)
                for arg, default in zip(pos_args, defaults):
                    callee = _depends_callee(default)
                    if callee:
                        auth_dep = callee
                    elif arg.annotation is not None and arg.arg in {"payload", "body"}:
                        request_type = _ann_str(arg.annotation)
                for arg in pos_args + node.args.kwonlyargs:
                    if arg.annotation is not None and "CsrfProtect" in (_ann_str(arg.annotation) or ""):
                        csrf_dep = True
                out.append({
                    "method": method,
                    "path": route_path,
                    "handler": node.name,
                    "module": str(path.relative_to(root)),
                    "auth_dep": auth_dep,
                    "rate_limit": _has_rate_limit(node),
                    "csrf_dep": csrf_dep,
                    "request_type": request_type,
                    "response_type": _ann_str(node.returns),
                })
    out.sort(key=lambda e: (e["module"], e["path"], e["method"]))
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args(argv)
    payload = {"routes": _scan(args.root)}
    if args.print:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    out_path = write_generated("backend_routes", payload)
    print(f"[INFO] wrote {len(payload['routes'])} routes → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
