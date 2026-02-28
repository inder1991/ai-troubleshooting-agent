"""
ToolExecutor: Dispatches investigation tool calls by intent name.
Each handler takes params dict -> returns ToolResult.
"""

import json
import re
from typing import Any

from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException

from src.tools.tool_result import ToolResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Domain mapping for K8s resource kinds
_KIND_TO_DOMAIN: dict[str, str] = {
    "pod": "compute",
    "deployment": "compute",
    "node": "compute",
    "configmap": "compute",
    "replicaset": "compute",
    "service": "network",
    "ingress": "network",
    "pvc": "storage",
    "persistentvolumeclaim": "storage",
}

# Error keywords for log severity classification
_CRITICAL_KEYWORDS = ("fatal", "panic")
_HIGH_KEYWORDS = ("oom", "killed", "segfault")
_MEDIUM_KEYWORDS = ("error", "exception", "timeout", "refused", "fail")

# Combined pattern for extracting error lines from logs
_ERROR_PATTERN = re.compile(
    r"|".join(_CRITICAL_KEYWORDS + _HIGH_KEYWORDS + _MEDIUM_KEYWORDS),
    re.IGNORECASE,
)

# Mapping of resource kind -> (api_method_name, is_cluster_scoped)
_KIND_TO_API_METHOD: dict[str, tuple[str, bool]] = {
    "pod": ("read_namespaced_pod", False),
    "service": ("read_namespaced_service", False),
    "configmap": ("read_namespaced_config_map", False),
    "pvc": ("read_namespaced_persistent_volume_claim", False),
    "node": ("read_node", True),
}


