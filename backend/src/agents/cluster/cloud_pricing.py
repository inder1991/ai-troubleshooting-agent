"""Multi-cloud instance pricing tables for cost analysis."""

from __future__ import annotations
from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Static pricing tables (monthly on-demand USD, us-east-1 equivalent)
# Updated periodically. For real-time pricing, integrate cloud APIs (Phase 2).
# ---------------------------------------------------------------------------

CLOUD_PRICING: dict[str, dict[str, dict[str, Any]]] = {
    "aws": {
        "m5.large":    {"vcpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "m5.xlarge":   {"vcpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "m5.2xlarge":  {"vcpu": 8, "memory_gi": 32, "monthly_usd": 280},
        "m5.4xlarge":  {"vcpu": 16, "memory_gi": 64, "monthly_usd": 560},
        "c5.large":    {"vcpu": 2, "memory_gi": 4, "monthly_usd": 62},
        "c5.xlarge":   {"vcpu": 4, "memory_gi": 8, "monthly_usd": 124},
        "c5.2xlarge":  {"vcpu": 8, "memory_gi": 16, "monthly_usd": 248},
        "r5.large":    {"vcpu": 2, "memory_gi": 16, "monthly_usd": 91},
        "r5.xlarge":   {"vcpu": 4, "memory_gi": 32, "monthly_usd": 182},
        "r5.2xlarge":  {"vcpu": 8, "memory_gi": 64, "monthly_usd": 364},
        "t3.medium":   {"vcpu": 2, "memory_gi": 4, "monthly_usd": 30},
        "t3.large":    {"vcpu": 2, "memory_gi": 8, "monthly_usd": 60},
        "t3.xlarge":   {"vcpu": 4, "memory_gi": 16, "monthly_usd": 121},
        "m6i.large":   {"vcpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "m6i.xlarge":  {"vcpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "m6i.2xlarge": {"vcpu": 8, "memory_gi": 32, "monthly_usd": 280},
    },
    "gcp": {
        "e2-standard-2":  {"vcpu": 2, "memory_gi": 8, "monthly_usd": 49},
        "e2-standard-4":  {"vcpu": 4, "memory_gi": 16, "monthly_usd": 97},
        "e2-standard-8":  {"vcpu": 8, "memory_gi": 32, "monthly_usd": 194},
        "e2-standard-16": {"vcpu": 16, "memory_gi": 64, "monthly_usd": 389},
        "n2-standard-2":  {"vcpu": 2, "memory_gi": 8, "monthly_usd": 71},
        "n2-standard-4":  {"vcpu": 4, "memory_gi": 16, "monthly_usd": 142},
        "n2-standard-8":  {"vcpu": 8, "memory_gi": 32, "monthly_usd": 284},
        "n2-highmem-2":   {"vcpu": 2, "memory_gi": 16, "monthly_usd": 95},
        "n2-highmem-4":   {"vcpu": 4, "memory_gi": 32, "monthly_usd": 190},
        "c2-standard-4":  {"vcpu": 4, "memory_gi": 16, "monthly_usd": 152},
        "c2-standard-8":  {"vcpu": 8, "memory_gi": 32, "monthly_usd": 304},
    },
    "azure": {
        "Standard_D2s_v3":  {"vcpu": 2, "memory_gi": 8, "monthly_usd": 70},
        "Standard_D4s_v3":  {"vcpu": 4, "memory_gi": 16, "monthly_usd": 140},
        "Standard_D8s_v3":  {"vcpu": 8, "memory_gi": 32, "monthly_usd": 280},
        "Standard_D16s_v3": {"vcpu": 16, "memory_gi": 64, "monthly_usd": 561},
        "Standard_E2s_v3":  {"vcpu": 2, "memory_gi": 16, "monthly_usd": 91},
        "Standard_E4s_v3":  {"vcpu": 4, "memory_gi": 32, "monthly_usd": 183},
        "Standard_E8s_v3":  {"vcpu": 8, "memory_gi": 64, "monthly_usd": 366},
        "Standard_F2s_v2":  {"vcpu": 2, "memory_gi": 4, "monthly_usd": 62},
        "Standard_F4s_v2":  {"vcpu": 4, "memory_gi": 8, "monthly_usd": 124},
        "Standard_B2s":     {"vcpu": 2, "memory_gi": 4, "monthly_usd": 30},
        "Standard_B2ms":    {"vcpu": 2, "memory_gi": 8, "monthly_usd": 60},
    },
}

# Default cost per core/GiB for on-prem or unknown providers
ON_PREM_DEFAULTS = {
    "cost_per_vcpu_monthly": 25.0,
    "cost_per_gi_monthly": 5.0,
}


def get_instance_pricing(provider: str, instance_type: str) -> dict | None:
    """Get pricing for a specific instance type."""
    return CLOUD_PRICING.get(provider, {}).get(instance_type)


def get_node_monthly_cost(provider: str, instance_type: str) -> float:
    """Get monthly cost for a node. Falls back to on-prem estimate."""
    pricing = get_instance_pricing(provider, instance_type)
    if pricing:
        return pricing["monthly_usd"]

    # Fallback: estimate from on-prem defaults if we know capacity
    logger.debug("No pricing for %s/%s, using on-prem estimate", provider, instance_type)
    return 0.0  # Will be estimated from node capacity in cost_analyzer


def estimate_node_cost_from_capacity(cpu_cores: int, memory_gi: int) -> float:
    """Estimate monthly cost from raw capacity (for on-prem or unknown types)."""
    return (
        cpu_cores * ON_PREM_DEFAULTS["cost_per_vcpu_monthly"]
        + memory_gi * ON_PREM_DEFAULTS["cost_per_gi_monthly"]
    )


def detect_provider_from_node(node: dict) -> str:
    """Infer cloud provider from node labels or metadata."""
    labels = node.get("labels", {})
    name = node.get("name", "").lower()

    # Check well-known labels
    if "eks.amazonaws.com/nodegroup" in labels or "node.kubernetes.io/instance-type" in labels:
        instance_type = labels.get("node.kubernetes.io/instance-type", "")
        if instance_type and any(instance_type.startswith(p) for p in ("m5", "m6", "c5", "c6", "r5", "r6", "t3", "t2")):
            return "aws"

    if "cloud.google.com/gke-nodepool" in labels:
        return "gcp"

    if "kubernetes.azure.com/agentpool" in labels:
        return "azure"

    # Heuristic from node name
    if "eks" in name or "aws" in name:
        return "aws"
    if "gke" in name or "gcp" in name:
        return "gcp"
    if "aks" in name or "azure" in name:
        return "azure"

    return "on_prem"


def detect_instance_type_from_node(node: dict) -> str:
    """Extract instance type from node labels."""
    labels = node.get("labels", {})
    return (
        labels.get("node.kubernetes.io/instance-type", "")
        or labels.get("beta.kubernetes.io/instance-type", "")
        or ""
    )


def get_all_instance_types(provider: str) -> list[dict]:
    """Get all available instance types for a provider, sorted by cost."""
    types = CLOUD_PRICING.get(provider, {})
    result = [
        {"instance_type": name, **specs}
        for name, specs in types.items()
    ]
    result.sort(key=lambda x: x["monthly_usd"])
    return result
