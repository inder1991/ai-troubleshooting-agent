"""Critic agent: 6-layer hypothesis validator."""

from __future__ import annotations

from collections import defaultdict, deque

from src.agents.cluster.diagnostic_graph_builder import bfs_reachable
from src.agents.cluster.state import DiagnosticGraph, Hypothesis, NormalizedSignal
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Layer 1: Evidence traceable
# ---------------------------------------------------------------------------

def _check_evidence_traceable(hypothesis: dict, signals_by_id: dict[str, dict]) -> tuple[bool, str]:
    """Every supporting_evidence signal_id must exist in normalized_signals."""
    missing = []
    for ev in hypothesis.get("supporting_evidence", []):
        sid = ev.get("signal_id", "")
        if sid and sid not in signals_by_id:
            missing.append(sid)
    if missing:
        return False, f"Missing signal_ids: {', '.join(missing[:5])}"
    return True, "All supporting evidence signal_ids found"


# ---------------------------------------------------------------------------
# Layer 2: Resource exists
# ---------------------------------------------------------------------------

def _check_resource_exists(hypothesis: dict, topology_nodes: dict) -> tuple[bool, str]:
    """root_resource must exist in topology nodes."""
    root = hypothesis.get("root_resource", "")
    if not root:
        return True, "No root_resource specified (skipped)"
    if root in topology_nodes:
        return True, f"root_resource '{root}' found in topology"
    # Fuzzy: check if resource key appears as substring in any topology node
    for node_key in topology_nodes:
        if root in node_key or node_key in root:
            return True, f"root_resource '{root}' fuzzy-matched topology node '{node_key}'"
    return False, f"root_resource '{root}' not found in topology"


# ---------------------------------------------------------------------------
# Layer 3: Causal chain valid
# ---------------------------------------------------------------------------

def _check_causal_chain_valid(hypothesis: dict, diagnostic_graph: dict | DiagnosticGraph) -> tuple[bool, str]:
    """Every consecutive pair in causal_chain must have an edge in diagnostic_graph."""
    chain = hypothesis.get("causal_chain", [])
    if len(chain) < 2:
        return True, "Causal chain too short to validate (trivially valid)"

    # Build adjacency from diagnostic graph edges
    edges_list = []
    if isinstance(diagnostic_graph, DiagnosticGraph):
        edges_list = diagnostic_graph.edges
    elif isinstance(diagnostic_graph, dict):
        edges_list = diagnostic_graph.get("edges", [])

    edge_set: set[tuple[str, str]] = set()
    from_types: dict[str, set[str]] = defaultdict(set)
    for edge in edges_list:
        if isinstance(edge, dict):
            f, t = edge.get("from_id", ""), edge.get("to_id", "")
        else:
            f, t = edge.from_id, edge.to_id
        edge_set.add((f, t))
        # Also track signal_type pairs for chain validation
        f_type = f.split("/")[1] if "/" in f else f
        t_type = t.split("/")[1] if "/" in t else t
        from_types[f_type].add(t_type)

    broken = []
    for i in range(len(chain) - 1):
        a, b = chain[i], chain[i + 1]
        # Check if there's a direct edge or a type-level edge
        if b not in from_types.get(a, set()):
            # Also check exact node id pairs
            found = False
            for (f, t) in edge_set:
                if a in f and b in t:
                    found = True
                    break
            if not found:
                broken.append(f"{a} -> {b}")
    if broken:
        return False, f"Broken causal chain links: {'; '.join(broken[:3])}"
    return True, "All causal chain links have edges"


# ---------------------------------------------------------------------------
# Layer 4: Contradiction ratio
# ---------------------------------------------------------------------------

