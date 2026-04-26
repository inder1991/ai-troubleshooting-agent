#!/usr/bin/env python3
"""SL — every gateway write must call self._audit(...).

One rule:
  SL.audit-emission-required — public StorageGateway method whose name starts
                                with create_/update_/delete_/upsert_/merge_/set_
                                must contain at least one `self._audit(...)` call.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src" / "storage",)
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
WRITE_PREFIXES = ("create_", "update_", "delete_", "upsert_", "merge_", "set_")
BASELINE = load_baseline("audit_emission")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _has_audit_call(fn) -> bool:
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_audit"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            return True
    return False


def _scan_file(path: Path, virtual: str) -> int:
    if not virtual.endswith("storage/gateway.py") and path.name != "gateway.py":
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
    errors = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StorageGateway":
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if any(sub.name.startswith(p) for p in WRITE_PREFIXES):
                        if not _has_audit_call(sub):
                            if _emit(path, "SL.audit-emission-required",
                                     f"StorageGateway.{sub.name} writes but does not call self._audit",
                                     'emit `await self._audit("<method>", payload)` before commit',
                                     sub.lineno):
                                errors += 1
    return errors


def _walk_python(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(tok in str(path) for tok in EXCLUDE):
            continue
        yield path


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual)
        else:
            for path in _walk_python(root):
                virtual = (
                    str(path.relative_to(REPO_ROOT))
                    if path.is_relative_to(REPO_ROOT) else path.name
                )
                total_errors += _scan_file(path, virtual)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
