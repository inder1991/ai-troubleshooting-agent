"""
ToolExecutor: Dispatches investigation tool calls by intent name.
Each handler takes params dict -> returns ToolResult.
"""

import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any

from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException

from src.tools.tool_result import ToolResult
from src.tools.tool_registry import TOOL_REGISTRY
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
        self._k8s_api_client = None  # Cached ApiClient
        self._k8s_core_api = None    # Injected or lazy-initialized
        self._k8s_apps_api = None
        self._prom_client = None
        self._es_client = None

    # ------------------------------------------------------------------
    # Lazy client initialization (config -> env var -> kubeconfig fallback)
    # ------------------------------------------------------------------

    def _get_k8s_client(self):
        """Build a kubernetes ApiClient from config/env vars/kubeconfig.

        Resolution order:
        1. self._config dict keys (cluster_url, cluster_token, verify_ssl)
        2. Environment variables (OPENSHIFT_API_URL, OPENSHIFT_TOKEN)
        3. Default kubeconfig (~/.kube/config)
        """
        if self._k8s_api_client is not None:
            return self._k8s_api_client

        from kubernetes import client, config

        api_url = None
        token = None
        verify_ssl = False

        if self._config:
            api_url = self._config.get("cluster_url") or None
            token = self._config.get("cluster_token") or None
            verify_ssl = self._config.get("verify_ssl", False)

        # Fallback to env vars
        if not api_url:
            api_url = os.getenv("OPENSHIFT_API_URL")
        if not token:
            token = os.getenv("OPENSHIFT_TOKEN")

        if api_url and token:
            configuration = client.Configuration()
            configuration.host = api_url
            configuration.api_key = {"authorization": f"Bearer {token}"}
            configuration.verify_ssl = verify_ssl
            api_client = client.ApiClient(configuration)
            self._k8s_api_client = api_client
            return api_client
        else:
            try:
                config.load_kube_config()
                api_client = client.ApiClient()
                self._k8s_api_client = api_client
                return api_client
            except Exception as e:
                raise RuntimeError(f"Failed to initialize K8s client: {e}")

    def _get_k8s_core_api(self):
        """Lazily initialize and cache the CoreV1Api client."""
        if self._k8s_core_api is None:
            from kubernetes import client
            api_client = self._get_k8s_client()
            self._k8s_core_api = client.CoreV1Api(api_client)
        return self._k8s_core_api

    def _get_k8s_apps_api(self):
        """Lazily initialize and cache the AppsV1Api client."""
        if self._k8s_apps_api is None:
            from kubernetes import client
            api_client = self._get_k8s_client()
            self._k8s_apps_api = client.AppsV1Api(api_client)
        return self._k8s_apps_api

    def _get_prom_client(self):
        """Lazily initialize and cache the Prometheus client."""
        if self._prom_client is None:
            from prometheus_api_client import PrometheusConnect

            prom_url = None
            if self._config:
                prom_url = self._config.get("prometheus_url")
            if not prom_url:
                prom_url = os.getenv("PROMETHEUS_URL")
            if not prom_url:
                raise RuntimeError(
                    "Prometheus URL not configured. Set 'prometheus_url' in "
                    "connection config or PROMETHEUS_URL env var."
                )
            self._prom_client = PrometheusConnect(url=prom_url, disable_ssl=True)
        return self._prom_client

    def _get_es_client(self):
        """Lazily initialize and cache the Elasticsearch client."""
        if self._es_client is None:
            from elasticsearch import Elasticsearch

            es_url = None
            if self._config:
                es_url = self._config.get("elasticsearch_url")
            if not es_url:
                es_url = os.getenv("ELASTICSEARCH_URL")
            if not es_url:
                raise RuntimeError(
                    "Elasticsearch URL not configured. Set 'elasticsearch_url' in "
                    "connection config or ELASTICSEARCH_URL env var."
                )
            self._es_client = Elasticsearch([es_url])
        return self._es_client

    HANDLERS: dict[str, str] = {
        "fetch_pod_logs": "_fetch_pod_logs",
        "describe_resource": "_describe_resource",
        "query_prometheus": "_query_prometheus",
        "search_logs": "_search_logs",
        "check_pod_status": "_check_pod_status",
        "get_events": "_get_events",
        "re_investigate_service": "_re_investigate_service",
    }

    # ------------------------------------------------------------------
    # Parameter validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_params(intent: str, params: dict[str, Any]) -> str | None:
        """Check that all required params (per TOOL_REGISTRY schema) are present.

        Returns an error string describing the missing params, or None if valid.
        """
        # Find the registry entry for this intent
        registry_entry = None
        for tool in TOOL_REGISTRY:
            if tool["intent"] == intent:
                registry_entry = tool
                break

        if registry_entry is None:
            # No schema to validate against — skip validation
            return None

        missing: list[str] = []
        for param_def in registry_entry.get("params_schema", []):
            if param_def.get("required", False):
                if param_def["name"] not in params or params[param_def["name"]] is None:
                    missing.append(param_def["name"])

        if missing:
            return f"Missing required parameter(s) for '{intent}': {', '.join(missing)}"
        return None

    async def execute(self, intent: str, params: dict[str, Any]) -> ToolResult:
        """Dispatch a tool call by intent name."""
        # Validate required params before dispatch
        validation_error = self._validate_params(intent, params)
        if validation_error:
            return ToolResult(
                success=False,
                intent=intent,
                raw_output="",
                summary=validation_error,
                evidence_snippets=[],
                evidence_type="unknown",
                domain="unknown",
                error=validation_error,
            )

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

            log_text: str = self._get_k8s_core_api().read_namespaced_pod_log(**kwargs)
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
        api_method = getattr(self._get_k8s_core_api(), method_name)

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
    # query_prometheus
    # ------------------------------------------------------------------

    async def _query_prometheus(self, params: dict[str, Any]) -> ToolResult:
        """Execute a PromQL range query and compute stats / anomaly flags."""
        query = params["query"]
        range_minutes = params.get("range_minutes", 60)
        domain = self._infer_domain_from_promql(query)

        try:
            response = self._get_prom_client().query_range(query, range_minutes)
        except Exception as exc:
            error_msg = f"Prometheus query failed: {exc}"
            logger.warning("query_prometheus failed", extra={"query": query, "error": str(exc)})
            return ToolResult(
                success=False,
                intent="query_prometheus",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="metric",
                domain=domain,
                error=error_msg,
                metadata={"query": query, "range_minutes": range_minutes},
            )

        results = response.get("data", {}).get("result", [])
        series_count = len(results)

        if series_count == 0:
            return ToolResult(
                success=True,
                intent="query_prometheus",
                raw_output=json.dumps(response),
                summary=f"PromQL query returned no data for: {query}",
                evidence_snippets=[],
                evidence_type="metric",
                domain=domain,
                severity="info",
                metadata={"series_count": 0, "query": query, "range_minutes": range_minutes},
            )

        # Aggregate all values across all series
        all_values: list[float] = []
        for series in results:
            for _ts, val in series.get("values", []):
                try:
                    all_values.append(float(val))
                except (ValueError, TypeError):
                    continue

        if all_values:
            latest_value = all_values[-1]
            max_value = max(all_values)
            avg_value = statistics.mean(all_values)
        else:
            latest_value = max_value = avg_value = 0.0

        # Anomaly detection: flag spikes > 2 stddev above mean
        evidence_snippets: list[str] = []
        severity = "info"
        if len(all_values) >= 2:
            stddev = statistics.stdev(all_values)
            threshold = avg_value + 2 * stddev
            spikes = [v for v in all_values if v > threshold]
            if spikes:
                severity = "high"
                evidence_snippets.append(
                    f"Detected {len(spikes)} spike(s) exceeding 2 stddev "
                    f"(threshold={threshold:.2f}, max={max_value:.2f})"
                )

        summary = (
            f"PromQL returned {series_count} series: "
            f"latest={latest_value:.2f}, max={max_value:.2f}, avg={avg_value:.2f}"
        )

        return ToolResult(
            success=True,
            intent="query_prometheus",
            raw_output=json.dumps(response),
            summary=summary,
            evidence_snippets=evidence_snippets,
            evidence_type="metric",
            domain=domain,
            severity=severity,
            metadata={
                "series_count": series_count,
                "query": query,
                "range_minutes": range_minutes,
                "latest_value": latest_value,
                "max_value": max_value,
                "avg_value": avg_value,
            },
        )

    # ------------------------------------------------------------------
    # search_logs
    # ------------------------------------------------------------------

    async def _search_logs(self, params: dict[str, Any]) -> ToolResult:
        """Search logs in Elasticsearch using query_string."""
        query = params["query"]
        index = params.get("index", (self._config or {}).get("es_index", "app-logs-*"))
        since_minutes = params.get("since_minutes", 60)

        try:
            es_response = self._get_es_client().search(
                index=index,
                body={
                    "query": {
                        "bool": {
                            "must": [{"simple_query_string": {"query": query}}],
                            "filter": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": f"now-{since_minutes}m",
                                            "lte": "now",
                                        }
                                    }
                                }
                            ],
                        }
                    },
                    "size": 20,
                    "sort": [{"@timestamp": {"order": "desc"}}],
                },
            )
        except Exception as exc:
            error_msg = f"Elasticsearch query failed: {exc}"
            logger.warning("search_logs failed", extra={"query": query, "error": str(exc)})
            return ToolResult(
                success=False,
                intent="search_logs",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="log",
                domain="unknown",
                error=error_msg,
                metadata={"query": query, "index": index},
            )

        total = es_response.get("hits", {}).get("total", {}).get("value", 0)
        hits = es_response.get("hits", {}).get("hits", [])

        evidence_snippets: list[str] = []
        for hit in hits[:20]:
            source = hit.get("_source", {})
            ts = source.get("@timestamp", "")
            msg = source.get("message", "")
            evidence_snippets.append(f"[{ts}] {msg}")

        if total == 0:
            summary = f"Log search returned 0 results for query: {query}"
        else:
            summary = f"Found {total} log entries matching '{query}' (showing up to 20)"

        return ToolResult(
            success=True,
            intent="search_logs",
            raw_output=json.dumps(es_response, default=str),
            summary=summary,
            evidence_snippets=evidence_snippets,
            evidence_type="log",
            domain="unknown",
            severity="info",
            metadata={"total": total, "query": query, "index": index},
        )

    # ------------------------------------------------------------------
    # check_pod_status
    # ------------------------------------------------------------------

    async def _check_pod_status(self, params: dict[str, Any]) -> ToolResult:
        """List pods in a namespace and report health / readiness / restarts."""
        namespace = params["namespace"]
        label_selector = params.get("label_selector")

        try:
            kwargs: dict[str, Any] = {"namespace": namespace}
            if label_selector:
                kwargs["label_selector"] = label_selector

            pod_list = self._get_k8s_core_api().list_namespaced_pod(**kwargs)
        except ApiException as exc:
            error_msg = f"Failed to list pods in namespace '{namespace}': {exc.reason}"
            logger.warning("check_pod_status failed", extra={"namespace": namespace, "status_code": exc.status})
            return ToolResult(
                success=False,
                intent="check_pod_status",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="k8s_event",
                domain="compute",
                error=error_msg,
                metadata={"namespace": namespace},
            )

        pods = pod_list.items
        total = len(pods)
        unhealthy = 0
        has_critical = False
        has_not_ready = False
        evidence_snippets: list[str] = []
        pod_summaries: list[str] = []

        for pod in pods:
            pod_name = pod.metadata.name
            phase = pod.status.phase
            container_statuses = pod.status.container_statuses or []

            pod_healthy = True
            for cs in container_statuses:
                restart_count = cs.restart_count or 0
                ready = cs.ready
                is_oom = False
                is_crashloop = False

                # Check for OOMKilled in terminated state
                terminated = getattr(getattr(cs, "state", None), "terminated", None)
                if terminated:
                    reason = getattr(terminated, "reason", "")
                    if reason and "oom" in reason.lower():
                        is_oom = True

                # Check for CrashLoopBackOff in waiting state
                waiting = getattr(getattr(cs, "state", None), "waiting", None)
                if waiting:
                    reason = getattr(waiting, "reason", "")
                    if reason == "CrashLoopBackOff":
                        is_crashloop = True

                if is_oom or is_crashloop or restart_count >= 5:
                    has_critical = True
                    pod_healthy = False
                    evidence_snippets.append(
                        f"Pod {pod_name}/{cs.name}: "
                        f"restarts={restart_count}, ready={ready}"
                        + (", OOMKilled" if is_oom else "")
                        + (", CrashLoopBackOff" if is_crashloop else "")
                    )
                elif not ready:
                    has_not_ready = True
                    pod_healthy = False
                    evidence_snippets.append(
                        f"Pod {pod_name}/{cs.name}: not ready, restarts={restart_count}"
                    )

            if not pod_healthy:
                unhealthy += 1
            pod_summaries.append(f"{pod_name}: phase={phase}")

        # Determine severity
        if has_critical:
            severity = "critical"
        elif has_not_ready:
            severity = "high"
        else:
            severity = "info"

        if unhealthy == 0:
            summary = f"All {total} pod(s) in '{namespace}' are healthy"
        else:
            summary = f"{unhealthy}/{total} pod(s) in '{namespace}' are unhealthy (severity: {severity})"

        return ToolResult(
            success=True,
            intent="check_pod_status",
            raw_output="\n".join(pod_summaries),
            summary=summary,
            evidence_snippets=evidence_snippets,
            evidence_type="k8s_event",
            domain="compute",
            severity=severity,
            metadata={"total": total, "unhealthy": unhealthy, "namespace": namespace},
        )

    # ------------------------------------------------------------------
    # get_events
    # ------------------------------------------------------------------

    async def _get_events(self, params: dict[str, Any]) -> ToolResult:
        """List K8s events in a namespace, filtered by time window."""
        namespace = params["namespace"]
        since_minutes = params.get("since_minutes", 60)
        involved_object = params.get("involved_object")

        try:
            kwargs: dict[str, Any] = {"namespace": namespace}
            if involved_object:
                kwargs["field_selector"] = f"involvedObject.name={involved_object}"

            event_list = self._get_k8s_core_api().list_namespaced_event(**kwargs)
        except ApiException as exc:
            error_msg = f"Failed to list events in namespace '{namespace}': {exc.reason}"
            logger.warning("get_events failed", extra={"namespace": namespace, "status_code": exc.status})
            return ToolResult(
                success=False,
                intent="get_events",
                raw_output="",
                summary=error_msg,
                evidence_snippets=[],
                evidence_type="k8s_event",
                domain="compute",
                error=error_msg,
                metadata={"namespace": namespace},
            )

        # Filter events by time window
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        filtered_events = []
        for event in event_list.items:
            event_ts = event.last_timestamp
            if event_ts is None:
                continue
            # Ensure timezone-aware comparison
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)
            if event_ts >= cutoff:
                filtered_events.append(event)

        # Sort by timestamp descending (ensure tz-aware for safe comparison)
        def _tz_aware_ts(e: Any) -> datetime:
            ts = e.last_timestamp
            if ts is None:
                return datetime.min.replace(tzinfo=timezone.utc)
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        filtered_events.sort(key=_tz_aware_ts, reverse=True)

        warning_count = sum(1 for e in filtered_events if e.type == "Warning")
        total_events = len(filtered_events)

        evidence_snippets: list[str] = []
        for event in filtered_events:
            prefix = "[WARNING] " if event.type == "Warning" else ""
            obj_name = getattr(event.involved_object, "name", "unknown")
            obj_kind = getattr(event.involved_object, "kind", "unknown")
            evidence_snippets.append(
                f"{prefix}{event.reason}: {event.message} "
                f"({obj_kind}/{obj_name}, count={event.count})"
            )

        if total_events == 0:
            summary = f"No events in '{namespace}' within the last {since_minutes} minutes"
        else:
            summary = (
                f"{total_events} event(s) in '{namespace}' "
                f"({warning_count} warning(s)) in the last {since_minutes} minutes"
            )

        return ToolResult(
            success=True,
            intent="get_events",
            raw_output="\n".join(evidence_snippets),
            summary=summary,
            evidence_snippets=evidence_snippets,
            evidence_type="k8s_event",
            domain="compute",
            severity="high" if warning_count > 0 else "info",
            metadata={
                "total_events": total_events,
                "warning_count": warning_count,
                "namespace": namespace,
            },
        )

    # ------------------------------------------------------------------
    # re_investigate_service (stub)
    # ------------------------------------------------------------------

    async def _re_investigate_service(self, params: dict[str, Any]) -> ToolResult:
        """Stub: re-investigate a service through the full agent pipeline.

        Not yet implemented — returns a failure result so callers know this
        intent was recognized but cannot be executed yet.
        """
        return ToolResult(
            success=False,
            intent="re_investigate_service",
            raw_output="",
            summary="re_investigate_service is not yet implemented",
            evidence_snippets=[],
            evidence_type="unknown",
            domain="unknown",
            error="not yet implemented",
            metadata={
                "service": params.get("service"),
                "namespace": params.get("namespace"),
            },
        )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_domain_from_promql(query: str) -> str:
        """Infer the infrastructure domain from a PromQL query string."""
        q_lower = query.lower()
        if any(kw in q_lower for kw in ("coredns", "ingress")):
            return "network"
        if any(kw in q_lower for kw in ("apiserver", "etcd")):
            return "control_plane"
        return "compute"

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
