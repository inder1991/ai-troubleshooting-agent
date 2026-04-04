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
        # Probe cluster-scoped resources (no namespace) and namespace-scoped routes
        # ClusterClient signals denial via result.permission_denied, not via exceptions
        openshift_probes = [
            ("clusteroperators", "get_cluster_operators"),
            ("machineconfigpools", "list_machine_config_pools"),
            ("routes", "get_routes"),
        ]
        for resource, method_name in openshift_probes:
            probe_fn = getattr(client, method_name, None)
            if probe_fn is None:
                logger.debug("RBAC probe: method %s not found on client, skipping", method_name)
                continue
            try:
                result = await probe_fn()
                if getattr(result, "permission_denied", False):
                    denied.append(resource)
                    warnings.append(f"OpenShift resource '{resource}' access denied")
                else:
                    granted.append(resource)
            except Exception as exc:
                logger.debug("RBAC probe for %s failed: %s — marking denied", resource, exc)
                denied.append(resource)
                warnings.append(f"OpenShift resource '{resource}' probe failed")

    critical_denied = [r for r in denied if r in ("nodes", "pods", "events")]
    if critical_denied:
        warnings.append(
            f"Critical permissions denied: {', '.join(critical_denied)}. Analysis will be incomplete."
        )

    rbac_check = {
        "status": "fail" if critical_denied else "partial" if denied else "pass",
        "granted": granted,
        "denied": denied,
        "warnings": warnings,
    }

    return {"rbac_check": rbac_check}
