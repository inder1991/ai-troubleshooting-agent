"""Multi-hypothesis root cause engine.

Generates, scores, deduplicates, and ranks competing root-cause hypotheses
from pattern matches, the diagnostic evidence graph, and correlated signals.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from src.agents.cluster.state import (
    DiagnosticGraph,
    DiagnosticIssue,
    DiagnosticNode,
    Hypothesis,
    IssueState,
    NormalizedSignal,
    PatternMatch,
    WeightedEvidence,
)
from src.agents.cluster.diagnostic_graph_builder import bfs_reachable, graph_has_path
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 1. Signal reliability weights
# ---------------------------------------------------------------------------

SIGNAL_RELIABILITY: dict[str, float] = {
    # Hard infrastructure signals (highest trust)
    "NODE_DISK_PRESSURE": 1.0,
    "NODE_MEMORY_PRESSURE": 1.0,
    "NODE_PID_PRESSURE": 1.0,
    "NODE_NOT_READY": 1.0,
    "OOM_KILLED": 0.95,
    "CRASHLOOP": 0.9,
    "POD_EVICTION": 0.9,
    # Workload signals
    "IMAGE_PULL_BACKOFF": 0.85,
    "POD_PENDING": 0.8,
    "DEPLOYMENT_DEGRADED": 0.8,
    "ROLLOUT_STUCK": 0.75,
    "HPA_MAXED": 0.7,
    # Service/network
    "SERVICE_ZERO_ENDPOINTS": 0.85,
    "LB_PENDING": 0.7,
    "DNS_RESOLUTION_FAILURE": 0.8,
    "NETWORK_POLICY_DENY": 0.75,
    # Storage
    "PVC_PENDING": 0.8,
    "VOLUME_MOUNT_FAILURE": 0.85,
    # RBAC
    "RBAC_DENIED": 0.7,
    # Soft signals (lowest trust)
    "LOG_ERROR": 0.4,
    "METRIC_ANOMALY": 0.5,
    "EVENT_WARNING": 0.45,
}

# ---------------------------------------------------------------------------
# 2. Signal families — used for deduplication merge keys
# ---------------------------------------------------------------------------

SIGNAL_FAMILIES: dict[str, str] = {
    "NODE_DISK_PRESSURE": "node_pressure",
    "NODE_MEMORY_PRESSURE": "node_pressure",
    "NODE_PID_PRESSURE": "node_pressure",
    "NODE_NOT_READY": "node_health",
    "OOM_KILLED": "pod_crash",
    "CRASHLOOP": "pod_crash",
    "POD_EVICTION": "pod_lifecycle",
    "IMAGE_PULL_BACKOFF": "pod_startup",
    "POD_PENDING": "pod_startup",
    "DEPLOYMENT_DEGRADED": "workload_health",
    "ROLLOUT_STUCK": "workload_health",
    "HPA_MAXED": "scaling",
    "SERVICE_ZERO_ENDPOINTS": "service_availability",
    "LB_PENDING": "service_availability",
    "DNS_RESOLUTION_FAILURE": "network",
    "NETWORK_POLICY_DENY": "network",
    "PVC_PENDING": "storage",
    "VOLUME_MOUNT_FAILURE": "storage",
    "RBAC_DENIED": "rbac",
    "LOG_ERROR": "soft_signal",
    "METRIC_ANOMALY": "soft_signal",
    "EVENT_WARNING": "soft_signal",
}

# ---------------------------------------------------------------------------
# 3. Contradiction rules
# ---------------------------------------------------------------------------

CONTRADICTION_RULES: list[dict[str, str | list[str]]] = [
    {
        "id": "CR-001",
        "hypothesis_type": "NODE_DISK_PRESSURE",
        "contradicted_by": ["NODE_DISK_OK"],
        "reason": "Disk pressure contradicted by healthy disk metrics",
    },
    {
        "id": "CR-002",
        "hypothesis_type": "OOM_KILLED",
        "contradicted_by": ["MEMORY_WITHIN_LIMITS", "NO_OOM_EVENTS"],
        "reason": "OOM hypothesis contradicted by normal memory usage",
    },
    {
        "id": "CR-003",
        "hypothesis_type": "NETWORK_POLICY_DENY",
        "contradicted_by": ["CONNECTIVITY_OK", "NETWORK_POLICY_ALLOW"],
        "reason": "Network deny contradicted by successful connectivity",
    },
    {
        "id": "CR-004",
        "hypothesis_type": "CRASHLOOP",
        "contradicted_by": ["POD_RUNNING_STABLE"],
        "reason": "CrashLoop contradicted by stable running pod",
    },
    {
        "id": "CR-005",
        "hypothesis_type": "PVC_PENDING",
        "contradicted_by": ["PVC_BOUND"],
        "reason": "PVC pending contradicted by bound PVC status",
    },
    {
        "id": "CR-006",
        "hypothesis_type": "DNS_RESOLUTION_FAILURE",
        "contradicted_by": ["DNS_RESOLVES_OK"],
        "reason": "DNS failure contradicted by successful resolution",
    },
    {
        "id": "CR-007",
        "hypothesis_type": "RBAC_DENIED",
        "contradicted_by": ["RBAC_ALLOWED"],
        "reason": "RBAC denied contradicted by successful auth",
    },
    {
        "id": "CR-008",
        "hypothesis_type": "IMAGE_PULL_BACKOFF",
        "contradicted_by": ["IMAGE_PULL_SUCCESS"],
        "reason": "Image pull failure contradicted by successful pull",
    },
]

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

MAX_SIGNAL_CONTRIBUTION = 0.6
MIN_EVIDENCE_SCORE = 0.4
MAX_HYPOTHESES_PER_ISSUE = 3
MAX_TOTAL_HYPOTHESES = 8
TEMPORAL_PROXIMITY_SECONDS = 60


# ---------------------------------------------------------------------------
# 4. hypotheses_from_patterns
# ---------------------------------------------------------------------------


def hypotheses_from_patterns(pattern_matches: list[dict]) -> list[Hypothesis]:
    """Each PatternMatch -> Hypothesis at 0.5 + confidence_boost."""
    hypotheses: list[Hypothesis] = []
    for pm_dict in pattern_matches:
        pm = PatternMatch(**pm_dict) if isinstance(pm_dict, dict) else pm_dict
        base = 0.5 + pm.confidence_boost
        evidence_items: list[WeightedEvidence] = []
        for cond in pm.matched_conditions:
            weight = SIGNAL_RELIABILITY.get(cond, 0.5)
            evidence_items.append(WeightedEvidence(
                signal_id=f"pattern/{pm.pattern_id}/{cond}",
                signal_type=cond,
                resource_key=pm.affected_resources[0] if pm.affected_resources else "",
                weight=weight,
                reliability=weight,
                relevance=f"Matched pattern condition: {cond}",
            ))

        cause = pm.probable_causes[0] if pm.probable_causes else pm.name
        cause_type = pm.matched_conditions[0] if pm.matched_conditions else pm.pattern_id
        root_resource = pm.affected_resources[0] if pm.affected_resources else ""

        h = Hypothesis(
            hypothesis_id=f"hyp/pattern/{pm.pattern_id}/{uuid.uuid4().hex[:8]}",
            cause=cause,
            cause_type=cause_type,
            source="pattern",
            supporting_evidence=evidence_items,
            evidence_score=base,
            confidence=base,
            affected_issues=[],
            explains_count=len(pm.affected_resources),
            blast_radius=len(pm.affected_resources),
            root_resource=root_resource,
            causal_chain=[cause_type],
            depth=0,
            evidence_ids=[e.signal_id for e in evidence_items],
        )
        hypotheses.append(h)
    return hypotheses


# ---------------------------------------------------------------------------
# 5. hypotheses_from_graph
# ---------------------------------------------------------------------------


def _find_root_nodes(graph: DiagnosticGraph) -> list[str]:
    """Root nodes: have outgoing CAUSES edges, no incoming CAUSES edges."""
    has_outgoing_causes: set[str] = set()
    has_incoming_causes: set[str] = set()
    for edge in graph.edges:
        if edge.edge_type == "CAUSES":
            has_outgoing_causes.add(edge.from_id)
            has_incoming_causes.add(edge.to_id)
    # Roots: have outgoing CAUSES but no incoming CAUSES
    roots = has_outgoing_causes - has_incoming_causes
    # If no explicit CAUSES edges, fall back to nodes with outgoing edges only
    if not roots:
        all_from = {e.from_id for e in graph.edges}
        all_to = {e.to_id for e in graph.edges}
        roots = all_from - all_to
    return list(roots)


def _causal_chain_from_bfs(graph: DiagnosticGraph, start_id: str) -> list[str]:
    """Build a causal chain of signal types from BFS reachable set."""
    reachable = bfs_reachable(graph, start_id)
    chain: list[str] = []
    for nid in reachable:
        node = graph.nodes.get(nid)
        if node and node.signal_type and node.signal_type not in chain:
            chain.append(node.signal_type)
    return chain


def hypotheses_from_graph(diagnostic_graph: dict | DiagnosticGraph) -> list[Hypothesis]:
    """Root nodes (outgoing CAUSES, no incoming) -> Hypothesis with causal chain."""
    if isinstance(diagnostic_graph, dict):
        graph = DiagnosticGraph(**diagnostic_graph)
    else:
        graph = diagnostic_graph

    if not graph.nodes:
        return []

    roots = _find_root_nodes(graph)
    hypotheses: list[Hypothesis] = []

    for root_id in roots:
        root_node = graph.nodes.get(root_id)
        if not root_node:
            continue

        reachable = bfs_reachable(graph, root_id)
        causal_chain = _causal_chain_from_bfs(graph, root_id)
        depth = len(causal_chain) - 1 if causal_chain else 0

        # Build supporting evidence from reachable nodes
        evidence_items: list[WeightedEvidence] = []
        affected_resources: set[str] = set()
        for nid in reachable:
            node = graph.nodes.get(nid)
            if not node:
                continue
            affected_resources.add(node.resource_key)
            weight = SIGNAL_RELIABILITY.get(node.signal_type, node.reliability)
            evidence_items.append(WeightedEvidence(
                signal_id=node.node_id,
                signal_type=node.signal_type,
                resource_key=node.resource_key,
                weight=weight,
                reliability=node.reliability,
                relevance=f"Reachable from root {root_node.signal_type}",
            ))

        # Base score from root reliability
        base = 0.5 + root_node.reliability * 0.3

        h = Hypothesis(
            hypothesis_id=f"hyp/graph/{root_id}/{uuid.uuid4().hex[:8]}",
            cause=f"{root_node.signal_type} on {root_node.resource_key}",
            cause_type=root_node.signal_type,
            source="graph_traversal",
            supporting_evidence=evidence_items,
            evidence_score=base,
            confidence=base,
            explains_count=len(reachable),
            blast_radius=len(affected_resources),
            root_resource=root_node.resource_key,
            causal_chain=causal_chain,
            depth=depth,
            evidence_ids=[e.signal_id for e in evidence_items],
        )
        hypotheses.append(h)

    return hypotheses


# ---------------------------------------------------------------------------
# 6. hypotheses_from_correlation
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: str) -> float | None:
    """Parse ISO timestamp to epoch seconds. Returns None on failure."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _extract_namespace_from_key(resource_key: str) -> str:
    """Extract namespace from resource_key like 'pod/production/app-xyz'."""
    parts = resource_key.split("/")
    return parts[1] if len(parts) >= 3 else ""


