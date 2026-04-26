"""Sprint H.0a Story 6 — owners_present (H-6)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

FIXTURES = REPO_ROOT / "tests/harness/fixtures"


def test_check_exists() -> None:
    assert (REPO_ROOT / ".harness/checks/owners_present.py").is_file()


def test_fires_on_missing_owner() -> None:
    assert_check_fires(
        "owners_present",
        FIXTURES / "violation/owners_present/missing_owner.md",
    )


def test_silent_on_present_owner() -> None:
    assert_check_silent(
        "owners_present",
        FIXTURES / "compliant/owners_present/with_owner.md",
    )
