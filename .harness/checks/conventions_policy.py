#!/usr/bin/env python3
"""Q18 — code conventions (naming + imports + commits).

Six static rules enforced (subprocess wrappers — ruff/eslint/commitlint —
deferred: those tools already run in pre-commit + run_validate.py
directly; this check focuses on what they don't catch):
  Q18.python-snake-case                — backend/src/*.py must be lower_snake_case.
  Q18.frontend-component-pascal-case   — frontend/src/components/*.tsx must be PascalCase.
  Q18.frontend-hook-camel-case         — frontend/src/hooks/*.ts(x) must start with `use`+camelCase.
  Q18.no-relative-import-backend       — `from .` banned in backend/src.
  Q18.no-dotdot-import-frontend        — `import … from "../...";` banned in frontend/src.
  Q18.no-default-export-in-components  — `export default` banned under
                                         frontend/src/components/.

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

DEFAULT_ROOTS = (REPO_ROOT,)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
BASELINE = load_baseline("conventions_policy")

SNAKE_CASE_RE = re.compile(r'^[a-z_][a-z0-9_]*$')
PASCAL_CASE_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')
HOOK_NAME_RE = re.compile(r'^use[A-Z][A-Za-z0-9]*$')
RELATIVE_IMPORT_RE = re.compile(r'^\s*from\s+\.+', re.MULTILINE)
DOTDOT_IMPORT_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']\.\.?/[^"']*["']''', re.MULTILINE)
DEFAULT_EXPORT_RE = re.compile(r'^\s*export\s+default\b', re.MULTILINE)


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (str(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _scan_naming(path: Path, virtual: str) -> int:
    # Naming rules check the *virtual* path's filename (so pretend-path
    # honors apply); fixture stems are usually descriptive, not canonical.
    vname = Path(virtual).name
    vstem = Path(virtual).stem
    errors = 0
    if virtual.startswith("backend/src/") and vname.endswith(".py"):
        if not SNAKE_CASE_RE.match(vstem):
            if _emit(path, "Q18.python-snake-case",
                     f"`{vname}` is not lower_snake_case",
                     f"rename to {re.sub(r'[^a-zA-Z0-9_]+', '_', vstem).lower()}.py"):
                errors += 1
    if virtual.startswith("frontend/src/components/") and vname.endswith(".tsx"):
        if not PASCAL_CASE_RE.match(vstem):
            if _emit(path, "Q18.frontend-component-pascal-case",
                     f"component file `{vname}` is not PascalCase",
                     f"rename to {vstem[:1].upper()}{vstem[1:]}.tsx"):
                errors += 1
    if virtual.startswith("frontend/src/hooks/") and (vname.endswith(".ts") or vname.endswith(".tsx")):
        if not HOOK_NAME_RE.match(vstem):
            if _emit(path, "Q18.frontend-hook-camel-case",
                     f"hook file `{vname}` does not start with `use` + camelCase",
                     f"rename to use{vstem[:1].upper()}{vstem[1:]}.ts"):
                errors += 1
    return errors


def _scan_imports(path: Path, virtual: str, source: str) -> int:
    errors = 0
    if virtual.startswith("backend/src/") and path.suffix == ".py":
        for m in RELATIVE_IMPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q18.no-relative-import-backend",
                     "relative import (from .x) banned in backend",
                     "use absolute import: from src.<module> import …",
                     line):
                errors += 1
    if virtual.startswith("frontend/src/") and path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        for m in DOTDOT_IMPORT_RE.finditer(source):
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q18.no-dotdot-import-frontend",
                     "`../..` import path banned in frontend",
                     "use the @/ alias (e.g., @/services/api/client)",
                     line):
                errors += 1
    return errors


def _scan_default_export(path: Path, virtual: str, source: str) -> int:
    if not virtual.startswith("frontend/src/components/"):
        return 0
    errors = 0
    for m in DEFAULT_EXPORT_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        if _emit(path, "Q18.no-default-export-in-components",
                 "`export default` inside frontend/src/components/",
                 "use a named export — `export const Foo = …`",
                 line):
            errors += 1
    return errors


def _scan_file(path: Path, virtual: str) -> int:
    errors = 0
    errors += _scan_naming(path, virtual)
    if path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return errors
        errors += _scan_imports(path, virtual, source)
        errors += _scan_default_export(path, virtual, source)
    return errors


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
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
    roots = tuple(args.target) if args.target else (REPO_ROOT / "backend" / "src", REPO_ROOT / "frontend" / "src")
    return scan(roots, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
