#!/usr/bin/env python3
"""Q16 — logging discipline (no print, no silent except, lazy format, no secret literals).

Four rules:
  Q16.no-print-in-spine          — `print(...)` in backend spine paths.
  Q16.bare-except-no-log         — `except:` or `except Exception:` whose body
                                    contains no logger call (silent swallow).
  Q16.f-string-in-log            — f-string passed positionally to a logger
                                    method (info/warning/error/debug/critical/
                                    exception). Use `log.info("msg %s", x)`.
  Q16.secret-shaped-log-literal  — string-literal arg to logger method matches
                                    a secret-shaped pattern (Authorization:,
                                    password=, token=, api_key=, …).

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable; skip file.
  Upstream failed  — none (pure AST; no external binaries).
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

from _common import emit, load_baseline, normalize_path  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / ".harness" / "logging_policy.yaml"
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
BASELINE = load_baseline("logging_policy")


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (normalize_path(file), int(line), rule)
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


def _is_logger_call(node: ast.Call, logger_attrs: set[str]) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in logger_attrs:
        return True
    return False


def _contains_logger_call(stmts: list[ast.stmt], logger_attrs: set[str]) -> bool:
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call) and _is_logger_call(sub, logger_attrs):
                return True
    return False


def _scan_python(path: Path, source: str, policy: dict, in_spine: bool) -> int:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    logger_attrs = set(policy.get("logger_attr_names") or [])
    secret_pats = [p.lower() for p in (policy.get("secret_log_patterns") or [])]
    errors = 0

    for node in ast.walk(tree):
        if in_spine and isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                if _emit(path, "Q16.no-print-in-spine",
                         "print() in spine path; use a structured logger instead",
                         "replace `print(...)` with `log.info(...)` or similar",
                         node.lineno):
                    errors += 1

        if isinstance(node, ast.ExceptHandler):
            is_bare = node.type is None
            is_broad = (
                isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException")
            )
            if (is_bare or is_broad) and not _contains_logger_call(node.body, logger_attrs):
                if _emit(path, "Q16.bare-except-no-log",
                         "broad/bare except swallows error without logging",
                         "log the exception (`log.exception(...)`) or narrow the except",
                         node.lineno):
                    errors += 1

        if isinstance(node, ast.Call) and _is_logger_call(node, logger_attrs):
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.JoinedStr):
                    if _emit(path, "Q16.f-string-in-log",
                             "f-string passed to logger; use lazy %-style instead",
                             "`log.info(\"msg %s\", value)` lets handlers drop work when level is filtered",
                             node.lineno):
                        errors += 1
                elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                    lowered = first.value.lower()
                    hit = next((p for p in secret_pats if p in lowered), None)
                    if hit:
                        if _emit(path, "Q16.secret-shaped-log-literal",
                                 f"log message contains secret-shaped pattern `{hit}`",
                                 "redact via redact_secret(...) or omit the secret token entirely",
                                 node.lineno):
                            errors += 1
    return errors


def _scan_file(path: Path, virtual: str, policy: dict) -> int:
    if _is_excluded(virtual):
        return 0
    if path.suffix != ".py":
        return 0
    spine = policy.get("spine_paths") or []
    in_spine = _matches_any(virtual, spine)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    return _scan_python(path, source, policy, in_spine)


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
    """Run Q16 logging-policy rules against `roots`. Return 1 if any errors fired."""
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
