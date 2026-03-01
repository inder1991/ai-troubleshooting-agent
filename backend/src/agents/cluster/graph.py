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
from src.agents.cluster.state import DiagnosticScope
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180

ALL_DOMAINS = ["ctrl_plane", "node", "network", "storage"]


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
    # Scope-governed diagnostics
    diagnostic_scope: Optional[dict]
    scoped_topology_graph: Optional[dict]
    dispatch_domains: list[str]
    scope_coverage: float


# ---------------------------------------------------------------------------
# Dispatch Router: determines which domain agents run based on scope
# ---------------------------------------------------------------------------


def dispatch_router(state: dict) -> dict:
    """Determine which domain agents should run based on DiagnosticScope."""
    scope_data = state.get("diagnostic_scope")
    if not scope_data:
        # No scope — run all domains
        return {"dispatch_domains": list(ALL_DOMAINS), "scope_coverage": 1.0}

    scope = DiagnosticScope(**scope_data)

    if scope.level == "cluster":
        domains = list(scope.domains)
    elif scope.level == "namespace":
        domains = list(scope.domains)
        if not scope.include_control_plane:
            domains = [d for d in domains if d != "ctrl_plane"]
    elif scope.level == "workload":
        # Workload: relevant domains only
        domains = [d for d in scope.domains if d in ("node", "network")]
        if scope.include_control_plane:
            domains.append("ctrl_plane")
    elif scope.level == "component":
        # Component = only the specified domains
        domains = list(scope.domains)
    else:
        domains = list(ALL_DOMAINS)

    scope_coverage = len(domains) / len(ALL_DOMAINS) if ALL_DOMAINS else 1.0
    return {"dispatch_domains": domains, "scope_coverage": scope_coverage}


# ---------------------------------------------------------------------------
# Domain agent wrapper: skips agents not in dispatch_domains
# ---------------------------------------------------------------------------


def _wrap_domain_agent(domain: str, agent_fn):
    """Wrap a domain agent to return SKIPPED if not in dispatch_domains."""
    async def wrapped(state: dict, config: dict | None = None) -> dict:
        dispatch = state.get("dispatch_domains", list(ALL_DOMAINS))
        if domain not in dispatch:
            return {"domain_reports": [{
                "domain": domain, "status": "SKIPPED", "confidence": 0,
                "anomalies": [], "ruled_out": [], "evidence_refs": [],
                "truncation_flags": {}, "duration_ms": 0,
            }]}
        return await agent_fn(state, config or {})
    wrapped.__name__ = agent_fn.__name__
    return wrapped


# ---------------------------------------------------------------------------
# Conditional edge: re-dispatch respecting scope
# ---------------------------------------------------------------------------


def _should_redispatch(state: dict) -> list[str]:
    """Conditional edge: re-dispatch to active agents or proceed to guard formatter."""
    re_dispatch = state.get("re_dispatch_domains", [])
    count = state.get("re_dispatch_count", 0)
    dispatch_domains = state.get("dispatch_domains", list(ALL_DOMAINS))
    if re_dispatch and count < 1:
        # Only re-dispatch domains that are in the active dispatch set
        domain_to_node = {
            "ctrl_plane": "dispatch_ctrl_plane",
            "node": "dispatch_node",
            "network": "dispatch_network",
            "storage": "dispatch_storage",
        }
        targets = [
            domain_to_node[d]
            for d in re_dispatch
            if d in dispatch_domains and d in domain_to_node
        ]
        return targets if targets else ["to_guard_formatter"]
    return ["to_guard_formatter"]


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    graph = StateGraph(State)

    # Wrap domain agents so they respect dispatch_domains
    wrapped_ctrl_plane = _wrap_domain_agent("ctrl_plane", ctrl_plane_agent)
    wrapped_node = _wrap_domain_agent("node", node_agent)
    wrapped_network = _wrap_domain_agent("network", network_agent)
    wrapped_storage = _wrap_domain_agent("storage", storage_agent)

    # Add all nodes
    graph.add_node("topology_snapshot_resolver", topology_snapshot_resolver)
    graph.add_node("alert_correlator", alert_correlator)
    graph.add_node("causal_firewall", causal_firewall)
    graph.add_node("dispatch_router", dispatch_router)
    graph.add_node("ctrl_plane_agent", wrapped_ctrl_plane)
    graph.add_node("node_agent", wrapped_node)
    graph.add_node("network_agent", wrapped_network)
    graph.add_node("storage_agent", wrapped_storage)
    graph.add_node("synthesize", synthesize)
    graph.add_node("guard_formatter", guard_formatter)

    # Sequential pre-processing: topology -> correlator -> firewall -> dispatch_router
    graph.add_edge(START, "topology_snapshot_resolver")
    graph.add_edge("topology_snapshot_resolver", "alert_correlator")
    graph.add_edge("alert_correlator", "causal_firewall")
    graph.add_edge("causal_firewall", "dispatch_router")

    # Fan-out: dispatch_router -> all 4 agents in parallel
    graph.add_edge("dispatch_router", "ctrl_plane_agent")
    graph.add_edge("dispatch_router", "node_agent")
    graph.add_edge("dispatch_router", "network_agent")
    graph.add_edge("dispatch_router", "storage_agent")

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
