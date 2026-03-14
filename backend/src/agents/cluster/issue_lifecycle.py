"""Issue lifecycle classifier with 9 states and priority scoring."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from src.agents.cluster.state import (
    IssueState, DiagnosticIssue, DiagnosticGraph, DiagnosticNode,
    NormalizedSignal, LifecycleThresholds,
)
from src.agents.cluster.temporal_analyzer import detect_worsening, detect_flapping
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

STATE_WEIGHT = {
    IssueState.ACTIVE_DISRUPTION: 4.0,
    IssueState.WORSENING: 2.5,
    IssueState.NEW: 2.0,
    IssueState.EXISTING: 0.5,
    IssueState.LONG_STANDING: 0.0,
    IssueState.INTERMITTENT: 0.5,
    IssueState.SYMPTOM: -1.5,
    IssueState.RESOLVED: -3.0,
    IssueState.ACKNOWLEDGED: -2.0,
}

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def classify_issue_state(
    resource_temporal: dict,
    is_symptom: bool,
    blast_radius: int,
    thresholds: LifecycleThresholds,
) -> IssueState:
    """Classify a single issue into lifecycle state."""
    if is_symptom:
        return IssueState.SYMPTOM

    event_age = resource_temporal.get("resource_age_seconds", 0)
    velocity = resource_temporal.get("restart_velocity", 0.0)

    # Active disruption: recent events + real blast radius or high velocity
    if (event_age < thresholds.active_event_age_seconds
        and (velocity > thresholds.active_restart_velocity or blast_radius >= thresholds.active_blast_radius_min)):
        return IssueState.ACTIVE_DISRUPTION

    # Worsening: trend detection
    if detect_worsening(resource_temporal, {"worsening_rate_multiplier": thresholds.worsening_rate_multiplier}):
        return IssueState.WORSENING

    # Flapping
    flap_count = detect_flapping(resource_temporal, {"flap_count_threshold": thresholds.flap_count_threshold})
    if flap_count >= thresholds.flap_count_threshold:
        return IssueState.INTERMITTENT

    # New: first seen recently
    first_seen_seconds = resource_temporal.get("resource_age_seconds", 0)
    if first_seen_seconds < thresholds.new_first_seen_seconds:
        return IssueState.NEW

    # Long-standing
    if first_seen_seconds > thresholds.long_standing_age_seconds:
        return IssueState.LONG_STANDING

    return IssueState.EXISTING


def compute_priority_score(
    state: IssueState,
    severity: str,
    blast_radius: int,
    is_root_cause: bool,
    is_symptom: bool = False,
) -> float:
    """Compute priority score for sorting issues."""
    base = (
        SEVERITY_WEIGHT.get(severity, 2)
        + 0.5 * blast_radius
        + STATE_WEIGHT.get(state, 0.0)
        + (2.0 if is_root_cause else 0)
    )
    if is_symptom:
        return min(base, 3.0)
    return base


def build_diagnostic_issues(
    diagnostic_graph: dict,
    signals: list[dict],
    pattern_matches: list[dict],
    temporal_data: dict,
    thresholds: LifecycleThresholds | None = None,
) -> list[DiagnosticIssue]:
    """Build and classify diagnostic issues from the evidence graph."""
    if thresholds is None:
        thresholds = LifecycleThresholds()

    if not diagnostic_graph or not isinstance(diagnostic_graph, dict):
        logger.warning("Empty or invalid diagnostic graph")
        return []
    if not diagnostic_graph.get("nodes"):
        logger.warning("Diagnostic graph has no nodes")
        return []
    try:
        graph = DiagnosticGraph(**diagnostic_graph)
    except Exception as e:
        logger.error("Failed to parse diagnostic graph: %s", e)
        return []
    resource_temporals = temporal_data.get("resource_temporals", {})

    # Build adjacency for blast radius calculation
    adj: dict[str, set[str]] = defaultdict(set)
    incoming_causes: dict[str, set[str]] = defaultdict(set)
    symptom_of: dict[str, str] = {}  # node_id -> cause_node_id

    for edge in graph.edges:
        adj[edge.from_id].add(edge.to_id)
        if edge.edge_type == "CAUSES":
            incoming_causes[edge.to_id].add(edge.from_id)
        if edge.edge_type == "SYMPTOM_OF":
            symptom_of[edge.to_id] = edge.from_id

    # Group signals by resource_key to form issues
    resource_signals: dict[str, list[str]] = defaultdict(list)  # resource_key -> [node_ids]
    for node_id, node in graph.nodes.items():
        resource_signals[node.resource_key].append(node_id)

    # Build issues per resource
    issues: list[DiagnosticIssue] = []
    now = datetime.now(timezone.utc).isoformat()

    for resource_key, node_ids in resource_signals.items():
        if not node_ids:
            continue

        # Get representative node
        primary_node = graph.nodes[node_ids[0]]

        # Determine if this is a symptom
        is_symptom = any(nid in symptom_of for nid in node_ids)
        root_cause_id = ""
        if is_symptom:
            cause_nid = symptom_of.get(node_ids[0], "")
            if cause_nid and cause_nid in graph.nodes:
                root_cause_id = graph.nodes[cause_nid].resource_key

        # Determine if this is a root cause (has outgoing CAUSES but no incoming CAUSES)
        has_outgoing = any(nid in adj for nid in node_ids)
        has_incoming = any(nid in incoming_causes for nid in node_ids)
        is_root_cause = has_outgoing and not has_incoming and not is_symptom

        # Calculate blast radius (downstream reachable resources)
        downstream = set()
        for nid in node_ids:
            for downstream_nid in adj.get(nid, set()):
                if downstream_nid in graph.nodes:
                    downstream.add(graph.nodes[downstream_nid].resource_key)
        blast_radius = len(downstream)

        # Get temporal data
        rt = resource_temporals.get(resource_key, {})

        # Classify state
        state = classify_issue_state(rt, is_symptom, blast_radius, thresholds)

        # Get severity (highest among signals for this resource)
        severities = [graph.nodes[nid].severity for nid in node_ids]
        severity = "critical" if "critical" in severities else "high" if "high" in severities else "medium"

        # Compute priority
        priority = compute_priority_score(state, severity, blast_radius, is_root_cause, is_symptom=is_symptom)

        # Find matching patterns
        matched_pattern_ids = []
        for pm in pattern_matches:
            pm_dict = pm if isinstance(pm, dict) else pm.model_dump()
            if resource_key in pm_dict.get("affected_resources", []):
                matched_pattern_ids.append(pm_dict.get("pattern_id", ""))

        # Build description from signal types
        sig_types = list(set(graph.nodes[nid].signal_type for nid in node_ids))
        description = f"{', '.join(sig_types)} on {resource_key}"

        issues.append(DiagnosticIssue(
            issue_id=f"issue-{resource_key.replace('/', '-')}",
            state=state,
            priority_score=round(priority, 2),
            first_seen=rt.get("first_seen", now),
            last_state_change=now,
            state_duration_seconds=0,
            event_count_recent=rt.get("event_count_recent", 0),
            event_count_baseline=rt.get("event_count_baseline", 0),
            restart_velocity=rt.get("restart_velocity", 0.0),
            severity_trend="stable",
            is_root_cause=is_root_cause,
            is_symptom=is_symptom,
            root_cause_id=root_cause_id,
            blast_radius=blast_radius,
            affected_resources=sorted(downstream),
            signals=[graph.nodes[nid].signal_type for nid in node_ids],
            pattern_matches=matched_pattern_ids,
            anomaly_ids=node_ids,
            description=description,
            severity=severity,
        ))

    # Sort by priority descending
    issues.sort(key=lambda i: i.priority_score, reverse=True)

    logger.info("Classified %d issues: %s",
                len(issues),
                {s.value: sum(1 for i in issues if i.state == s) for s in IssueState if sum(1 for i in issues if i.state == s) > 0})

    return issues


@traced_node(timeout_seconds=5)
async def issue_lifecycle_classifier(state: dict, config: dict) -> dict:
    """Classify issues into lifecycle states. Deterministic, zero LLM cost."""
    diagnostic_graph = state.get("diagnostic_graph", {})
    signals = state.get("normalized_signals", [])
    pattern_matches = state.get("pattern_matches", [])
    temporal_data = state.get("temporal_analysis", {})

    thresholds_dict = config.get("configurable", {}).get("lifecycle_thresholds")
    thresholds = LifecycleThresholds(**thresholds_dict) if thresholds_dict else LifecycleThresholds()

    issues = build_diagnostic_issues(diagnostic_graph, signals, pattern_matches, temporal_data, thresholds)

    # Build lifecycle summary
    lifecycle_summary = {}
    for issue in issues:
        state_val = issue.state.value if hasattr(issue.state, 'value') else str(issue.state)
        lifecycle_summary[state_val] = lifecycle_summary.get(state_val, 0) + 1

    return {
        "diagnostic_issues": [i.model_dump(mode="json") for i in issues],
    }
