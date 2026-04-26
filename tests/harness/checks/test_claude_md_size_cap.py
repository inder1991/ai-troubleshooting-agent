"""Sprint H.0a Story 6 — claude_md_size_cap check enforces H-1 (root ≤ 70 lines)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/claude_md_size_cap.py"
FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def _run_check(target: Path) -> tuple[int, str]:
    """Invoke the check with --target <fixture> and return (exit_code, stdout)."""
    result = subprocess.run(
        [sys.executable, str(CHECK), "--target", str(target)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode, result.stdout


def test_check_exists() -> None:
    assert CHECK.is_file()


def test_fires_on_oversized_root() -> None:
    fixture = FIXTURES / "violation/claude_md_size_cap/oversized_root.md"
    code, out = _run_check(fixture)
    assert code != 0, f"check should fail on oversized root; got exit 0 with {out}"
    assert "[ERROR]" in out
    assert "rule=claude_md_size_cap" in out
    assert "suggestion=" in out


def test_silent_on_compliant_root() -> None:
    fixture = FIXTURES / "compliant/claude_md_size_cap/normal_root.md"
    code, out = _run_check(fixture)
    assert code == 0, f"check should pass on compliant root; got exit {code} with {out}"
    assert out.strip() == ""