def hypotheses_from_correlation(
    signals: list[dict],
    diagnostic_graph: dict | DiagnosticGraph,
) -> list[Hypothesis]:
    """Signals sharing topology + namespace + temporal proximity (<60s) -> Hypothesis."""
    if isinstance(diagnostic_graph, dict):
        graph = DiagnosticGraph(**diagnostic_graph)
    else:
        graph = diagnostic_graph

    parsed_signals: list[NormalizedSignal] = []
    for s in signals:
        sig = NormalizedSignal(**s) if isinstance(s, dict) else s
        parsed_signals.append(sig)

    if len(parsed_signals) < 2:
        return []

    # Group signals by namespace
    ns_groups: dict[str, list[NormalizedSignal]] = defaultdict(list)
    for sig in parsed_signals:
        ns = sig.namespace or _extract_namespace_from_key(sig.resource_key)
        if ns:
            ns_groups[ns].append(sig)

    hypotheses: list[Hypothesis] = []

    for ns, ns_signals in ns_groups.items():
        if len(ns_signals) < 2:
            continue

        # Check temporal proximity within the group
        timestamped = []
        for sig in ns_signals:
            ts = _parse_timestamp(sig.timestamp)
            if ts is not None:
                timestamped.append((sig, ts))
        timestamped.sort(key=lambda x: x[1])

        # Find temporal clusters within TEMPORAL_PROXIMITY_SECONDS
        clusters: list[list[NormalizedSignal]] = []
        current_cluster: list[NormalizedSignal] = []
        last_ts: float | None = None

        for sig, ts in timestamped:
            if last_ts is None or (ts - last_ts) <= TEMPORAL_PROXIMITY_SECONDS:
                current_cluster.append(sig)
            else:
                if len(current_cluster) >= 2:
                    clusters.append(current_cluster)
                current_cluster = [sig]
            last_ts = ts

        if len(current_cluster) >= 2:
            clusters.append(current_cluster)

        # Also check topology adjacency for non-timestamped signals
        if not clusters and len(ns_signals) >= 2:
            # Fall back to namespace-only grouping
            clusters = [ns_signals]

        for cluster in clusters:
            # Verify topology adjacency: at least two signals must share a graph path
            has_topo_link = False
            for i, s1 in enumerate(cluster):
                for s2 in cluster[i + 1:]:
                    node1 = f"sig/{s1.signal_type}/{s1.resource_key}"
                    node2 = f"sig/{s2.signal_type}/{s2.resource_key}"
                    if (node1 in graph.nodes and node2 in graph.nodes
                            and (graph_has_path(graph, node1, node2)
                                 or graph_has_path(graph, node2, node1))):
                        has_topo_link = True
                        break
                if has_topo_link:
                    break

            if not has_topo_link and graph.nodes:
                # Without topology link, skip unless graph has no relevant nodes
                continue

            # Build hypothesis from the correlated cluster
            evidence_items: list[WeightedEvidence] = []
            resources: set[str] = set()
            signal_types: set[str] = set()
            for sig in cluster:
                weight = SIGNAL_RELIABILITY.get(sig.signal_type, sig.reliability)
                evidence_items.append(WeightedEvidence(
                    signal_id=sig.signal_id or f"corr/{sig.signal_type}/{sig.resource_key}",
                    signal_type=sig.signal_type,
                    resource_key=sig.resource_key,
                    weight=weight,
                    reliability=sig.reliability,
                    relevance=f"Correlated in namespace {ns} within {TEMPORAL_PROXIMITY_SECONDS}s",
                ))
                resources.add(sig.resource_key)
                signal_types.add(sig.signal_type)

            # Pick the highest-reliability signal as the cause
            best = max(cluster, key=lambda s: SIGNAL_RELIABILITY.get(s.signal_type, s.reliability))
            base = 0.5 + best.reliability * 0.2

            h = Hypothesis(
                hypothesis_id=f"hyp/corr/{ns}/{uuid.uuid4().hex[:8]}",
                cause=f"Correlated {', '.join(sorted(signal_types))} in namespace {ns}",
                cause_type=best.signal_type,
                source="signal_correlation",
                supporting_evidence=evidence_items,
                evidence_score=base,
                confidence=base,
                explains_count=len(cluster),
                blast_radius=len(resources),
                root_resource=best.resource_key,
                causal_chain=list(signal_types),
                depth=0,
                evidence_ids=[e.signal_id for e in evidence_items],
            )
            hypotheses.append(h)

    return hypotheses


