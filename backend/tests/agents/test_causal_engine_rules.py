"""Task 2.2 — rule-based root vs symptom over a typed IncidentGraph."""
import pytest

from src.agents.causal_engine import Root, find_root_causes
from src.agents.incident_graph import IncidentGraph


def _g_cpu_only_correlates_to_outage() -> IncidentGraph:
    """CPU spike correlates with outage but does not 'cause' it."""
    g = IncidentGraph()
    g.add_node("cpu", t=0)
    g.add_node("outage", t=60)
    g.add_edge("cpu", "outage", edge_type="correlates")
    return g


def _g_deploy_causes_oom_and_outage() -> IncidentGraph:
    g = IncidentGraph()
    g.add_node("deploy", t=0)
    g.add_node("oom", t=120)
    g.add_node("outage", t=180)
    g.add_edge(
        "deploy", "oom",
        edge_type="causes", lag_s=120, pattern_id="deploy_to_oom",
    )
    g.add_edge(
        "deploy", "outage",
        edge_type="causes", lag_s=180, pattern_id="deploy_to_outage",
    )
    return g


class TestFindRootCausesRules:
    def test_topological_source_alone_does_not_qualify_as_root(self):
        # CPU spike has no incoming edges in the graph but only 'correlates' outgoing;
        # must NOT be returned as root.
        g = _g_cpu_only_correlates_to_outage()
        assert find_root_causes(g) == []

    def test_root_requires_at_least_one_outgoing_causes_edge(self):
        g = _g_deploy_causes_oom_and_outage()
        roots = find_root_causes(g)
        assert "deploy" in [r.node_id for r in roots]

    def test_node_with_incoming_causes_is_not_root(self):
        g = _g_deploy_causes_oom_and_outage()
        # 'oom' has an incoming 'causes' edge from deploy. Even if it had its own
        # outgoing 'causes', it cannot be a root.
        g.add_node("downstream", t=240)
        g.add_edge(
            "oom", "downstream",
            edge_type="causes", lag_s=60, pattern_id="oom_cascades",
        )
        roots = find_root_causes(g)
        assert "oom" not in [r.node_id for r in roots]
        assert "deploy" in [r.node_id for r in roots]

    def test_isolated_node_is_not_root(self):
        g = IncidentGraph()
        g.add_node("lonely", t=0)
        assert find_root_causes(g) == []

    def test_score_orders_roots_deterministically(self):
        g = _g_deploy_causes_oom_and_outage()
        # Add a second root with only one outgoing 'causes' to compare ranking.
        g.add_node("flag_flip", t=0)
        g.add_node("rate_limit", t=120)
        g.add_edge(
            "flag_flip", "rate_limit",
            edge_type="causes", lag_s=120, pattern_id="flag_flip_to_rate_limit",
        )
        roots = find_root_causes(g)
        names = [r.node_id for r in roots]
        # 'deploy' has 2 'causes' descendants; 'flag_flip' has 1 → deploy ranks higher
        assert names.index("deploy") < names.index("flag_flip")

    def test_root_dataclass_shape(self):
        g = _g_deploy_causes_oom_and_outage()
        roots = find_root_causes(g)
        assert isinstance(roots[0], Root)
        assert isinstance(roots[0].node_id, str)
        assert isinstance(roots[0].score, float)
        assert roots[0].score > 0

    def test_pure_function_no_graph_mutation(self):
        g = _g_deploy_causes_oom_and_outage()
        before_nodes = list(g.G.nodes)
        before_edges = list(g.G.edges(data=True))
        find_root_causes(g)
        find_root_causes(g)
        assert list(g.G.nodes) == before_nodes
        assert list(g.G.edges(data=True)) == before_edges

    def test_empty_graph_yields_empty(self):
        assert find_root_causes(IncidentGraph()) == []
