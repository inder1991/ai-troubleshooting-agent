"""Prometheus endpoint auto-detection from cluster routes/services."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_OPENSHIFT_PROMETHEUS_NAMES = frozenset(("thanos-querier", "prometheus-k8s"))
_K8S_MONITORING_NAMESPACES = ("monitoring", "kube-monitoring", "prometheus", "kube-system")


async def detect_prometheus_endpoint(cluster_client, platform: str) -> str:
    """
    Auto-detect Prometheus endpoint from cluster routes/services.
    Returns URL string or "" if not found.
    """
    try:
        if platform == "openshift":
            return await _detect_openshift(cluster_client)
        else:
            return await _detect_kubernetes(cluster_client)
    except Exception as exc:
        logger.warning("Prometheus auto-detection failed: %s", exc)
        return ""


async def _detect_openshift(cluster_client) -> str:
    """Detect thanos-querier or prometheus-k8s route in openshift-monitoring."""
    try:
        result = await cluster_client.get_routes(namespace="openshift-monitoring")
        routes = result.data if hasattr(result, "data") else []
        for route in routes:
            if isinstance(route, dict):
                name = route.get("name", "")
                host = route.get("host", "")
                ns = route.get("namespace", "")
            else:
                name = getattr(route, "name", "")
                host = getattr(route, "host", "")
                ns = getattr(route, "namespace", "")

            if ns == "openshift-monitoring" and name in _OPENSHIFT_PROMETHEUS_NAMES and host:
                return f"https://{host}"
    except Exception as exc:
        logger.debug("OpenShift route detection failed: %s", exc)
    return ""


async def _detect_kubernetes(cluster_client) -> str:
    """Detect prometheus service in common monitoring namespaces."""
    for ns in _K8S_MONITORING_NAMESPACES:
        try:
            result = await cluster_client.list_services(namespace=ns)
            services = result.data if hasattr(result, "data") else []
            for svc in services:
                if isinstance(svc, dict):
                    name = svc.get("name", "")
                    ip = svc.get("external_ip", "")
                    port = svc.get("port", 9090)
                else:
                    name = getattr(svc, "name", "")
                    ip = getattr(svc, "external_ip", "")
                    port = getattr(svc, "port", 9090)

                if "prometheus" in name.lower() and ip:
                    return f"http://{ip}:{port}"
        except Exception:
            continue
    return ""
