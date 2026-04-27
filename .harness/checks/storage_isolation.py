#!/usr/bin/env python3
"""storage — every X.execute(...) call lives inside backend/src/storage/.

One rule:
  storage.execute-outside-gateway — `<name>.execute(...)` where <name> is
                                     cursor/connection/session/engine/conn,
                                     outside backend/src/storage/.

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

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("backend_src", ("backend/src",))
EXCLUDE = (
    "__pycache__", ".venv", "/venv/", "node_modules",
    "tests/harness/fixtures", "site-packages", ".git", ".pytest_cache",
)
EXECUTE_RE = re.compile(r'\b(cursor|connection|session|engine|conn)\.execute\s*\(')
STORAGE_PREFIX = "backend/src/storage"
BASELINE = load_baseline("storage_isolation")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _scan_file(path: Path, virtual: str) -> int:
    if virtual.startswith(STORAGE_PREFIX + "/") or virtual == STORAGE_PREFIX:
        return 0
    errors = 0
    try:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            m = EXECUTE_RE.search(line)
            if m:
                if _emit(path, "storage.execute-outside-gateway",
                         f"`{m.group(1)}.execute(...)` outside backend/src/storage/",
                         "add a method to StorageGateway and route through it",
                         lineno):
                    errors += 1
    except (OSError, UnicodeDecodeError):
        return 0
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
            for p in _walk_python(root):
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