def _check_contradiction_ratio(hypothesis: dict) -> tuple[bool, str, str]:
    """
    sum(contradicting weights) / sum(supporting weights).
    >1.0 = REJECTED, >0.5 = WEAKENED, else VALID.
    Returns (passed, reason, verdict_override).
    """
    supporting = hypothesis.get("supporting_evidence", [])
    contradicting = hypothesis.get("contradicting_evidence", [])

    support_sum = sum(e.get("weight", 0.5) for e in supporting) if supporting else 0.0
    contra_sum = sum(e.get("weight", 0.5) for e in contradicting) if contradicting else 0.0

    if support_sum == 0 and contra_sum == 0:
        return True, "No evidence weights to compare", ""

    ratio = contra_sum / support_sum if support_sum > 0 else (999.0 if contra_sum > 0 else 0.0)

    if ratio > 1.0:
        return False, f"Contradiction ratio {ratio:.2f} > 1.0 — evidence contradicts hypothesis", "REJECTED"
    if ratio > 0.5:
        return True, f"Contradiction ratio {ratio:.2f} > 0.5 — hypothesis weakened", "WEAKENED"
    return True, f"Contradiction ratio {ratio:.2f} — acceptable", ""


# ---------------------------------------------------------------------------
# Layer 5: Temporal consistency
# ---------------------------------------------------------------------------

def _check_temporal_consistency(
    hypothesis: dict,
    diagnostic_graph: dict | DiagnosticGraph,
) -> tuple[bool, str]:
    """Root cause node first_seen <= all downstream nodes first_seen."""
    root = hypothesis.get("root_resource", "")
    if not root:
        return True, "No root_resource to check temporal consistency"

    nodes_map: dict[str, dict] = {}
    if isinstance(diagnostic_graph, DiagnosticGraph):
        nodes_map = {k: v.model_dump() if hasattr(v, "model_dump") else v for k, v in diagnostic_graph.nodes.items()}
    elif isinstance(diagnostic_graph, dict):
        nodes_map = diagnostic_graph.get("nodes", {})

    # Find root node
    root_node = None
    for nid, ndata in nodes_map.items():
        nd = ndata if isinstance(ndata, dict) else {}
        if nd.get("resource_key", "") == root or root in nid:
            root_node = nd
            break

    if not root_node or not root_node.get("first_seen"):
        return True, "Root node has no first_seen timestamp (skipped)"

    root_first = root_node["first_seen"]
    violations = []
    chain_resources = set()
    for ev in hypothesis.get("supporting_evidence", []):
        rk = ev.get("resource_key", "")
        if rk:
            chain_resources.add(rk)

    for nid, ndata in nodes_map.items():
        nd = ndata if isinstance(ndata, dict) else {}
        rk = nd.get("resource_key", "")
        if rk in chain_resources and rk != root:
            fs = nd.get("first_seen", "")
            if fs and fs < root_first:
                violations.append(f"{rk} first_seen={fs} < root {root_first}")

    if violations:
        return False, f"Temporal violation: {'; '.join(violations[:3])}"
    return True, "Root cause appeared before or at same time as downstream"


# ---------------------------------------------------------------------------
# Layer 6: Graph reachability
# ---------------------------------------------------------------------------

def _check_graph_reachability(
    hypothesis: dict,
    diagnostic_graph: dict | DiagnosticGraph,
) -> tuple[bool, str]:
    """root_resource can reach all affected_issues resources via BFS in diagnostic graph."""
    root = hypothesis.get("root_resource", "")
    affected = hypothesis.get("affected_issues", [])
    if not root or not affected:
        return True, "No root/affected_issues to check reachability"

    # Ensure we have a DiagnosticGraph object for bfs_reachable
    if isinstance(diagnostic_graph, dict):
        try:
            graph_obj = DiagnosticGraph(**diagnostic_graph)
        except Exception:
            return True, "Could not parse diagnostic_graph for BFS (skipped)"
    else:
        graph_obj = diagnostic_graph

    # Find root node id
    root_node_id = None
    for nid, ndata in graph_obj.nodes.items():
        if ndata.resource_key == root or root in nid:
            root_node_id = nid
            break

    if not root_node_id:
        return True, "Root node not found in graph (skipped)"

    reachable = bfs_reachable(graph_obj, root_node_id)
    reachable_resources = set()
    for nid in reachable:
        nd = graph_obj.nodes.get(nid)
        if nd:
            reachable_resources.add(nd.resource_key)
            reachable_resources.add(nid)

    unreachable = []
    for issue_id in affected:
        # Check if issue_id or a resource matching it is reachable
        found = False
        for r in reachable_resources:
            if issue_id in r or r in issue_id:
                found = True
                break
        if not found:
            unreachable.append(issue_id)

    if unreachable:
        return False, f"Unreachable from root: {', '.join(unreachable[:3])}"
    return True, "All affected issues reachable from root via BFS"