# ---------------------------------------------------------------------------
# 7. collect_negative_evidence
# ---------------------------------------------------------------------------


def collect_negative_evidence(
    hypothesis: Hypothesis,
    all_signals: list[dict],
    ruled_out: list[str],
) -> list[WeightedEvidence]:
    """Find contradicting evidence from CONTRADICTION_RULES + ruled_out."""
    contradictions: list[WeightedEvidence] = []

    # Check CONTRADICTION_RULES
    for rule in CONTRADICTION_RULES:
        if hypothesis.cause_type != rule["hypothesis_type"]:
            continue
        contradicted_by = rule["contradicted_by"]
        for sig_dict in all_signals:
            sig = NormalizedSignal(**sig_dict) if isinstance(sig_dict, dict) else sig_dict
            if sig.signal_type in contradicted_by:
                # Only contradict if on the same resource or namespace
                if (sig.resource_key == hypothesis.root_resource
                        or _extract_namespace_from_key(sig.resource_key)
                        == _extract_namespace_from_key(hypothesis.root_resource)):
                    contradictions.append(WeightedEvidence(
                        signal_id=sig.signal_id or f"neg/{sig.signal_type}/{sig.resource_key}",
                        signal_type=sig.signal_type,
                        resource_key=sig.resource_key,
                        weight=SIGNAL_RELIABILITY.get(sig.signal_type, sig.reliability),
                        reliability=sig.reliability,
                        relevance=str(rule["reason"]),
                    ))

    # Check ruled_out list from domain reports
    for ro in ruled_out:
        ro_lower = ro.lower()
        cause_lower = hypothesis.cause_type.lower()
        cause_name_lower = hypothesis.cause.lower()
        if cause_lower in ro_lower or cause_name_lower in ro_lower:
            contradictions.append(WeightedEvidence(
                signal_id=f"ruled_out/{ro}",
                signal_type="RULED_OUT",
                resource_key=hypothesis.root_resource,
                weight=0.8,
                reliability=0.8,
                relevance=f"Domain agent ruled out: {ro}",
            ))

    return contradictions


