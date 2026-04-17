"""Task 2.1 — typed edges + rule-engine certification for 'causes'."""
import pytest

from src.agents.incident_graph import (
    CausalRuleEngine,
    EDGE_TYPES,
    IncidentGraph,
)


class TestEdgeTypes:
    def test_edge_must_have_type(self):
        g = IncidentGraph()
        with pytest.raises(ValueError, match="edge_type"):
            g.add_edge("a", "b")  # missing type
        g.add_edge("a", "b", edge_type="precedes", lag_s=120)
        assert ("a", "b") in g.G.edges

    def test_unknown_edge_type_rejected(self):
        g = IncidentGraph()
        with pytest.raises(ValueError, match="edge_type"):
            g.add_edge("a", "b", edge_type="who_knows")

    def test_all_canonical_edge_types_accepted(self):
        g = IncidentGraph()
        g.add_node("a", t=1000)
        g.add_node("b", t=1100)
        # 'causes' requires certification — validated separately below
        for et in ("correlates", "precedes", "contradicts", "supports"):
            g.add_edge("a", "b", edge_type=et)
            assert g.G.edges["a", "b"]["edge_type"] == et
            g.G.remove_edge("a", "b")

    def test_canonical_edge_type_set(self):
        assert EDGE_TYPES == {"causes", "correlates", "precedes", "contradicts", "supports"}


class TestCausesRequiresCertification:
    def test_causes_edge_requires_temporal_precedence_and_pattern_match(self):
        g = IncidentGraph()
        g.add_node("deploy", t=1000)
        g.add_node("oom", t=1300)
        # 'causes' requires the rule engine to certify it; raw add must reject:
        with pytest.raises(ValueError):
            g.add_edge("deploy", "oom", edge_type="causes")
        # but 'precedes' is fine:
        g.add_edge("deploy", "oom", edge_type="precedes", lag_s=300)

    def test_causes_accepts_when_certified(self):
        g = IncidentGraph()
        g.add_node("deploy", t=1000)
        g.add_node("oom", t=1300)
        g.add_edge(
            "deploy", "oom",
            edge_type="causes", lag_s=300,
            pattern_id="deploy_to_oom",
        )
        assert g.G.edges["deploy", "oom"]["edge_type"] == "causes"

    def test_causes_rejects_when_source_is_temporally_after_target(self):
        g = IncidentGraph()
        g.add_node("a", t=2000)
        g.add_node("b", t=1000)
        with pytest.raises(ValueError, match="temporal"):
            g.add_edge(
                "a", "b",
                edge_type="causes", lag_s=100,
                pattern_id="x",
            )

    def test_causes_rejects_when_lag_exceeds_bound(self):
        g = IncidentGraph()
        g.add_node("a", t=0)
        g.add_node("b", t=1)
        with pytest.raises(ValueError, match="lag"):
            g.add_edge(
                "a", "b",
                edge_type="causes", lag_s=10**9,
                pattern_id="x",
            )

    def test_causes_rejects_when_no_pattern_and_no_override(self):
        g = IncidentGraph()
        g.add_node("a", t=0)
        g.add_node("b", t=60)
        with pytest.raises(ValueError, match="pattern"):
            g.add_edge("a", "b", edge_type="causes", lag_s=60)

    def test_causes_accepts_user_override(self):
        g = IncidentGraph()
        g.add_node("a", t=0)
        g.add_node("b", t=60)
        g.add_edge(
            "a", "b",
            edge_type="causes", lag_s=60,
            user_override=True,
        )
        assert g.G.edges["a", "b"]["edge_type"] == "causes"


class TestRuleEngineIsolated:
    def test_rule_engine_is_exposed_as_public_api(self):
        engine = CausalRuleEngine()
        assert hasattr(engine, "certify")

    def test_rule_engine_rejects_when_temporal_missing(self):
        g = IncidentGraph()
        g.add_node("a")  # no timestamp
        g.add_node("b", t=100)
        with pytest.raises(ValueError, match="temporal"):
            g.add_edge("a", "b", edge_type="causes", lag_s=10, pattern_id="x")


class TestRankRootCausesWeightsByEdgeType:
    def test_causes_outweighs_correlates(self):
        """Node with outgoing 'causes' ranks above node with same count of 'correlates'."""
        g = IncidentGraph()
        g.add_node("root_causes", t=0)
        g.add_node("root_corr", t=0)
        for target in ("c1", "c2", "c3"):
            g.add_node(target, t=100)
        # root_causes emits 3 certified causes
        for target in ("c1", "c2", "c3"):
            g.add_edge(
                "root_causes", target,
                edge_type="causes", lag_s=100, pattern_id="p",
            )
        # root_corr emits 3 correlations (same shape, weaker edge type)
        for target in ("c1", "c2", "c3"):
            g.add_edge("root_corr", target, edge_type="correlates")
        ranked = dict(g.rank_root_causes())
        assert ranked["root_causes"] > ranked["root_corr"]

    def test_precedes_outweighs_correlates(self):
        g = IncidentGraph()
        g.add_node("p", t=0)
        g.add_node("c", t=0)
        g.add_node("leaf", t=100)
        g.add_edge("p", "leaf", edge_type="precedes", lag_s=100)
        g.add_edge("c", "leaf", edge_type="correlates")
        ranked = dict(g.rank_root_causes())
        assert ranked["p"] > ranked["c"]

    def test_contradictions_penalize_score(self):
        g = IncidentGraph()
        g.add_node("clean", t=0)
        g.add_node("bad", t=0)
        g.add_node("leaf", t=100)
        g.add_edge("clean", "leaf", edge_type="precedes", lag_s=100)
        g.add_edge("bad", "leaf", edge_type="precedes", lag_s=100)
        g.add_edge("bad", "leaf2", edge_type="contradicts")
        g.add_node("leaf2", t=100)
        ranked = dict(g.rank_root_causes())
        assert ranked["clean"] > ranked["bad"]

    def test_empty_graph_yields_empty_ranking(self):
        assert IncidentGraph().rank_root_causes() == []
