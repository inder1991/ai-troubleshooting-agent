import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.agents.react_base import ReActAgent
from src.models.schemas import PodHealthStatus, K8sEvent, K8sAnalysisResult, TokenUsage


class K8sAgent(ReActAgent):
    """ReAct agent for Kubernetes/OpenShift cluster health analysis."""

    def __init__(self, max_iterations: int = 8, connection_config=None):
        super().__init__(agent_name="k8s_agent", max_iterations=max_iterations)
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
                "description": "Get status of all pods matching a label selector in a namespace.",
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
                "description": "Get Kubernetes events for a namespace, optionally filtered by involved object.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "involved_object_name": {"type": "string", "description": "Filter events for this object name (deployment, pod, etc.)"},
                    },
                    "required": ["namespace"],
                },
            },
            {
                "name": "get_deployment",
                "description": "Get deployment details including replicas, resource specs, and conditions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "namespace": {"type": "string"},
                        "name": {"type": "string"},
                    },
                    "required": ["namespace", "name"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Kubernetes/OpenShift Health Agent for SRE troubleshooting. You use the ReAct pattern.

IMPORTANT: Always call test_cluster_connectivity FIRST before any other K8s tool to verify the connection. If connectivity fails, report the error immediately instead of attempting further queries.

Your goals:
1. Test cluster connectivity first
2. Check pod status — look for CrashLoopBackOff, Error, OOMKilled, Pending states
3. Check restart counts and termination reasons
4. Get events for the namespace/deployment — focus on Warning events
5. Check resource requests vs limits
6. Report negative findings when everything looks healthy
7. Cross-reference with metrics data if provided

After analysis, provide your final answer as JSON:
{
    "pod_statuses": [{"pod_name": "...", "status": "...", "restart_count": 0, "last_termination_reason": "...", "resource_requests": {}, "resource_limits": {}}],
    "events": [{"timestamp": "...", "type": "Warning", "reason": "...", "message": "...", "source_component": "..."}],
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
        if context.get("error_patterns"):
            parts.append(f"Error patterns from log analysis: {json.dumps(context['error_patterns'])}")
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

        return {
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

    # --- Tool implementations ---

    async def _test_cluster_connectivity(self) -> str:
        """Test if K8s/OpenShift cluster is reachable and auth is valid."""
        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())
            nodes = v1.list_node(limit=100)
            version_api = client.VersionApi(self._get_k8s_client())
            version_info = version_api.get_code()

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
            pods = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)

            result = []
            for pod in pods.items:
                pod_info = self._extract_pod_info(pod)
                result.append(pod_info)

            if not result:
                self.add_negative_finding(
                    what_was_checked=f"Pods in namespace '{namespace}' with selector '{label_selector}'",
                    result="No pods found",
                    implication="Service may not be deployed or selector is incorrect",
                    source_reference=f"K8s API, namespace: {namespace}",
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

        try:
            from kubernetes import client
            v1 = client.CoreV1Api(self._get_k8s_client())
            events = v1.list_namespaced_event(namespace=namespace)

            result = []
            for event in events.items:
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

            self.add_breadcrumb(
                action="get_events",
                source_type="k8s_event",
                source_reference=f"namespace: {namespace}",
                raw_evidence=f"Found {len(result)} events ({len(warning_events)} warnings)",
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
            deployment = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

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
                source_reference=f"deployment: {namespace}/{name}",
                raw_evidence=f"Desired: {result['replicas_desired']}, Available: {result['replicas_available']}, Ready: {result['replicas_ready']}",
            )

            return json.dumps(result, default=str)

        except ImportError:
            return json.dumps({"error": "kubernetes package not installed"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Helper methods ---

    def _extract_pod_info(self, pod) -> dict:
        """Extract relevant info from a K8s Pod object."""
        info = {
            "pod_name": pod.metadata.name,
            "status": pod.status.phase,
            "restart_count": 0,
            "last_termination_reason": None,
            "container_statuses": [],
        }

        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                info["restart_count"] += cs.restart_count

                container_info = {"name": cs.name, "ready": cs.ready, "restart_count": cs.restart_count}

                # Check current state
                if cs.state:
                    if cs.state.waiting:
                        container_info["state"] = "waiting"
                        container_info["reason"] = cs.state.waiting.reason or ""
                        if cs.state.waiting.reason == "CrashLoopBackOff":
                            info["status"] = "CrashLoopBackOff"
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