# ---------------------------------------------------------------------------
# 8. score_hypothesis
# ---------------------------------------------------------------------------


def _logistic(x: float) -> float:
    """Logistic normalization to [0, 1]."""
    return 1.0 / (1.0 + math.exp(-x))


def score_hypothesis(h: Hypothesis) -> Hypothesis:
    """Score a hypothesis using evidence, contradictions, and bonuses.

    Formula:
        raw = capped_evidence - contradiction
              + explanatory_bonus + diversity_bonus - depth_penalty
        final = logistic(raw * 4 - 2)  # map to (0, 1)
    """
    # Capped evidence score: sum of weights, capped at MAX_SIGNAL_CONTRIBUTION
    evidence_sum = sum(e.weight for e in h.supporting_evidence)
    capped_evidence = min(evidence_sum, MAX_SIGNAL_CONTRIBUTION)

    # Contradiction penalty: sum of contradicting weights
    contradiction = sum(e.weight for e in h.contradicting_evidence)

    # Explanatory bonus: how many things this hypothesis explains
    explanatory_bonus = h.explains_count * 0.1

    # Diversity bonus: unique signal types in evidence
    unique_types = len({e.signal_type for e in h.supporting_evidence})
    diversity_bonus = unique_types * 0.05

    # Depth penalty: deeper causal chains are less certain
    depth_penalty = h.depth * 0.05

    raw = capped_evidence - contradiction + explanatory_bonus + diversity_bonus - depth_penalty

    # Logistic normalization
    final = _logistic(raw * 4.0 - 2.0)

    h.evidence_score = round(capped_evidence, 4)
    h.contradiction_penalty = round(contradiction, 4)
    h.confidence = round(final, 4)
    return h


