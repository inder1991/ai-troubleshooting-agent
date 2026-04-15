"""Verify every @traced_node-decorated non-agent node has a default output entry."""
import pytest
from src.agents.cluster.traced_node import _NODE_DEFAULT_OUTPUTS, _AGENT_NODE_NAMES

EXPECTED_NON_AGENT_NODES = {
    "signal_normalizer",
    "failure_pattern_matcher",
    "temporal_analyzer",
    "diagnostic_graph_builder",
    "issue_lifecycle_classifier",
    "hypothesis_engine",
    "critic_validator",
    "solution_validator",
    "alert_correlator",
    "causal_firewall",
    "rbac_preflight",
    "topology_snapshot_resolver",
    "synthesize",
    "guard_formatter",
}


@pytest.mark.parametrize("node_name", sorted(EXPECTED_NON_AGENT_NODES))
def test_node_has_default_output(node_name):
    assert node_name in _NODE_DEFAULT_OUTPUTS, (
        f"{node_name} missing from _NODE_DEFAULT_OUTPUTS"
    )


def test_agent_nodes_not_in_defaults():
    for name in _AGENT_NODE_NAMES:
        assert name not in _NODE_DEFAULT_OUTPUTS


def test_proactive_analysis_is_traced():
    """_proactive_analysis_node must be wrapped with @traced_node."""
    from src.agents.cluster.graph import _proactive_analysis_node
    assert hasattr(_proactive_analysis_node, "__wrapped__"), (
        "_proactive_analysis_node is not decorated with @traced_node"
    )
