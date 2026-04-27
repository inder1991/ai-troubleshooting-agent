#!/usr/bin/env python3
"""Q2 + Q3 — frontend data layer (state management + API access).

Six rules (presence/api_client deferred to H.2 generators):
  Q2.no-redux                          — redux/@reduxjs/toolkit/mobx/recoil/jotai banned.
  Q2.zustand-quarantine                — zustand outside frontend/src/stores/.
  Q2.zustand-needs-justification       — zustand inside stores/ without
                                         `// JUSTIFICATION:` comment.
  Q3.no-axios                          — axios banned.
  Q3.no-raw-fetch-in-ui                — `fetch(` inside components/, pages/, hooks/.
  Q3.component-no-direct-services-api  — components/pages may not import
                                         from @/services/api/* (excluding client.ts).
  Q3.queryfn-must-use-apiclient        — useQuery({ queryFn: () => fetch(...) }) banned.

H-25:
  Missing input    — exit 2; emit ERROR rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip.
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
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures",
)
BANNED_STATE_LIBS = {
    "redux", "@reduxjs/toolkit", "mobx", "mobx-react-lite", "recoil", "jotai",
}
BASELINE = load_baseline("frontend_data_layer")

IMPORT_FROM_RE = re.compile(r'''^\s*import\s+[^;]*?\bfrom\s+["']([^"']+)["']''', re.MULTILINE)
USE_QUERY_RE = re.compile(r'useQuery\s*\(\s*\{[^}]*queryFn\s*:\s*\(?\)?\s*=>\s*([^,}]+)', re.DOTALL)
FETCH_CALL_RE = re.compile(r'\bfetch\s*\(')


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (str(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


def _is_component_or_page(virtual: str) -> bool:
    return (
        virtual.startswith("frontend/src/components/")
        or virtual.startswith("frontend/src/pages/")
    )


def _is_hook_file(virtual: str) -> bool:
    return virtual.startswith("frontend/src/hooks/")


def _is_store_file(virtual: str) -> bool:
    return virtual.startswith("frontend/src/stores/")


def _scan_imports(path: Path, virtual: str, source: str) -> int:
    errors = 0
    seen_zustand_in_stores = False
    for m in IMPORT_FROM_RE.finditer(source):
        module = m.group(1)
        line = source[:m.start()].count("\n") + 1
        if module in BANNED_STATE_LIBS or any(module.startswith(b + "/") for b in BANNED_STATE_LIBS):
            if _emit(path, "Q2.no-redux",
                     f"banned state-management library `{module}`",
                     "use TanStack Query for server state, useState/Context for UI state",
                     line):
                errors += 1
        if module == "zustand" or module.startswith("zustand/"):
            if _is_store_file(virtual):
                seen_zustand_in_stores = True
            else:
                if _emit(path, "Q2.zustand-quarantine",
                         "zustand imported outside frontend/src/stores/",
                         "move state into a slice under frontend/src/stores/ with a JUSTIFICATION comment",
                         line):
                    errors += 1
        if module == "axios":
            if _emit(path, "Q3.no-axios",
                     "`axios` banned; use apiClient<T>() wrapper",
                     "rewrite via @/services/api/client",
                     line):
                errors += 1
        if (
            _is_component_or_page(virtual)
            and module.startswith("@/services/api/")
            and not module.endswith("/client")
            and module != "@/services/api/client"
        ):
            if _emit(path, "Q3.component-no-direct-services-api",
                     f"component imports `{module}` directly",
                     "consume via a TanStack Query hook under @/hooks/",
                     line):
                errors += 1
    if seen_zustand_in_stores and "JUSTIFICATION:" not in source:
        if _emit(path, "Q2.zustand-needs-justification",
                 "zustand store missing `// JUSTIFICATION:` comment",
                 "add a single-line comment explaining why this UI state warrants Zustand",
                 1):
            errors += 1
    return errors


def _scan_fetch_in_ui(path: Path, virtual: str, source: str) -> int:
    if not (_is_component_or_page(virtual) or _is_hook_file(virtual)):
        return 0
    errors = 0
    for m in FETCH_CALL_RE.finditer(source):
        line = source[:m.start()].count("\n") + 1
        if _emit(path, "Q3.no-raw-fetch-in-ui",
                 "raw `fetch(` inside UI/hook code",
                 "route the call through apiClient<T>() and a TanStack Query hook",
                 line):
            errors += 1
    return errors


def _scan_usequery_queryfn(path: Path, virtual: str, source: str) -> int:
    errors = 0
    for m in USE_QUERY_RE.finditer(source):
        callee = m.group(1).strip()
        if "fetch(" in callee:
            line = source[:m.start()].count("\n") + 1
            if _emit(path, "Q3.queryfn-must-use-apiclient",
                     "useQuery queryFn calls raw fetch()",
                     "call apiClient<T>() so retry/timeout/typing apply",
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
    errors += _scan_imports(path, virtual, source)
    errors += _scan_fetch_in_ui(path, virtual, source)
    errors += _scan_usequery_queryfn(path, virtual, source)
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
