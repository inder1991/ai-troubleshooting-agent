"""Real Kubernetes cluster client using the kubernetes Python library."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from functools import partial
from typing import Any, Optional

from src.agents.cluster_client.base import ClusterClient, QueryResult, OBJECT_CAPS

logger = logging.getLogger(__name__)

# kubernetes is optional — degrade gracefully
try:
    from kubernetes import client, config
    from kubernetes.client import ApiClient, CoreV1Api, AppsV1Api
    from kubernetes.client.exceptions import ApiException
    _K8S_AVAILABLE = True
except ImportError:
    _K8S_AVAILABLE = False


class KubernetesClient(ClusterClient):
    """Real Kubernetes cluster client.

    Parameters
    ----------
    api_url : str
        Kubernetes API server URL (e.g. https://k8s.example.com:6443)
    token : str
        Bearer token for authentication
    verify_ssl : bool
        Whether to verify SSL certificates
    kubeconfig_path : str
        Path to kubeconfig file (used if api_url/token not provided)
    """

    # Cache topology for 60 seconds
    _TOPOLOGY_TTL = 60

    def __init__(
        self,
        api_url: str = "",
        token: str = "",
        verify_ssl: bool = False,
        kubeconfig_path: str = "",
    ) -> None:
        if not _K8S_AVAILABLE:
            raise ImportError(
                "kubernetes library is required. Install with: pip install kubernetes"
            )

        self._api_url = api_url
        self._token = token
        self._verify_ssl = verify_ssl
        self._kubeconfig_path = kubeconfig_path
        self._api_client: Optional[ApiClient] = None
        self._core_api: Optional[CoreV1Api] = None
        self._apps_api: Optional[AppsV1Api] = None
        self._platform: Optional[str] = None
        self._topology_cache: Optional[Any] = None
        self._topology_cache_ts: float = 0

    def _ensure_client(self) -> None:
        """Lazily initialize the K8s API client."""
        if self._api_client is not None:
            return

        if self._api_url and self._token:
            configuration = client.Configuration()
            configuration.host = self._api_url
            configuration.api_key = {"authorization": f"Bearer {self._token}"}
            configuration.verify_ssl = self._verify_ssl
            self._api_client = client.ApiClient(configuration)
        elif self._kubeconfig_path:
            config.load_kube_config(config_file=self._kubeconfig_path)
            self._api_client = client.ApiClient()
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            self._api_client = client.ApiClient()

        self._core_api = client.CoreV1Api(self._api_client)
        self._apps_api = client.AppsV1Api(self._api_client)

    async def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous kubernetes API call in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def detect_platform(self) -> dict[str, str]:
        self._ensure_client()
        try:
            version_info = await self._run_sync(
                client.VersionApi(self._api_client).get_code
            )
            version = f"{version_info.major}.{version_info.minor}"

            # Detect OpenShift by checking for openshift API group
            try:
                api_groups = await self._run_sync(
                    client.ApisApi(self._api_client).get_api_versions
                )
                is_openshift = any(
                    g.name == "apps.openshift.io" for g in api_groups.groups
                )
            except Exception:
                is_openshift = False

            platform = "openshift" if is_openshift else "kubernetes"
            self._platform = platform
            return {"platform": platform, "version": version}
        except Exception as e:
            logger.error("Failed to detect platform: %s", e)
            return {"platform": "kubernetes", "version": "unknown"}

    async def list_namespaces(self) -> QueryResult:
        self._ensure_client()
        try:
            result = await self._run_sync(self._core_api.list_namespace)
            ns_names = [ns.metadata.name for ns in result.items]
            return QueryResult(
                data=ns_names,
                total_available=len(ns_names),
                returned=len(ns_names),
            )
        except ApiException as e:
            logger.error("Failed to list namespaces: %s", e)
            return QueryResult()

    async def list_nodes(self) -> QueryResult:
        self._ensure_client()
        try:
            result = await self._run_sync(self._core_api.list_node)
            cap = OBJECT_CAPS["nodes"]
            nodes = []
            for node in result.items[:cap]:
                conditions = {c.type: c.status for c in (node.status.conditions or [])}
                nodes.append({
                    "name": node.metadata.name,
                    "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                    "roles": ",".join(
                        k.replace("node-role.kubernetes.io/", "")
                        for k in (node.metadata.labels or {})
                        if k.startswith("node-role.kubernetes.io/")
                    ) or "worker",
                    "version": node.status.node_info.kubelet_version if node.status.node_info else "",
                    "cpu_capacity": node.status.capacity.get("cpu", "") if node.status.capacity else "",
                    "memory_capacity": node.status.capacity.get("memory", "") if node.status.capacity else "",
                    "disk_pressure": conditions.get("DiskPressure") == "True",
                    "memory_pressure": conditions.get("MemoryPressure") == "True",
                })
            truncated = len(result.items) > cap
            return QueryResult(
                data=nodes,
                total_available=len(result.items),
                returned=len(nodes),
                truncated=truncated,
            )
        except ApiException as e:
            logger.error("Failed to list nodes: %s", e)
            return QueryResult()

    async def list_pods(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(
                    self._core_api.list_namespaced_pod, namespace
                )
            else:
                result = await self._run_sync(
                    self._core_api.list_pod_for_all_namespaces
                )
            cap = OBJECT_CAPS["pods"]
            pods = []
            for pod in result.items[:cap]:
                container_statuses = pod.status.container_statuses or []
                restarts = sum(cs.restart_count for cs in container_statuses)
                # Determine effective status
                phase = pod.status.phase or "Unknown"
                for cs in container_statuses:
                    if cs.state and cs.state.waiting:
                        phase = cs.state.waiting.reason or phase
                        break
                pods.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": phase,
                    "node": pod.spec.node_name or "",
                    "restarts": restarts,
                    "age": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else "",
                })
            truncated = len(result.items) > cap
            return QueryResult(
                data=pods,
                total_available=len(result.items),
                returned=len(pods),
                truncated=truncated,
            )
        except ApiException as e:
            logger.error("Failed to list pods: %s", e)
            return QueryResult()

    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        self._ensure_client()
        try:
            kwargs = {}
            if field_selector:
                kwargs["field_selector"] = field_selector
            if namespace:
                result = await self._run_sync(
                    self._core_api.list_namespaced_event, namespace, **kwargs
                )
            else:
                result = await self._run_sync(
                    self._core_api.list_event_for_all_namespaces, **kwargs
                )
            cap = OBJECT_CAPS["events"]
            events = []
            for ev in result.items[:cap]:
                events.append({
                    "type": ev.type or "Normal",
                    "reason": ev.reason or "",
                    "message": ev.message or "",
                    "namespace": ev.metadata.namespace or "",
                    "involved_object": f"{ev.involved_object.kind}/{ev.involved_object.name}" if ev.involved_object else "",
                    "count": ev.count or 1,
                    "last_timestamp": ev.last_timestamp.isoformat() if ev.last_timestamp else "",
                })
            truncated = len(result.items) > cap
            return QueryResult(
                data=events,
                total_available=len(result.items),
                returned=len(events),
                truncated=truncated,
            )
        except ApiException as e:
            logger.error("Failed to list events: %s", e)
            return QueryResult()

    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(
                    self._core_api.list_namespaced_persistent_volume_claim, namespace
                )
            else:
                result = await self._run_sync(
                    self._core_api.list_persistent_volume_claim_for_all_namespaces
                )
            cap = OBJECT_CAPS["pvcs"]
            pvcs = []
            for pvc in result.items[:cap]:
                pvcs.append({
                    "name": pvc.metadata.name,
                    "namespace": pvc.metadata.namespace,
                    "status": pvc.status.phase if pvc.status else "Unknown",
                    "capacity": (pvc.status.capacity or {}).get("storage", "") if pvc.status else "",
                    "storage_class": pvc.spec.storage_class_name or "",
                    "access_modes": pvc.spec.access_modes or [],
                })
            truncated = len(result.items) > cap
            return QueryResult(
                data=pvcs,
                total_available=len(result.items),
                returned=len(pvcs),
                truncated=truncated,
            )
        except ApiException as e:
            logger.error("Failed to list PVCs: %s", e)
            return QueryResult()

    async def get_api_health(self) -> dict[str, Any]:
        self._ensure_client()
        try:
            # Check /healthz endpoint
            health = await self._run_sync(
                self._core_api.api_client.call_api,
                "/healthz", "GET",
                _return_http_data_only=True,
                _preload_content=True,
            )
            return {"status": "ok", "response": str(health)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        # Prometheus is accessed via a separate client, not K8s API
        # Return empty — the tool_executor has its own Prometheus client
        return QueryResult()

    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        # Elasticsearch logs are accessed via a separate client
        return QueryResult()

    async def get_cluster_operators(self) -> QueryResult:
        """OpenShift-specific: list ClusterOperators."""
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            result = await self._run_sync(
                custom_api.list_cluster_custom_object,
                "config.openshift.io", "v1", "clusteroperators"
            )
            operators = []
            for op in result.get("items", []):
                conditions = {c["type"]: c["status"] for c in op.get("status", {}).get("conditions", [])}
                operators.append({
                    "name": op["metadata"]["name"],
                    "available": conditions.get("Available") == "True",
                    "degraded": conditions.get("Degraded") == "True",
                    "progressing": conditions.get("Progressing") == "True",
                    "version": (op.get("status", {}).get("versions", [{}]) or [{}])[0].get("version", ""),
                })
            return QueryResult(
                data=operators,
                total_available=len(operators),
                returned=len(operators),
            )
        except Exception as e:
            logger.error("Failed to list cluster operators: %s", e)
            return QueryResult()

    async def get_machine_sets(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            result = await self._run_sync(
                custom_api.list_namespaced_custom_object,
                "machine.openshift.io", "v1beta1", "openshift-machine-api", "machinesets"
            )
            machine_sets = []
            for ms in result.get("items", []):
                spec = ms.get("spec", {})
                status = ms.get("status", {})
                machine_sets.append({
                    "name": ms["metadata"]["name"],
                    "replicas": spec.get("replicas", 0),
                    "ready": status.get("readyReplicas", 0),
                    "available": status.get("availableReplicas", 0),
                })
            return QueryResult(
                data=machine_sets,
                total_available=len(machine_sets),
                returned=len(machine_sets),
            )
        except Exception as e:
            logger.error("Failed to list machine sets: %s", e)
            return QueryResult()

    async def get_routes(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            if namespace:
                result = await self._run_sync(
                    custom_api.list_namespaced_custom_object,
                    "route.openshift.io", "v1", namespace, "routes"
                )
            else:
                result = await self._run_sync(
                    custom_api.list_cluster_custom_object,
                    "route.openshift.io", "v1", "routes"
                )
            routes = []
            for route in result.get("items", []):
                spec = route.get("spec", {})
                status_ingress = route.get("status", {}).get("ingress", [])
                admitted = any(
                    c.get("type") == "Admitted" and c.get("status") == "True"
                    for ing in status_ingress
                    for c in ing.get("conditions", [])
                )
                routes.append({
                    "name": route["metadata"]["name"],
                    "namespace": route["metadata"].get("namespace", ""),
                    "host": spec.get("host", ""),
                    "status": "Admitted" if admitted else "Pending",
                })
            return QueryResult(
                data=routes,
                total_available=len(routes),
                returned=len(routes),
            )
        except Exception as e:
            logger.error("Failed to list routes: %s", e)
            return QueryResult()

    async def build_topology_snapshot(self) -> "TopologySnapshot":
        """Build resource topology from live cluster state with TTL caching."""
        now = time.monotonic()
        if self._topology_cache and (now - self._topology_cache_ts) < self._TOPOLOGY_TTL:
            return self._topology_cache

        from src.agents.cluster.state import TopologySnapshot, TopologyNode, TopologyEdge

        topo_nodes: dict[str, TopologyNode] = {}
        edges: list[TopologyEdge] = []

        # Nodes
        nodes_result = await self.list_nodes()
        for n in nodes_result.data:
            key = f"node/{n['name']}"
            topo_nodes[key] = TopologyNode(
                kind="node", name=n["name"], status=n.get("status", "Unknown")
            )

        # Pods
        pods_result = await self.list_pods()
        for p in pods_result.data:
            ns = p.get("namespace", "default")
            key = f"pod/{ns}/{p['name']}"
            node_name = p.get("node", "")
            topo_nodes[key] = TopologyNode(
                kind="pod", name=p["name"], namespace=ns,
                status=p.get("status", "Unknown"), node_name=node_name,
            )
            if node_name:
                edges.append(TopologyEdge(
                    from_key=f"node/{node_name}", to_key=key, relation="hosts"
                ))

        # Deployments -> ReplicaSets -> Pods (if apps API available)
        try:
            deploy_result = await self._run_sync(
                self._apps_api.list_deployment_for_all_namespaces
            )
            for dep in deploy_result.items:
                ns = dep.metadata.namespace
                key = f"deployment/{ns}/{dep.metadata.name}"
                ready = dep.status.ready_replicas or 0
                desired = dep.spec.replicas or 0
                status = "Available" if ready >= desired else "Degraded"
                topo_nodes[key] = TopologyNode(
                    kind="deployment", name=dep.metadata.name,
                    namespace=ns, status=status,
                )
                # Link deployment to its pods via label selector
                for pod_key, pod_node in topo_nodes.items():
                    if pod_node.kind == "pod" and pod_node.namespace == ns:
                        edges.append(TopologyEdge(
                            from_key=key, to_key=pod_key, relation="manages"
                        ))
        except Exception:
            pass  # Apps API may not be available

        # OpenShift operators
        if self._platform == "openshift":
            ops = await self.get_cluster_operators()
            for op in ops.data:
                key = f"operator/{op['name']}"
                status = "Degraded" if op.get("degraded") else (
                    "Available" if op.get("available") else "Unavailable"
                )
                topo_nodes[key] = TopologyNode(
                    kind="operator", name=op["name"], status=status
                )

        snapshot = TopologySnapshot(
            nodes=topo_nodes,
            edges=edges,
            built_at=datetime.now(timezone.utc).isoformat(),
        )
        self._topology_cache = snapshot
        self._topology_cache_ts = now
        return snapshot

    async def close(self) -> None:
        if self._api_client:
            try:
                await self._run_sync(self._api_client.close)
            except Exception:
                pass
            self._api_client = None
            self._core_api = None
            self._apps_api = None
