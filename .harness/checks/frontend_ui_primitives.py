#!/usr/bin/env python3
"""Q4 — shadcn-pattern UI primitives, no third-party kits.

Four rules (folder-presence deferred to H.2 generators):
  Q4.no-bare-html-primitive    — bare <button>/<input>/<select>/<textarea>/
                                  <a onClick=...> in components/* or pages/*.
  Q4.no-third-party-ui-kit     — MUI/Chakra/Mantine/react-bootstrap/antd/
                                  semantic-ui banned.
  Q4.primitive-no-business-logic — imports inside frontend/src/components/ui/*
                                    may not start with @/services, @/hooks,
                                    @/pages, @/lib/api.
  Q4.no-wrapper-reexport       — re-export of @/components/ui/* outside
                                  ui/index.ts.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
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

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("frontend_src", ("frontend/src",))
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/e2e/",
    "frontend/src/test-utils/",
    "tests/harness/fixtures/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures",
)
THIRD_PARTY_UI_PREFIXES = (
    "@mui/", "@chakra-ui/", "@mantine/",
    "react-bootstrap", "antd", "semantic-ui-react",
)
BUSINESS_IMPORT_PREFIXES = ("@/services", "@/hooks", "@/pages", "@/lib/api")
UI_PRIMITIVE_PATH_PREFIX = "frontend/src/components/ui/"
BASELINE = load_baseline("frontend_ui_primitives")

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
REEXPORT_RE = re.compile(r'''^\s*export\s*\{[^}]*\}\s*from\s+["'](@/components/ui/[^"']+)["']''', re.MULTILINE)
BARE_PRIMITIVE_RE = re.compile(r'<(button|input|select|textarea)\b[^>]*>')
ANCHOR_ONCLICK_RE = re.compile(r'<a\b[^>]*\bonClick\s*=')


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_feature_file(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    ) and not virtual.startswith(UI_PRIMITIVE_PATH_PREFIX)


def _is_ui_primitive(virtual: str) -> bool:
    return virtual.startswith(UI_PRIMITIVE_PATH_PREFIX)


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
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if any(module.startswith(p) for p in THIRD_PARTY_UI_PREFIXES):
            if _emit(path, "Q4.no-third-party-ui-kit",
                     f"third-party UI library `{module}` banned",
                     "copy a Radix-based primitive into frontend/src/components/ui/",
                     line):
                errors += 1
        if _is_ui_primitive(virtual) and any(module.startswith(p) for p in BUSINESS_IMPORT_PREFIXES):
            if _emit(path, "Q4.primitive-no-business-logic",
                     f"ui primitive imports business module `{module}`",
                     "primitives are presentation only; lift the call into the consuming feature",
                     line):
                errors += 1
    if _is_feature_file(virtual):
        for m in BARE_PRIMITIVE_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q4.no-bare-html-primitive",
                     f"bare <{m.group(1)}> in feature code",
                     f"use the locally-owned <{m.group(1).capitalize()}> from @/components/ui/{m.group(1)}",
                     line):
                errors += 1
        for m in ANCHOR_ONCLICK_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q4.no-bare-html-primitive",
                     "<a onClick=...> imitating a button",
                     "use <Button> for actions or <Link to=...> for navigation",
                     line):
                errors += 1
    if not virtual.endswith("frontend/src/components/ui/index.ts"):
        for m in REEXPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q4.no-wrapper-reexport",
                     f"wrapper re-export of `{m.group(1)}`",
                     "edit the primitive in place under components/ui/ instead of wrapping",
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
