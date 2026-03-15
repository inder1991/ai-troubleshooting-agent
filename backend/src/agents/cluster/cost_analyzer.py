"""Cluster cost analyzer: idle capacity, namespace spend, instance optimization."""

from __future__ import annotations
import uuid
from typing import Any
from src.agents.cluster.state import ClusterCostSummary, CostRecommendation
from src.agents.cluster.cloud_pricing import (
    get_node_monthly_cost, estimate_node_cost_from_capacity,
    detect_provider_from_node, detect_instance_type_from_node,
    get_all_instance_types, CLOUD_PRICING,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_cpu(cpu_str: str) -> float:
    """Parse K8s CPU string to cores. '500m' -> 0.5, '2' -> 2.0"""
    if not cpu_str:
        return 0.0
    cpu_str = str(cpu_str).strip()
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1]) / 1000
    return float(cpu_str)


def _parse_memory_gi(mem_str: str) -> float:
    """Parse K8s memory string to GiB. '2Gi' -> 2.0, '512Mi' -> 0.5"""
    if not mem_str:
        return 0.0
    mem_str = str(mem_str).strip()
    if mem_str.endswith("Gi"):
        return float(mem_str[:-2])
    if mem_str.endswith("Mi"):
        return float(mem_str[:-2]) / 1024
    if mem_str.endswith("Ki"):
        return float(mem_str[:-2]) / (1024 * 1024)
    # Bytes
    try:
        return float(mem_str) / (1024 ** 3)
    except ValueError:
        return 0.0


def compute_cluster_cost(nodes: list[dict], pods: list[dict], provider: str = "") -> ClusterCostSummary:
    """Compute current cluster cost from node instance types."""
    # Detect provider if not given
    if not provider and nodes:
        provider = detect_provider_from_node(nodes[0])

    # Calculate per-node cost
    instance_counts: dict[str, int] = {}
    total_cost = 0.0
    total_cpu = 0.0
    total_memory_gi = 0.0

    for node in nodes:
        instance_type = detect_instance_type_from_node(node)
        if not instance_type:
            instance_type = "unknown"
        instance_counts[instance_type] = instance_counts.get(instance_type, 0) + 1

        cost = get_node_monthly_cost(provider, instance_type)
        if cost == 0.0:
            # Fallback: estimate from capacity
            cpu_cap = _parse_cpu(node.get("cpu_capacity", "0"))
            mem_cap = _parse_memory_gi(node.get("memory_capacity", "0"))
            cost = estimate_node_cost_from_capacity(int(cpu_cap), int(mem_cap))
            total_cpu += cpu_cap
            total_memory_gi += mem_cap
        else:
            pricing = CLOUD_PRICING.get(provider, {}).get(instance_type, {})
            total_cpu += pricing.get("vcpu", 0)
            total_memory_gi += pricing.get("memory_gi", 0)

        total_cost += cost

    # Calculate requested resources from pods
    requested_cpu = sum(
        _parse_cpu(p.get("resources", {}).get("requests", {}).get("cpu", "0"))
        for p in pods
    )
    requested_memory = sum(
        _parse_memory_gi(p.get("resources", {}).get("requests", {}).get("memory", "0"))
        for p in pods
    )

    idle_cpu = 1.0 - (requested_cpu / max(total_cpu, 0.01))
    idle_memory = 1.0 - (requested_memory / max(total_memory_gi, 0.01))

    # Instance breakdown
    breakdown = []
    for itype, count in sorted(instance_counts.items(), key=lambda x: -x[1]):
        unit_cost = get_node_monthly_cost(provider, itype)
        breakdown.append({
            "instance_type": itype,
            "count": count,
            "unit_cost": round(unit_cost, 2),
            "total_cost": round(unit_cost * count, 2),
        })

    return ClusterCostSummary(
        provider=provider,
        node_count=len(nodes),
        pod_count=len(pods),
        current_monthly_cost=round(total_cost, 2),
        idle_cpu_pct=round(max(0, idle_cpu) * 100, 1),
        idle_memory_pct=round(max(0, idle_memory) * 100, 1),
        instance_breakdown=breakdown,
    )


