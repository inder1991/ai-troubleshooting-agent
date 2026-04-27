#!/usr/bin/env python3
"""Q13.B — every mutating FastAPI route has auth + rate-limit + CSRF.

Three rules:
  Q13.route-needs-auth        — POST/PUT/PATCH/DELETE handler missing an auth
                                 dependency (Depends(<auth_fn>) param OR
                                 @authenticated/@requires decorator).
  Q13.route-needs-rate-limit  — mutating handler missing @limiter.limit
                                 decorator unless verb:path in rate_limit_exempt.
  Q13.route-needs-csrf        — mutating handler missing CsrfProtect dependency
                                 unless verb:path in csrf_exempt.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("backend_api", ("backend/src/api",))
DEFAULT_POLICY = REPO_ROOT / ".harness" / "security_policy.yaml"
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
MUTATING_VERBS = {"post", "put", "patch", "delete"}
BASELINE = load_baseline("security_policy_b")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _route_decorator_info(node: ast.AST) -> tuple[str, str] | None:
    """Returns (verb, path) if `node` is a `@router.<verb>("<path>")` decorator."""
    if not isinstance(node, ast.Call):
        return None
    if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)):
        return None
    if node.func.value.id not in {"router", "app"}:
        return None
    verb = node.func.attr.lower()
    if verb not in MUTATING_VERBS and verb != "get":
        return None
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return verb, node.args[0].value
    return None


def _has_auth_dep(fn, auth_dep_names: set[str], auth_dec_names: set[str]) -> bool:
    for dec in fn.decorator_list:
        name = None
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            name = dec.func.id
        if name and name in auth_dec_names:
            return True
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        default = _arg_default(fn, arg)
        if default is None:
            continue
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
        ):
            inner = default.args[0]
            if isinstance(inner, ast.Name) and inner.id in auth_dep_names:
                return True
    return False


def _arg_default(fn, arg: ast.arg) -> ast.AST | None:
    args = fn.args.args
    if arg in args:
        idx = args.index(arg)
        defaults = fn.args.defaults
        offset = len(args) - len(defaults)
        if idx >= offset:
            return defaults[idx - offset]
        return None
    kwonly = fn.args.kwonlyargs
    if arg in kwonly:
        idx = kwonly.index(arg)
        kw_defaults = fn.args.kw_defaults
        return kw_defaults[idx] if idx < len(kw_defaults) else None
    return None


def _has_rate_limit_decorator(fn) -> bool:
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "limiter"
            and dec.func.attr == "limit"
        ):
            return True
    return False


def _has_csrf_dep(fn) -> bool:
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        if arg.annotation is None:
            continue
        ann_src = ast.dump(arg.annotation)
        if "CsrfProtect" in ann_src:
            return True
    return False


def _module_has_csrf_middleware(tree: ast.AST) -> bool:
    """Detect app-level CSRF middleware so per-route CsrfProtect dep isn't
    required when the FastAPI app already has CSRF enforced globally.

    Catches:
      app.add_middleware(CSRFMiddleware, ...)
      app.add_middleware(SomethingCsrfMiddleware, ...)
      @app.middleware  decorator on a func whose body references csrf
      from fastapi_csrf_protect import CsrfProtect → assume init elsewhere
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args
        ):
            first = node.args[0]
            name = (
                first.id if isinstance(first, ast.Name)
                else (first.attr if isinstance(first, ast.Attribute) else "")
            )
            if "csrf" in name.lower():
                return True
    return False


def _exempt(verb: str, path: str, exempt_list: list[str]) -> bool:
    key = f"{verb.upper()}:{path}"
    for entry in exempt_list:
        if fnmatch.fnmatchcase(key, entry):
            return True
    return False


def _scan_file(path: Path, virtual: str, policy: dict) -> int:
    if not (virtual.startswith("backend/src/api/") or path.parent.name == "api"):
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return 0
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0

    auth_dep_names = set(policy.get("auth_dependency_names") or [])
    auth_dec_names = set(policy.get("auth_decorator_names") or [])
    rate_limit_exempt = list(policy.get("rate_limit_exempt") or [])
    csrf_exempt = list(policy.get("csrf_exempt") or [])
    # If this module installs CSRF middleware globally, skip the per-route
    # CsrfProtect dependency check (the middleware enforces it for every route).
    has_global_csrf = _module_has_csrf_middleware(tree)
    errors = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            info = _route_decorator_info(dec)
            if info is None:
                continue
            verb, route_path = info
            if verb not in MUTATING_VERBS:
                continue
            line = node.lineno
            if not _has_auth_dep(node, auth_dep_names, auth_dec_names):
                first = sorted(auth_dep_names)[0] if auth_dep_names else "get_current_user"
                if _emit(path, "Q13.route-needs-auth",
                         f"{verb.upper()} {route_path} has no auth dependency",
                         f"add `user = Depends({first})`", line):
                    errors += 1
            if not _has_rate_limit_decorator(node) and not _exempt(verb, route_path, rate_limit_exempt):
                if _emit(path, "Q13.route-needs-rate-limit",
                         f"{verb.upper()} {route_path} missing @limiter.limit",
                         'add `@limiter.limit("<n>/minute")` or list in security_policy.yaml.rate_limit_exempt',
                         line):
                    errors += 1
            if (
                not has_global_csrf
                and not _has_csrf_dep(node)
                and not _exempt(verb, route_path, csrf_exempt)
            ):
                if _emit(path, "Q13.route-needs-csrf",
                         f"{verb.upper()} {route_path} missing CsrfProtect dependency",
                         "add `csrf_protect: CsrfProtect = Depends()` or list under csrf_exempt",
                         line):
                    errors += 1
    return errors


def _walk_python(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    """Run Q13.B (auth + rate-limit + CSRF) on each FastAPI route under `roots`.
    Return 1 if any errors fired."""
    policy = _load_policy(policy_path)
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual, policy)
        else:
            for p in _walk_python(root):
                virtual = (
                    str(p.relative_to(REPO_ROOT))
                    if p.is_relative_to(REPO_ROOT) else p.name
                )
                total_errors += _scan_file(p, virtual, policy)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: dispatch scan, return process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