class ToolExecutor:
    """Stateless tool dispatcher. Each method: params -> ToolResult."""

    def __init__(self, connection_config: dict):
        self._config = connection_config
        self._k8s_core_api = None    # Injected or lazy-initialized
        self._k8s_apps_api = None
        self._prom_client = None
        self._es_client = None

    HANDLERS: dict[str, str] = {
        "fetch_pod_logs": "_fetch_pod_logs",
        "describe_resource": "_describe_resource",
        "query_prometheus": "_query_prometheus",
        "search_logs": "_search_logs",
        "check_pod_status": "_check_pod_status",
        "get_events": "_get_events",
    }

    async def execute(self, intent: str, params: dict[str, Any]) -> ToolResult:
        """Dispatch a tool call by intent name."""
        handler_name = self.HANDLERS[intent]  # KeyError if unknown intent
        handler = getattr(self, handler_name)
        return await handler(params)

    # ------------------------------------------------------------------
    # fetch_pod_logs
    # ------------------------------------------------------------------

    async def _fetch_pod_logs(self, params: dict[str, Any]) -> ToolResult:
        """Fetch pod logs from the K8s API and extract error evidence."""
        namespace = params["namespace"]
        pod = params["pod"]
        container = params.get("container")
        previous = params.get("previous", False)
        tail_lines = params.get("tail_lines", 200)

        try:
            kwargs: dict[str, Any] = {
                "name": pod,
                "namespace": namespace,
                "timestamps": True,
                "tail_lines": tail_lines,
                "previous": previous,
            }
            if container:
                kwargs["container"] = container

            log_text: str = self._k8s_core_api.read_namespaced_pod_log(**kwargs)
        except ApiException as exc:
            if exc.status == 404:
                error_msg = f"Pod '{pod}' not found in namespace '{namespace}'"
            elif exc.status == 400:
                error_msg = (
                    f"Bad request fetching logs for pod '{pod}': {exc.reason}. "
                    "The pod may not have a previous container."
                )
            else:
                error_msg = f"K8s API error ({exc.status}): {exc.reason}"
            logger.warning(
                "fetch_pod_logs failed",
                extra={"pod": pod, "namespace": namespace, "status_code": exc.status},
            )
            return ToolResult(
                success=False,
                intent="fetch_pod_logs",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="log",
                domain="compute",
                error=error_msg,
                metadata={"pod": pod, "namespace": namespace},
            )

        # Extract error lines
        error_lines: list[str] = []
        for line in log_text.splitlines():
            if _ERROR_PATTERN.search(line):
                error_lines.append(line.strip())

        severity = self._classify_log_severity(error_lines)

        if error_lines:
            summary = (
                f"Found {len(error_lines)} error line(s) in {pod} logs "
                f"(severity: {severity})"
            )
        else:
            summary = f"No errors found in {pod} logs"

        return ToolResult(
            success=True,
            intent="fetch_pod_logs",
            raw_output=log_text,
            summary=summary,
            evidence_snippets=error_lines,
            evidence_type="log",
            domain="compute",
            severity=severity,
            metadata={
                "pod": pod,
                "namespace": namespace,
                "container": container,
                "previous": previous,
                "tail_lines": tail_lines,
                "error_count": len(error_lines),
            },
        )

    # ------------------------------------------------------------------
    # describe_resource
    # ------------------------------------------------------------------

    async def _describe_resource(self, params: dict[str, Any]) -> ToolResult:
        """Describe a K8s resource by kind and name."""
        kind = params["kind"].lower()
        name = params["name"]
        namespace = params.get("namespace")

        if kind not in _KIND_TO_API_METHOD:
            error_msg = (
                f"Unsupported resource kind '{kind}'. "
                f"Supported kinds: {', '.join(sorted(_KIND_TO_API_METHOD.keys()))}"
            )
            return ToolResult(
                success=False,
                intent="describe_resource",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="k8s_resource",
                domain=_KIND_TO_DOMAIN.get(kind, "unknown"),
                error=error_msg,
                metadata={"kind": kind, "name": name},
            )

        method_name, is_cluster_scoped = _KIND_TO_API_METHOD[kind]
        api_method = getattr(self._k8s_core_api, method_name)

        try:
            if is_cluster_scoped:
                resource = api_method(name=name)
            else:
                resource = api_method(name=name, namespace=namespace)
        except ApiException as exc:
            if exc.status == 404:
                error_msg = (
                    f"{kind.capitalize()} '{name}' not found"
                    + (f" in namespace '{namespace}'" if namespace else "")
                )
            else:
                error_msg = f"K8s API error ({exc.status}): {exc.reason}"
            logger.warning(
                "describe_resource failed",
                extra={"kind": kind, "resource_name": name, "status_code": exc.status},
            )
            return ToolResult(
                success=False,
                intent="describe_resource",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="k8s_resource",
                domain=_KIND_TO_DOMAIN.get(kind, "unknown"),
                error=error_msg,
                metadata={"kind": kind, "name": name, "namespace": namespace},
            )

        # Serialize to JSON text
        raw_text = self._resource_to_text(resource, kind)

        # Extract signals
        signals = self._extract_resource_signals(resource, kind)

        domain = _KIND_TO_DOMAIN.get(kind, "unknown")

        return ToolResult(
            success=True,
            intent="describe_resource",
            raw_output=raw_text,
            summary=signals["summary"],
            evidence_snippets=signals["key_lines"],
            evidence_type="k8s_resource",
            domain=domain,
            severity="high" if signals["has_issues"] else "info",
            metadata={
                "kind": kind,
                "name": name,
                "namespace": namespace,
                "has_issues": signals["has_issues"],
            },
        )

    # ------------------------------------------------------------------
    # Placeholder handlers (Task 4)
    # ------------------------------------------------------------------

    async def _query_prometheus(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError("Task 4")

    async def _search_logs(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError("Task 4")

    async def _check_pod_status(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError("Task 4")

    async def _get_events(self, params: dict[str, Any]) -> ToolResult:
        raise NotImplementedError("Task 4")

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_log_severity(error_lines: list[str]) -> str:
        """Classify overall log severity from extracted error lines."""
        combined = " ".join(error_lines).lower()
        if any(kw in combined for kw in _CRITICAL_KEYWORDS):
            return "critical"
        if any(kw in combined for kw in _HIGH_KEYWORDS):
            return "high"
        if error_lines:
            return "medium"
        return "info"

    @staticmethod
    def _resource_to_text(resource: Any, kind: str) -> str:
        """Serialize a K8s resource object to JSON text."""
        try:
            return json.dumps(
                ApiClient().sanitize_for_serialization(resource),
                indent=2,
            )
        except Exception:
            return str(resource)

    @staticmethod
    def _extract_resource_signals(resource: Any, kind: str) -> dict[str, Any]:
        """Extract diagnostic signals from a K8s resource.

        Returns:
            {"summary": str, "key_lines": list[str], "has_issues": bool}
        """
        signals: dict[str, Any] = {
            "summary": "",
            "key_lines": [],
            "has_issues": False,
        }

        if kind == "pod":
            container_statuses = getattr(
                getattr(resource, "status", None), "container_statuses", None
            )
            if container_statuses:
                issues: list[str] = []
                for cs in container_statuses:
                    if not cs.ready:
                        issues.append(f"Container '{cs.name}' is not ready")
                    terminated = getattr(
                        getattr(cs, "state", None), "terminated", None
                    )
                    if terminated:
                        reason = getattr(terminated, "reason", "Unknown")
                        exit_code = getattr(terminated, "exit_code", "?")
                        issues.append(
                            f"Container '{cs.name}' terminated: "
                            f"{reason} (exit code {exit_code})"
                        )
                    waiting = getattr(
                        getattr(cs, "state", None), "waiting", None
                    )
                    if waiting:
                        reason = getattr(waiting, "reason", "Unknown")
                        issues.append(
                            f"Container '{cs.name}' waiting: {reason}"
                        )
                if issues:
                    signals["has_issues"] = True
                    signals["key_lines"] = issues
                    signals["summary"] = f"Pod has issues: {'; '.join(issues)}"
                else:
                    signals["summary"] = "Pod containers are all ready"
            else:
                signals["summary"] = "Pod status has no container statuses"

        elif kind == "service":
            svc_type = getattr(
                getattr(resource, "spec", None), "type", "Unknown"
            )
            svc_name = getattr(
                getattr(resource, "metadata", None), "name", "unknown"
            )
            signals["summary"] = f"Service '{svc_name}' type: {svc_type}"

        else:
            # Default for node, configmap, pvc, etc.
            res_name = getattr(
                getattr(resource, "metadata", None), "name", "unknown"
            )
            signals["summary"] = f"{kind.capitalize()} '{res_name}' described"

        return signals
