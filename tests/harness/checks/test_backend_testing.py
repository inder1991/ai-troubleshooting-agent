"""H.1a.3 — backend_testing check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "backend_testing"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("learning_module_no_hypothesis_test.py", "Q9.learning-needs-hypothesis", "backend/src/learning/calibrator.py"),
        ("test_uses_real_openai.py", "Q9.no-live-llm", "backend/tests/test_routes.py"),
        ("extract_function_no_hypothesis.py", "Q9.extractor-needs-hypothesis", "backend/src/agents/log_agent.py"),
        ("test_imports_openai.py", "Q9.no-live-llm", "backend/tests/test_call.py"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_dir,pretend_path",
    [
        # Test-pair compliance is checked at the directory level: learning_module.py
        # has a sibling test_learning_module.py that imports hypothesis.
        ("compliant", "backend/src/learning/calibrator.py"),
    ],
)
def test_compliant_directory_silent(fixture_dir: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / fixture_dir,
        pretend_path=pretend_path,
    )
