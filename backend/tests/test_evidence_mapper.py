"""Tests for evidence_mapper — rules-first signal attribution."""

from __future__ import annotations

import pytest

from src.hypothesis.evidence_mapper import (
    EVIDENCE_RULES,
    EvidenceMapper,
    EvidenceRule,
)
from src.models.hypothesis import EvidenceSignal, Hypothesis


def _signal(name: str, sid: str = "s1") -> EvidenceSignal:
    return EvidenceSignal(
        signal_id=sid,
        signal_type="k8s",
        signal_name=name,
        source_agent="test",
    )


@pytest.fixture
def hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(hypothesis_id="h1", category="memory", source_patterns=[]),
        Hypothesis(hypothesis_id="h2", category="connection", source_patterns=[]),
        Hypothesis(hypothesis_id="h3", category="database", source_patterns=[]),
    ]


@pytest.fixture
def mapper() -> EvidenceMapper:
    return EvidenceMapper()


# ── Rule mapping ──────────────────────────────────────────────


class TestRuleMapping:
    def test_oom_kill_maps_to_memory(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_signal(_signal("oom_kill"), hypotheses)
        assert result == ["h1"]

    def test_timeout_maps_to_connection_and_database(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_signal(_signal("timeout_error"), hypotheses)
        assert sorted(result) == ["h2", "h3"]

    def test_ambiguous_signal_stays_unattributed(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_signal(_signal("latency_spike"), hypotheses)
        assert result == []

    def test_no_matching_hypothesis_category(self, mapper: EvidenceMapper):
        disk_only = [Hypothesis(hypothesis_id="hd", category="disk", source_patterns=[])]
        result = mapper.map_signal(_signal("oom_kill"), disk_only)
        assert result == []

    def test_unknown_signal_returns_empty(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_signal(_signal("totally_unknown"), hypotheses)
        assert result == []


# ── Priority resolution ──────────────────────────────────────


class TestPriorityResolution:
    def test_higher_priority_wins(self):
        rules = [
            EvidenceRule("r1", 1, "test_signal", ["cpu"], priority=3),
            EvidenceRule("r2", 1, "test_signal", ["memory"], priority=10),
        ]
        mapper = EvidenceMapper(rules=rules)
        hyps = [
            Hypothesis(hypothesis_id="hc", category="cpu", source_patterns=[]),
            Hypothesis(hypothesis_id="hm", category="memory", source_patterns=[]),
        ]
        result = mapper.map_signal(_signal("test_signal"), hyps)
        # Higher priority (10) maps to memory, not cpu
        assert result == ["hm"]


# ── Contradiction mapping ────────────────────────────────────


class TestContradictionMapping:
    def test_low_memory_contradicts_memory(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_contradiction(_signal("low_memory_usage"), hypotheses)
        assert result == ["h1"]

    def test_unknown_signal_no_contradiction(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_contradiction(_signal("unknown_signal"), hypotheses)
        assert result == []

    def test_healthy_connections_contradicts_connection(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        result = mapper.map_contradiction(_signal("healthy_connections"), hypotheses)
        assert result == ["h2"]


# ── Apply (batch) mapping ────────────────────────────────────


class TestApplyMapping:
    def test_maps_evidence_to_hypotheses(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        signals = [
            _signal("oom_kill", sid="s1"),
            _signal("high_memory_usage", sid="s2"),
        ]
        mapper.apply(signals, hypotheses)
        h1 = hypotheses[0]
        assert len(h1.evidence_for) == 2
        assert {s.signal_id for s in h1.evidence_for} == {"s1", "s2"}

    def test_does_not_duplicate(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        sig = _signal("oom_kill", sid="s1")
        mapper.apply([sig], hypotheses)
        mapper.apply([sig], hypotheses)
        h1 = hypotheses[0]
        assert len(h1.evidence_for) == 1

    def test_skips_eliminated_hypotheses(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        hypotheses[0].status = "eliminated"
        mapper.apply([_signal("oom_kill", sid="s1")], hypotheses)
        assert len(hypotheses[0].evidence_for) == 0

    def test_contradiction_populates_evidence_against(self, mapper: EvidenceMapper, hypotheses: list[Hypothesis]):
        mapper.apply([_signal("low_memory_usage", sid="s1")], hypotheses)
        h1 = hypotheses[0]
        assert len(h1.evidence_against) == 1
        assert h1.evidence_against[0].signal_id == "s1"
