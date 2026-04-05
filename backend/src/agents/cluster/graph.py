"""LangGraph StateGraph for cluster diagnostics with fan-out/fan-in."""

import operator
from typing import Any, Annotated, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END

from src.agents.cluster.topology_resolver import topology_snapshot_resolver
from src.agents.cluster.alert_correlator import alert_correlator
from src.agents.cluster.causal_firewall import causal_firewall
from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.rbac_agent import rbac_agent
from src.agents.cluster.critic_agent import critic_validator
from src.agents.cluster.synthesizer import synthesize
from src.agents.cluster.guard_formatter import guard_formatter
from src.agents.cluster.signal_normalizer import signal_normalizer
from src.agents.cluster.failure_patterns import failure_pattern_matcher
from src.agents.cluster.temporal_analyzer import temporal_analyzer
from src.agents.cluster.diagnostic_graph_builder import diagnostic_graph_builder
from src.agents.cluster.issue_lifecycle import issue_lifecycle_classifier
from src.agents.cluster.hypothesis_engine import hypothesis_engine
from src.agents.cluster.solution_validator import solution_validator
from src.agents.cluster.rbac_checker import rbac_preflight
from src.agents.cluster.state import DiagnosticScope
from src.utils.logger import get_logger


logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180

ALL_DOMAINS = ["ctrl_plane", "node", "network", "storage", "rbac"]


def _build_partial_health_report(state: dict) -> dict:
    """
    Build a partial ClusterHealthReport from whatever state was checkpointed before timeout.
    Called when graph.ainvoke() times out — returns PARTIAL_TIMEOUT status with all
    anomalies found so far in uncorrelated_findings (no causal chains, no remediation).
    """
    domain_reports = state.get("domain_reports") or []
    proactive_findings = state.get("proactive_findings") or []
    data_completeness = state.get("data_completeness") or 0.0

    # Derive health from domain statuses
    statuses = [r.get("status", "PENDING") if isinstance(r, dict) else r.status.value
                for r in domain_reports]
    has_failed = any(s in ("FAILED",) for s in statuses)
    has_anomalies = any(
        len(r.get("anomalies", []) if isinstance(r, dict) else r.anomalies) > 0
        for r in domain_reports
    )

    if has_failed and has_anomalies:
        overall_status = "CRITICAL"
    elif has_failed:
        overall_status = "UNKNOWN"
    elif has_anomalies:
        overall_status = "DEGRADED"
    else:
        overall_status = "UNKNOWN"  # Can't claim HEALTHY without completed synthesis

    # Collect all anomalies from completed domains as uncorrelated_findings
    uncorrelated: list[dict] = []
    for r in domain_reports:
        anomalies = r.get("anomalies", []) if isinstance(r, dict) else [
            a.model_dump(mode="json") for a in r.anomalies
        ]
        uncorrelated.extend(anomalies)

    return {
        "status": "PARTIAL_TIMEOUT",
        "overall_status": overall_status,
        "data_completeness": data_completeness,
        "domain_reports": domain_reports,
        "proactive_findings": proactive_findings,
        "causal_chains": [],
        "uncorrelated_findings": uncorrelated,
        "remediation": {"immediate": [], "long_term": []},
        "blast_radius": {
            "summary": f"Diagnosis timed out. {len(uncorrelated)} anomalies found before timeout.",
            "affected_namespaces": state.get("namespaces", []),
            "affected_pods": [],
            "affected_nodes": [],
        },
        "note": "Diagnosis timed out before synthesis. Results reflect partial data only.",
    }


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
    cluster_url: str
    cluster_type: str
    cluster_role: str
    previous_scan: Optional[dict]
    guard_scan_result: Optional[dict]
    # Scope-governed diagnostics
    diagnostic_scope: Optional[dict]
    scoped_topology_graph: Optional[dict]
    dispatch_domains: list[str]
    scope_coverage: float
    # Pre-flight RBAC check result
    rbac_check: Optional[dict]
    rbac_skipped: Annotated[list[dict], operator.add]
    # Critic validation result
    critic_result: Optional[dict]
    # Proactive analysis findings (fan-out merge)
    proactive_findings: Annotated[list[dict], operator.add]
    # Diagnostic intelligence pipeline
    normalized_signals: list[dict]
    pattern_matches: list[dict]
    temporal_analysis: Optional[dict]
    diagnostic_graph: Optional[dict]
    diagnostic_issues: list[dict]
    ranked_hypotheses: list[dict]
    hypotheses_by_issue: Optional[dict]
    hypothesis_selection: Optional[dict]