# ---------------------------------------------------------------------------
# Main critic node
# ---------------------------------------------------------------------------

@traced_node(timeout_seconds=8)
async def critic_validator(state: dict, config: dict) -> dict:
    """Validate hypotheses with 6-layer checks. Deterministic, no LLM."""
    hypotheses = state.get("ranked_hypotheses", [])
    if not hypotheses:
        return {
            "critic_result": {
                "validations": [],
                "dropped_hypotheses": [],
                "weakened_hypotheses": [],
                "warnings": [],
            }
        }

    # Build lookup structures
    normalized_signals = state.get("normalized_signals", [])
    signals_by_id: dict[str, dict] = {}
    for sig in normalized_signals:
        s = sig if isinstance(sig, dict) else sig.model_dump() if hasattr(sig, "model_dump") else {}
        sid = s.get("signal_id", "")
        if sid:
            signals_by_id[sid] = s

    diagnostic_graph = state.get("diagnostic_graph", {})
    topology = state.get("scoped_topology_graph") or state.get("topology_graph", {})
    topo_nodes = topology.get("nodes", {}) if isinstance(topology, dict) else {}

    validations = []
    dropped: list[str] = []
    weakened: list[str] = []
    warnings: list[str] = []

    for h in hypotheses:
        h_dict = h if isinstance(h, dict) else h.model_dump() if hasattr(h, "model_dump") else {}
        h_id = h_dict.get("hypothesis_id", "unknown")
        checks_passed: list[str] = []
        checks_failed: list[str] = []
        verdict = "VALID"

        # Layer 1: Evidence traceable
        ok, reason = _check_evidence_traceable(h_dict, signals_by_id)
        (checks_passed if ok else checks_failed).append(f"evidence_traceable: {reason}")

        # Layer 2: Resource exists
        ok, reason = _check_resource_exists(h_dict, topo_nodes)
        (checks_passed if ok else checks_failed).append(f"resource_exists: {reason}")

        # Layer 3: Causal chain valid
        ok, reason = _check_causal_chain_valid(h_dict, diagnostic_graph)
        (checks_passed if ok else checks_failed).append(f"causal_chain_valid: {reason}")

        # Layer 4: Contradiction ratio
        ok, reason, verdict_override = _check_contradiction_ratio(h_dict)
        (checks_passed if ok else checks_failed).append(f"contradiction_ratio: {reason}")
        if verdict_override == "REJECTED":
            verdict = "REJECTED"
        elif verdict_override == "WEAKENED" and verdict != "REJECTED":
            verdict = "WEAKENED"

        # Layer 5: Temporal consistency
        ok, reason = _check_temporal_consistency(h_dict, diagnostic_graph)
        (checks_passed if ok else checks_failed).append(f"temporal_consistency: {reason}")

        # Layer 6: Graph reachability
        ok, reason = _check_graph_reachability(h_dict, diagnostic_graph)
        (checks_passed if ok else checks_failed).append(f"graph_reachability: {reason}")

        # Determine final verdict from failures (if not already overridden)
        if verdict != "REJECTED" and len(checks_failed) >= 3:
            verdict = "REJECTED"
        elif verdict != "REJECTED" and checks_failed and verdict == "VALID":
            verdict = "WEAKENED"

        if verdict == "REJECTED":
            dropped.append(h_id)
        elif verdict == "WEAKENED":
            weakened.append(h_id)

        validations.append({
            "hypothesis_id": h_id,
            "verdict": verdict,
            "reason": checks_failed[0] if checks_failed else "All checks passed",
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
        })

    if dropped or weakened:
        warnings.append(
            f"Critic: {len(dropped)} hypotheses rejected, {len(weakened)} weakened out of {len(hypotheses)}"
        )
        logger.info(
            "Critic validated %d hypotheses: %d valid, %d weakened, %d rejected",
            len(hypotheses),
            len(hypotheses) - len(dropped) - len(weakened),
            len(weakened),
            len(dropped),
            extra={"action": "critic_validation"},
        )

    return {
        "critic_result": {
            "validations": validations,
            "dropped_hypotheses": dropped,
            "weakened_hypotheses": weakened,
            "warnings": warnings,
        }
    }
