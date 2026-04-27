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


def _read_existing_count(out_path: Path) -> int:
    """Return the number of entries in the existing baseline, or 0 if missing/unparseable."""
    if not out_path.exists():
        return 0
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    return len(data) if isinstance(data, list) else 0


def _refresh_one(check: Path) -> int:
    """Run check fresh (no baseline filter), parse ERROR lines, write baseline.

    Atomicity (#13): we always write to a sibling .new file first, then
    atomically rename onto the canonical baseline. A mid-run crash leaves
    the previous baseline intact instead of a half-written file.

    Growth warning (#12): if the new baseline has MORE entries than the old
    one, emit a [WARN] rather than silently widening. Q19 only catches growth
    in mypy/tsc baselines via git-diff; this catches every per-rule baseline.
    """
    out_path = BASELINES_DIR / f"{check.stem}_baseline.json"
    new_path = out_path.with_suffix(out_path.suffix + ".new")
    backup = out_path.with_suffix(out_path.suffix + ".bak")
    old_count = _read_existing_count(out_path)

    # Move existing baseline to .bak so the check sees no filter for this run.
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

    # #13 — atomic write: stage in .new, then rename onto out_path.
    new_path.write_text(
        json.dumps(findings, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    new_path.replace(out_path)
    if backup.exists():
        backup.unlink()

    # #12 — growth warning. Skip if old baseline didn't exist (first-time
    # snapshot is by definition growth and shouldn't warn).
    new_count = len(findings)
    if old_count > 0 and new_count > old_count:
        delta = new_count - old_count
        print(
            f"[WARN] {out_path.relative_to(REPO_ROOT)}: baseline grew "
            f"{old_count} → {new_count} (+{delta}). Investigate before committing — "
            f"a check bug can silently widen baselines.",
            file=sys.stderr,
        )

    print(f"[INFO] {out_path.relative_to(REPO_ROOT)}: {new_count} entries")
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
