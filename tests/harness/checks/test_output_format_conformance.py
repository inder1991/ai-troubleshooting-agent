"""H.1b.8 — output_format_conformance check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "output_format_conformance"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "bad_output_check.py",
        expected_rule="H16.output-format-violation",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "good_output_check.py",
    )
