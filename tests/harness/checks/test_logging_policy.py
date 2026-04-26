"""H.1c.4 — logging_policy check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "logging_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("print_in_spine.py", "Q16.no-print-in-spine"),
        ("bare_except_silent.py", "Q16.bare-except-no-log"),
        ("fstring_in_log.py", "Q16.f-string-in-log"),
        ("secret_in_log_literal.py", "Q16.secret-shaped-log-literal"),
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
        target=FIXTURE_ROOT / "compliant" / "proper_logging.py",
        pretend_path="backend/src/api/routes_v4.py",
    )
