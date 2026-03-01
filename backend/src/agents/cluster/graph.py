"""LangGraph StateGraph for cluster diagnostics with fan-out/fan-in."""

from __future__ import annotations

import operator
from typing import Any, Annotated, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from src.agents.cluster.topology_resolver import topology_snapshot_resolver
from src.agents.cluster.alert_correlator import alert_correlator
from src.agents.cluster.causal_firewall import causal_firewall
from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.synthesizer import synthesize
from src.agents.cluster.guard_formatter import guard_formatter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180


class State(TypedDict):
    # Existing fields
    diagnostic_id: str
    platform: str
    platform_version: str
    namespaces: list[str]
    exclude_namespaces: list[str]
    domain_reports: Annotated[list[dict], operator.add]
    causal_chains: Annotated[list[dict], operator.add]
    uncorrelated_findings: Annotated[list[dict], operator.add]
    health_report: Optional[dict]
    phase: str
    re_dispatch_count: int
    re_dispatch_domains: list[str]
    data_completeness: float
    error: Optional[str]
    _trace: Annotated[list[dict], operator.add]
    # New fields
    topology_graph: dict
    topology_freshness: dict
    issue_clusters: list[dict]
    causal_search_space: dict
    scan_mode: str
    previous_scan: Optional[dict]
    guard_scan_result: Optional[dict]


def _should_redispatch(state: dict) -> list[str]:
    """Conditional edge: re-dispatch to all 4 agents or proceed to guard formatter."""
    re_dispatch = state.get("re_dispatch_domains", [])
    count = state.get("re_dispatch_count", 0)
    if re_dispatch and count < 1:
        return ["dispatch_ctrl_plane", "dispatch_node", "dispatch_network", "dispatch_storage"]
    return ["to_guard_formatter"]


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    graph = StateGraph(State)

    # Add all nodes
    graph.add_node("topology_snapshot_resolver", topology_snapshot_resolver)
    graph.add_node("alert_correlator", alert_correlator)
    graph.add_node("causal_firewall", causal_firewall)
    graph.add_node("ctrl_plane_agent", ctrl_plane_agent)
    graph.add_node("node_agent", node_agent)
    graph.add_node("network_agent", network_agent)
    graph.add_node("storage_agent", storage_agent)
    graph.add_node("synthesize", synthesize)
    graph.add_node("guard_formatter", guard_formatter)

    # Sequential pre-processing: topology -> correlator -> firewall
    graph.add_edge(START, "topology_snapshot_resolver")
    graph.add_edge("topology_snapshot_resolver", "alert_correlator")
    graph.add_edge("alert_correlator", "causal_firewall")

    # Fan-out: firewall -> all 4 agents in parallel
    graph.add_edge("causal_firewall", "ctrl_plane_agent")
    graph.add_edge("causal_firewall", "node_agent")
    graph.add_edge("causal_firewall", "network_agent")
    graph.add_edge("causal_firewall", "storage_agent")

    # All agents fan-in to synthesize
    graph.add_edge("ctrl_plane_agent", "synthesize")
    graph.add_edge("node_agent", "synthesize")
    graph.add_edge("network_agent", "synthesize")
    graph.add_edge("storage_agent", "synthesize")

    # After synthesis: check confidence and optionally re-dispatch
    graph.add_conditional_edges(
        "synthesize",
        _should_redispatch,
        {
            "dispatch_ctrl_plane": "ctrl_plane_agent",
            "dispatch_node": "node_agent",
            "dispatch_network": "network_agent",
            "dispatch_storage": "storage_agent",
            "to_guard_formatter": "guard_formatter",
        },
    )

    # Guard formatter -> END
    graph.add_edge("guard_formatter", END)

    compiled = graph.compile()
    return compiled
