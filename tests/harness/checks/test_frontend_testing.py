"""H.1b.4 — frontend_testing check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "frontend_testing"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("api_module_no_test.ts", "Q5.api-module-needs-test", "frontend/src/services/api/orphan.ts"),
        ("hook_no_test.ts", "Q5.hook-needs-test", "frontend/src/hooks/useOrphan.ts"),
        ("test_imports_jest.test.ts", "Q5.no-jest-or-mocha", "frontend/src/foo.test.ts"),
        ("test_imports_playwright.test.ts", "Q5.no-playwright-in-unit", "frontend/src/foo.test.ts"),
        ("e2e_imports_vitest.spec.ts", "Q5.e2e-must-use-playwright", "frontend/e2e/login.spec.ts"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


def test_compliant_directory_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant",
        pretend_path="frontend/src/services/api/foo.ts",
    )