# ---------------------------------------------------------------------------
# 9. deduplicate_hypotheses
# ---------------------------------------------------------------------------


def _merge_key(h: Hypothesis) -> str:
    """Dedup key: (resource_key, signal_family)."""
    family = SIGNAL_FAMILIES.get(h.cause_type, h.cause_type)
    return f"{h.root_resource}||{family}"


def deduplicate_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Merge hypotheses sharing (resource_key, signal_family). Keep highest confidence."""
    groups: dict[str, list[Hypothesis]] = defaultdict(list)
    for h in hypotheses:
        key = _merge_key(h)
        groups[key].append(h)

    merged: list[Hypothesis] = []
    for key, group in groups.items():
        # Sort by confidence descending, keep the best
        group.sort(key=lambda h: h.confidence, reverse=True)
        winner = group[0]

        # Absorb evidence from duplicates
        seen_ids: set[str] = set(winner.evidence_ids)
        for dup in group[1:]:
            for ev in dup.supporting_evidence:
                if ev.signal_id not in seen_ids:
                    winner.supporting_evidence.append(ev)
                    seen_ids.add(ev.signal_id)
            for ev in dup.contradicting_evidence:
                if ev.signal_id not in seen_ids:
                    winner.contradicting_evidence.append(ev)
                    seen_ids.add(ev.signal_id)
            # Merge explains count
            winner.explains_count = max(winner.explains_count, dup.explains_count)
            winner.blast_radius = max(winner.blast_radius, dup.blast_radius)

        winner.evidence_ids = list(seen_ids)
        merged.append(winner)

    return merged


# ---------------------------------------------------------------------------
# 10. filter_and_cap
# ---------------------------------------------------------------------------


def filter_and_cap(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Filter by MIN_EVIDENCE_SCORE, cap per issue and total."""
    # Filter below minimum
    filtered = [h for h in hypotheses if h.confidence >= MIN_EVIDENCE_SCORE]

    # Sort by confidence descending
    filtered.sort(key=lambda h: h.confidence, reverse=True)

    # Cap per issue: group by root_resource, keep top MAX_HYPOTHESES_PER_ISSUE
    resource_counts: dict[str, int] = defaultdict(int)
    capped: list[Hypothesis] = []
    for h in filtered:
        if resource_counts[h.root_resource] < MAX_HYPOTHESES_PER_ISSUE:
            capped.append(h)
            resource_counts[h.root_resource] += 1

    # Global cap
    return capped[:MAX_TOTAL_HYPOTHESES]


