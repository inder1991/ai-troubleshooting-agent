"""Sprint H.0a Story 6 — owners_present check enforces H-6 (owner: in front-matter)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/owners_present.py"
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def _run_check(target: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECK), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def test_check_exists() -> None:
    assert CHECK.is_file()


def test_fires_on_missing_owner() -> None:
    fixture = FIXTURES / "violation/owners_present/missing_owner.md"
    code, out = _run_check(fixture)
    assert code != 0
    assert "rule=owners_present" in out
    assert "suggestion=" in out


def test_silent_on_present_owner() -> None:
    fixture = FIXTURES / "compliant/owners_present/with_owner.md"
    code, out = _run_check(fixture)
    assert code == 0
    assert out.strip() == ""
