"""H.1c.2 — security_policy_b check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "security_policy_b"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("post_no_auth.py", "Q13.route-needs-auth"),
        ("post_no_rate_limit.py", "Q13.route-needs-rate-limit"),
        ("post_no_csrf.py", "Q13.route-needs-csrf"),
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
        target=FIXTURE_ROOT / "compliant" / "post_full_protection.py",
        pretend_path="backend/src/api/routes_v4.py",
    )
