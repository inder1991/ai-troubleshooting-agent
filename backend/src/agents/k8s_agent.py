import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.agents.react_base import ReActAgent
from src.models.schemas import PodHealthStatus, K8sEvent, K8sAnalysisResult, TokenUsage
from src.utils.event_emitter import EventEmitter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class K8sAgent(ReActAgent):
    """ReAct agent for Kubernetes/OpenShift cluster health analysis."""

    def __init__(self, max_iterations: int = 5, connection_config=None):
        super().__init__(
            agent_name="k8s_agent",
            max_iterations=max_iterations,
            connection_config=connection_config,
        )
        self._k8s_client = None
        self._connection_config = connection_config

    def _get_k8s_client(self):
        """Lazily initialize Kubernetes client."""
        if self._k8s_client is None:
            try:
                from kubernetes import client, config

                # Use connection config from profile if available
                api_url = None
                token = None
                verify_ssl = False

                if self._connection_config:
                    api_url = self._connection_config.cluster_url or None
                    token = self._connection_config.cluster_token or None
                    verify_ssl = self._connection_config.verify_ssl

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
                    self._k8s_client = client.ApiClient(configuration)
                else:
                    config.load_kube_config()
                    self._k8s_client = client.ApiClient()
            except Exception as e:
                raise RuntimeError(f"Failed to initialize K8s client: {e}")
        return self._k8s_client

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "test_cluster_connectivity",
                "description": "Test if the Kubernetes/OpenShift cluster is reachable and auth is valid. Call this FIRST before any other K8s tool to verify the connection. Returns cluster version and node count on success, or error details on failure.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "get_pod_status",
                "description": "Get status of all pods matching a label selector in a namespace. Returns pod phase, restart counts, termination reasons, resource specs, init container failures, and image pull errors.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "label_selector": {"type": "string", "description": "e.g. 'app=order-service'"},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "get_events",
                "description": "Get Kubernetes events for a namespace, optionally filtered by involved object and time window.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "involved_object_name": {"type": "string", "description": "Filter events for this object name (deployment, pod, etc.)"},
                        "since_minutes": {"type": "integer", "description": "Only return events from the last N minutes (default 60)", "default": 60},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "get_deployment",
                "description": "Get deployment details including replicas, resource specs, and conditions. For OpenShift clusters, falls back to DeploymentConfig if Deployment is not found.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["namespace", "name"],
                },
            },
            {
                "name": "get_pod_logs",
                "description": "Fetch tail logs from a specific pod/container. Useful for diagnosing CrashLoopBackOff, OOMKilled, and application errors. Supports fetching logs from terminated (previous) containers.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "pod_name": {"type": "string"},
                        "container": {"type": "string", "description": "Container name (optional, defaults to first container)"},
                        "tail_lines": {"type": "integer", "description": "Number of lines from the end (default 200, max 200)", "default": 200},
                        "previous": {"type": "boolean", "description": "Fetch logs from previously terminated container (default false)", "default": False},
                    },
                    "required": ["namespace", "pod_name"],
                },
            },
            {
                "name": "get_hpa_status",
                "description": "List Horizontal Pod Autoscalers in a namespace. Shows current/desired/min/max replicas and scaling conditions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                    },
                    "required": ["namespace"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Kubernetes/OpenShift Health Agent for SRE troubleshooting. You use the ReAct pattern with BATCHED tool calls to minimize round-trips.

## TURN-BASED BATCHING (CRITICAL — follow exactly)

### TURN 1 — Discovery (emit ALL of these in ONE response)
Call these tools IN PARALLEL in a single response:
- test_cluster_connectivity
- get_pod_status (use suggested_label_selector if provided, otherwise app={service_name})
- get_events (use since_minutes=60)

### TURN 2 — Deep Dive (emit ALL of these in ONE response)
Based on Turn 1 results, call these tools IN PARALLEL:
- get_deployment (use service_name as deployment name)
- get_pod_logs ONLY if any pod is in CrashLoopBackOff, OOMKilled, Error, or has restarts > 0. Use previous=true for terminated containers.
- get_hpa_status
If all pods are healthy and no warnings, you may skip get_pod_logs.

### TURN 3 — Synthesis
Emit your final JSON answer. Do NOT call any more tools.

## IMPORTANT: You MUST batch multiple tool calls per turn. Do NOT call tools one at a time.

## Negative Findings
When all pods are healthy (Running, 0 restarts), emit a negative finding: "All pods healthy".
When no Warning events are found, emit a negative finding: "No warning events".
Negative findings build trust in the diagnosis — always report them.

## Label Selectors
Use the suggested_label_selector from context if provided. Otherwise derive from service name: app={service_name}.

## OpenShift DeploymentConfig
If get_deployment returns a 404, the workload may be an OpenShift DeploymentConfig. The tool handles this fallback automatically.

## Final Output
After analysis, provide your final answer as JSON:
{
    "pod_statuses": [{"pod_name": "...", "namespace": "...", "status": "...", "restart_count": 0, "last_termination_reason": null, "resource_requests": {}, "resource_limits": {}, "init_container_failures": [], "image_pull_errors": [], "container_count": 1, "ready_containers": 1}],
    "events": [{"timestamp": "...", "type": "Warning", "reason": "...", "message": "...", "source_component": "...", "count": 1, "involved_object": "pod-name"}],
    "is_crashloop": false,
    "total_restarts_last_hour": 0,
    "resource_mismatch": null,
    "overall_confidence": 80
}"""

    async def _build_initial_prompt(self, context: dict) -> str:
        parts = [f"Check Kubernetes health for service: {context.get('service_name', 'unknown')}"]
        if context.get("namespace"):
            parts.append(f"Namespace: {context['namespace']}")
        if context.get("cluster_url"):
            parts.append(f"Cluster: {context['cluster_url']}")
        if context.get("suggested_label_selector"):
            parts.append(f"Suggested label selector: {context['suggested_label_selector']}")
        if context.get("error_patterns"):
            parts.append(f"Error patterns from log analysis: {json.dumps(context['error_patterns'])}")
        parts.append("")
        parts.append("BEGIN TURN 1: Call test_cluster_connectivity + get_pod_status + get_events in parallel NOW.")
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "test_cluster_connectivity":
            return await self._test_cluster_connectivity()
        elif tool_name == "get_pod_status":
            return await self._get_pod_status(tool_input)
        elif tool_name == "get_events":
            return await self._get_events(tool_input)
        elif tool_name == "get_deployment":
            return await self._get_deployment(tool_input)
        elif tool_name == "get_pod_logs":
            return await self._get_pod_logs(tool_input)
        elif tool_name == "get_hpa_status":
            return await self._get_hpa_status(tool_input)
        return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        import re
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse response", "raw_response": text}

        result = {
            "pod_statuses": data.get("pod_statuses", []),
            "events": data.get("events", []),
            "is_crashloop": data.get("is_crashloop", False),
            "total_restarts_last_hour": data.get("total_restarts_last_hour", 0),
            "resource_mismatch": data.get("resource_mismatch"),
            "overall_confidence": data.get("overall_confidence", 50),
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }
        logger.info("K8s agent complete", extra={"agent_name": self.agent_name, "action": "complete", "extra": {"pods": len(result["pod_statuses"]), "events": len(result["events"]), "confidence": result["overall_confidence"]}})
        return result

    # --- Tool implementations ---

    async def _test_cluster_connectivity(self) -> str:
        """Test if K8s/OpenShift cluster is reachable and auth is valid."""
        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())
            nodes = v1.list_node(limit=1, _request_timeout=10)
            version_api = client.VersionApi(self._get_k8s_client())
            version_info = version_api.get_code(_request_timeout=10)

            # Use continue token metadata to get total count without fetching all nodes
            node_count = len(nodes.items) if nodes.items else 0
            version_str = f"{version_info.major}.{version_info.minor}"

            self.add_breadcrumb(
                action="test_cluster_connectivity",
                source_type="k8s_event",
                source_reference="K8s API server",
                raw_evidence=f"Connected: version {version_str}, {node_count} nodes",
            )

            return json.dumps({
                "reachable": True,
                "version": version_str,
                "nodes": node_count,
                "platform": version_info.platform or "unknown",
            })

        except ImportError:
            return json.dumps({"reachable": False, "error": "kubernetes package not installed"})
        except RuntimeError as e:
            return json.dumps({"reachable": False, "error": str(e)})
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                error_msg = "401 Unauthorized — check cluster token"
            elif "403" in error_msg or "Forbidden" in error_msg:
                error_msg = "403 Forbidden — token lacks required permissions"
            return json.dumps({"reachable": False, "error": error_msg})

    async def _get_pod_status(self, params: dict) -> str:
        namespace = params["namespace"]
        label_selector = params.get("label_selector", "")

        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())
            pods = v1.list_namespaced_pod(
                namespace=namespace, label_selector=label_selector, _request_timeout=10,
            )

            result = []
            all_healthy = True
            for pod in pods.items:
                pod_info = self._extract_pod_info(pod)
                result.append(pod_info)
                if pod_info["status"] not in ("Running",) or pod_info["restart_count"] > 0:
                    all_healthy = False

            if not result:
                self.add_negative_finding(
                    what_was_checked=f"Pods in namespace '{namespace}' with selector '{label_selector}'",
                    result="No pods found",
                    implication="Service may not be deployed or selector is incorrect",
                    source_reference=f"K8s API, namespace: {namespace}",
                )
            elif all_healthy:
                self.add_negative_finding(
                    what_was_checked=f"Pod health in namespace '{namespace}'",
                    result="All pods healthy (Running, 0 restarts)",
                    implication="No pod-level issues detected — problem may be elsewhere",
                    source_reference=f"K8s API, namespace: {namespace}, {len(result)} pods checked",
                )

            self.add_breadcrumb(
                action="get_pod_status",
                source_type="k8s_event",
                source_reference=f"namespace: {namespace}, selector: {label_selector}",
                raw_evidence=f"Found {len(result)} pods",
            )

            return json.dumps({"pods": result}, default=str)

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _get_events(self, params: dict) -> str:
        namespace = params["namespace"]
        involved_object = params.get("involved_object_name", "")
        since_minutes = params.get("since_minutes", 60)

        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())
            events = v1.list_namespaced_event(namespace=namespace, _request_timeout=10)

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

            result = []
            for event in events.items:
                # Filter by time
                event_time = event.last_timestamp or event.event_time
                if event_time:
                    # Ensure timezone-aware comparison
                    if hasattr(event_time, 'tzinfo') and event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                    if event_time < cutoff:
                        continue

                if involved_object and event.involved_object.name and involved_object not in event.involved_object.name:
                    continue
                result.append({
                    "timestamp": str(event.last_timestamp or event.event_time or ""),
                    "type": event.type or "Normal",
                    "reason": event.reason or "",
                    "message": event.message or "",
                    "source_component": event.source.component if event.source else "",
                    "count": event.count or 1,
                    "involved_object": event.involved_object.name if event.involved_object else "",
                })

            warning_events = [e for e in result if e["type"] == "Warning"]

            if not warning_events:
                self.add_negative_finding(
                    what_was_checked=f"Warning events in namespace '{namespace}' (last {since_minutes} min)",
                    result="No warning events found",
                    implication="No K8s-level warnings — cluster events are healthy",
                    source_reference=f"K8s API, namespace: {namespace}",
                )

            self.add_breadcrumb(
                action="get_events",
                source_type="k8s_event",
                source_reference=f"namespace: {namespace}",
                raw_evidence=f"Found {len(result)} events ({len(warning_events)} warnings) in last {since_minutes} min",
            )

            return json.dumps({"total": len(result), "warnings": len(warning_events), "events": result}, default=str)

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _get_deployment(self, params: dict) -> str:
        namespace = params["namespace"]
        name = params["name"]

        try:
            from kubernetes import client
            apps_v1 = client.AppsV1Api(self._get_k8s_client())

            deployment = None
            is_dc = False
            try:
                deployment = apps_v1.read_namespaced_deployment(
                    name=name, namespace=namespace, _request_timeout=10,
                )
            except client.exceptions.ApiException as e:
                if e.status == 404:
                    # Fallback to OpenShift DeploymentConfig
                    try:
                        custom_api = client.CustomObjectsApi(self._get_k8s_client())
                        deployment = custom_api.get_namespaced_custom_object(
                            group="apps.openshift.io",
                            version="v1",
                            namespace=namespace,
                            plural="deploymentconfigs",
                            name=name,
                            _request_timeout=10,
                        )
                        is_dc = True
                    except Exception:
                        return json.dumps({"error": f"Deployment '{name}' not found (tried Deployment and DeploymentConfig)"})
                else:
                    raise

            if is_dc:
                # Parse DeploymentConfig (raw dict from CustomObjectsApi)
                spec = deployment.get("spec", {})
                status = deployment.get("status", {})
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                container_specs = []
                for c in containers:
                    cs = {"name": c.get("name", "")}
                    resources = c.get("resources", {})
                    if resources.get("requests"):
                        cs["requests"] = resources["requests"]
                    if resources.get("limits"):
                        cs["limits"] = resources["limits"]
                    container_specs.append(cs)

                result = {
                    "name": deployment.get("metadata", {}).get("name", name),
                    "type": "DeploymentConfig",
                    "replicas_desired": spec.get("replicas", 1),
                    "replicas_available": status.get("availableReplicas", 0),
                    "replicas_ready": status.get("readyReplicas", 0),
                    "containers": container_specs,
                    "conditions": [
                        {"type": c.get("type", ""), "status": c.get("status", ""), "reason": c.get("reason", ""), "message": c.get("message", "")}
                        for c in status.get("conditions", [])
                    ],
                }
            else:
                containers = deployment.spec.template.spec.containers
                container_specs = []
                for c in containers:
                    spec = {"name": c.name}
                    if c.resources:
                        if c.resources.requests:
                            spec["requests"] = dict(c.resources.requests)
                        if c.resources.limits:
                            spec["limits"] = dict(c.resources.limits)
                    container_specs.append(spec)

                result = {
                    "name": deployment.metadata.name,
                    "type": "Deployment",
                    "replicas_desired": deployment.spec.replicas,
                    "replicas_available": deployment.status.available_replicas or 0,
                    "replicas_ready": deployment.status.ready_replicas or 0,
                    "containers": container_specs,
                    "conditions": [
                        {"type": c.type, "status": c.status, "reason": c.reason or "", "message": c.message or ""}
                        for c in (deployment.status.conditions or [])
                    ],
                }

            self.add_breadcrumb(
                action="get_deployment",
                source_type="k8s_event",
                source_reference=f"{result.get('type', 'Deployment')}: {namespace}/{name}",
                raw_evidence=f"Desired: {result['replicas_desired']}, Available: {result['replicas_available']}, Ready: {result['replicas_ready']}",
            )

            return json.dumps(result, default=str)

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _get_pod_logs(self, params: dict) -> str:
        """Fetch tail logs from a specific pod/container."""
        namespace = params["namespace"]
        pod_name = params["pod_name"]
        container = params.get("container")
        tail_lines = min(params.get("tail_lines", 200), 200)
        previous = params.get("previous", False)

        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())

            kwargs = {
                "name": pod_name,
                "namespace": namespace,
                "tail_lines": tail_lines,
                "previous": previous,
                "_request_timeout": 10,
            }
            if container:
                kwargs["container"] = container

            logs = v1.read_namespaced_pod_log(**kwargs)

            # Cap at 8KB to avoid overwhelming the LLM context
            max_bytes = 8192
            if len(logs) > max_bytes:
                logs = logs[-max_bytes:]
                logs = f"[truncated to last {max_bytes} bytes]\n" + logs

            self.add_breadcrumb(
                action="get_pod_logs",
                source_type="log",
                source_reference=f"pod: {namespace}/{pod_name}",
                raw_evidence=f"Fetched {tail_lines} tail lines (previous={previous})",
            )

            return json.dumps({
                "pod_name": pod_name,
                "container": container or "default",
                "previous": previous,
                "lines": len(logs.splitlines()),
                "logs": logs,
            })

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            error_msg = str(e)
            if "previous terminated" in error_msg.lower() or "not found" in error_msg.lower():
                return json.dumps({"error": f"No logs available: {error_msg}"})
            return json.dumps({"error": error_msg})

    async def _get_hpa_status(self, params: dict) -> str:
        """List HPAs in namespace, show current/desired/min/max replicas and conditions."""
        namespace = params["namespace"]

        try:
            from kubernetes import client
            autoscaling_v1 = client.AutoscalingV1Api(self._get_k8s_client())
            hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(
                namespace=namespace, _request_timeout=10,
            )

            result = []
            for hpa in hpas.items:
                result.append({
                    "name": hpa.metadata.name,
                    "target": hpa.spec.scale_target_ref.name if hpa.spec.scale_target_ref else "",
                    "min_replicas": hpa.spec.min_replicas,
                    "max_replicas": hpa.spec.max_replicas,
                    "current_replicas": hpa.status.current_replicas or 0,
                    "desired_replicas": hpa.status.desired_replicas or 0,
                    "current_cpu_utilization": hpa.status.current_cpu_utilization_percentage,
                    "target_cpu_utilization": hpa.spec.target_cpu_utilization_percentage,
                })

            if not result:
                self.add_negative_finding(
                    what_was_checked=f"HPA in namespace '{namespace}'",
                    result="No HPA configured",
                    implication="No autoscaling — replica count is static",
                    source_reference=f"K8s API, namespace: {namespace}",
                )

            self.add_breadcrumb(
                action="get_hpa_status",
                source_type="k8s_event",
                source_reference=f"namespace: {namespace}",
                raw_evidence=f"Found {len(result)} HPAs",
            )

            return json.dumps({"hpas": result}, default=str)

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Helper methods ---

    def _extract_pod_info(self, pod) -> dict:
        """Extract relevant info from a K8s Pod object."""
        info = {
            "pod_name": pod.metadata.name,
            "namespace": pod.metadata.namespace or "",
            "status": pod.status.phase,
            "restart_count": 0,
            "last_termination_reason": None,
            "resource_requests": {},
            "resource_limits": {},
            "init_container_failures": [],
            "image_pull_errors": [],
            "container_count": 0,
            "ready_containers": 0,
            "container_statuses": [],
        }

        # Extract resource specs from pod spec containers
        if pod.spec and pod.spec.containers:
            info["container_count"] = len(pod.spec.containers)
            for c in pod.spec.containers:
                if c.resources:
                    if c.resources.requests:
                        for k, v in c.resources.requests.items():
                            info["resource_requests"][f"{c.name}/{k}"] = str(v)
                    if c.resources.limits:
                        for k, v in c.resources.limits.items():
                            info["resource_limits"][f"{c.name}/{k}"] = str(v)

        # Check init container statuses for failures
        if pod.status.init_container_statuses:
            for ics in pod.status.init_container_statuses:
                if ics.state and ics.state.waiting:
                    reason = ics.state.waiting.reason or "Unknown"
                    info["init_container_failures"].append(f"{ics.name}: {reason}")
                elif ics.state and ics.state.terminated and ics.state.terminated.exit_code != 0:
                    reason = ics.state.terminated.reason or f"exit code {ics.state.terminated.exit_code}"
                    info["init_container_failures"].append(f"{ics.name}: {reason}")

        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                info["restart_count"] += cs.restart_count
                if cs.ready:
                    info["ready_containers"] += 1

                container_info = {"name": cs.name, "ready": cs.ready, "restart_count": cs.restart_count}

                # Check current state
                if cs.state:
                    if cs.state.waiting:
                        container_info["state"] = "waiting"
                        container_info["reason"] = cs.state.waiting.reason or ""
                        if cs.state.waiting.reason == "CrashLoopBackOff":
                            info["status"] = "CrashLoopBackOff"
                        elif cs.state.waiting.reason in ("ImagePullBackOff", "ErrImagePull"):
                            msg = cs.state.waiting.message or cs.state.waiting.reason
                            info["image_pull_errors"].append(f"{cs.name}: {msg}")
                    elif cs.state.running:
                        container_info["state"] = "running"
                    elif cs.state.terminated:
                        container_info["state"] = "terminated"
                        container_info["reason"] = cs.state.terminated.reason or ""

                # Check last state for termination reason
                if cs.last_state and cs.last_state.terminated:
                    info["last_termination_reason"] = cs.last_state.terminated.reason

                info["container_statuses"].append(container_info)

        return info

    @staticmethod
    def _analyze_pod_statuses(pod_statuses: list[dict]) -> dict:
        """Analyze a list of pod status dicts (for testing without K8s client)."""
        is_crashloop = False
        total_restarts = 0
        termination_reasons = []

        for pod in pod_statuses:
            total_restarts += pod.get("restart_count", 0)

            # Check container statuses for CrashLoopBackOff
            for cs in pod.get("container_statuses", []):
                state = cs.get("state", {})
                if isinstance(state, dict) and "waiting" in state:
                    if state["waiting"].get("reason") == "CrashLoopBackOff":
                        is_crashloop = True

            # Check last state termination
            if pod.get("last_termination_reason"):
                termination_reasons.append(pod["last_termination_reason"])

            # Also check container_statuses for last_state
            for cs in pod.get("container_statuses", []):
                last_state = cs.get("last_state", {})
                if isinstance(last_state, dict) and "terminated" in last_state:
                    reason = last_state["terminated"].get("reason", "")
                    if reason:
                        termination_reasons.append(reason)

        return {
            "is_crashloop": is_crashloop,
            "total_restarts": total_restarts,
            "termination_reasons": termination_reasons,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  Two-Pass Mode (1 LLM call)
    # ══════════════════════════════════════════════════════════════════════

    async def run_two_pass(self, context: dict, event_emitter: EventEmitter | None = None) -> dict:
        """Execute K8s health analysis in exactly 1 LLM call.

        Phase 0a: Pre-fetch — test connectivity + get pod status + get events.
                  Zero LLM calls, pure K8s API.
        Phase 0b: Deep dive — get deployment + HPA + pod logs (for unhealthy pods).
                  Zero LLM calls, pure K8s API.
        Call 1:   Analyze — LLM sees ALL K8s data and produces final JSON.
        """
        service_name = context.get("service_name", "unknown")
        namespace = context.get("namespace", "default")
        label_selector = context.get("suggested_label_selector", f"app={service_name}")

        logger.info("K8s agent two-pass starting", extra={
            "agent_name": self.agent_name, "action": "two_pass_start",
            "extra": {"service": service_name, "namespace": namespace, "selector": label_selector},
        })

        if event_emitter:
            await event_emitter.emit(self.agent_name, "started", "K8s agent starting two-pass analysis")

        # ── Phase 0a: Discovery (connectivity + pods + events) ───────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "Pre-fetching cluster connectivity, pods, and events")

        connectivity_raw, pods_raw, events_raw = await asyncio.gather(
            self._test_cluster_connectivity(),
            self._get_pod_status({"namespace": namespace, "label_selector": label_selector}),
            self._get_events({"namespace": namespace, "since_minutes": 60}),
            return_exceptions=True,
        )

        connectivity = self._safe_parse(connectivity_raw)
        pods_data = self._safe_parse(pods_raw)
        events_data = self._safe_parse(events_raw)

        # Check if cluster is unreachable — early exit
        if not connectivity.get("reachable"):
            logger.warning("Cluster unreachable", extra={
                "agent_name": self.agent_name, "action": "cluster_unreachable",
                "extra": {"error": connectivity.get("error", "unknown")},
            })
            if event_emitter:
                await event_emitter.emit(self.agent_name, "error", f"Cluster unreachable: {connectivity.get('error', '')}")
            return {
                "pod_statuses": [],
                "events": [],
                "is_crashloop": False,
                "total_restarts_last_hour": 0,
                "resource_mismatch": None,
                "overall_confidence": 10,
                "error": f"Cluster unreachable: {connectivity.get('error', '')}",
                "mode": "two_pass",
                "llm_calls": 0,
                "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
                "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
                "tokens_used": self.get_token_usage().model_dump(),
            }

        # Determine which pods need log fetching
        pods_list = pods_data.get("pods", [])
        unhealthy_pods = [
            p for p in pods_list
            if p.get("restart_count", 0) > 0
            or p.get("status") in ("CrashLoopBackOff", "Error", "OOMKilled", "Pending", "Unknown")
        ]

        logger.info("Phase 0a complete", extra={
            "agent_name": self.agent_name, "action": "discovery_complete",
            "extra": {
                "cluster_reachable": True,
                "pods_found": len(pods_list),
                "unhealthy_pods": len(unhealthy_pods),
                "events": events_data.get("total", 0),
                "warnings": events_data.get("warnings", 0),
            },
        })

        # ── Phase 0b: Deep dive (deployment + HPA + pod logs) ────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "Fetching deployment, HPA, and pod logs")

        # Build deep-dive tasks
        deep_dive_tasks = [
            self._get_deployment({"namespace": namespace, "name": service_name}),
            self._get_hpa_status({"namespace": namespace}),
        ]

        # Fetch logs for unhealthy pods (max 3 to control data volume)
        log_pod_names = [p["pod_name"] for p in unhealthy_pods[:3]]
        for pod_name in log_pod_names:
            # Current container logs
            deep_dive_tasks.append(
                self._get_pod_logs({"namespace": namespace, "pod_name": pod_name, "tail_lines": 100})
            )
            # Previous (terminated) container logs for crashloops/OOM
            if any(p.get("status") in ("CrashLoopBackOff", "OOMKilled") for p in unhealthy_pods if p["pod_name"] == pod_name):
                deep_dive_tasks.append(
                    self._get_pod_logs({"namespace": namespace, "pod_name": pod_name, "tail_lines": 100, "previous": True})
                )

        deep_results = await asyncio.gather(*deep_dive_tasks, return_exceptions=True)

        # Parse results
        deployment_data = self._safe_parse(deep_results[0]) if len(deep_results) > 0 else {}
        hpa_data = self._safe_parse(deep_results[1]) if len(deep_results) > 1 else {}
        pod_logs: list[dict] = []
        for item in deep_results[2:]:
            parsed = self._safe_parse(item)
            if parsed and "logs" in parsed:
                pod_logs.append(parsed)

        logger.info("Phase 0b complete", extra={
            "agent_name": self.agent_name, "action": "deep_dive_complete",
            "extra": {
                "has_deployment": "name" in deployment_data,
                "hpas": len(hpa_data.get("hpas", [])),
                "pod_logs_fetched": len(pod_logs),
            },
        })

        # ── Call 1: Analyze (the only LLM call) ─────────────────────────
        if event_emitter:
            await event_emitter.emit(self.agent_name, "tool_call", "LLM Call 1: Analyzing all K8s data")

        analyze_prompt = self._build_k8s_analyze_prompt(
            context, connectivity, pods_data, events_data,
            deployment_data, hpa_data, pod_logs
        )
        analyze_response = await self.llm_client.chat(
            prompt=analyze_prompt,
            system=self._two_pass_k8s_system_prompt(),
            max_tokens=4096,
        )

        if event_emitter:
            await event_emitter.emit(self.agent_name, "success", "K8s agent completed analysis")

        result = self._parse_final_response(analyze_response.text)
        result["mode"] = "two_pass"
        result["llm_calls"] = 1
        logger.info("Two-pass K8s analysis complete", extra={
            "agent_name": self.agent_name, "action": "complete",
            "extra": {
                "pods": len(result.get("pod_statuses", [])),
                "events": len(result.get("events", [])),
                "confidence": result.get("overall_confidence", 0),
            },
        })
        return result

    # ── Two-pass helpers ─────────────────────────────────────────────────

    @staticmethod
    def _safe_parse(raw) -> dict:
        """Safely parse a JSON string or return empty dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        if isinstance(raw, Exception):
            return {"error": str(raw)}
        return {}

    def _two_pass_k8s_system_prompt(self) -> str:
        return (
            "You are a Kubernetes/OpenShift Health Agent for SRE troubleshooting.\n\n"
            "You are given ALL pre-fetched K8s data: cluster connectivity, pod statuses, "
            "events, deployment info, HPA status, and pod logs (for unhealthy pods).\n\n"
            "Analyze all this data and produce the final JSON.\n\n"
            "NEGATIVE FINDINGS: When all pods are healthy, report it. When no warnings, report it. "
            "Negative findings build trust in the diagnosis.\n\n"
            "OUTPUT FORMAT — Respond with ONLY JSON (no markdown, no extra text):\n"
            "{\n"
            '    "pod_statuses": [{"pod_name": "...", "namespace": "...", "status": "...", '
            '"restart_count": 0, "last_termination_reason": null, "resource_requests": {}, '
            '"resource_limits": {}, "init_container_failures": [], "image_pull_errors": [], '
            '"container_count": 1, "ready_containers": 1}],\n'
            '    "events": [{"timestamp": "...", "type": "Warning", "reason": "...", '
            '"message": "...", "source_component": "...", "count": 1, "involved_object": "pod-name"}],\n'
            '    "is_crashloop": false,\n'
            '    "total_restarts_last_hour": 0,\n'
            '    "resource_mismatch": null,\n'
            '    "overall_confidence": 80\n'
            "}\n"
        )

    def _build_k8s_analyze_prompt(
        self,
        context: dict,
        connectivity: dict,
        pods_data: dict,
        events_data: dict,
        deployment_data: dict,
        hpa_data: dict,
        pod_logs: list[dict],
    ) -> str:
        parts = [
            "# Kubernetes Health Analysis — All Data Pre-Fetched\n",
            f"## Service: {context.get('service_name', 'unknown')}",
            f"## Namespace: {context.get('namespace', 'default')}",
        ]

        if context.get("error_patterns"):
            parts.append(f"\n## Error Patterns from Log Agent\n{json.dumps(context['error_patterns'], indent=2)}")

        # Cluster connectivity
        parts.append(f"\n## Cluster Connectivity")
        if connectivity.get("reachable"):
            parts.append(
                f"  Connected: version {connectivity.get('version', '?')}, "
                f"{connectivity.get('nodes', '?')} nodes, platform: {connectivity.get('platform', '?')}"
            )
        else:
            parts.append(f"  ERROR: {connectivity.get('error', 'Unknown')}")

        # Pod statuses
        pods_list = pods_data.get("pods", [])
        parts.append(f"\n## Pod Statuses ({len(pods_list)} pods)")
        for pod in pods_list:
            parts.append(
                f"  - **{pod.get('pod_name', '?')}**: status={pod.get('status', '?')}, "
                f"restarts={pod.get('restart_count', 0)}, "
                f"containers={pod.get('ready_containers', 0)}/{pod.get('container_count', 0)}"
            )
            if pod.get("last_termination_reason"):
                parts.append(f"    Last termination: {pod['last_termination_reason']}")
            if pod.get("init_container_failures"):
                parts.append(f"    Init failures: {pod['init_container_failures']}")
            if pod.get("image_pull_errors"):
                parts.append(f"    Image pull errors: {pod['image_pull_errors']}")
            if pod.get("resource_requests"):
                parts.append(f"    Requests: {json.dumps(pod['resource_requests'])}")
            if pod.get("resource_limits"):
                parts.append(f"    Limits: {json.dumps(pod['resource_limits'])}")

        # Events
        events_list = events_data.get("events", [])
        warning_events = [e for e in events_list if e.get("type") == "Warning"]
        parts.append(f"\n## Events ({len(events_list)} total, {len(warning_events)} warnings)")
        for evt in warning_events[:20]:
            parts.append(
                f"  - [{evt.get('type', '?')}] {evt.get('reason', '?')}: "
                f"{evt.get('message', '?')[:200]} (count={evt.get('count', 1)}, "
                f"object={evt.get('involved_object', '?')})"
            )
        if not warning_events:
            parts.append("  No warning events — cluster events are healthy")

        # Deployment
        if deployment_data and "name" in deployment_data:
            parts.append(f"\n## Deployment: {deployment_data.get('name', '?')} ({deployment_data.get('type', 'Deployment')})")
            parts.append(
                f"  Replicas: desired={deployment_data.get('replicas_desired', '?')}, "
                f"available={deployment_data.get('replicas_available', '?')}, "
                f"ready={deployment_data.get('replicas_ready', '?')}"
            )
            for cond in deployment_data.get("conditions", []):
                parts.append(f"  Condition: {cond.get('type', '?')}={cond.get('status', '?')} — {cond.get('message', '')[:100]}")
            for cs in deployment_data.get("containers", []):
                parts.append(f"  Container '{cs.get('name', '?')}': requests={cs.get('requests', {})}, limits={cs.get('limits', {})}")
        elif deployment_data.get("error"):
            parts.append(f"\n## Deployment: ERROR — {deployment_data['error']}")

        # HPA
        hpas = hpa_data.get("hpas", [])
        if hpas:
            parts.append(f"\n## HPA ({len(hpas)} autoscalers)")
            for hpa in hpas:
                parts.append(
                    f"  - {hpa.get('name', '?')}: {hpa.get('current_replicas', 0)}/{hpa.get('max_replicas', '?')} replicas, "
                    f"CPU: {hpa.get('current_cpu_utilization', '?')}% (target {hpa.get('target_cpu_utilization', '?')}%)"
                )
        else:
            parts.append("\n## HPA: No autoscaler configured — replica count is static")

        # Pod logs (for unhealthy pods)
        if pod_logs:
            parts.append(f"\n## Pod Logs ({len(pod_logs)} pods)")
            for log_entry in pod_logs:
                pod_name = log_entry.get("pod_name", "?")
                previous = log_entry.get("previous", False)
                label = f" (PREVIOUS container)" if previous else ""
                lines = log_entry.get("lines", 0)
                logs_text = log_entry.get("logs", "")
                # Truncate to avoid overwhelming the prompt
                if len(logs_text) > 4000:
                    logs_text = logs_text[-4000:]
                    logs_text = f"[truncated]\n{logs_text}"
                parts.append(f"\n### {pod_name}{label} ({lines} lines)")
                parts.append(f"```\n{logs_text}\n```")

        parts.append("\n## Your Task")
        parts.append("Analyze ALL the data above and produce the final K8s health analysis JSON.")

        return "\n".join(parts)
