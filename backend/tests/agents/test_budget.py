"""Task 3.1 — per-investigation budget."""
from __future__ import annotations

import asyncio

import pytest

from src.agents.budget import (
    BudgetExceeded,
    InvestigationBudget,
    price_per_call,
)


class TestToolCallBudget:
    @pytest.mark.asyncio
    async def test_budget_blocks_after_limit_exceeded(self):
        b = InvestigationBudget(max_tool_calls=3)
        await b.charge_tool_call("logs.search")
        await b.charge_tool_call("metrics.query")
        await b.charge_tool_call("k8s.list_pods")
        with pytest.raises(BudgetExceeded):
            await b.charge_tool_call("logs.search")

    @pytest.mark.asyncio
    async def test_snapshot_after_charges(self):
        b = InvestigationBudget(max_tool_calls=10)
        await b.charge_tool_call("logs.search")
        await b.charge_tool_call("logs.search")
        await b.charge_tool_call("metrics.query")
        s = b.snapshot()
        assert s["tool_calls"] == 3
        assert s["tool_calls_remaining"] == 7
        assert s["by_tool"] == {"logs.search": 2, "metrics.query": 1}

    @pytest.mark.asyncio
    async def test_concurrent_charges_are_atomic(self):
        """100 concurrent charges must produce tool_calls == 100 exactly."""
        b = InvestigationBudget(max_tool_calls=1000)
        await asyncio.gather(*(b.charge_tool_call("t") for _ in range(100)))
        assert b.snapshot()["tool_calls"] == 100


class TestLLMBudget:
    @pytest.mark.asyncio
    async def test_llm_charge_accumulates_usd(self):
        b = InvestigationBudget(max_tool_calls=100, max_llm_usd=10.0)
        cost = await b.charge_llm(
            input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6"
        )
        # sonnet-4-6: $0.003/1k input + $0.015/1k output
        # 1k*0.003 + 0.5k*0.015 = 0.003 + 0.0075 = 0.0105
        assert cost == pytest.approx(0.0105, abs=1e-6)
        assert b.snapshot()["llm_usd"] == pytest.approx(0.0105, abs=1e-6)

    @pytest.mark.asyncio
    async def test_llm_budget_rejects_before_mutation(self):
        b = InvestigationBudget(max_tool_calls=100, max_llm_usd=0.005)
        with pytest.raises(BudgetExceeded):
            await b.charge_llm(
                input_tokens=10_000, output_tokens=10_000, model="claude-opus-4-7"
            )
        # nothing was applied because the cap would have been exceeded
        assert b.snapshot()["llm_usd"] == 0.0
        assert b.snapshot()["llm_calls"] == 0

    @pytest.mark.asyncio
    async def test_unknown_model_uses_conservative_price(self):
        b = InvestigationBudget(max_tool_calls=100, max_llm_usd=10.0)
        cost = await b.charge_llm(
            input_tokens=1000, output_tokens=1000, model="some-new-model"
        )
        # Conservative fallback: opus pricing — $0.015 + $0.075 = $0.090 / 1k
        assert cost == pytest.approx(0.090, abs=1e-6)

    def test_price_table_is_deterministic(self):
        a = price_per_call("claude-opus-4-7", 1000, 500)
        b = price_per_call("claude-opus-4-7", 1000, 500)
        assert a == b


class TestFormatting:
    @pytest.mark.asyncio
    async def test_format_for_prompt_matches_schema(self):
        b = InvestigationBudget(max_tool_calls=50, max_llm_usd=1.0)
        await b.charge_tool_call("t")
        await b.charge_llm(100, 100, "claude-sonnet-4-6")
        line = b.format_for_prompt()
        assert "Budget remaining:" in line
        assert "49 calls" in line
        assert "$" in line


class TestValidation:
    def test_zero_or_negative_budgets_rejected(self):
        with pytest.raises(ValueError):
            InvestigationBudget(max_tool_calls=0)
        with pytest.raises(ValueError):
            InvestigationBudget(max_llm_usd=0)
        with pytest.raises(ValueError):
            InvestigationBudget(max_tool_calls=-1)
