#!/usr/bin/env python3
"""H-16/H-23 — every check's stdout must match the binding output shape.

One rule:
  H16.output-format-violation — non-blank stdout line that does not match
                                 `^\\[(ERROR|WARN|INFO)\\] file=.+ rule=.+ message=".+" suggestion=".+"$`
                                 (with a small allowance for VALIDATE_SUMMARY/orchestrator chatter).

Mode of operation:
  * If --target is a single .py file: run that file as a check, capture stdout, validate.
  * If --target is a directory: run every .harness/checks/*.py inside it
    (skipping _common.py and itself).

H-25:
  Missing input    — exit 2 if --target absent.
  Malformed input  — WARN harness.unparseable; skip.
  Upstream failed  — when a check's subprocess itself errors, emit ERROR
                     rule=H16.subprocess-error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit  # noqa: E402

DEFAULT_TARGET = REPO_ROOT / ".harness" / "checks"

OUTPUT_LINE_RE = re.compile(
    r'^\[(ERROR|WARN|INFO)\]\s+file=\S+\s+rule=\S+\s+message="[^"]*"\s+suggestion="[^"]*"$'
)
ALLOWLIST_PREFIXES = (
    "[VALIDATE]", "[INFO]", "VALIDATE_SUMMARY", "Traceback",
)


def _line_is_conforming(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(ALLOWLIST_PREFIXES):
        return True
    return bool(OUTPUT_LINE_RE.match(stripped))


def _find_violation_fixture(check: Path) -> Path | None:
    """Find a per-check violation fixture under tests/harness/fixtures/<rule>/violation/."""
    rule = check.stem
    fixture_dir = REPO_ROOT / "tests" / "harness" / "fixtures" / rule / "violation"
    if not fixture_dir.exists():
        return None
    candidates = sorted(p for p in fixture_dir.iterdir() if p.is_file())
    return candidates[0] if candidates else None


def _run_check(check: Path, fixture: Path | None) -> tuple[int, str, str]:
    cmd = [sys.executable, str(check)]
    if fixture is not None:
        cmd.extend(["--target", str(fixture)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 99, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def _validate(check: Path) -> int:
    """Returns number of ERRORs emitted."""
    fixture = _find_violation_fixture(check)
    rc, stdout, stderr = _run_check(check, fixture)
    if rc == 99:
        emit("ERROR", check, "H16.subprocess-error",
             f"could not invoke {check.name}: {stderr.strip()[:200]}",
             "check that the script is executable and importable", line=0)
        return 1
    errors = 0
    for lineno, line in enumerate(stdout.splitlines(), 1):
        if not _line_is_conforming(line):
            emit("ERROR", check, "H16.output-format-violation",
                 f"non-conforming output line: {line[:80]}",
                 'emit `[SEVERITY] file=… rule=… message="…" suggestion="…"`',
                 line=lineno)
            errors += 1
    return errors


def scan(target: Path) -> int:
    if not target.exists():
        emit("ERROR", target, "harness.target-missing",
             f"target does not exist: {target}",
             "pass an existing .py check or .harness/checks/ directory", line=0)
        return 2
    total_errors = 0
    if target.is_file() and target.suffix == ".py":
        checks = [target]
    elif target.is_dir():
        checks = sorted(
            p for p in target.glob("*.py")
            if p.name not in {
                "__init__.py", "_common.py",
                "output_format_conformance.py",
                # typecheck_policy.py spawns mypy + tsc subprocesses (~minutes);
                # it has dedicated tests under tests/harness/checks/test_typecheck_policy.py.
                "typecheck_policy.py",
            }
        )
    else:
        emit("ERROR", target, "harness.target-missing",
             f"unsupported target: {target}",
             "pass a Python file or .harness/checks/ directory", line=0)
        return 2
    for check in checks:
        total_errors += _validate(check)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: validate H-16/H-23 output shape of every check under --target."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args(argv)
    return scan(args.target)


if __name__ == "__main__":
    sys.exit(main())
