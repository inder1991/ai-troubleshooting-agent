#!/usr/bin/env python3
"""Q17 — error-handling discipline (no silent swallow, preserve chain, narrow types, detail HTTP).

Four rules:
  Q17.no-pass-in-except          — `except X: pass` (or `... ; pass`) silently
                                    swallows the error. Even narrow excepts
                                    must do something (re-raise, log, return).
  Q17.reraise-without-from       — inside `except E as exc:`, raising a *new*
                                    exception without `from exc` discards the
                                    original cause chain.
  Q17.generic-exception-raised   — `raise Exception(...)` / `raise BaseException(...)`.
                                    Use a specific class so callers can catch.
  Q17.http-exception-needs-detail — `raise HTTPException(...)` (or
                                    StarletteHTTPException) without a `detail`
                                    keyword arg. Detail makes the response
                                    body actionable.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable; skip file.
  Upstream failed  — none (pure AST).
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

from _common import emit, load_baseline  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / ".harness" / "error_handling_policy.yaml"
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
    "backend/venv/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
BASELINE = load_baseline("error_handling_policy")


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (str(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _matches_any(virtual: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(virtual, g) for g in globs)


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _scan_python(path: Path, source: str, policy: dict) -> int:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    http_names = set(policy.get("http_exception_names") or [])
    generic_names = set(policy.get("generic_exception_names") or [])
    errors = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                if _emit(path, "Q17.no-pass-in-except",
                         "except handler is `pass` only — silently swallows the error",
                         "log, re-raise, or convert to a specific return value with intent",
                         node.lineno):
                    errors += 1
            if node.name:
                exc_var = node.name
                for sub in ast.walk(ast.Module(body=body, type_ignores=[])):
                    if (
                        isinstance(sub, ast.Raise)
                        and sub.exc is not None
                        and sub.cause is None
                    ):
                        if not (
                            isinstance(sub.exc, ast.Name)
                            and sub.exc.id == exc_var
                        ):
                            if _emit(path, "Q17.reraise-without-from",
                                     "raising a new exception inside `except as exc` without `from exc` discards the cause chain",
                                     f"use `raise NewError(...) from {exc_var}`",
                                     sub.lineno):
                                errors += 1

        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            call = node.exc
            name = _name_of(call.func)
            if name in generic_names:
                if _emit(path, "Q17.generic-exception-raised",
                         f"`raise {name}(...)` is too broad for callers to catch",
                         "raise a specific subclass (define one if needed)",
                         node.lineno):
                    errors += 1
            if name in http_names:
                has_detail = any(kw.arg == "detail" for kw in call.keywords)
                has_positional_detail = len(call.args) >= 2
                if not has_detail and not has_positional_detail:
                    if _emit(path, "Q17.http-exception-needs-detail",
                             f"`raise {name}(...)` missing `detail=` — response body will be empty/generic",
                             "add `detail=\"...\"` describing the failure for the client",
                             node.lineno):
                        errors += 1
    return errors


def _scan_file(path: Path, virtual: str, policy: dict) -> int:
    if _is_excluded(virtual):
        return 0
    if path.suffix != ".py":
        return 0
    spine = policy.get("spine_paths") or []
    if not _matches_any(virtual, spine):
        return 0
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return _scan_python(path, source, policy)


def _glob_to_root(glob: str) -> str:
    parts = []
    for seg in glob.split("/"):
        if any(c in seg for c in "*?["):
            break
        parts.append(seg)
    return "/".join(parts)


def _scoped_walk_roots(policy: dict) -> list[Path]:
    seen: set[str] = set()
    roots: list[Path] = []
    for glob in policy.get("spine_paths") or []:
        prefix = _glob_to_root(glob)
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        candidate = REPO_ROOT / prefix
        if candidate.exists():
            roots.append(candidate)
    return roots


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    """Run Q17 error-handling rules against `roots`. Return 1 if any errors fired."""
    policy = _load_policy(policy_path)
    total_errors = 0
    roots_list = list(roots)
    for root in roots_list:
        if not root.exists():
            continue
        if root.is_file():
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual, policy)
        else:
            walk_roots = _scoped_walk_roots(policy) if root == REPO_ROOT else [root]
            for walk_root in walk_roots:
                for p in _walk_files(walk_root):
                    virtual = (
                        str(p.relative_to(REPO_ROOT))
                        if p.is_relative_to(REPO_ROOT) else p.name
                    )
                    total_errors += _scan_file(p, virtual, policy)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: parse args, dispatch scan, return process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else (REPO_ROOT,)
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
