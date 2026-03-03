"""LangGraph StateGraph wiring for the network diagnosis pipeline.

Pipeline:
  START -> input_resolver -> [conditional] -> graph_pathfinder ->
  traceroute_probe -> hop_attributor -> firewall_evaluator ->
  nat_resolver -> path_synthesizer -> report_generator -> END

Follows the cluster diagnostic pattern from src.agents.cluster.graph.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any

from langgraph.graph import StateGraph, START, END

from src.agents.network.state import NetworkPipelineState
from src.agents.network.input_resolver import input_resolver
from src.agents.network.graph_pathfinder import graph_pathfinder
from src.agents.network.traceroute_probe import traceroute_probe
from src.agents.network.hop_attributor import hop_attributor
from src.agents.network.firewall_evaluator import firewall_evaluator
from src.agents.network.nacl_evaluator import nacl_evaluator
from src.agents.network.nat_resolver import nat_resolver
from src.agents.network.path_synthesizer import path_synthesizer
from src.agents.network.report_generator import report_generator
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.base import FirewallAdapter
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Conditional routing helpers
# ---------------------------------------------------------------------------


def _route_after_input_resolver(state: dict) -> str:
    """Conditional routing after input_resolver.

    - "ambiguous" -> END (user must disambiguate)
    - "failed"    -> END (IPs not in any known subnet)
    - otherwise   -> graph_pathfinder
    """
    status = state.get("resolution_status", "")
    if status == "ambiguous":
        return "end"
    if status == "failed":
        return "end"
    return "graph_pathfinder"


def _route_after_graph_pathfinder(state: dict) -> str:
    """Conditional routing after graph_pathfinder.

    If no candidate_paths and diagnosis_status == "no_path_known",
    skip traceroute/hop_attributor/firewall/nat and go straight
    to path_synthesizer (not enough topology data for traceroute).
    """
    candidate_paths = state.get("candidate_paths", [])
    diagnosis_status = state.get("diagnosis_status", "")
    if not candidate_paths and diagnosis_status == "no_path_known":
        return "path_synthesizer"
    return "traceroute_probe"


# ---------------------------------------------------------------------------
# Sync-to-async wrappers for sync nodes
# ---------------------------------------------------------------------------


def _make_async_wrapper(fn):
    """Wrap a sync node function as an async def for LangGraph compatibility.

    Offloads to a thread to avoid blocking the event loop.
    """
    async def wrapper(state: dict) -> dict:
        return await asyncio.to_thread(fn, state)
    # functools.partial objects don't have __name__, use .func.__name__ fallback
    name = getattr(fn, "__name__", None) or getattr(getattr(fn, "func", None), "__name__", "unknown")
    wrapper.__name__ = name
    return wrapper


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_network_diagnostic_graph(
    kg: NetworkKnowledgeGraph,
    adapters: dict[str, FirewallAdapter],
):
    """Build and compile the network diagnostic LangGraph.

    Uses functools.partial to bind dependencies (kg, adapters) into
    node functions that require them.
    """
    graph = StateGraph(NetworkPipelineState)

    # Bind dependencies via partial
    bound_input_resolver = functools.partial(input_resolver, kg=kg)
    bound_graph_pathfinder = functools.partial(graph_pathfinder, kg=kg)
    bound_hop_attributor = functools.partial(hop_attributor, kg=kg)

    # firewall_evaluator and nat_resolver are already async and take adapters
    bound_firewall_evaluator = functools.partial(firewall_evaluator, adapters=adapters)
    bound_nat_resolver = functools.partial(nat_resolver, adapters=adapters)

    # NACL evaluator uses the topology store
    bound_nacl_evaluator = functools.partial(nacl_evaluator, store=kg.store)
    async_nacl_evaluator = _make_async_wrapper(bound_nacl_evaluator)

    # Wrap sync nodes as async
    async_input_resolver = _make_async_wrapper(bound_input_resolver)
    async_graph_pathfinder = _make_async_wrapper(bound_graph_pathfinder)
    async_traceroute_probe = _make_async_wrapper(traceroute_probe)
    async_hop_attributor = _make_async_wrapper(bound_hop_attributor)
    async_path_synthesizer = _make_async_wrapper(path_synthesizer)
    async_report_generator = _make_async_wrapper(report_generator)

    # Add all nodes
    graph.add_node("input_resolver", async_input_resolver)
    graph.add_node("graph_pathfinder", async_graph_pathfinder)
    graph.add_node("traceroute_probe", async_traceroute_probe)
    graph.add_node("hop_attributor", async_hop_attributor)
    graph.add_node("firewall_evaluator", bound_firewall_evaluator)
    graph.add_node("nacl_evaluator", async_nacl_evaluator)
    graph.add_node("nat_resolver", bound_nat_resolver)
    graph.add_node("path_synthesizer", async_path_synthesizer)
    graph.add_node("report_generator", async_report_generator)

    # START -> input_resolver
    graph.add_edge(START, "input_resolver")

    # Conditional: input_resolver -> graph_pathfinder | END
    graph.add_conditional_edges(
        "input_resolver",
        _route_after_input_resolver,
        {
            "graph_pathfinder": "graph_pathfinder",
            "end": END,
        },
    )

    # Conditional: graph_pathfinder -> traceroute_probe | path_synthesizer
    graph.add_conditional_edges(
        "graph_pathfinder",
        _route_after_graph_pathfinder,
        {
            "traceroute_probe": "traceroute_probe",
            "path_synthesizer": "path_synthesizer",
        },
    )

    # traceroute -> hop_attributor -> [firewall_evaluator, nacl_evaluator] -> nat_resolver -> path_synthesizer
    graph.add_edge("traceroute_probe", "hop_attributor")
    graph.add_edge("hop_attributor", "firewall_evaluator")
    graph.add_edge("hop_attributor", "nacl_evaluator")
    graph.add_edge("firewall_evaluator", "nat_resolver")
    graph.add_edge("nacl_evaluator", "nat_resolver")
    graph.add_edge("nat_resolver", "path_synthesizer")

    # path_synthesizer -> report_generator -> END
    graph.add_edge("path_synthesizer", "report_generator")
    graph.add_edge("report_generator", END)

    compiled = graph.compile()
    logger.info("Network diagnostic graph compiled successfully")
    return compiled
