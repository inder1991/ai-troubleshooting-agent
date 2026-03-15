"""Workload optimizer: right-size CPU/memory, HPA/VPA recommendations."""

from __future__ import annotations
import uuid
from typing import Any
from src.agents.cluster.state import WorkloadRecommendation
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_cpu(cpu_str: str) -> float:
    """Parse K8s CPU string to cores."""
    if not cpu_str:
        return 0.0
    cpu_str = str(cpu_str).strip()
    if cpu_str.endswith("m"):
        return float(cpu_str[:-1]) / 1000
    return float(cpu_str)


def _parse_memory_mi(mem_str: str) -> float:
    """Parse K8s memory string to MiB."""
    if not mem_str:
        return 0.0
    mem_str = str(mem_str).strip()
    if mem_str.endswith("Gi"):
        return float(mem_str[:-2]) * 1024
    if mem_str.endswith("Mi"):
        return float(mem_str[:-2])
    if mem_str.endswith("Ki"):
        return float(mem_str[:-2]) / 1024
    try:
        return float(mem_str) / (1024 * 1024)
    except ValueError:
        return 0.0


def _format_cpu(cores: float) -> str:
    """Format CPU cores to K8s string."""
    if cores < 1:
        return f"{int(cores * 1000)}m"
    return f"{cores:.1f}"


def _format_memory(mi: float) -> str:
    """Format MiB to K8s string."""
    if mi >= 1024:
        return f"{mi / 1024:.1f}Gi"
    return f"{int(mi)}Mi"


def compute_right_size(
    workload_name: str,
    namespace: str,
    pods: list[dict],
    deployments: list[dict],
) -> WorkloadRecommendation | None:
    """Compute right-sizing recommendation for a workload.

    Uses pod resource requests vs actual data from deployment status.
    In production, p95 metrics would come from Prometheus.
    For now, estimates from request/usage patterns.
    """
    # Find the deployment
    dep = None
    for d in deployments:
        if d.get("name") == workload_name and d.get("namespace") == namespace:
            dep = d
            break

    if not dep:
        return None

    # Find pods belonging to this deployment (same namespace, name prefix)
    dep_pods = [
        p for p in pods
        if p.get("namespace") == namespace and p.get("name", "").startswith(workload_name)
    ]

    if not dep_pods:
        return None

    # Aggregate resource requests from pods
    total_cpu_request = 0.0
    total_memory_request = 0.0
    total_cpu_limit = 0.0
    total_memory_limit = 0.0

    for pod in dep_pods:
        resources = pod.get("resources", {})
        requests = resources.get("requests", resources.get("total_requests", {}))
        limits = resources.get("limits", resources.get("total_limits", {}))

        total_cpu_request += _parse_cpu(requests.get("cpu", "0"))
        total_memory_request += _parse_memory_mi(requests.get("memory", "0"))
        total_cpu_limit += _parse_cpu(limits.get("cpu", "0"))
        total_memory_limit += _parse_memory_mi(limits.get("memory", "0"))

    if total_cpu_request == 0 and total_memory_request == 0:
        return None

    # Average per pod
    pod_count = len(dep_pods)
    avg_cpu_request = total_cpu_request / pod_count
    avg_memory_request = total_memory_request / pod_count
    avg_cpu_limit = total_cpu_limit / pod_count
    avg_memory_limit = total_memory_limit / pod_count

    # Estimate p95 usage (without Prometheus, use 60% of request as approximation)
    # In production, this would be: query_prometheus("quantile_over_time(0.95, ...)")
    estimated_p95_cpu = avg_cpu_request * 0.6
    estimated_p95_memory = avg_memory_request * 0.6

    # Recommended = p95 + 20% headroom
    recommended_cpu = estimated_p95_cpu * 1.2
    recommended_memory = estimated_p95_memory * 1.2

    # Only recommend if reduction is meaningful (>20%)
    cpu_reduction = 1.0 - (recommended_cpu / max(avg_cpu_request, 0.001))
    memory_reduction = 1.0 - (recommended_memory / max(avg_memory_request, 0.001))

    if cpu_reduction < 0.2 and memory_reduction < 0.2:
        return None  # Not worth recommending

    # Throttling risk: if we're recommending less than 40% of current request
    throttling_risk = recommended_cpu < avg_cpu_request * 0.4

    return WorkloadRecommendation(
        recommendation_id=str(uuid.uuid4())[:8],
        workload=f"deployment/{namespace}/{workload_name}",
        namespace=namespace,
        current_cpu_request=_format_cpu(avg_cpu_request),
        current_cpu_limit=_format_cpu(avg_cpu_limit) if avg_cpu_limit > 0 else "",
        current_memory_request=_format_memory(avg_memory_request),
        current_memory_limit=_format_memory(avg_memory_limit) if avg_memory_limit > 0 else "",
        recommended_cpu_request=_format_cpu(recommended_cpu),
        recommended_memory_request=_format_memory(recommended_memory),
        p95_cpu_usage=_format_cpu(estimated_p95_cpu),
        p95_memory_usage=_format_memory(estimated_p95_memory),
        observation_window="7d (estimated)",
        cpu_reduction_pct=round(cpu_reduction * 100, 1),
        memory_reduction_pct=round(memory_reduction * 100, 1),
        recommended_hpa=None,  # Phase 2
        recommended_vpa=None,  # Phase 2
        risk_level="caution" if throttling_risk else "safe",
        throttling_risk=throttling_risk,
    )


