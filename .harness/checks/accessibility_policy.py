#!/usr/bin/env python3
"""Q14 — accessibility policy.

Four rules (eslint config + e2e + folder presence deferred to H.2):
  Q14.primitive-needs-axe-test        — components/ui/*.test.tsx must call axe()
                                         (or runAxe()).
  Q14.img-needs-alt                   — <img> without alt= attribute.
  Q14.button-needs-accessible-name    — <button>/<a> with no children and
                                         no aria-label/aria-labelledby.
  Q14.no-positive-tabindex            — tabIndex={n} where n > 0.

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

# #10 — consumer-overridable via .harness/spine_paths.yaml.
# Falls back to "frontend/src" for backward compat.
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
BASELINE = load_baseline("accessibility_policy")

IMG_TAG_RE = re.compile(r'<img\b([^>]*?)/?>', re.IGNORECASE | re.DOTALL)
BUTTON_OR_ANCHOR_RE = re.compile(r'<(button|a)\b([^>]*)>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
# Self-closing tag — match attrs that may contain JSX expressions including > characters
# inside braces; terminate at `/>` not preceded by `=`.
SELF_CLOSING_BUTTON_RE = re.compile(
    r'<(button|a)\b((?:[^>]|=>)*?)/>',
    re.IGNORECASE | re.DOTALL,
)
TABINDEX_RE = re.compile(r'tabIndex\s*=\s*\{?\s*(-?\d+)')


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _has_attr(attrs: str, name: str) -> bool:
    return re.search(rf'\b{name}\s*=', attrs, re.IGNORECASE) is not None


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

    for m in IMG_TAG_RE.finditer(source):
        attrs = m.group(1)
        if not _has_attr(attrs, "alt"):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q14.img-needs-alt",
                     "<img> missing alt attribute",
                     'add alt="" for decorative or alt="<description>" for content',
                     line):
                errors += 1

    for m in BUTTON_OR_ANCHOR_RE.finditer(source):
        attrs = m.group(2)
        body = m.group(3).strip()
        if not body and not _has_attr(attrs, "aria-label") and not _has_attr(attrs, "aria-labelledby"):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q14.button-needs-accessible-name",
                     f"<{m.group(1)}> without accessible name",
                     "add visible text, aria-label, or aria-labelledby",
                     line):
                errors += 1
    for m in SELF_CLOSING_BUTTON_RE.finditer(source):
        attrs = m.group(2)
        if not _has_attr(attrs, "aria-label") and not _has_attr(attrs, "aria-labelledby"):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q14.button-needs-accessible-name",
                     f"self-closing <{m.group(1)}> without accessible name",
                     "add aria-label or expand to include children",
                     line):
                errors += 1

    for m in TABINDEX_RE.finditer(source):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        if value > 0:
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q14.no-positive-tabindex",
                     f"tabIndex={value} (positive value creates focus-order trap)",
                     "use tabIndex={0} or tabIndex={-1}; let DOM order drive focus",
                     line):
                errors += 1

    # Check if this is a UI primitive test file (use virtual path to honor pretend-path).
    virtual_name = Path(virtual).name
    if virtual.startswith("frontend/src/components/ui/") and ".test." in virtual_name:
        # Strip block + line comments so words inside docstrings don't satisfy
        # the axe() requirement.
        stripped = re.sub(r'/\*[\s\S]*?\*/', '', source)
        stripped = re.sub(r'//.*', '', stripped)
        if "axe(" not in stripped and "runAxe(" not in stripped:
            if _emit(path, "Q14.primitive-needs-axe-test",
                     f"primitive test {virtual_name} does not call axe()",
                     "import { axe } from 'vitest-axe' and assert no violations",
                     1):
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
    """Run Q14 a11y rules on each path under `roots`. Return 1 if any errors fired."""
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
    """CLI entrypoint: dispatch scan, return process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
