"""Causal Firewall — two-tier pre-LLM filtering of causal links."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.causal_invariants import check_hard_block, SOFT_RULES
from src.agents.cluster.state import BlockedLink, CausalAnnotation, CausalSearchSpace
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_kind(resource_key: str) -> str:
    """Extract kind from resource key like 'pod/namespace/name' or 'node/name'."""
    return resource_key.split("/")[0]


def _generate_candidate_links(clusters: list[dict], topo_edges: list[dict]) -> list[dict]:
    """Generate all potential causal links from issue clusters + topology."""
    links: list[dict] = []

    for cluster in clusters:
        alerts = cluster.get("alerts", [])
        # Every pair of alerts in a cluster is a potential causal link
        for i, a in enumerate(alerts):
            for j, b in enumerate(alerts):
                if i >= j:
                    continue
                links.append({
                    "from": a["resource_key"],
                    "to": b["resource_key"],
                    "cluster_id": cluster["cluster_id"],
                })
                links.append({
                    "from": b["resource_key"],
                    "to": a["resource_key"],
                    "cluster_id": cluster["cluster_id"],
                })

    return links


def _check_soft_rules(from_key: str, to_key: str, state: dict) -> CausalAnnotation | None:
    """Check Tier 2 soft rules based on context."""
    topo_nodes = (state.get("scoped_topology_graph") or state.get("topology_graph", {})).get("nodes", {})
    from_node = topo_nodes.get(from_key, {})
    to_node = topo_nodes.get(to_key, {})
    from_kind = _extract_kind(from_key)
    to_kind = _extract_kind(to_key)

    # SOFT-001: Node transient — no cascading effects
    if from_kind == "node" and from_node.get("status") == "NotReady":
        # Check if any pods on this node were actually affected
        topo_edges = (state.get("scoped_topology_graph") or state.get("topology_graph", {})).get("edges", [])
        hosted_pods = [e["to_key"] for e in topo_edges if e["from_key"] == from_key and e["relation"] == "hosts"]
        problem_pods = [p for p in hosted_pods if topo_nodes.get(p, {}).get("status") in ("Evicted", "CrashLoopBackOff", "OOMKilled")]
        if not problem_pods:
            return CausalAnnotation(
                from_resource=from_key, to_resource=to_key,
                rule_id="SOFT-001", confidence_hint=0.2,
                reason="Node issue with no observed cascading effects on hosted pods",
                supporting_evidence=["no_evictions", "no_pod_failures"],
            )

    # SOFT-003: PVC pending but storage backend healthy
    if from_kind == "pvc" and from_node.get("status") == "Pending":
        return CausalAnnotation(
            from_resource=from_key, to_resource=to_key,
            rule_id="SOFT-003", confidence_hint=0.25,
            reason="PVC pending — check if provisioner or quota issue rather than storage failure",
            supporting_evidence=["pvc_pending_status"],
        )

    return None


@traced_node(timeout_seconds=10)
async def causal_firewall(state: dict, config: dict) -> dict:
    """LangGraph node: two-tier causal link filtering."""
    clusters = state.get("issue_clusters", [])
    topo_edges = (state.get("scoped_topology_graph") or state.get("topology_graph", {})).get("edges", [])

    # Generate all candidate links
    candidate_links = _generate_candidate_links(clusters, topo_edges)

    valid: list[dict] = []
    annotated: list[dict] = []
    blocked: list[BlockedLink] = []
    now = datetime.now(timezone.utc).isoformat()

    for link in candidate_links:
        from_kind = _extract_kind(link["from"])
        to_kind = _extract_kind(link["to"])

        # Tier 1: Hard block check
        invariant = check_hard_block(from_kind, to_kind)
        if invariant:
            blocked.append(BlockedLink(
                from_resource=link["from"],
                to_resource=link["to"],
                reason_code="violates_topology_direction",
                invariant_id=invariant.id,
                invariant_description=invariant.description,
                timestamp=now,
            ))
            continue

        # Tier 2: Soft annotation check
        annotation = _check_soft_rules(link["from"], link["to"], state)
        if annotation:
            link_with_annotation = {**link, "annotation": annotation.model_dump(mode="json")}
            annotated.append(link_with_annotation)
            continue

        # Passed both tiers
        valid.append(link)

    search_space = CausalSearchSpace(
        valid_links=valid,
        annotated_links=annotated,
        blocked_links=blocked,
        total_evaluated=len(candidate_links),
        total_blocked=len(blocked),
        total_annotated=len(annotated),
    )

    logger.info("Causal firewall complete", extra={
        "action": "firewall_complete",
        "evaluated": search_space.total_evaluated,
        "blocked": search_space.total_blocked,
        "annotated": search_space.total_annotated,
        "valid": len(valid),
    })

    return {"causal_search_space": search_space.model_dump(mode="json")}
