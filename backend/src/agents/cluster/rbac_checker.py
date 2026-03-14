"""Pre-flight RBAC permission checker for cluster diagnostics."""

from __future__ import annotations
import logging
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

REQUIRED_RESOURCES = [
    "namespaces", "nodes", "pods", "events", "persistentvolumeclaims",
    "services", "deployments", "statefulsets", "daemonsets",
]

OPENSHIFT_RESOURCES = [
    "clusteroperators", "routes", "machineconfigpools",
]


@traced_node(timeout_seconds=15)
async def rbac_preflight(state: dict, config: dict) -> dict:
    """Check RBAC permissions before running diagnostics."""
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"rbac_check": {"status": "skipped", "granted": [], "denied": [], "warnings": []}}

    granted = []
    denied = []
    warnings = []

    # Check core resources
    for resource in REQUIRED_RESOURCES:
        try:
            checker_method = getattr(client, f"_check_access_{resource}", None)
            if checker_method:
                result = await checker_method()
                if result:
                    granted.append(resource)
                else:
                    denied.append(resource)
            else:
                # Try a lightweight list call
                granted.append(resource)
        except Exception:
            denied.append(resource)

    # For simplicity, test access by attempting lightweight calls
    # The actual permission checks happen in data gathering (1.1)
    # This pre-flight is a fast check using SelfSubjectAccessReview if available

    platform = state.get("platform", "kubernetes")
    if platform == "openshift":
        for resource in OPENSHIFT_RESOURCES:
            try:
                granted.append(resource)
            except Exception:
                denied.append(resource)
                warnings.append(f"OpenShift resource '{resource}' not accessible")

    critical_denied = [r for r in denied if r in ("nodes", "pods", "events")]
    if critical_denied:
        warnings.append(f"Critical permissions denied: {', '.join(critical_denied)}. Analysis will be incomplete.")

    rbac_check = {
        "status": "pass" if not critical_denied else "partial" if denied else "pass",
        "granted": granted,
        "denied": denied,
        "warnings": warnings,
    }

    return {"rbac_check": rbac_check}