# ---------------------------------------------------------------------------
# 11. determine_root_causes
# ---------------------------------------------------------------------------


def determine_root_causes(ranked: list[Hypothesis]) -> dict:
    """If gap > 0.15 between top two: deterministic; else LLM disambiguation needed."""
    if not ranked:
        return {
            "root_causes": [],
            "selection_method": "none",
            "llm_reasoning_needed": False,
        }

    if len(ranked) == 1:
        return {
            "root_causes": [ranked[0].model_dump()],
            "selection_method": "deterministic_single",
            "llm_reasoning_needed": False,
        }

    top = ranked[0]
    runner_up = ranked[1]
    gap = top.confidence - runner_up.confidence

    if gap > 0.15:
        return {
            "root_causes": [top.model_dump()],
            "selection_method": "deterministic_gap",
            "llm_reasoning_needed": False,
        }
    else:
        # Ambiguous: include top candidates within the gap threshold
        ambiguous = [top]
        for h in ranked[1:]:
            if (top.confidence - h.confidence) <= 0.15:
                ambiguous.append(h)
            else:
                break
        return {
            "root_causes": [h.model_dump() for h in ambiguous],
            "selection_method": "llm_disambiguation",
            "llm_reasoning_needed": True,
        }


# ---------------------------------------------------------------------------
# 12. hypothesis_engine traced node
# ---------------------------------------------------------------------------


