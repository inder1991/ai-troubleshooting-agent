"""Q12 hard gate: agent runs must stay within budget.

assert_within_budget(workflow_id, snapshot) raises BudgetExceeded if
the snapshot violates the budget for that workflow. Workflow overrides
in .harness/performance_budgets.yaml; unknown workflows fall back to
default.

Note: this is the Q12 substrate helper. The existing
backend/src/agents/budget.py (no leading underscore) covers a different
concern (per-investigation token+time tracking via InvestigationBudget)
and is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
PERF_YAML = REPO_ROOT / ".harness/performance_budgets.yaml"


class BudgetExceeded(Exception):
    """Raised when an agent run exceeds its budget."""


@dataclass(frozen=True)
class BudgetSnapshot:
    tool_calls_used: int
    tokens_used: int
    wall_clock_s: float


@lru_cache(maxsize=1)
def _load_budgets() -> dict[str, dict[str, Any]]:
    """Load + cache the budget table. Reload by clearing the cache."""
    if not PERF_YAML.exists():
        return {"default": {"tool_calls_max": 20, "tokens_max": 20000, "wall_clock_max_s": 30}}
    data = yaml.safe_load(PERF_YAML.read_text())
    agent_budgets = data.get("hard", {}).get("agent_budgets", {})
    table = {"default": agent_budgets.get(
        "default",
        {"tool_calls_max": 20, "tokens_max": 20000, "wall_clock_max_s": 30},
    )}
    table.update(agent_budgets.get("overrides", {}) or {})
    return table


def assert_within_budget(workflow_id: str, snapshot: BudgetSnapshot) -> None:
    table = _load_budgets()
    budget = table.get(workflow_id, table["default"])
    breaches: list[str] = []
    if snapshot.tool_calls_used > budget["tool_calls_max"]:
        breaches.append(
            f"tool_calls: {snapshot.tool_calls_used} > {budget['tool_calls_max']}"
        )
    if snapshot.tokens_used > budget["tokens_max"]:
        breaches.append(
            f"tokens: {snapshot.tokens_used} > {budget['tokens_max']}"
        )
    if snapshot.wall_clock_s > budget["wall_clock_max_s"]:
        breaches.append(
            f"wall_clock: {snapshot.wall_clock_s:.1f}s > {budget['wall_clock_max_s']}s"
        )
    if breaches:
        raise BudgetExceeded(
            f"workflow `{workflow_id}` exceeded budget: " + "; ".join(breaches)
        )
