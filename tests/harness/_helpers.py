"""Shared test helpers for harness checks.

Re-export common patterns so individual check tests stay short:
  assert_check_fires(rule_id, fixture_path) — runs the check and
    asserts it emits ≥ 1 ERROR matching that rule id.
  assert_check_silent(rule_id, fixture_path) — runs the check and
    asserts it produces zero output and exits 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness/checks"


def _run_check(rule_id: str, target: Path) -> tuple[int, str]:
    script = CHECKS_DIR / f"{rule_id}.py"
    if not script.exists():
        raise FileNotFoundError(f"no check at {script}")
    result = subprocess.run(
        [sys.executable, str(script), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def assert_check_fires(rule_id: str, fixture: Path) -> None:
    code, out = _run_check(rule_id, fixture)
    assert code != 0, (
        f"check `{rule_id}` should have failed on {fixture} but exited 0. "
        f"Output: {out}"
    )
    assert f"rule={rule_id}" in out, (
        f"check `{rule_id}` fired but didn't tag itself with rule={rule_id}: {out}"
    )
    assert "[ERROR]" in out, (
        f"check `{rule_id}` should emit at least one [ERROR] line: {out}"
    )
    assert "suggestion=" in out, (
        f"check `{rule_id}` violations must include `suggestion=` field (H-23). Got: {out}"
    )


def assert_check_silent(rule_id: str, fixture: Path) -> None:
    code, out = _run_check(rule_id, fixture)
    assert code == 0, (
        f"check `{rule_id}` should pass on {fixture} but exited {code}. Output: {out}"
    )
    assert out.strip() == "", (
        f"check `{rule_id}` produced output on a compliant fixture: {out}"
    )
