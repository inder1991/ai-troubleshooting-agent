"""H.1c.5 — error_handling_policy check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "error_handling_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("pass_in_except.py", "Q17.no-pass-in-except"),
        ("reraise_without_from.py", "Q17.reraise-without-from"),
        ("generic_exception_raised.py", "Q17.generic-exception-raised"),
        ("http_exception_no_detail.py", "Q17.http-exception-needs-detail"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path="backend/src/api/routes_v4.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "proper_error_handling.py",
        pretend_path="backend/src/api/routes_v4.py",
    )
