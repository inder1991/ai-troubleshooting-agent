"""Task 2.7 — CriticRetriever pulls independent evidence from cross-source tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from src.agents.critic_retriever import (
    CriticRetriever,
    RetrievedPin,
    _keywords_from_claim,
)


class FakeTools:
    def __init__(self):
        self._responses: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, dict]] = []

    def set_response(self, tool_name: str, rows: list[dict]) -> None:
        self._responses[tool_name] = rows

    async def call(self, tool_name: str, *, params: dict):
        self.calls.append((tool_name, params))
        return self._responses.get(tool_name, [])


@dataclass
class FakeFinding:
    claim: str
    source_agent: str
    source_tool: str
    timestamp: datetime
    originating_tool: str = ""  # test helper; not read by retriever

    def __post_init__(self):
        self.originating_tool = self.source_tool


class TestKeywordExtraction:
    def test_short_tokens_dropped(self):
        # 'OOM' (3), 'in' (2), 'pod' (3), 'x' (1) all below the >=4 threshold
        assert _keywords_from_claim("OOM in pod x payment") == ["payment"]

    def test_dedupes_preserves_order(self):
        kw = _keywords_from_claim("payment OOMKilled payment service payment")
        assert kw == ["payment", "oomkilled", "service"]

    def test_limit_cap(self):
        kw = _keywords_from_claim(
            "alpha beta gamma delta epsilon zeta eta theta", limit=3
        )
        assert kw == ["alpha", "beta", "gamma"]


class TestCriticRetriever:
    @pytest.mark.asyncio
    async def test_retriever_pulls_independent_evidence_for_finding(self):
        tools = FakeTools()
        tools.set_response(
            "metrics.query",
            [
                {
                    "@timestamp": "2026-04-17T14:30:00+00:00",
                    "message": "cpu above 95% for 5m",
                }
            ],
        )
        tools.set_response(
            "k8s.events",
            [
                {
                    "@timestamp": "2026-04-17T14:30:05+00:00",
                    "message": "OOMKilled: payment-api-0",
                }
            ],
        )

        finding = FakeFinding(
            claim="payment-api OOM at 14:30",
            source_agent="log_agent",
            source_tool="logs.search",
            timestamp=datetime.fromisoformat("2026-04-17T14:30:00+00:00"),
        )

        pins = await CriticRetriever(tools=tools).fetch_independent_evidence(finding)

        assert any("OOMKilled" in p.raw_snippet for p in pins)
        # Must NOT have queried the originating tool
        assert all(p.source_tool != finding.source_tool for p in pins)
        # Must have queried the cross-source tools
        queried = {name for name, _ in tools.calls}
        assert queried == {"metrics.query", "k8s.events"}

    @pytest.mark.asyncio
    async def test_unknown_originating_tool_returns_empty_without_calls(self):
        tools = FakeTools()
        finding = FakeFinding(
            claim="weird",
            source_agent="zzz",
            source_tool="unregistered.thing",
            timestamp=datetime.fromisoformat("2026-04-17T14:30:00+00:00"),
        )
        pins = await CriticRetriever(tools=tools).fetch_independent_evidence(finding)
        assert pins == []
        assert tools.calls == []

    @pytest.mark.asyncio
    async def test_keywordless_claim_returns_empty_without_calls(self):
        tools = FakeTools()
        finding = FakeFinding(
            claim="xx yy",
            source_agent="log_agent",
            source_tool="logs.search",
            timestamp=datetime.fromisoformat("2026-04-17T14:30:00+00:00"),
        )
        pins = await CriticRetriever(tools=tools).fetch_independent_evidence(finding)
        assert pins == []
        assert tools.calls == []

    @pytest.mark.asyncio
    async def test_tool_exception_does_not_block_other_tools(self):
        class FlakyTools(FakeTools):
            async def call(self, tool_name, *, params):
                if tool_name == "metrics.query":
                    raise RuntimeError("boom")
                return await super().call(tool_name, params=params)

        tools = FlakyTools()
        tools.set_response(
            "k8s.events",
            [{"@timestamp": "2026-04-17T14:30:05+00:00", "message": "pod evicted"}],
        )
        finding = FakeFinding(
            claim="payment-api OOM at 14:30",
            source_agent="log_agent",
            source_tool="logs.search",
            timestamp=datetime.fromisoformat("2026-04-17T14:30:00+00:00"),
        )
        pins = await CriticRetriever(tools=tools).fetch_independent_evidence(finding)
        assert len(pins) == 1
        assert pins[0].source_tool == "k8s.events"

    @pytest.mark.asyncio
    async def test_retriever_plugs_into_ensemble_as_third_pool(self):
        """Retrieved pins are added to the evidence pool before partitioning."""
        from src.agents.critic_ensemble import CriticEnsemble
        import json

        class CaptureClient:
            def __init__(self):
                self.prompts = []

            async def chat(self, *, system, messages, model, temperature):
                self.prompts.append(messages[0]["content"])
                return json.dumps({"verdict": "insufficient_evidence", "reasoning": "stub"})

        tools = FakeTools()
        tools.set_response(
            "metrics.query",
            [{"@timestamp": "2026-04-17T14:30:00+00:00", "message": "cpu nominal"}],
        )
        tools.set_response(
            "k8s.events",
            [{"@timestamp": "2026-04-17T14:30:00+00:00", "message": "pod evicted: payment-api"}],
        )
        retriever = CriticRetriever(tools=tools)
        client = CaptureClient()
        ensemble = CriticEnsemble(client=client, retriever=retriever, top_k=2)

        finding = {
            "claim": "payment api OOMKilled",
            "source_agent": "log_agent",
            "source_tool": "logs.search",
            "timestamp": datetime.fromisoformat("2026-04-17T14:30:00+00:00"),
        }
        # Seed the pool with existing pins so the retrieved pins mix in
        seed_pins = [
            {"claim": "payment latency", "source_agent": "metrics_agent", "evidence_type": "metric"}
        ]
        await ensemble.evaluate(finding=finding, evidence_pins=seed_pins)
        # retrieved k8s pin about 'evicted payment-api' should show up in one
        # of the two captured prompts
        joined = "\n".join(client.prompts).lower()
        assert "evicted" in joined

    @pytest.mark.asyncio
    async def test_window_is_applied_to_params(self):
        tools = FakeTools()
        ts = datetime.fromisoformat("2026-04-17T14:30:00+00:00")
        finding = FakeFinding(
            claim="payment OOMKilled",
            source_agent="log_agent",
            source_tool="logs.search",
            timestamp=ts,
        )
        await CriticRetriever(tools=tools, window=timedelta(minutes=2)).fetch_independent_evidence(finding)
        for _, params in tools.calls:
            assert params["start"] == (ts - timedelta(minutes=2)).isoformat()
            assert params["end"] == (ts + timedelta(minutes=2)).isoformat()
            assert "payment" in params["keywords"]