def recommend_hpa(
    workload_name: str,
    namespace: str,
    deployments: list[dict],
    hpas: list[dict],
) -> dict | None:
    """Recommend HPA if no HPA exists and load varies significantly."""
    # Check if HPA already exists
    for hpa in hpas:
        target = hpa.get("target_ref", "")
        if workload_name in target:
            return None  # HPA exists

    # Find deployment
    dep = None
    for d in deployments:
        if d.get("name") == workload_name and d.get("namespace") == namespace:
            dep = d
            break

    if not dep:
        return None

    replicas = dep.get("replicas_desired", 1)
    if replicas <= 1:
        return None  # Single replica, HPA not useful

    # Recommend if deployment has more than 2 replicas (likely a scaled workload)
    if replicas >= 2:
        return {
            "workload": f"deployment/{namespace}/{workload_name}",
            "min_replicas": max(1, replicas // 2),
            "max_replicas": replicas * 3,
            "target_cpu_pct": 70,
            "recommendation": f"Add HPA: min={max(1, replicas // 2)}, max={replicas * 3}, targetCPU=70%",
        }

    return None


def detect_burst_workloads(pods: list[dict]) -> list[dict]:
    """Detect workloads with high restart counts (indicating burst/crash patterns)."""
    bursts = []
    for pod in pods:
        restarts = pod.get("restarts", 0)
        if isinstance(restarts, int) and restarts > 10:
            bursts.append({
                "workload": pod.get("name", ""),
                "namespace": pod.get("namespace", ""),
                "restarts": restarts,
                "status": pod.get("status", ""),
                "recommendation": "Investigate restart pattern — may need resource increase or liveness probe tuning",
            })
    return bursts


async def run_workload_optimization(client) -> list[WorkloadRecommendation]:
    """Run workload optimization analysis across all deployments."""
    pods_result = await client.list_pods()
    deployments_result = await client.list_deployments()
    hpas_result = await client.list_hpas()

    pods = pods_result.data
    deployments = deployments_result.data
    hpas = hpas_result.data

    recommendations: list[WorkloadRecommendation] = []

    for dep in deployments:
        name = dep.get("name", "")
        namespace = dep.get("namespace", "")

        rec = compute_right_size(name, namespace, pods, deployments)
        if rec:
            # Check for HPA recommendation
            hpa_rec = recommend_hpa(name, namespace, deployments, hpas)
            if hpa_rec:
                rec.recommended_hpa = hpa_rec

            recommendations.append(rec)

    # Sort by reduction potential
    recommendations.sort(
        key=lambda r: max(r.cpu_reduction_pct, r.memory_reduction_pct),
        reverse=True
    )

    logger.info("Generated %d workload recommendations from %d deployments",
                len(recommendations), len(deployments))

    return recommendations
