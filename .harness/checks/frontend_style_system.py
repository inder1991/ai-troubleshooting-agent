#!/usr/bin/env python3
"""Q1 — Tailwind-only style system + cn() class merging.

Four rules:
  Q1.no-css-in-js              — bans styled-components/emotion/stitches/
                                  vanilla-extract/linaria.
  Q1.no-extra-css-imports      — only frontend/src/index.css may be imported.
  Q1.no-inline-style-static    — `style={{ color: "..." }}` (static value)
                                  banned. Geometry escape hatch
                                  (width/height/transform/etc.) IS allowed.
  Q1.classname-needs-cn        — multi-class concat via `+` or template
                                  literal inside className requires cn().

Scope: frontend/src/**/*.{ts,tsx,js,jsx}. Excludes frontend/e2e/ and
frontend/src/test-utils/.

H-25:
  Missing input    — exit 2; emit ERROR rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip the file.
  Upstream failed  — none.
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
    "frontend/src/test-utils/",
    "tests/harness/fixtures/",
    "frontend/dist/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures",
)
BASELINE = load_baseline("frontend_style_system")

CSS_IN_JS_MODULES = {
    "styled-components",
    "@emotion/styled",
    "@emotion/react",
    "@stitches/react",
    "@vanilla-extract/css",
    "@linaria/core",
    "@linaria/react",
}
GEOMETRY_PROPS = {
    "width", "height", "minWidth", "minHeight", "maxWidth", "maxHeight",
    "top", "left", "right", "bottom",
    "transform", "transformOrigin", "translate", "rotate", "scale",
    "gridTemplateColumns", "gridTemplateRows",
}

CSS_IMPORT_RE = re.compile(r'''^\s*import\s+["']([^"']+\.(?:css|scss|sass|less|styl))["']''', re.MULTILINE)
IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
STYLE_PROP_RE = re.compile(r'style\s*=\s*\{\{([^}]*)\}\}', re.DOTALL)
CLASSNAME_PROP_RE = re.compile(r'className\s*=\s*\{([^}]*)\}', re.DOTALL)


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _scan_css_imports(path: Path, source: str) -> int:
    errors = 0
    for m in CSS_IMPORT_RE.finditer(source):
        spec = m.group(1)
        if not spec.endswith("index.css"):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q1.no-extra-css-imports",
                     f"CSS import `{spec}` outside frontend/src/index.css",
                     "move styles into Tailwind classes or extend index.css",
                     line):
                errors += 1
    return errors


def _scan_css_in_js(path: Path, source: str) -> int:
    errors = 0
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        if module in CSS_IN_JS_MODULES:
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q1.no-css-in-js",
                     f"CSS-in-JS library `{module}` banned (Q1: Tailwind only)",
                     "rewrite styles as Tailwind utility classes",
                     line):
                errors += 1
    return errors


def _scan_inline_styles(path: Path, source: str) -> int:
    errors = 0
    for m in STYLE_PROP_RE.finditer(source):
        body = m.group(1)
        pairs = [p.strip() for p in body.split(",") if ":" in p]
        if not pairs:
            continue
        offending: list[str] = []
        for pair in pairs:
            key_raw, _sep, value_raw = pair.partition(":")
            key = key_raw.strip().strip('"').strip("'")
            value = value_raw.strip().rstrip(",").strip()
            if not key or key in GEOMETRY_PROPS:
                continue
            if (
                value.startswith('"') and value.endswith('"')
                or value.startswith("'") and value.endswith("'")
                or re.match(r"^-?[0-9]", value)
            ):
                offending.append(key)
        if offending:
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q1.no-inline-style-static",
                     f"inline style with static keys {offending}",
                     "move static styling to Tailwind utility classes",
                     line):
                errors += 1
    return errors


def _scan_classname_concat(path: Path, source: str) -> int:
    errors = 0
    for m in CLASSNAME_PROP_RE.finditer(source):
        body = m.group(1).strip()
        if body.startswith("cn(") or body.startswith("clsx(") or body.startswith("twMerge("):
            continue
        if "+" in body or "${" in body:
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q1.classname-needs-cn",
                     "className concatenated via `+` or template literal",
                     "use cn(...) from @/lib/utils to merge classes",
                     line):
                errors += 1
    return errors


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
    errors += _scan_css_imports(path, source)
    errors += _scan_css_in_js(path, source)
    errors += _scan_inline_styles(path, source)
    errors += _scan_classname_concat(path, source)
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