@traced_node(timeout_seconds=10)
async def hypothesis_engine(state: dict, config: dict) -> dict:
    """Multi-hypothesis root cause engine. Generates, scores, deduplicates,
    and ranks competing root-cause hypotheses."""

    pattern_matches = state.get("pattern_matches", [])
    signals = state.get("normalized_signals", [])
    diagnostic_graph_data = state.get("diagnostic_graph", {})
    issues: list[dict] = state.get("diagnostic_issues", [])

    # Collect ruled_out from domain reports
    ruled_out: list[str] = []
    for report in state.get("domain_reports", []):
        r = report if isinstance(report, dict) else report.model_dump()
        ruled_out.extend(r.get("ruled_out", []))

    # --- Generate hypotheses from three sources ---
    h_patterns = hypotheses_from_patterns(pattern_matches)
    h_graph = hypotheses_from_graph(diagnostic_graph_data)
    h_corr = hypotheses_from_correlation(signals, diagnostic_graph_data)

    all_hypotheses = h_patterns + h_graph + h_corr
    logger.info(
        "Generated hypotheses: %d pattern, %d graph, %d correlation",
        len(h_patterns), len(h_graph), len(h_corr),
    )

    # --- Collect negative evidence ---
    for h in all_hypotheses:
        contradictions = collect_negative_evidence(h, signals, ruled_out)
        h.contradicting_evidence = contradictions

    # --- Link hypotheses to issues ---
    issue_objs: list[DiagnosticIssue] = []
    for iss_dict in issues:
        iss = DiagnosticIssue(**iss_dict) if isinstance(iss_dict, dict) else iss_dict
        issue_objs.append(iss)

    for h in all_hypotheses:
        for iss in issue_objs:
            # Link if the hypothesis resource matches any affected resource
            if (h.root_resource in iss.affected_resources
                    or h.root_resource == iss.issue_id
                    or any(sig_id in h.evidence_ids for sig_id in iss.signals)):
                if iss.issue_id not in h.affected_issues:
                    h.affected_issues.append(iss.issue_id)
                    h.issue_state = iss.state.value if isinstance(iss.state, IssueState) else iss.state

    # --- Score ---
    for h in all_hypotheses:
        score_hypothesis(h)

    # --- Deduplicate ---
    deduped = deduplicate_hypotheses(all_hypotheses)

    # --- Re-score after dedup (evidence may have been absorbed) ---
    for h in deduped:
        score_hypothesis(h)

    # --- Filter and cap ---
    ranked = filter_and_cap(deduped)

    # --- Group by issue ---
    hypotheses_by_issue: dict[str, list[Hypothesis]] = defaultdict(list)
    for h in ranked:
        for issue_id in h.affected_issues:
            hypotheses_by_issue[issue_id].append(h)
    # Also add unlinked hypotheses under a special key
    for h in ranked:
        if not h.affected_issues:
            hypotheses_by_issue["_unlinked"].append(h)

    # --- Determine root causes ---
    hypothesis_selection = determine_root_causes(ranked)

    logger.info(
        "Hypothesis engine: %d ranked, selection=%s, llm_needed=%s",
        len(ranked),
        hypothesis_selection["selection_method"],
        hypothesis_selection["llm_reasoning_needed"],
    )

    return {
        "ranked_hypotheses": [h.model_dump() for h in ranked],
        "hypotheses_by_issue": {
            issue_id: [h.model_dump() for h in hs]
            for issue_id, hs in hypotheses_by_issue.items()
        },
        "hypothesis_selection": hypothesis_selection,
    }
