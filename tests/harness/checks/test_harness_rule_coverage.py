"""H.1d.2 — harness_rule_coverage check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "harness_rule_coverage"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_violation_fires() -> None:
    fixture = FIXTURE_ROOT / "violation" / "missing_rule_check"
    assert_check_fires(
        check_name=CHECK,
        target=fixture,
        expected_rule="H21.rule-not-covered",
        extra_args=[
            "--plans", str(fixture / "plan.md"),
            "--exemptions", str(fixture / "exemptions.yaml"),
            "--checks-dir", str(fixture),
        ],
    )


def test_compliant_silent() -> None:
    fixture = FIXTURE_ROOT / "compliant" / "all_covered"
    assert_check_silent(
        check_name=CHECK,
        target=fixture,
        extra_args=[
            "--plans", str(fixture / "plan.md"),
            "--exemptions", str(fixture / "exemptions.yaml"),
            "--checks-dir", str(fixture),
        ],
    )
