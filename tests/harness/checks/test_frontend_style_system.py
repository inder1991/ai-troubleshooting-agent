"""H.1b.1 — frontend_style_system check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "frontend_style_system"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("imports_styled_components.tsx", "Q1.no-css-in-js", "frontend/src/components/Foo.tsx"),
        ("imports_extra_css.tsx", "Q1.no-extra-css-imports", "frontend/src/components/Foo.tsx"),
        ("inline_style_color.tsx", "Q1.no-inline-style-static", "frontend/src/components/Foo.tsx"),
        ("raw_classname_concat.tsx", "Q1.classname-needs-cn", "frontend/src/components/Foo.tsx"),
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
        ("uses_cn.tsx", "frontend/src/components/Foo.tsx"),
        ("dynamic_style_escape.tsx", "frontend/src/components/Bar.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