# ---------------------------------------------------------------------------
# Dispatch Router: determines which domain agents run based on scope
# ---------------------------------------------------------------------------

# Mapping: denied resource name → domains that require that resource
_RBAC_DOMAIN_GATES = {
    "nodes": ["node"],
    "pods": ["ctrl_plane", "node"],
    "routes": ["network"],
    "persistentvolumeclaims": ["storage"],
}


def dispatch_router(state: dict) -> dict:
    """Determine which domain agents should run based on DiagnosticScope and RBAC."""
    scope_data = state.get("diagnostic_scope")
    rbac_check = state.get("rbac_check") or {}
    denied_resources = set(rbac_check.get("denied", []))

    # Determine base domains from scope
    if not scope_data:
        domains = list(ALL_DOMAINS)
    else:
        scope = DiagnosticScope(**scope_data)
        if scope.level == "cluster":
            domains = list(scope.domains)
        elif scope.level == "namespace":
            domains = list(scope.domains)
            if not scope.include_control_plane:
                domains = [d for d in domains if d != "ctrl_plane"]
        elif scope.level == "workload":
            domains = [d for d in scope.domains if d in ("node", "network")]
            if scope.include_control_plane:
                domains.append("ctrl_plane")
        elif scope.level == "component":
            domains = list(scope.domains)
        else:
            domains = list(ALL_DOMAINS)

    # Gate domains based on RBAC denials
    rbac_skipped = []
    for resource, gated_domains in _RBAC_DOMAIN_GATES.items():
        if resource in denied_resources:
            for d in gated_domains:
                if d in domains:
                    domains.remove(d)
                    rbac_skipped.append({"domain": d, "reason": f"{resource} permission denied"})

    scope_coverage = len(domains) / len(ALL_DOMAINS) if ALL_DOMAINS else 1.0

    logger.info(
        "Dispatch router: domains=%s, scope=%s",
        domains, scope_data.get("level", "cluster") if scope_data else "cluster",
        extra={"action": "dispatch_router", "extra": {"selected_domains": domains}},
    )

    result: dict = {"dispatch_domains": domains, "scope_coverage": scope_coverage}
    if rbac_skipped:
        result["rbac_skipped"] = rbac_skipped
    return result


# ---------------------------------------------------------------------------
# Domain agent wrapper: skips agents not in dispatch_domains
# ---------------------------------------------------------------------------


def _wrap_domain_agent(domain: str, agent_fn):
    """Wrap a domain agent to return SKIPPED if not in dispatch_domains."""
    async def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
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
    logger.info(
        "Re-dispatch decision: domains=%s, count=%d",
        re_dispatch, count,
        extra={"action": "redispatch_decision"},
    )

    if re_dispatch and count < 1:
        # Only re-dispatch domains that are in the active dispatch set
        domain_to_node = {
            "ctrl_plane": "dispatch_ctrl_plane",
            "node": "dispatch_node",
            "network": "dispatch_network",
            "storage": "dispatch_storage",
            "rbac": "dispatch_rbac",
        }
        targets = [
            domain_to_node[d]
            for d in re_dispatch
            if d in dispatch_domains and d in domain_to_node
        ]
        return targets if targets else ["to_guard_formatter"]
    return ["to_guard_formatter"]


