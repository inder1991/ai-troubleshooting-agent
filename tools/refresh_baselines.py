#!/usr/bin/env python3
"""Regenerate every .harness/baselines/<rule>_baseline.json by running each
check, parsing its [ERROR] lines, and writing canonical sorted JSON.

Called by `make harness-baseline-refresh`. Use sparingly — every re-baseline
requires an ADR (enforced by Q15.adr-required-on-change in H.1c.3 and
Q19.baseline-grew-without-adr in H.1d.1). Output is deterministic
(sort_keys=True, indent=2, trailing newline) so a clean re-run produces a
byte-identical file.

Skipped: substrate / self-test checks that have no per-finding baseline.

H-25:
  Missing input    — exit 0 if no checks dir (silent no-op).
  Malformed input  — checks that crash → printed to stderr; baseline left untouched.
  Upstream failed  — n/a (we drive the checks ourselves).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKS_DIR = REPO_ROOT / ".harness" / "checks"
BASELINES_DIR = REPO_ROOT / ".harness" / "baselines"

EXEMPT_NAMES = {
    "_common.py", "__init__.py",
    "output_format_conformance.py",
    "harness_rule_coverage.py",
    "harness_fixture_pairing.py",
    "harness_policy_schema.py",
    "typecheck_policy.py",
}

LINE_RE = re.compile(
    r'^\[ERROR\]\s+file=(?P<file>\S+?):(?P<line>\d+)\s+rule=(?P<rule>\S+)'
)


def _refresh_one(check: Path) -> int:
    """Run check fresh (no baseline filter), parse ERROR lines, write baseline."""
    out_path = BASELINES_DIR / f"{check.stem}_baseline.json"
    # Backup existing baseline so the check sees no filter for this run.
    backup = out_path.with_suffix(out_path.suffix + ".bak")
    if out_path.exists():
        out_path.rename(backup)
    try:
        result = subprocess.run(
            [sys.executable, str(check)],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"[WARN] {check.name} crashed: {exc}", file=sys.stderr)
        if backup.exists():
            backup.rename(out_path)
        return 1

    seen: set[tuple[str, int, str]] = set()
    findings: list[dict] = []
    for line in result.stdout.splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        file_str = m.group("file")
        line_int = int(m.group("line"))
        rule_str = m.group("rule")
        key = (file_str, line_int, rule_str)
        if key in seen:
            continue
        seen.add(key)
        findings.append({"file": file_str, "line": line_int, "rule": rule_str})

    findings.sort(key=lambda e: (e["file"], e["line"], e["rule"]))
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(findings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if backup.exists():
        backup.unlink()
    print(f"[INFO] {out_path.relative_to(REPO_ROOT)}: {len(findings)} entries")
    return 0


def main() -> int:
    """Walk .harness/checks/, refresh baseline for each non-exempt check."""
    if not CHECKS_DIR.is_dir():
        return 0
    rc = 0
    for check in sorted(CHECKS_DIR.glob("*.py")):
        if check.name in EXEMPT_NAMES:
            continue
        rc |= _refresh_one(check)
    return rc


if __name__ == "__main__":
    sys.exit(main())
