"""H.1a.6 — performance_budgets check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "performance_budgets"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK
BUDGETS = FIXTURE_ROOT / "_test_budgets.yaml"


@pytest.mark.parametrize(
    "fixture_name,expected_rule,extra_args",
    [
        ("agent_missing_cost_hint.yaml", "Q12.agent-cost-hint-required", ["--budgets", str(BUDGETS)]),
        ("agent_exceeds_budget.yaml", "Q12.agent-budget-exceeded", ["--budgets", str(BUDGETS)]),
        ("gateway_no_timed_query.py", "Q12.gateway-needs-timed-query", ["--budgets", str(BUDGETS), "--pretend-path", "backend/src/storage/gateway.py"]),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, extra_args: list[str]) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        extra_args=extra_args,
    )


@pytest.mark.parametrize(
    "fixture_name,extra_args",
    [
        ("agent_within_budget.yaml", ["--budgets", str(BUDGETS)]),
        ("gateway_with_timed_query.py", ["--budgets", str(BUDGETS), "--pretend-path", "backend/src/storage/gateway.py"]),
    ],
)
def test_compliant_silent(fixture_name: str, extra_args: list[str]) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        extra_args=extra_args,
    )