async def _proactive_analysis_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """Run proactive checks and return findings as graph state update."""
    from .proactive_analyzer import run_proactive_analysis

    cluster_client = (config or {}).get("configurable", {}).get("cluster_client")

    if cluster_client is None:
        return {"proactive_findings": []}

    try:
        results = await run_proactive_analysis(client=cluster_client)
        findings = [
            f.model_dump() if hasattr(f, "model_dump") else dict(f)
            for f in results
        ]
        return {"proactive_findings": findings}
    except Exception as exc:
        logger.warning("Proactive analysis failed: %s", exc)
        return {"proactive_findings": []}


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    graph = StateGraph(State)

    # Wrap domain agents so they respect dispatch_domains
    wrapped_ctrl_plane = _wrap_domain_agent("ctrl_plane", ctrl_plane_agent)
    wrapped_node = _wrap_domain_agent("node", node_agent)
    wrapped_network = _wrap_domain_agent("network", network_agent)
    wrapped_storage = _wrap_domain_agent("storage", storage_agent)
    wrapped_rbac = _wrap_domain_agent("rbac", rbac_agent)

    # Add all nodes
    graph.add_node("rbac_preflight", rbac_preflight)
    graph.add_node("topology_snapshot_resolver", topology_snapshot_resolver)
    graph.add_node("alert_correlator", alert_correlator)
    graph.add_node("causal_firewall", causal_firewall)
    graph.add_node("dispatch_router", dispatch_router)
    graph.add_node("ctrl_plane_agent", wrapped_ctrl_plane)
    graph.add_node("node_agent", wrapped_node)
    graph.add_node("network_agent", wrapped_network)
    graph.add_node("storage_agent", wrapped_storage)
    graph.add_node("rbac_agent", wrapped_rbac)
    graph.add_node("signal_normalizer", signal_normalizer)
    graph.add_node("failure_pattern_matcher", failure_pattern_matcher)
    graph.add_node("temporal_analyzer", temporal_analyzer)
    graph.add_node("proactive_analysis", _proactive_analysis_node)
    graph.add_node("diagnostic_graph_builder", diagnostic_graph_builder)
    graph.add_node("issue_lifecycle_classifier", issue_lifecycle_classifier)
    graph.add_node("hypothesis_engine", hypothesis_engine)
    graph.add_node("critic_validator", critic_validator)
    graph.add_node("synthesize", synthesize)
    graph.add_node("solution_validator", solution_validator)
    graph.add_node("guard_formatter", guard_formatter)

    # Sequential pre-processing: rbac_preflight -> topology -> correlator -> firewall -> dispatch_router
    graph.add_edge(START, "rbac_preflight")
    graph.add_edge("rbac_preflight", "topology_snapshot_resolver")
    graph.add_edge("topology_snapshot_resolver", "alert_correlator")
    graph.add_edge("alert_correlator", "causal_firewall")
    graph.add_edge("causal_firewall", "dispatch_router")

    # Fan-out: dispatch_router -> all 5 agents in parallel
    graph.add_edge("dispatch_router", "ctrl_plane_agent")
    graph.add_edge("dispatch_router", "node_agent")
    graph.add_edge("dispatch_router", "network_agent")
    graph.add_edge("dispatch_router", "storage_agent")
    graph.add_edge("dispatch_router", "rbac_agent")

    # Fan-in: agents → diagnostic intelligence pipeline
    graph.add_edge("ctrl_plane_agent", "signal_normalizer")
    graph.add_edge("node_agent", "signal_normalizer")
    graph.add_edge("network_agent", "signal_normalizer")
    graph.add_edge("storage_agent", "signal_normalizer")
    graph.add_edge("rbac_agent", "signal_normalizer")

    # Sequential intelligence pipeline
    graph.add_edge("signal_normalizer", "failure_pattern_matcher")
    graph.add_edge("failure_pattern_matcher", "temporal_analyzer")
    graph.add_edge("temporal_analyzer", "proactive_analysis")
    graph.add_edge("proactive_analysis", "diagnostic_graph_builder")
    graph.add_edge("diagnostic_graph_builder", "issue_lifecycle_classifier")
    graph.add_edge("issue_lifecycle_classifier", "hypothesis_engine")
    graph.add_edge("hypothesis_engine", "critic_validator")

    # Critic → Synthesizer → Solution Validator
    graph.add_edge("critic_validator", "synthesize")
    graph.add_edge("synthesize", "solution_validator")

    # After solution validation: check confidence and optionally re-dispatch
    graph.add_conditional_edges(
        "solution_validator",
        _should_redispatch,
        {
            "dispatch_ctrl_plane": "ctrl_plane_agent",
            "dispatch_node": "node_agent",
            "dispatch_network": "network_agent",
            "dispatch_storage": "storage_agent",
            "dispatch_rbac": "rbac_agent",
            "to_guard_formatter": "guard_formatter",
        },
    )

    # Guard formatter -> END
    graph.add_edge("guard_formatter", END)

    compiled = graph.compile()
    return compiled
