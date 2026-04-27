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

import argparse
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

# B5 hardening — import the shared regex from _common so we never drift.
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
from _common import ERROR_LINE_PATTERN as LINE_RE, normalize_path  # noqa: E402


def _read_existing_count(out_path: Path) -> int:
    """Return the number of entries in the existing baseline, or 0 if missing/unparseable.

    B19 (v1.2.1): if the previous baseline is corrupt, we used to silently
    return 0 — which then made the growth check (`old_count > 0`) skip the
    warning and overwrite the corrupt file with whatever the fresh run
    produced. Now we WARN to stderr so the user notices the corruption.
    """
    if not out_path.exists():
        return 0
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"[WARN] {out_path.relative_to(REPO_ROOT)}: previous baseline "
            f"unparseable ({exc}); growth check will be skipped",
            file=sys.stderr,
        )
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

    # B25 (v1.2.1): if the check produced ZERO findings AND exited
    # non-zero, treat that as "the check itself misbehaved" and DO NOT
    # overwrite the previous baseline with `[]`. This guards against
    # silent baseline reset when a check has a bug that prevents it
    # from emitting anything (vs. genuinely finding nothing). A clean
    # zero-finding run with rc=0 is still treated as authoritative.
    if not findings and result.returncode != 0 and old_count > 0:
        print(
            f"[WARN] {check.name}: check exited {result.returncode} with zero "
            "parseable findings; refusing to overwrite previous baseline. "
            "Investigate the check before re-running.",
            file=sys.stderr,
        )
        if backup.exists():
            backup.rename(out_path)
        return 1

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


def _migrate_one(out_path: Path) -> tuple[int, int, int]:
    """Rewrite one baseline JSON in place, normalizing every entry's `file`
    field to repo-relative POSIX form.

    S7 (B1 follow-on): legacy v1.0.x baselines store absolute paths from
    whatever machine snapshotted them. This in-place migration converts
    them to relative paths WITHOUT re-running the underlying check (which
    would also pick up new findings — a separate decision).

    Returns (kept, dropped_foreign, total_in).
    """
    if not out_path.exists():
        return (0, 0, 0)
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] {out_path.name}: unparseable, skipping ({exc})", file=sys.stderr)
        return (0, 0, 0)
    if not isinstance(data, list):
        print(f"[WARN] {out_path.name}: not a JSON array, skipping", file=sys.stderr)
        return (0, 0, 0)

    repo_root_str = str(REPO_ROOT.resolve())
    kept: list[dict] = []
    dropped = 0
    seen: set[tuple[str, int, str]] = set()
    for entry in data:
        if not (isinstance(entry, dict) and {"file", "line", "rule"} <= set(entry.keys())):
            continue
        raw = str(entry["file"])
        # Foreign-machine detection mirrors load_baseline() exactly.
        if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
            if not raw.startswith(repo_root_str + "/") and not raw.startswith(repo_root_str + "\\"):
                try:
                    Path(raw).resolve().relative_to(REPO_ROOT.resolve())
                except (ValueError, OSError):
                    dropped += 1
                    continue
        normalized = normalize_path(raw)
        key = (normalized, int(entry["line"]), str(entry["rule"]))
        if key in seen:
            continue
        seen.add(key)
        new_entry = dict(entry)
        new_entry["file"] = normalized
        kept.append(new_entry)

    kept.sort(key=lambda e: (e["file"], e["line"], e["rule"]))

    # Atomic write — same pattern as _refresh_one.
    new_path = out_path.with_suffix(out_path.suffix + ".new")
    new_path.write_text(
        json.dumps(kept, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    new_path.replace(out_path)
    return (len(kept), dropped, len(data))


def _migrate_all() -> int:
    """Walk every baseline JSON; normalize paths in place.

    Exits 0 on success; 1 if any baseline was dropped foreign entries
    (caller may want to review the diff before committing).
    """
    if not BASELINES_DIR.is_dir():
        print("[INFO] no baselines directory; nothing to migrate")
        return 0
    total_kept = 0
    total_dropped = 0
    files_touched = 0
    for path in sorted(BASELINES_DIR.glob("*_baseline.json")):
        kept, dropped, total = _migrate_one(path)
        if total == 0:
            continue
        files_touched += 1
        total_kept += kept
        total_dropped += dropped
        rel = path.relative_to(REPO_ROOT)
        if dropped:
            print(
                f"[WARN] {rel}: kept {kept}, dropped {dropped} foreign-machine entries "
                f"(of {total} total)"
            )
        else:
            print(f"[INFO] {rel}: {kept} entries (paths normalized)")
    print(
        f"[INFO] migration complete: {files_touched} baselines, "
        f"{total_kept} entries kept, {total_dropped} foreign entries dropped"
    )
    return 1 if total_dropped else 0


def main(argv: list[str] | None = None) -> int:
    """Walk .harness/checks/, refresh baseline for each non-exempt check.

    With `--migrate-paths`, instead of re-running checks, walk every
    baseline JSON and convert absolute file paths to repo-relative POSIX
    form (S7 — supports v1.0.x → v1.1.0 baseline migration without picking
    up new findings).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrate-paths",
        action="store_true",
        help="In-place normalize every baseline's `file` field to repo-relative POSIX. "
             "Drops entries whose absolute paths point outside this repo.",
    )
    args = parser.parse_args(argv)

    if args.migrate_paths:
        return _migrate_all()

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