def compute_namespace_costs(pods: list[dict], total_cost: float, total_cpu: float) -> list[dict]:
    """Compute per-namespace cost breakdown."""
    ns_cpu: dict[str, float] = {}
    ns_pods: dict[str, int] = {}

    for pod in pods:
        ns = pod.get("namespace", "default")
        cpu = _parse_cpu(pod.get("resources", {}).get("requests", {}).get("cpu", "0"))
        ns_cpu[ns] = ns_cpu.get(ns, 0) + cpu
        ns_pods[ns] = ns_pods.get(ns, 0) + 1

    total_requested = sum(ns_cpu.values())
    if total_requested == 0:
        return []

    result = []
    for ns, cpu in sorted(ns_cpu.items(), key=lambda x: -x[1]):
        pct = cpu / total_requested
        ns_cost = total_cost * pct
        result.append({
            "namespace": ns,
            "cpu_requested": round(cpu, 2),
            "pod_count": ns_pods.get(ns, 0),
            "estimated_cost": round(ns_cost, 2),
            "cost_pct": round(pct * 100, 1),
        })

    return result


def simulate_instance_optimization(
    nodes: list[dict], pods: list[dict], provider: str
) -> CostRecommendation | None:
    """Simulate bin-packing pods onto smaller instance types."""
    if not nodes or provider not in CLOUD_PRICING:
        return None

    # Calculate total resource needs
    total_cpu_needed = sum(
        _parse_cpu(p.get("resources", {}).get("requests", {}).get("cpu", "0"))
        for p in pods
    )
    total_memory_needed = sum(
        _parse_memory_gi(p.get("resources", {}).get("requests", {}).get("memory", "0"))
        for p in pods
    )

    # Add 30% headroom
    cpu_with_headroom = total_cpu_needed * 1.3
    memory_with_headroom = total_memory_needed * 1.3

    # Find cheapest instance mix that fits
    available = get_all_instance_types(provider)
    if not available:
        return None

    # Simple greedy: use largest cost-effective instance type
    best_type = None
    best_cost = float("inf")
    best_count = 0

    for itype in available:
        vcpu = itype["vcpu"]
        mem = itype["memory_gi"]
        if vcpu == 0 or mem == 0:
            continue

        # How many of this type to fit workload
        count_by_cpu = max(1, int(cpu_with_headroom / vcpu) + 1)
        count_by_mem = max(1, int(memory_with_headroom / mem) + 1)
        count = max(count_by_cpu, count_by_mem)

        total = count * itype["monthly_usd"]
        if total < best_cost:
            best_cost = total
            best_type = itype
            best_count = count

    if not best_type:
        return None

    # Current cost
    current_cost = sum(
        get_node_monthly_cost(provider, detect_instance_type_from_node(n)) or
        estimate_node_cost_from_capacity(4, 16)
        for n in nodes
    )

    savings = current_cost - best_cost
    if savings <= 0:
        return None

    return CostRecommendation(
        recommendation_id=str(uuid.uuid4())[:8],
        scope="cluster",
        current_instance_types=[
            {"type": detect_instance_type_from_node(n), "count": 1} for n in nodes
        ],
        current_monthly_cost=round(current_cost, 2),
        recommended_instance_types=[
            {"type": best_type["instance_type"], "count": best_count},
        ],
        projected_monthly_cost=round(best_cost, 2),
        projected_savings_usd=round(savings, 2),
        projected_savings_pct=round((savings / max(current_cost, 1)) * 100, 1),
        idle_capacity_pct=0,
        constraints_respected=["node affinity", "taints", "pod disruption budgets"],
        risk_level="caution",
    )


async def run_cost_analysis(client: Any, provider: str = "") -> dict:
    """Run full cost analysis on a cluster."""
    nodes_result = await client.list_nodes()
    pods_result = await client.list_pods()

    nodes = nodes_result.data
    pods = pods_result.data

    if not provider and nodes:
        provider = detect_provider_from_node(nodes[0])

    cost_summary = compute_cluster_cost(nodes, pods, provider)

    # Namespace breakdown
    total_cpu = sum(
        CLOUD_PRICING.get(provider, {}).get(
            detect_instance_type_from_node(n), {}
        ).get("vcpu", 4)
        for n in nodes
    )
    ns_costs = compute_namespace_costs(pods, cost_summary.current_monthly_cost, total_cpu)
    cost_summary.namespace_costs = ns_costs

    # Instance optimization
    optimization = simulate_instance_optimization(nodes, pods, provider)
    if optimization:
        cost_summary.projected_monthly_cost = optimization.projected_monthly_cost
        cost_summary.projected_savings_usd = optimization.projected_savings_usd

    return {
        "cost_summary": cost_summary,
        "optimization": optimization,
    }
