"""H.1b.6 — accessibility_policy check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "accessibility_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("img_no_alt.tsx", "Q14.img-needs-alt", "frontend/src/components/Foo.tsx"),
        ("button_no_name.tsx", "Q14.button-needs-accessible-name", "frontend/src/components/Foo.tsx"),
        ("positive_tabindex.tsx", "Q14.no-positive-tabindex", "frontend/src/components/Foo.tsx"),
        ("missing_axe_test.tsx", "Q14.primitive-needs-axe-test", "frontend/src/components/ui/badge.test.tsx"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("img_with_alt.tsx", "frontend/src/components/Foo.tsx"),
        ("button_with_label.tsx", "frontend/src/components/Foo.tsx"),
        ("primitive_with_axe.test.tsx", "frontend/src/components/ui/button.test.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
