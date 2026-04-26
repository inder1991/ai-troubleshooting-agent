"""H.1b.7 — conventions_policy check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "conventions_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("PascalCase.py", "Q18.python-snake-case", "backend/src/services/PascalCase.py"),
        ("kebab-case.py", "Q18.python-snake-case", "backend/src/services/kebab-case.py"),
        ("lowercase_component.tsx", "Q18.frontend-component-pascal-case", "frontend/src/components/lowercase.tsx"),
        ("relative_import.py", "Q18.no-relative-import-backend", "backend/src/services/foo.py"),
        ("dotdot_import.tsx", "Q18.no-dotdot-import-frontend", "frontend/src/components/Foo.tsx"),
        ("default_export.tsx", "Q18.no-default-export-in-components", "frontend/src/components/Foo.tsx"),
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
        ("snake_case_module.py", "backend/src/services/clean_module.py"),
        ("PascalCaseComponent.tsx", "frontend/src/components/CleanComponent.tsx"),
        ("named_exports.tsx", "frontend/src/components/Bar.tsx"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
