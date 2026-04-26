#!/usr/bin/env python3
"""discipline — no TODO/FIXME/XXX/HACK in production paths.

One rule:
  discipline.todo-in-prod — comment marker outside tests/, docs/, .harness/,
                            tests/harness/fixtures/, frontend/e2e/.

H-25 — same defaults as siblings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
EXCLUDE_FS = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache", "dist",
)
EXEMPT_VIRTUAL_PREFIXES = (
    "tests/",
    "docs/",
    ".harness/",
    "tests/harness/",
    "frontend/e2e/",
    "backend/tests/",
)
MARKER_RE = re.compile(r'^\s*(#|//)\s*(TODO|FIXME|XXX|HACK)\b')
BASELINE = load_baseline("todo_in_prod")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_exempt(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXEMPT_VIRTUAL_PREFIXES)


def _scan_file(path: Path, virtual: str) -> int:
    if _is_exempt(virtual):
        return 0
    if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        return 0
    errors = 0
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = MARKER_RE.match(line)
            if m:
                if _emit(path, "discipline.todo-in-prod",
                         f"`{m.group(2)}` marker in production file",
                         "resolve, file an issue, or move to docs/decisions/",
                         lineno):
                    errors += 1
    except (OSError, UnicodeDecodeError):
        return 0
    return errors


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual)
        else:
            for p in _walk_files(root):
                virtual = (
                    str(p.relative_to(REPO_ROOT))
                    if p.is_relative_to(REPO_ROOT) else p.name
                )
                total_errors += _scan_file(p, virtual)
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
