"""Sprint H.0a Story 6 — claude_md_size_cap (H-1)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def test_check_exists() -> None:
    assert (REPO_ROOT / ".harness/checks/claude_md_size_cap.py").is_file()


def test_fires_on_oversized_root() -> None:
    assert_check_fires(
        "claude_md_size_cap",
        FIXTURES / "violation/claude_md_size_cap/oversized_root.md",
    )


def test_silent_on_compliant_root() -> None:
    assert_check_silent(
        "claude_md_size_cap",
        FIXTURES / "compliant/claude_md_size_cap/normal_root.md",
    )
