#!/usr/bin/env python3
"""Generate baseline files for mypy and tsc.

Per Q19 beta — existing violations grandfathered into a baseline; new
violations block merge. Regenerating the baseline grows the snapshot
of allowed violations and requires an ADR (Q15) — except when
violations *shrink* (errors fixed), which is always allowed.

Invoked via `make harness-typecheck-baseline`."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = REPO_ROOT / ".harness/baselines"
MYPY_OUT = BASELINES_DIR / "mypy_baseline.json"
TSC_OUT = BASELINES_DIR / "tsc_baseline.json"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def collect_mypy() -> dict:
    """Walk mypy across the strict paths; collect violations."""
    if shutil.which("mypy") is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_version": "unavailable",
            "violations": [],
            "_note": "mypy not on PATH at baseline generation time",
        }
    code, out = _run(
        ["mypy", "--no-color-output", "--show-column-numbers", "--strict",
         "src/storage/", "src/learning/", "src/models/", "src/api/"],
        cwd=REPO_ROOT / "backend",
    )
    violations = []
    pattern = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+): error: (?P<msg>.+)$")
    for line in out.splitlines():
        if m := pattern.match(line):
            violations.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "message": m.group("msg"),
            })
    _, version_out = _run(["mypy", "--version"], cwd=REPO_ROOT)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": version_out.strip(),
        "violations": violations,
    }


def collect_tsc() -> dict:
    if shutil.which("npx") is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_version": "unavailable",
            "violations": [],
            "_note": "npx not on PATH",
        }
    code, out = _run(
        ["npx", "tsc", "--noEmit", "-p", "tsconfig.json"],
        cwd=REPO_ROOT / "frontend",
    )
    violations = []
    pattern = re.compile(r"^(?P<file>[^()]+)\((?P<line>\d+),(?P<col>\d+)\): error TS(?P<code>\d+): (?P<msg>.+)$")
    for line in out.splitlines():
        if m := pattern.match(line):
            violations.append({
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "code": int(m.group("code")),
                "message": m.group("msg"),
            })
    _, version_out = _run(["npx", "tsc", "--version"], cwd=REPO_ROOT / "frontend")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": version_out.strip(),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true",
                        help="Don't write; print summary and exit.")
    args = parser.parse_args(argv)

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    mypy_data = collect_mypy()
    tsc_data = collect_tsc()

    if not args.check_only:
        MYPY_OUT.write_text(json.dumps(mypy_data, indent=2, sort_keys=True) + "\n")
        TSC_OUT.write_text(json.dumps(tsc_data, indent=2, sort_keys=True) + "\n")

    print(f"mypy_baseline: {len(mypy_data['violations'])} violations")
    print(f"tsc_baseline:  {len(tsc_data['violations'])} violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
