"""Task 4.5 — self-consistency 3-shot wrapper."""
from __future__ import annotations

import pytest

from src.agents.orchestration.self_consistency import (
    SelfConsistency,
    SingleRun,
    _seeded_shuffles,
)


class TestDeterministicShuffles:
    def test_same_seed_same_shuffles(self):
        agents = ["log_agent", "metrics_agent", "k8s_agent", "tracing_agent"]
        a = _seeded_shuffles(agents, n=3, seed="r1")
        b = _seeded_shuffles(agents, n=3, seed="r1")
        assert a == b

    def test_different_seed_different_shuffles(self):
        agents = ["log_agent", "metrics_agent", "k8s_agent", "tracing_agent"]
        a = _seeded_shuffles(agents, n=3, seed="r1")
        b = _seeded_shuffles(agents, n=3, seed="r2")
        assert a != b


class TestVoting:
    @pytest.mark.asyncio
    async def test_three_runs_with_same_winner_keep_confidence(self):
        async def fake_call(order):
            return SingleRun(winner="oom_cascade", confidence=0.82, agent_order=order)

        sc = SelfConsistency(n=3)
        out = await sc.run(agents=["a", "b", "c"], seed="r1", supervisor_call=fake_call)
        assert out.verdict == "consistent"
        assert out.final_winner == "oom_cascade"
        assert out.final_confidence == 0.82
        assert out.agreed_count == 3
        assert out.penalty_pct == 0

    @pytest.mark.asyncio
    async def test_majority_agreement_applies_20pct_penalty(self):
        # First two runs return oom_cascade, third returns deploy_regression.
        counter = {"n": 0}

        async def fake_call(order):
            counter["n"] += 1
            if counter["n"] <= 2:
                return SingleRun(winner="oom_cascade", confidence=0.80, agent_order=order)
            return SingleRun(winner="deploy_regression", confidence=0.60, agent_order=order)

        sc = SelfConsistency(n=3)
        out = await sc.run(agents=["a", "b", "c"], seed="r1", supervisor_call=fake_call)
        assert out.verdict == "majority"
        assert out.final_winner == "oom_cascade"
        # 0.80 * (1 - 0.20) = 0.64
        assert out.final_confidence == pytest.approx(0.64, abs=0.001)
        assert out.agreed_count == 2
        assert out.penalty_pct == 20

    @pytest.mark.asyncio
    async def test_no_majority_marks_inconclusive(self):
        winners = iter(["a_pattern", "b_pattern", "c_pattern"])

        async def fake_call(order):
            return SingleRun(winner=next(winners), confidence=0.80, agent_order=order)

        sc = SelfConsistency(n=3)
        out = await sc.run(agents=["x"], seed="r1", supervisor_call=fake_call)
        assert out.verdict == "inconclusive"
        assert out.final_winner is None
        assert out.final_confidence <= 0.30

    @pytest.mark.asyncio
    async def test_single_run_is_always_consistent(self):
        async def fake_call(order):
            return SingleRun(winner="oom", confidence=0.82, agent_order=order)

        sc = SelfConsistency(n=1)
        out = await sc.run(agents=["x"], seed="r1", supervisor_call=fake_call)
        assert out.verdict == "consistent"
        assert out.final_confidence == 0.82


class TestDeterminismEndToEnd:
    @pytest.mark.asyncio
    async def test_same_seed_same_result(self):
        calls = {"a": 0}

        async def fake_call(order):
            calls["a"] += 1
            return SingleRun(winner="oom", confidence=0.80, agent_order=order)

        sc1 = SelfConsistency(n=3)
        sc2 = SelfConsistency(n=3)
        out1 = await sc1.run(agents=["a", "b", "c"], seed="r1", supervisor_call=fake_call)
        out2 = await sc2.run(agents=["a", "b", "c"], seed="r1", supervisor_call=fake_call)
        assert out1.final_winner == out2.final_winner
        assert out1.final_confidence == out2.final_confidence


class TestValidation:
    def test_zero_or_negative_n_rejected(self):
        with pytest.raises(ValueError):
            SelfConsistency(n=0)
        with pytest.raises(ValueError):
            SelfConsistency(n=-1)
