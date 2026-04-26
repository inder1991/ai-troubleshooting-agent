"""Sprint H.0b Story 5 — assert_within_budget helper (Q12 agent budgets).

Note: separate from the existing tests/agents/test_budget.py which covers
src.agents.budget.InvestigationBudget. This Q12 helper lives at
src.agents._budget (leading underscore) and reads .harness/performance_budgets.yaml.
"""

from __future__ import annotations

import pytest


def test_assert_within_budget_passes_when_under() -> None:
    from src.agents._budget import assert_within_budget, BudgetSnapshot

    snapshot = BudgetSnapshot(tool_calls_used=10, tokens_used=5000, wall_clock_s=15.0)
    # Should not raise
    assert_within_budget("default", snapshot)


def test_assert_within_budget_raises_when_over() -> None:
    from src.agents._budget import assert_within_budget, BudgetSnapshot, BudgetExceeded

    snapshot = BudgetSnapshot(tool_calls_used=25, tokens_used=21000, wall_clock_s=35.0)
    with pytest.raises(BudgetExceeded):
        assert_within_budget("default", snapshot)


def test_assert_within_budget_uses_workflow_override_if_present() -> None:
    """Per Q12: overrides via YAML; unknown workflow falls back to default."""
    from src.agents._budget import assert_within_budget, BudgetSnapshot, BudgetExceeded

    snapshot = BudgetSnapshot(tool_calls_used=30, tokens_used=10000, wall_clock_s=20.0)
    with pytest.raises(BudgetExceeded):
        assert_within_budget("nonexistent_workflow", snapshot)
