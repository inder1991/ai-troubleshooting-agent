"""H.1a.5 — dependency_policy check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "dependency_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK
POLICY = FIXTURE_ROOT / "_test_dependencies.yaml"


@pytest.mark.parametrize(
    "fixture_name,expected_rule,extra_args",
    [
        ("pyproject_unlisted.toml", "Q11.python-unlisted", ["--policy", str(POLICY)]),
        ("package_unlisted.json", "Q11.npm-unlisted", ["--policy", str(POLICY)]),
        ("spine_imports_unlisted.py", "Q11.spine-import-unlisted", ["--policy", str(POLICY), "--pretend-path", "backend/src/api/routes_v4.py"]),
        ("blacklisted_dep.toml", "Q11.blacklisted", ["--policy", str(POLICY)]),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, extra_args: list[str]) -> None:
    # spine_imports_* needs pretend_path passed in extra_args (helper de-dups)
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        extra_args=extra_args,
    )


@pytest.mark.parametrize(
    "fixture_name,extra_args",
    [
        ("pyproject_clean.toml", ["--policy", str(POLICY)]),
        ("package_clean.json", ["--policy", str(POLICY)]),
        ("spine_imports_clean.py", ["--policy", str(POLICY), "--pretend-path", "backend/src/api/routes_v4.py"]),
    ],
)
def test_compliant_silent(fixture_name: str, extra_args: list[str]) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        extra_args=extra_args,
    )
