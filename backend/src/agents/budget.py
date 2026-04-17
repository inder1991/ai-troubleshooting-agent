"""Per-investigation budget — tool calls and LLM spend.

A single ``InvestigationBudget`` instance is attached to a run and consulted
before every tool call / LLM request. When exhausted, the next ``charge_*``
raises ``BudgetExceeded`` so the supervisor can stop cleanly rather than
silently burning through the user's spend.

Cost table for LLM calls is a static map keyed by model. Prices in USD per
1K tokens. Updated when Anthropic's published pricing changes — keeping it
in code (not config) means the diff is auditable.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    """Raised when an investigation runs out of tool calls or LLM budget."""


# Static price table, USD per 1K tokens. Keep keys as published model IDs.
# See Anthropic pricing: https://www.anthropic.com/pricing (2026-04 snapshot).
_MODEL_PRICES_USD_PER_1K: dict[str, tuple[float, float]] = {
    # (input_price, output_price)
    "claude-opus-4-7": (0.015, 0.075),
    "claude-opus-4-6": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-sonnet-4-20250514": (0.003, 0.015),
    "claude-haiku-4-5": (0.001, 0.005),
    "claude-haiku-4-5-20251001": (0.001, 0.005),
}

# Price assumed when a model isn't in the table. Set high on purpose — a
# bug that swaps to an unknown model gets caught by the budget, not by the
# invoice.
_UNKNOWN_MODEL_PRICE: tuple[float, float] = (0.015, 0.075)


def price_per_call(model: str, input_tokens: int, output_tokens: int) -> float:
    """Deterministic USD cost for a single LLM call."""
    in_rate, out_rate = _MODEL_PRICES_USD_PER_1K.get(model, _UNKNOWN_MODEL_PRICE)
    return (input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate


@dataclass
class _Counters:
    """Private mutable state guarded by the lock in InvestigationBudget."""

    tool_calls: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_usd: float = 0.0
    by_tool: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, int] = field(default_factory=dict)


class InvestigationBudget:
    """Atomic counters for tool calls and LLM spend over one investigation."""

    def __init__(
        self,
        *,
        max_tool_calls: int = 100,
        max_llm_usd: float = 1.00,
    ) -> None:
        if max_tool_calls <= 0:
            raise ValueError("max_tool_calls must be positive")
        if max_llm_usd <= 0:
            raise ValueError("max_llm_usd must be positive")
        self._max_tool_calls = max_tool_calls
        self._max_llm_usd = max_llm_usd
        self._lock = asyncio.Lock()
        self._counters = _Counters()

    # ── Budget checks ─────────────────────────────────────────────────

    async def charge_tool_call(self, tool_name: str) -> None:
        """Count one tool call. Raises BudgetExceeded when the cap is reached."""
        async with self._lock:
            if self._counters.tool_calls >= self._max_tool_calls:
                raise BudgetExceeded(
                    f"tool_call_budget_exhausted: "
                    f"{self._counters.tool_calls}/{self._max_tool_calls} "
                    f"(attempted tool={tool_name!r})"
                )
            self._counters.tool_calls += 1
            self._counters.by_tool[tool_name] = (
                self._counters.by_tool.get(tool_name, 0) + 1
            )

    async def charge_llm(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Charge an LLM call by token count. Returns the USD cost added.

        The call is rejected BEFORE mutation if it would push the total spend
        over the cap — we don't want a "you owe $1.15" after the fact.
        """
        cost = price_per_call(model, input_tokens, output_tokens)
        async with self._lock:
            projected = self._counters.llm_usd + cost
            if projected > self._max_llm_usd:
                raise BudgetExceeded(
                    f"llm_budget_exhausted: "
                    f"${self._counters.llm_usd:.4f} + ${cost:.4f} "
                    f"= ${projected:.4f} > ${self._max_llm_usd:.2f} "
                    f"(model={model!r})"
                )
            self._counters.llm_calls += 1
            self._counters.input_tokens += input_tokens
            self._counters.output_tokens += output_tokens
            self._counters.llm_usd = projected
            self._counters.by_model[model] = (
                self._counters.by_model.get(model, 0) + 1
            )
            return cost

    # ── Introspection ────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Non-locking snapshot for logging / status reporting.

        Reads are on single Python ops so this is safe without the lock;
        tests that assert on counters post-hoc use this.
        """
        c = self._counters
        return {
            "tool_calls": c.tool_calls,
            "tool_calls_max": self._max_tool_calls,
            "tool_calls_remaining": max(self._max_tool_calls - c.tool_calls, 0),
            "llm_calls": c.llm_calls,
            "llm_usd": round(c.llm_usd, 6),
            "llm_usd_max": self._max_llm_usd,
            "llm_usd_remaining": round(max(self._max_llm_usd - c.llm_usd, 0.0), 6),
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "by_tool": dict(c.by_tool),
            "by_model": dict(c.by_model),
        }

    def format_for_prompt(self) -> str:
        """Human-readable budget line for inclusion in agent system prompts."""
        s = self.snapshot()
        return (
            f"Budget remaining: {s['tool_calls_remaining']} calls / "
            f"${s['llm_usd_remaining']:.2f}"
        )
