#!/usr/bin/env python3
"""Q6 — single React Router v6 route table, lazy-imported pages.

Four rules (router.tsx-presence deferred to H.2 generators):
  Q6.single-route-table             — createBrowserRouter / createMemoryRouter
                                       outside router.tsx banned.
  Q6.pages-must-be-lazy             — page module imported synchronously
                                       inside router.tsx.
  Q6.no-anchor-for-internal-nav     — <a href="/...."> in components/* or pages/*.
  Q6.useNavigate-not-at-top-level   — `useNavigate(` at module top-level.

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

from _common import emit, load_baseline, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("frontend_src", ("frontend/src",))
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/dist/",
    "tests/harness/fixtures/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures",
)
BASELINE = load_baseline("frontend_routing")

CREATE_ROUTER_RE = re.compile(r'\bcreate(?:Browser|Memory)Router\s*\(')
ANCHOR_INTERNAL_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\'](/[^"\']*)["\']')
PAGE_IMPORT_RE = re.compile(r'''^\s*import\s+(\w+)\s+from\s+["'](?:@/pages/[^"']+|\.\./pages/[^"']+|\./pages/[^"']+)["']''', re.MULTILINE)
USE_NAVIGATE_TOP_RE = re.compile(r'^const\s+\w+\s*=\s*useNavigate\s*\(', re.MULTILINE)


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_router_tsx(virtual: str) -> bool:
    return virtual == "frontend/src/router.tsx" or virtual.endswith("/router.tsx")


def _is_feature_file(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    )


def _scan_file(path: Path, virtual: str) -> int:
    if _is_excluded(virtual):
        return 0
    if path.suffix not in SCANNED_EXTS:
        return 0
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0

    if not _is_router_tsx(virtual):
        for m in CREATE_ROUTER_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q6.single-route-table",
                     "createBrowserRouter outside frontend/src/router.tsx",
                     "declare all routes in router.tsx (Q6: single route table)",
                     line):
                errors += 1

    if _is_feature_file(virtual):
        for m in ANCHOR_INTERNAL_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q6.no-anchor-for-internal-nav",
                     f'<a href="{m.group(1)}"> for internal navigation',
                     f'use <Link to="{m.group(1)}"> from react-router-dom',
                     line):
                errors += 1

    for m in USE_NAVIGATE_TOP_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        if _emit(path, "Q6.useNavigate-not-at-top-level",
                 "useNavigate() invoked at module top-level",
                 "call useNavigate() inside a component/hook function body",
                 line):
            errors += 1

    if _is_router_tsx(virtual):
        for m in PAGE_IMPORT_RE.finditer(source):
            page_name = m.group(1)
            # Confirm there's no surrounding lazy(...) wrapper for this name
            # by looking at the text near the import.
            window = source[max(0, m.start() - 80):m.start()]
            if "lazy(" in window:
                continue
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q6.pages-must-be-lazy",
                     f"page `{page_name}` imported synchronously",
                     f'const {page_name} = lazy(() => import("@/pages/{page_name}"))',
                     line):
                errors += 1

    return errors


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_EXTS:
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def scan(roots: Iterable[Path], pretend_path: str | None) -> int:
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix in SCANNED_EXTS:
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
