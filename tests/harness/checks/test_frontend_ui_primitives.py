"""H.1b.3 — frontend_ui_primitives check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "frontend_ui_primitives"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("bare_button.tsx", "Q4.no-bare-html-primitive", "frontend/src/components/Foo.tsx"),
        ("imports_mui.tsx", "Q4.no-third-party-ui-kit", "frontend/src/components/Foo.tsx"),
        ("anchor_with_onclick.tsx", "Q4.no-bare-html-primitive", "frontend/src/components/Foo.tsx"),
        ("ui_primitive_imports_service.tsx", "Q4.primitive-no-business-logic", "frontend/src/components/ui/button.tsx"),
        ("wrapper_reexport.tsx", "Q4.no-wrapper-reexport", "frontend/src/components/Wrappers.tsx"),
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
        ("uses_local_button.tsx", "frontend/src/components/Foo.tsx"),
        ("clean_ui_primitive.tsx", "frontend/src/components/ui/button.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
