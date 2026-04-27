#!/usr/bin/env python3
"""Validate orchestrator — `make validate-fast` and `make validate-full`.

H-14: single contract. Invokes lint + typecheck + every script in
.harness/checks/ (in --fast mode) or all-of-fast + tests + heavy audits
(in --full mode). Aggregates exit codes; aggregates structured output
per H-16 / H-23.

H-17: fast tier must run in < 30 s; tests are deferred to --full.

Point #25 — every [ERROR] emitted by a check during this run is appended
to .harness/.failure-log.jsonl with timestamp + commit + session UUID +
host. The log gives the AI (and humans) trend visibility — "this rule
fired 47 times this week" — without any API spend. The log is gitignored
(per-machine telemetry); rotation kicks in at 10 MB.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = REPO_ROOT / ".harness/checks"

# Point #25 — rolling failure log.
FAILURE_LOG_PATH = REPO_ROOT / ".harness" / ".failure-log.jsonl"
FAILURE_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB rotation threshold

# B14 (v1.2.0) — wall budget per check subprocess. Matches
# refresh_baselines._refresh_one's timeout. A check that hangs (infinite
# loop, blocked I/O, runaway recursion) gets killed and surfaces as a
# synthetic harness.timeout finding.
CHECK_TIMEOUT_S = 180

# B5 hardening — import the shared regex from _common so we never drift.
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
from _common import ERROR_LINE_PATTERN as ERROR_LINE_RE  # noqa: E402

# Set once per process so every log line in a run shares one session id.
_SESSION_ID = uuid.uuid4().hex[:12]
_SESSION_HOST = socket.gethostname()


def _have(cmd: str) -> bool:
    """True if `cmd` is on PATH."""
    return shutil.which(cmd) is not None


def _current_commit() -> str | None:
    """Return current HEAD short SHA, or None if outside a git repo / no git."""
    if not _have("git"):
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


# B2 hardening — fcntl is POSIX-only; on Windows we fall back to no locking
# (concurrent runs can interleave; documented limitation).
try:
    import fcntl as _fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover — Windows
    _HAVE_FCNTL = False


def _rotate_failure_log() -> None:
    """If FAILURE_LOG_PATH exceeds its size cap, rename to .1.

    B10 (v1.1.1): the rotate path is now held under fcntl.LOCK_EX so
    concurrent run_validate processes can't both observe size > cap
    and double-rename onto .1, clobbering the first rotation's bytes.
    Re-checks size under the lock — another process may have already
    rotated between our exists() and our lock acquisition.

    Windows fallback: no lock available; documented in the v1.1.0
    release notes (B2 already had the same limitation for append).
    """
    if not FAILURE_LOG_PATH.exists():
        return
    if not _HAVE_FCNTL:
        try:
            if FAILURE_LOG_PATH.stat().st_size > FAILURE_LOG_MAX_BYTES:
                rotated = FAILURE_LOG_PATH.with_suffix(FAILURE_LOG_PATH.suffix + ".1")
                if rotated.exists():
                    rotated.unlink()
                FAILURE_LOG_PATH.rename(rotated)
        except OSError:
            pass
        return
    try:
        with FAILURE_LOG_PATH.open("a+", encoding="utf-8") as fh:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            try:
                if FAILURE_LOG_PATH.stat().st_size <= FAILURE_LOG_MAX_BYTES:
                    return
                rotated = FAILURE_LOG_PATH.with_suffix(FAILURE_LOG_PATH.suffix + ".1")
                if rotated.exists():
                    try:
                        rotated.unlink()
                    except OSError:
                        pass
                FAILURE_LOG_PATH.rename(rotated)
            finally:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
    except OSError:
        # Rotation must never abort validate.
        pass


def _append_failure_log(rule: str, file: str, line: int, commit: str | None) -> None:
    """Append one structured failure entry to .harness/.failure-log.jsonl.

    B2 hardening: holds fcntl.LOCK_EX during the write so concurrent
    validate-fast invocations (CI + local + IDE pre-save trigger) can't
    interleave entries and corrupt the JSONL.
    """
    entry = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "rule": rule,
        "file": file,
        "line": line,
        "commit": commit,
        "host": _SESSION_HOST,
        "session": _SESSION_ID,
    }
    try:
        FAILURE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FAILURE_LOG_PATH.open("a", encoding="utf-8") as fh:
            if _HAVE_FCNTL:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
                try:
                    fh.write(json.dumps(entry, sort_keys=True) + "\n")
                finally:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            else:
                # Windows: no lock available. Document, don't crash.
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        # Log failure must never abort validate-fast.
        pass


def _run(label: str, cmd: Sequence[str], cwd: Path = REPO_ROOT) -> int:
    """Run a subprocess; stream its stdout/stderr; return exit code.

    For check invocations we ALSO capture stdout, parse [ERROR] lines, and
    append to .harness/.failure-log.jsonl. Lint/typecheck use the older
    streaming path (their output isn't H-16-conformant).
    """
    print(f"\n[VALIDATE] {label} → {' '.join(cmd)}")
    start = time.monotonic()
    is_check = label.startswith("check:")
    if is_check:
        # Capture stdout to parse for errors; re-print verbatim so the user
        # sees the same output they would have without the failure log.
        try:
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True,
                timeout=CHECK_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            # B14 (v1.2.0): a check exceeded its wall budget. Emit a
            # synthetic H-16 [ERROR] line + failure-log entry, return 1.
            elapsed = time.monotonic() - start
            check_name = label.removeprefix("check:")
            emit_line = (
                f'[ERROR] file={check_name} rule=harness.timeout '
                f'message="check exceeded {CHECK_TIMEOUT_S}s wall budget" '
                f'suggestion="profile the check or split its scope"\n'
            )
            sys.stdout.write(emit_line)
            sys.stdout.flush()
            commit = _current_commit()
            _append_failure_log(
                rule="harness.timeout",
                file=check_name,
                line=0,
                commit=commit,
            )
            print(f"[VALIDATE] {label} TIMED OUT after {elapsed:.1f}s")
            return 1
        if result.stdout:
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
        if result.stderr:
            sys.stderr.write(result.stderr)
            sys.stderr.flush()
        commit = _current_commit()
        for line in result.stdout.splitlines():
            m = ERROR_LINE_RE.match(line)
            if m:
                _append_failure_log(
                    rule=m.group("rule"),
                    file=m.group("file"),
                    line=int(m.group("line")),
                    commit=commit,
                )
    else:
        try:
            result = subprocess.run(cmd, cwd=cwd, timeout=CHECK_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            print(f"[VALIDATE] {label} TIMED OUT after {elapsed:.1f}s")
            return 1
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

# Heavy checks that exceed per-iteration cost in the fast tier. They run only
# in --full mode. Each one earned its slot here by exceeding ~3s wall and
# enforcing rules that don't typically change between consecutive commits
# (output shape, fixture-driven self-tests).
FULL_ONLY_CHECKS = {
    "output_format_conformance.py",
    "backend_testing.py",
    "frontend_testing.py",
    "backend_async_correctness.py",
    "backend_db_layer.py",
}


def run_custom_checks(full: bool) -> int:
    """Invoke every .harness/checks/*.py except _common.py / __init__.py,
    DEDICATED_RUNNERS, and (in --fast mode) FULL_ONLY_CHECKS."""
    if not CHECKS_DIR.is_dir():
        return 0
    overall = 0
    _rotate_failure_log()
    for script in sorted(CHECKS_DIR.glob("*.py")):
        if script.name in ("__init__.py", "_common.py"):
            continue
        if script.name in DEDICATED_RUNNERS:
            continue
        if not full and script.name in FULL_ONLY_CHECKS:
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
    overall |= run_custom_checks(full=args.full)

    if args.full:
        overall |= run_tests()

    status = "PASS" if overall == 0 else "FAIL"
    mode_label = "fast" if args.fast else "full"
    print(f"\nVALIDATE_SUMMARY mode={mode_label} status={status}")
    return overall


if __name__ == "__main__":
    sys.exit(main())
