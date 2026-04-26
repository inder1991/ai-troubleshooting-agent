#!/usr/bin/env python3
"""Q5 — Vitest discipline + Playwright scope.

Five rules:
  Q5.api-module-needs-test   — frontend/src/services/api/*.ts needs paired *.test.ts.
  Q5.hook-needs-test         — frontend/src/hooks/*.ts(x) needs paired *.test.ts(x).
  Q5.no-jest-or-mocha        — *.test.ts(x) banned from importing jest/mocha/enzyme.
  Q5.no-playwright-in-unit   — *.test.ts(x) banned from importing @playwright/test.
  Q5.e2e-must-use-playwright — frontend/e2e/*.spec.ts must import @playwright/test
                                AND must NOT import vitest.

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

from _common import emit, load_baseline  # noqa: E402

DEFAULT_ROOTS = (REPO_ROOT / "frontend",)
SCANNED_EXTS = {".ts", ".tsx", ".js", ".jsx"}
EXCLUDE_VIRTUAL_PREFIXES = (
    "frontend/dist/",
    "tests/harness/fixtures/",
    "frontend/node_modules/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures",
)
BANNED_TEST_FRAMEWORKS = {"jest", "mocha", "enzyme"}
PLAYWRIGHT_MODULE = "@playwright/test"
VITEST_MODULES = {"vitest"}
BASELINE = load_baseline("frontend_testing")

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
IT_OR_TEST_BLOCK_RE = re.compile(r'\b(it|test)\s*\(\s*["\']')


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_test_file(virtual: str) -> bool:
    return ".test." in virtual.split("/")[-1]


def _is_e2e_file(virtual: str) -> bool:
    return virtual.startswith("frontend/e2e/")


def _scan_test_imports(path: Path, virtual: str, source: str) -> int:
    errors = 0
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if _is_test_file(virtual):
            if module in BANNED_TEST_FRAMEWORKS:
                if _emit(path, "Q5.no-jest-or-mocha",
                         f"banned test framework `{module}` in unit test",
                         "use vitest instead", line):
                    errors += 1
            if module == PLAYWRIGHT_MODULE:
                if _emit(path, "Q5.no-playwright-in-unit",
                         "`@playwright/test` imported in unit test",
                         "move e2e tests under frontend/e2e/", line):
                    errors += 1
        if _is_e2e_file(virtual) and module in VITEST_MODULES:
            if _emit(path, "Q5.e2e-must-use-playwright",
                     "vitest imported in e2e spec",
                     "use @playwright/test in frontend/e2e/", line):
                errors += 1
    return errors


def _scan_e2e_must_use_playwright(path: Path, virtual: str, source: str) -> int:
    if not _is_e2e_file(virtual):
        return 0
    if PLAYWRIGHT_MODULE in source:
        return 0
    if _emit(path, "Q5.e2e-must-use-playwright",
             f"e2e spec {path.name} does not import from @playwright/test",
             'add `import { test, expect } from "@playwright/test";`', 1):
        return 1
    return 0


def _scan_paired_tests(root: Path) -> int:
    """services/api/*.ts and hooks/*.ts(x) must have paired *.test.ts(x) with at least one it/test."""
    errors = 0
    api_dir = root / "src" / "services" / "api"
    hook_dir = root / "src" / "hooks"
    if api_dir.exists():
        for src_file in api_dir.glob("*.ts"):
            if src_file.name in {"client.ts", "index.ts"} or src_file.name.endswith(".test.ts"):
                continue
            test_file = src_file.with_name(src_file.stem + ".test.ts")
            if not test_file.exists() or not IT_OR_TEST_BLOCK_RE.search(test_file.read_text(encoding="utf-8")):
                if _emit(src_file, "Q5.api-module-needs-test",
                         f"services/api/{src_file.name} missing non-empty paired test",
                         f"add {test_file.name} with at least one `it(` block", 1):
                    errors += 1
    if hook_dir.exists():
        for src_file in hook_dir.glob("*.ts"):
            if src_file.name == "index.ts" or src_file.name.endswith(".test.ts"):
                continue
            test_ts = src_file.with_name(src_file.stem + ".test.ts")
            test_tsx = src_file.with_name(src_file.stem + ".test.tsx")
            if not test_ts.exists() and not test_tsx.exists():
                if _emit(src_file, "Q5.hook-needs-test",
                         f"hooks/{src_file.name} missing paired test",
                         f"add {src_file.stem}.test.ts(x)", 1):
                    errors += 1
        for src_file in hook_dir.glob("*.tsx"):
            if src_file.name.endswith(".test.tsx"):
                continue
            test_tsx = src_file.with_name(src_file.stem + ".test.tsx")
            test_ts = src_file.with_name(src_file.stem + ".test.ts")
            if not test_tsx.exists() and not test_ts.exists():
                if _emit(src_file, "Q5.hook-needs-test",
                         f"hooks/{src_file.name} missing paired test",
                         f"add {src_file.stem}.test.tsx", 1):
                    errors += 1
    return errors


def _scan_pairing_for_single_file(path: Path, virtual: str) -> int:
    """When --target is a single .ts file under services/api/ or hooks/,
    check pairing relative to the file's actual on-disk neighbors."""
    errors = 0
    name = path.name
    if name in {"client.ts", "index.ts"} or ".test." in name or ".spec." in name:
        return 0
    if virtual.startswith("frontend/src/services/api/") and path.suffix == ".ts":
        test_file = path.with_name(path.stem + ".test.ts")
        if not test_file.exists() or not IT_OR_TEST_BLOCK_RE.search(test_file.read_text(encoding="utf-8")):
            if _emit(path, "Q5.api-module-needs-test",
                     f"services/api/{path.name} missing non-empty paired test",
                     f"add {test_file.name} with at least one `it(` block", 1):
                errors += 1
    elif virtual.startswith("frontend/src/hooks/") and path.suffix in {".ts", ".tsx"}:
        test_ts = path.with_name(path.stem + ".test.ts")
        test_tsx = path.with_name(path.stem + ".test.tsx")
        if not test_ts.exists() and not test_tsx.exists():
            if _emit(path, "Q5.hook-needs-test",
                     f"hooks/{path.name} missing paired test",
                     f"add {path.stem}.test.ts(x)", 1):
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
    errors += _scan_test_imports(path, virtual, source)
    errors += _scan_e2e_must_use_playwright(path, virtual, source)
    errors += _scan_pairing_for_single_file(path, virtual)
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
            # In dir mode: also do paired-test pairing under root if it's
            # a frontend/-shaped dir (has src/ inside).
            if (root / "src").is_dir():
                total_errors += _scan_paired_tests(root)
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
