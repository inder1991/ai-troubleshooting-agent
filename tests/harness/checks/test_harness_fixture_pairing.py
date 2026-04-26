"""H.1d.3 — harness_fixture_pairing check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "harness_fixture_pairing"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_violation_fires() -> None:
    root = FIXTURE_ROOT / "violation" / "missing_pairing"
    assert_check_fires(
        check_name=CHECK,
        target=root,
        expected_rule="H24.fixture-pairing-missing",
        extra_args=[
            "--checks-dir", str(root / "checks"),
            "--fixtures-dir", str(root / "fixtures"),
        ],
    )


def test_compliant_silent() -> None:
    root = FIXTURE_ROOT / "compliant" / "has_pairing"
    assert_check_silent(
        check_name=CHECK,
        target=root,
        extra_args=[
            "--checks-dir", str(root / "checks"),
            "--fixtures-dir", str(root / "fixtures"),
        ],
    )
