"""Task 2.6 — adversarial advocate/challenger with diverse evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from src.agents.critic_ensemble import (
    CriticEnsemble,
    CriticVerdict,
    EvidencePartitioner,
    JudgeAggregator,
    supports_finding_score,
)


# ── test doubles ─────────────────────────────────────────────────────────


@dataclass
class StubPin:
    claim: str
    source_agent: str = "log_agent"
    evidence_type: str = "log"


def _supporting_pins(n: int, finding_keyword: str) -> list[StubPin]:
    return [
        StubPin(claim=f"{finding_keyword} detail number {i} in service")
        for i in range(n)
    ]


def _neutral_pins(n: int) -> list[StubPin]:
    return [StubPin(claim=f"unrelated housekeeping entry {i}") for i in range(n)]


def _contradicting_pins(n: int) -> list[StubPin]:
    return [
        StubPin(claim=f"baseline nominal operating state reading {i}")
        for i in range(n)
    ]


class TapClient:
    """Records prompts; returns a canned verdict per call index."""

    def __init__(self, verdicts: list[str]):
        self._verdicts = list(verdicts)
        self.captured: list[str] = []

    async def chat(self, *, system, messages, model, temperature):
        self.captured.append(messages[0]["content"])
        if not self._verdicts:
            return json.dumps({"verdict": "insufficient_evidence", "reasoning": "drained"})
        return self._verdicts.pop(0)


def _verdict(v: str, reasoning: str = "ok") -> str:
    return json.dumps({"verdict": v, "reasoning": reasoning})


# ── supports_finding_score ────────────────────────────────────────────────


class TestSupportsFindingScore:
    def test_full_overlap_returns_1(self):
        assert supports_finding_score(StubPin(claim="oom killed payment service"), "oom killed payment") == 1.0

    def test_zero_overlap_returns_0(self):
        assert supports_finding_score(StubPin(claim="disk low on node"), "oom killed payment") == 0.0

    def test_partial_overlap_between_0_and_1(self):
        s = supports_finding_score(StubPin(claim="oom detected on worker"), "oom killed payment")
        assert 0.0 < s < 1.0

    def test_empty_claim_returns_0(self):
        assert supports_finding_score(StubPin(claim=""), "oom killed payment") == 0.0


# ── partitioner ───────────────────────────────────────────────────────────


class TestEvidencePartitioner:
    def test_advocate_and_challenger_subsets_differ(self):
        finding = "oom payment"
        pins = _supporting_pins(3, "oom payment") + _neutral_pins(4) + _contradicting_pins(3)
        advocate, challenger = EvidencePartitioner().partition(pins, finding, top_k=3)
        # size parity
        assert len(advocate) == len(challenger)
        # advocate got top-supporting pins
        advocate_claims = {p.claim for p in advocate}
        challenger_claims = {p.claim for p in challenger}
        # disjoint enough
        overlap = advocate_claims & challenger_claims
        assert len(overlap) / max(len(advocate_claims), 1) < 0.5

    def test_degenerate_pin_count_splits_in_half(self):
        finding = "a"
        pins = [StubPin(claim="a b c"), StubPin(claim="d e")]
        advocate, challenger = EvidencePartitioner().partition(pins, finding, top_k=3)
        assert len(advocate) == 1 and len(challenger) == 1


# ── ensemble: diverse subsets + rubber-stamp guard ────────────────────────


class TestEnsembleAdversarialContract:
    @pytest.mark.asyncio
    async def test_advocate_and_challenger_see_different_evidence_subsets(self):
        client = TapClient([_verdict("confirmed"), _verdict("challenged")])
        ensemble = CriticEnsemble(client=client, top_k=3)
        pins = _supporting_pins(3, "oom payment") + _neutral_pins(4) + _contradicting_pins(3)

        result = await ensemble.evaluate(
            finding={"claim": "oom payment"},
            evidence_pins=pins,
        )

        assert len(client.captured) == 2
        advocate_prompt, challenger_prompt = client.captured
        assert advocate_prompt != challenger_prompt
        # sanity: advocate prompt should be dominated by the finding's
        # keyword-echoing pins, challenger by the nominal/baseline pins
        assert "oom" in advocate_prompt.lower()
        assert "baseline" in challenger_prompt.lower()
        assert result.final_verdict == "needs_more_evidence"

    @pytest.mark.asyncio
    async def test_challenger_cannot_rubber_stamp_when_no_contradictions(self):
        # Every pin supports the finding strongly — the challenger's subset
        # has no below-threshold pins. Even if the LLM says "confirmed",
        # the ensemble must force insufficient_evidence.
        client = TapClient([_verdict("confirmed"), _verdict("confirmed")])
        ensemble = CriticEnsemble(client=client, top_k=2)
        all_confirmatory = [
            StubPin(claim="oom payment detail " + str(i)) for i in range(6)
        ]

        result = await ensemble.evaluate(
            finding={"claim": "oom payment"},
            evidence_pins=all_confirmatory,
        )

        assert result.challenger.verdict in ("insufficient_evidence", "challenged")

    @pytest.mark.asyncio
    async def test_both_confirmed_on_mixed_evidence_promotes_to_confirmed(self):
        client = TapClient([_verdict("confirmed"), _verdict("confirmed")])
        ensemble = CriticEnsemble(client=client, top_k=3)
        pins = _supporting_pins(3, "oom payment") + _neutral_pins(4) + _contradicting_pins(3)

        result = await ensemble.evaluate(
            finding={"claim": "oom payment"},
            evidence_pins=pins,
        )

        # Challenger is given contradicting pins, so the guard should NOT fire
        # and an honest "confirmed" from both is respected.
        assert result.final_verdict == "confirmed"

    @pytest.mark.asyncio
    async def test_both_challenged_promotes_to_challenged(self):
        client = TapClient([_verdict("challenged"), _verdict("challenged")])
        ensemble = CriticEnsemble(client=client, top_k=3)
        pins = _supporting_pins(3, "oom payment") + _neutral_pins(4) + _contradicting_pins(3)

        result = await ensemble.evaluate(
            finding={"claim": "oom payment"},
            evidence_pins=pins,
        )
        assert result.final_verdict == "challenged"


# ── judge aggregator (pure) ───────────────────────────────────────────────


class TestJudgeAggregator:
    def _adv(self, v):
        return CriticVerdict(role="advocate", verdict=v, reasoning="")

    def _chal(self, v):
        return CriticVerdict(role="challenger", verdict=v, reasoning="")

    def test_both_confirmed(self):
        assert JudgeAggregator().aggregate(self._adv("confirmed"), self._chal("confirmed")) == "confirmed"

    def test_both_challenged(self):
        assert JudgeAggregator().aggregate(self._adv("challenged"), self._chal("challenged")) == "challenged"

    def test_mixed_returns_needs_more_evidence(self):
        assert JudgeAggregator().aggregate(self._adv("confirmed"), self._chal("challenged")) == "needs_more_evidence"
        assert JudgeAggregator().aggregate(self._adv("challenged"), self._chal("confirmed")) == "needs_more_evidence"
        assert JudgeAggregator().aggregate(self._adv("confirmed"), self._chal("insufficient_evidence")) == "needs_more_evidence"
