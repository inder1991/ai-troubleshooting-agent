"""Tests for CausalLinker — validated causal links + hypothesis graph."""

from datetime import datetime, timezone, timedelta

import pytest

from src.models.hypothesis import CausalLink, EvidenceSignal, Hypothesis
from src.hypothesis.causal_linker import CausalLinker


def _signal(
    name: str,
    ts_offset_sec: int,
    agent: str = "k8s_agent",
    entity: str = "pod/inventory-abc",
) -> EvidenceSignal:
    ts = datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc) + timedelta(
        seconds=ts_offset_sec
    )
    return EvidenceSignal(
        signal_id=f"s_{name}_{ts_offset_sec}",
        signal_type="k8s",
        signal_name=name,
        raw_data={"involved_object": entity},
        source_agent=agent,
        timestamp=ts,
    )


class TestCausalLinkBuilding:
    def test_oom_causes_restart(self):
        signals = [_signal("oom_kill", 0), _signal("pod_restart", 30)]
        links = CausalLinker().build_links(signals)
        assert len(links) == 1
        assert links[0].cause_signal == "s_oom_kill_0"
        assert links[0].effect_signal == "s_pod_restart_30"
        assert links[0].same_entity is True
        assert links[0].confidence > 0.0

    def test_wrong_temporal_order_no_link(self):
        signals = [_signal("pod_restart", 0), _signal("oom_kill", 30)]
        links = CausalLinker().build_links(signals)
        assert len(links) == 0

    def test_too_far_apart_no_link(self):
        signals = [_signal("oom_kill", 0), _signal("pod_restart", 7200)]
        links = CausalLinker().build_links(signals)
        assert len(links) == 0

    def test_different_entities_lower_confidence(self):
        signals = [
            _signal("oom_kill", 0, entity="pod/a"),
            _signal("pod_restart", 30, entity="pod/b"),
        ]
        links = CausalLinker().build_links(signals)
        assert len(links) == 1
        assert links[0].same_entity is False
        assert links[0].confidence < 0.8

    def test_same_entity_higher_confidence(self):
        signals = [
            _signal("oom_kill", 0, entity="pod/a"),
            _signal("pod_restart", 5, entity="pod/a"),
        ]
        links = CausalLinker().build_links(signals)
        assert len(links) == 1
        assert links[0].same_entity is True
        assert links[0].confidence > 0.8

    def test_empty_signals(self):
        assert CausalLinker().build_links([]) == []

    def test_no_timestamp_skipped(self):
        s1 = EvidenceSignal(
            signal_id="s1",
            signal_type="k8s",
            signal_name="oom_kill",
            raw_data={"involved_object": "pod/a"},
            source_agent="k8s_agent",
            timestamp=None,
        )
        s2 = _signal("pod_restart", 30)
        links = CausalLinker().build_links([s1, s2])
        assert len(links) == 0


class TestHypothesisGraph:
    def test_links_root_to_downstream(self):
        oom_sig = _signal("oom_kill", 0)
        lat_sig = _signal("latency_spike", 60)

        h1 = Hypothesis(
            hypothesis_id="h1", category="memory", evidence_for=[oom_sig]
        )
        h2 = Hypothesis(
            hypothesis_id="h2", category="latency", evidence_for=[lat_sig]
        )

        links = CausalLinker().build_links([oom_sig, lat_sig])
        assert len(links) >= 1

        CausalLinker().build_hypothesis_graph([h1, h2], links)
        assert "h2" in h1.downstream_effects
        assert h2.root_cause_of == "h1"

    def test_no_collapse_both_survive(self):
        oom_sig = _signal("oom_kill", 0)
        lat_sig = _signal("latency_spike", 60)

        h1 = Hypothesis(
            hypothesis_id="h1", category="memory", evidence_for=[oom_sig]
        )
        h2 = Hypothesis(
            hypothesis_id="h2", category="latency", evidence_for=[lat_sig]
        )

        links = CausalLinker().build_links([oom_sig, lat_sig])
        CausalLinker().build_hypothesis_graph([h1, h2], links)

        assert h1.status == "active"
        assert h2.status == "active"

    def test_same_hypothesis_no_self_link(self):
        oom_sig = _signal("oom_kill", 0)
        restart_sig = _signal("pod_restart", 30)

        h1 = Hypothesis(
            hypothesis_id="h1",
            category="memory",
            evidence_for=[oom_sig, restart_sig],
        )

        links = CausalLinker().build_links([oom_sig, restart_sig])
        CausalLinker().build_hypothesis_graph([h1], links)

        assert h1.downstream_effects == []
        assert h1.root_cause_of is None
