"""LangGraph StateGraph for cluster diagnostics with fan-out/fan-in."""

from __future__ import annotations

import operator
from typing import Any, Annotated, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.synthesizer import synthesize
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180


class State(TypedDict):
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


def _should_redispatch(state: dict) -> list[str]:
    """Conditional edge: re-dispatch to all 4 agents or end."""
    re_dispatch = state.get("re_dispatch_domains", [])
    count = state.get("re_dispatch_count", 0)
    if re_dispatch and count < 1:
        return ["dispatch_ctrl_plane", "dispatch_node", "dispatch_network", "dispatch_storage"]
    return ["end"]


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    graph = StateGraph(State)

    # Add nodes
    graph.add_node("ctrl_plane_agent", ctrl_plane_agent)
    graph.add_node("node_agent", node_agent)
    graph.add_node("network_agent", network_agent)
    graph.add_node("storage_agent", storage_agent)
    graph.add_node("synthesize", synthesize)

    # Fan-out: START -> all 4 agents in parallel
    graph.add_edge(START, "ctrl_plane_agent")
    graph.add_edge(START, "node_agent")
    graph.add_edge(START, "network_agent")
    graph.add_edge(START, "storage_agent")

    # All agents fan-in to synthesize
    graph.add_edge("ctrl_plane_agent", "synthesize")
    graph.add_edge("node_agent", "synthesize")
    graph.add_edge("network_agent", "synthesize")
    graph.add_edge("storage_agent", "synthesize")

    # After synthesis: check confidence and optionally re-dispatch to all agents
    graph.add_conditional_edges(
        "synthesize",
        _should_redispatch,
        {
            "dispatch_ctrl_plane": "ctrl_plane_agent",
            "dispatch_node": "node_agent",
            "dispatch_network": "network_agent",
            "dispatch_storage": "storage_agent",
            "end": END,
        },
    )

    compiled = graph.compile()
    return compiled
