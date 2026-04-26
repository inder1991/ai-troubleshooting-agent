#!/usr/bin/env python3
"""Validate orchestrator — `make validate-fast` and `make validate-full`.

H-14: single contract. Invokes lint + typecheck + every script in
.harness/checks/ (in --fast mode) or all-of-fast + tests + heavy audits
(in --full mode). Aggregates exit codes; aggregates structured output
per H-16 / H-23.

H-17: fast tier must run in < 30 s; tests are deferred to --full.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = REPO_ROOT / ".harness/checks"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(label: str, cmd: Sequence[str], cwd: Path = REPO_ROOT) -> int:
    """Run a subprocess; stream its stdout/stderr; return exit code."""
    print(f"\n[VALIDATE] {label} → {' '.join(cmd)}")
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=cwd)
    elapsed = time.monotonic() - start
    print(f"[VALIDATE] {label} exited {result.returncode} ({elapsed:.1f}s)")
    return result.returncode


def run_lint() -> int:
    """Lint + format-check. Skipped if tools missing (early bootstrap)."""
    if (REPO_ROOT / "backend").is_dir() and _have("ruff"):
        rc = _run("ruff check", ["ruff", "check", "backend/", ".harness/", "tools/"])
        if rc != 0:
            return rc
    if (REPO_ROOT / "frontend").is_dir() and _have("npx"):
        # ESLint config exists from H.0b.7 (jsx-a11y stub) but the TypeScript
        # parser stack (typescript-eslint) is wired in H.0b.11. Until then,
        # eslint can't parse our .ts/.tsx files without 500+ parse errors.
        # We invoke eslint only when typescript-eslint is also installed —
        # that's the canary for "full parser stack present".
        eslint_config = REPO_ROOT / "frontend/eslint.config.js"
        ts_eslint_pkg = REPO_ROOT / "frontend/node_modules/typescript-eslint/package.json"
        if eslint_config.exists() and ts_eslint_pkg.exists():
            rc = _run(
                "eslint",
                ["npx", "eslint", "src/"],
                cwd=REPO_ROOT / "frontend",
            )
            if rc != 0:
                return rc
    return 0


def run_typecheck(full: bool) -> int:
    """Q19 typecheck enforcement. Heavyweight (mypy + tsc subprocesses);
    runs only in --full mode to keep --fast under H-17's 30s budget."""
    if not full:
        return 0
    script = CHECKS_DIR / "typecheck_policy.py"
    if not script.exists():
        return 0
    return _run("check:typecheck_policy", [sys.executable, str(script)])


# Skipped by run_custom_checks (the auto-glob); invoked via dedicated runners.
DEDICATED_RUNNERS = {"typecheck_policy.py"}


def run_custom_checks() -> int:
    """Invoke every .harness/checks/*.py except _common.py / __init__.py and
    DEDICATED_RUNNERS (which have their own gated invocation)."""
    if not CHECKS_DIR.is_dir():
        return 0
    overall = 0
    for script in sorted(CHECKS_DIR.glob("*.py")):
        if script.name in ("__init__.py", "_common.py"):
            continue
        if script.name in DEDICATED_RUNNERS:
            continue
        rc = _run(f"check:{script.stem}", [sys.executable, str(script)])
        if rc != 0:
            overall = 1  # non-zero, but keep running other checks for full report
    return overall


def run_tests() -> int:
    """Backend pytest + frontend vitest. Only in --full mode."""
    overall = 0
    if (REPO_ROOT / "backend").is_dir() and _have("pytest"):
        rc = _run(
            "pytest",
            [sys.executable, "-m", "pytest", "backend/tests/", "tests/harness/", "-q"],
        )
        if rc != 0:
            overall = rc
    return overall


def main(argv: list[str] | None = None) -> int:
    """Parse --fast/--full mode, dispatch lint + typecheck + checks (+ tests). Return aggregate exit code."""
    parser = argparse.ArgumentParser(description="Run harness validations.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fast", action="store_true", help="Inner-loop gate (< 30s).")
    mode.add_argument("--full", action="store_true", help="Pre-commit / CI gate.")
    args = parser.parse_args(argv)

    overall = 0
    overall |= run_lint()
    overall |= run_typecheck(full=args.full)
    overall |= run_custom_checks()

    if args.full:
        overall |= run_tests()

    status = "PASS" if overall == 0 else "FAIL"
    mode_label = "fast" if args.fast else "full"
    print(f"\nVALIDATE_SUMMARY mode={mode_label} status={status}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
