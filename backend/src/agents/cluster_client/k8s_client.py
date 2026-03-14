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
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="namespaces")
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
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="nodes")
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
            # Prioritize unhealthy pods before truncation
            _STATUS_PRIORITY = {
                "CrashLoopBackOff": 0, "Error": 0, "Failed": 0, "OOMKilled": 0,
                "ImagePullBackOff": 1, "Pending": 2, "Running": 3, "Succeeded": 4,
            }
            def _pod_sort_key(p):
                phase = p.status.phase or "Unknown"
                for cs in (p.status.container_statuses or []):
                    if cs.state and cs.state.waiting:
                        phase = cs.state.waiting.reason or phase
                        break
                return _STATUS_PRIORITY.get(phase, 3)
            sorted_items = sorted(result.items, key=_pod_sort_key)
            pods = []
            for pod in sorted_items[:cap]:
                container_statuses = pod.status.container_statuses or []
                restarts = sum(cs.restart_count for cs in container_statuses)
                # Determine effective status
                phase = pod.status.phase or "Unknown"
                for cs in container_statuses:
                    if cs.state and cs.state.waiting:
                        phase = cs.state.waiting.reason or phase
                        break
                # Aggregate resource requests/limits across all containers
                total_requests: dict[str, str] = {"cpu": "", "memory": ""}
                total_limits: dict[str, str] = {"cpu": "", "memory": ""}
                has_requests = False
                has_limits = False
                for container in (pod.spec.containers or []):
                    if container.resources:
                        if container.resources.requests:
                            has_requests = True
                            total_requests["cpu"] = container.resources.requests.get("cpu", "") or total_requests["cpu"]
                            total_requests["memory"] = container.resources.requests.get("memory", "") or total_requests["memory"]
                        if container.resources.limits:
                            has_limits = True
                            total_limits["cpu"] = container.resources.limits.get("cpu", "") or total_limits["cpu"]
                            total_limits["memory"] = container.resources.limits.get("memory", "") or total_limits["memory"]

                pods.append({
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": phase,
                    "node": pod.spec.node_name or "",
                    "restarts": restarts,
                    "age": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else "",
                    "resources": {
                        "requests": total_requests if has_requests else {},
                        "limits": total_limits if has_limits else {},
                    },
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
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="pods")
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
            # Prioritize: Warning events first, then Normal, sorted by timestamp
            sorted_events = sorted(
                result.items,
                key=lambda e: (
                    0 if e.type == "Warning" else 1,
                    e.last_timestamp.isoformat() if e.last_timestamp else "",
                ),
            )
            events = []
            for ev in sorted_events[:cap]:
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
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="events")
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
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="persistentvolumeclaims")
            return QueryResult()

    async def list_deployments(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(self._apps_api.list_namespaced_deployment, namespace)
            else:
                result = await self._run_sync(self._apps_api.list_deployment_for_all_namespaces)
            deployments = []
            for dep in result.items:
                ready = dep.status.ready_replicas or 0
                desired = dep.spec.replicas or 0
                conditions = {
                    c.type: {"status": c.status, "reason": c.reason or "", "message": c.message or ""}
                    for c in (dep.status.conditions or [])
                }
                deployments.append({
                    "name": dep.metadata.name,
                    "namespace": dep.metadata.namespace,
                    "replicas_desired": desired,
                    "replicas_ready": ready,
                    "replicas_available": dep.status.available_replicas or 0,
                    "replicas_updated": dep.status.updated_replicas or 0,
                    "strategy": dep.spec.strategy.type if dep.spec.strategy else "RollingUpdate",
                    "conditions": conditions,
                    "stuck_rollout": ready < desired and conditions.get("Progressing", {}).get("status") == "False",
                    "age": dep.metadata.creation_timestamp.isoformat() if dep.metadata.creation_timestamp else "",
                })
            return QueryResult(data=deployments, total_available=len(deployments), returned=len(deployments))
        except ApiException as e:
            logger.error("Failed to list deployments: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="deployments")
            return QueryResult()

    async def list_statefulsets(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(self._apps_api.list_namespaced_stateful_set, namespace)
            else:
                result = await self._run_sync(self._apps_api.list_stateful_set_for_all_namespaces)
            statefulsets = []
            for sts in result.items:
                ready = sts.status.ready_replicas or 0
                desired = sts.spec.replicas or 0
                conditions = {
                    c.type: {"status": c.status, "reason": c.reason or "", "message": c.message or ""}
                    for c in (sts.status.conditions or [])
                }
                statefulsets.append({
                    "name": sts.metadata.name,
                    "namespace": sts.metadata.namespace,
                    "replicas_desired": desired,
                    "replicas_ready": ready,
                    "replicas_current": sts.status.current_replicas or 0,
                    "replicas_updated": sts.status.updated_replicas or 0,
                    "ordinal_start": sts.spec.ordinals.start if sts.spec.ordinals else 0,
                    "conditions": conditions,
                    "stuck_rollout": ready < desired,
                    "age": sts.metadata.creation_timestamp.isoformat() if sts.metadata.creation_timestamp else "",
                })
            return QueryResult(data=statefulsets, total_available=len(statefulsets), returned=len(statefulsets))
        except ApiException as e:
            logger.error("Failed to list statefulsets: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="statefulsets")
            return QueryResult()

    async def list_daemonsets(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(self._apps_api.list_namespaced_daemon_set, namespace)
            else:
                result = await self._run_sync(self._apps_api.list_daemon_set_for_all_namespaces)
            daemonsets = []
            for ds in result.items:
                desired = ds.status.desired_number_scheduled or 0
                ready = ds.status.number_ready or 0
                daemonsets.append({
                    "name": ds.metadata.name,
                    "namespace": ds.metadata.namespace,
                    "desired_number_scheduled": desired,
                    "number_ready": ready,
                    "number_unavailable": ds.status.number_unavailable or 0,
                    "number_misscheduled": ds.status.number_misscheduled or 0,
                    "updated_number_scheduled": ds.status.updated_number_scheduled or 0,
                    "age": ds.metadata.creation_timestamp.isoformat() if ds.metadata.creation_timestamp else "",
                })
            return QueryResult(data=daemonsets, total_available=len(daemonsets), returned=len(daemonsets))
        except ApiException as e:
            logger.error("Failed to list daemonsets: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="daemonsets")
            return QueryResult()

    async def list_hpas(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            autoscaling_api = client.AutoscalingV2Api(self._api_client)
            if namespace:
                result = await self._run_sync(autoscaling_api.list_namespaced_horizontal_pod_autoscaler, namespace)
            else:
                result = await self._run_sync(autoscaling_api.list_horizontal_pod_autoscaler_for_all_namespaces)
            hpas = []
            for hpa in result.items:
                conditions = {
                    c.type: {"status": c.status, "reason": c.reason or "", "message": c.message or ""}
                    for c in (hpa.status.conditions or [])
                }
                current_replicas = hpa.status.current_replicas or 0
                max_replicas = hpa.spec.max_replicas or 0
                metrics_status = []
                for metric in (hpa.spec.metrics or []):
                    m: dict[str, Any] = {"type": metric.type}
                    if metric.type == "Resource" and metric.resource:
                        m["resource_name"] = metric.resource.name
                        if metric.resource.target:
                            m["target_type"] = metric.resource.target.type
                            m["target_value"] = metric.resource.target.average_utilization or (
                                metric.resource.target.average_value or metric.resource.target.value or ""
                            )
                    metrics_status.append(m)
                hpas.append({
                    "name": hpa.metadata.name,
                    "namespace": hpa.metadata.namespace,
                    "min_replicas": hpa.spec.min_replicas or 1,
                    "max_replicas": max_replicas,
                    "current_replicas": current_replicas,
                    "desired_replicas": hpa.status.desired_replicas or 0,
                    "target_ref": f"{hpa.spec.scale_target_ref.kind}/{hpa.spec.scale_target_ref.name}" if hpa.spec.scale_target_ref else "",
                    "metrics": metrics_status,
                    "conditions": conditions,
                    "scaling_limited": conditions.get("ScalingLimited", {}).get("status") == "True",
                    "at_max": current_replicas >= max_replicas and max_replicas > 0,
                })
            return QueryResult(data=hpas, total_available=len(hpas), returned=len(hpas))
        except ApiException as e:
            logger.error("Failed to list HPAs: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="horizontalpodautoscalers")
            return QueryResult()
        except Exception as e:
            logger.warning("HPA listing unavailable: %s", e)
            return QueryResult()

    async def list_vpas(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            if namespace:
                result = await self._run_sync(
                    custom_api.list_namespaced_custom_object,
                    "autoscaling.k8s.io", "v1", namespace, "verticalpodautoscalers"
                )
            else:
                result = await self._run_sync(
                    custom_api.list_cluster_custom_object,
                    "autoscaling.k8s.io", "v1", "verticalpodautoscalers"
                )
            vpas = []
            for vpa in result.get("items", []):
                recommendations = {}
                rec = vpa.get("status", {}).get("recommendation", {})
                for container_rec in rec.get("containerRecommendations", []):
                    recommendations[container_rec.get("containerName", "")] = {
                        "target": container_rec.get("target", {}),
                        "lower_bound": container_rec.get("lowerBound", {}),
                        "upper_bound": container_rec.get("upperBound", {}),
                    }
                vpas.append({
                    "name": vpa["metadata"]["name"],
                    "namespace": vpa["metadata"].get("namespace", ""),
                    "target_ref": f"{vpa.get('spec', {}).get('targetRef', {}).get('kind', '')}/{vpa.get('spec', {}).get('targetRef', {}).get('name', '')}",
                    "update_policy": vpa.get("spec", {}).get("updatePolicy", {}).get("updateMode", "Auto"),
                    "recommendations": recommendations,
                })
            return QueryResult(data=vpas, total_available=len(vpas), returned=len(vpas))
        except Exception as e:
            logger.debug("VPA listing unavailable (CRD may not be installed): %s", e)
            return QueryResult()

    async def list_services(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(
                    self._core_api.list_namespaced_service, namespace
                )
            else:
                result = await self._run_sync(
                    self._core_api.list_service_for_all_namespaces
                )
            services = []
            for svc in result.items:
                ports = []
                for p in (svc.spec.ports or []):
                    ports.append({
                        "port": p.port,
                        "target_port": str(p.target_port) if p.target_port else "",
                        "protocol": p.protocol or "TCP",
                        "name": p.name or "",
                    })
                external_ip = ""
                if svc.spec.type == "LoadBalancer" and svc.status and svc.status.load_balancer:
                    ingress_list = svc.status.load_balancer.ingress or []
                    if ingress_list:
                        external_ip = ingress_list[0].ip or ingress_list[0].hostname or ""
                    else:
                        external_ip = "<Pending>"
                services.append({
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "type": svc.spec.type or "ClusterIP",
                    "cluster_ip": svc.spec.cluster_ip or "",
                    "ports": ports,
                    "selector": dict(svc.spec.selector) if svc.spec.selector else {},
                    "external_ip": external_ip,
                })
            return QueryResult(
                data=services,
                total_available=len(services),
                returned=len(services),
            )
        except ApiException as e:
            logger.error("Failed to list services: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="services")
            return QueryResult()

    async def list_endpoints(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(
                    self._core_api.list_namespaced_endpoints, namespace
                )
            else:
                result = await self._run_sync(
                    self._core_api.list_endpoints_for_all_namespaces
                )
            endpoints = []
            for ep in result.items:
                subsets_info = []
                for subset in (ep.subsets or []):
                    addresses_count = len(subset.addresses or [])
                    not_ready_count = len(subset.not_ready_addresses or [])
                    ports = [
                        {"port": p.port, "protocol": p.protocol or "TCP", "name": p.name or ""}
                        for p in (subset.ports or [])
                    ]
                    subsets_info.append({
                        "addresses_count": addresses_count,
                        "not_ready_addresses_count": not_ready_count,
                        "ports": ports,
                    })
                endpoints.append({
                    "name": ep.metadata.name,
                    "namespace": ep.metadata.namespace,
                    "subsets": subsets_info,
                    "total_ready_addresses": sum(s["addresses_count"] for s in subsets_info),
                    "total_not_ready_addresses": sum(s["not_ready_addresses_count"] for s in subsets_info),
                })
            return QueryResult(
                data=endpoints,
                total_available=len(endpoints),
                returned=len(endpoints),
            )
        except ApiException as e:
            logger.error("Failed to list endpoints: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="endpoints")
            return QueryResult()

    async def list_pdbs(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            policy_api = client.PolicyV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(
                    policy_api.list_namespaced_pod_disruption_budget, namespace
                )
            else:
                result = await self._run_sync(
                    policy_api.list_pod_disruption_budget_for_all_namespaces
                )
            pdbs = []
            for pdb in result.items:
                pdbs.append({
                    "name": pdb.metadata.name,
                    "namespace": pdb.metadata.namespace,
                    "min_available": str(pdb.spec.min_available) if pdb.spec.min_available is not None else "",
                    "max_unavailable": str(pdb.spec.max_unavailable) if pdb.spec.max_unavailable is not None else "",
                    "disruptions_allowed": pdb.status.disruptions_allowed if pdb.status else 0,
                    "current_healthy": pdb.status.current_healthy if pdb.status else 0,
                    "desired_healthy": pdb.status.desired_healthy if pdb.status else 0,
                    "expected_pods": pdb.status.expected_pods if pdb.status else 0,
                })
            return QueryResult(
                data=pdbs,
                total_available=len(pdbs),
                returned=len(pdbs),
            )
        except ApiException as e:
            logger.error("Failed to list PDBs: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="poddisruptionbudgets")
            return QueryResult()
        except Exception as e:
            logger.warning("PDB listing unavailable: %s", e)
            return QueryResult()

    async def list_network_policies(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            networking_api = client.NetworkingV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(
                    networking_api.list_namespaced_network_policy, namespace
                )
            else:
                result = await self._run_sync(
                    networking_api.list_network_policy_for_all_namespaces
                )
            policies = []
            for np in result.items:
                policy_types = np.spec.policy_types or []
                ingress_rules = np.spec.ingress or []
                egress_rules = np.spec.egress or []
                # Empty ingress/egress means block all for that direction
                has_empty_ingress = "Ingress" in policy_types and len(ingress_rules) == 0
                has_empty_egress = "Egress" in policy_types and len(egress_rules) == 0
                pod_selector = {}
                if np.spec.pod_selector and np.spec.pod_selector.match_labels:
                    pod_selector = dict(np.spec.pod_selector.match_labels)
                policies.append({
                    "name": np.metadata.name,
                    "namespace": np.metadata.namespace,
                    "pod_selector": pod_selector,
                    "policy_types": policy_types,
                    "ingress_rules_count": len(ingress_rules),
                    "egress_rules_count": len(egress_rules),
                    "has_empty_ingress": has_empty_ingress,
                    "has_empty_egress": has_empty_egress,
                })
            return QueryResult(
                data=policies,
                total_available=len(policies),
                returned=len(policies),
            )
        except ApiException as e:
            logger.error("Failed to list network policies: %s", e)
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="networkpolicies")
            return QueryResult()
        except Exception as e:
            logger.warning("NetworkPolicy listing unavailable: %s", e)
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

    async def get_security_context_constraints(self) -> QueryResult:
        """OpenShift-specific: list SecurityContextConstraints."""
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            result = await self._run_sync(
                custom_api.list_cluster_custom_object,
                "security.openshift.io", "v1", "securitycontextconstraints"
            )
            sccs = []
            for scc in result.get("items", []):
                sccs.append({
                    "name": scc["metadata"]["name"],
                    "allowed_capabilities": scc.get("allowedCapabilities", []),
                    "run_as_user_strategy": scc.get("runAsUser", {}).get("type", ""),
                    "volumes": scc.get("volumes", []),
                })
            return QueryResult(
                data=sccs,
                total_available=len(sccs),
                returned=len(sccs),
            )
        except Exception as e:
            logger.error("Failed to list SCCs: %s", e)
            return QueryResult()

    async def get_build_configs(self, namespace: str = "") -> QueryResult:
        """OpenShift-specific: list BuildConfigs."""
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            if namespace:
                result = await self._run_sync(
                    custom_api.list_namespaced_custom_object,
                    "build.openshift.io", "v1", namespace, "buildconfigs"
                )
            else:
                result = await self._run_sync(
                    custom_api.list_cluster_custom_object,
                    "build.openshift.io", "v1", "buildconfigs"
                )
            build_configs = []
            for bc in result.get("items", []):
                status = bc.get("status", {})
                strategy = bc.get("spec", {}).get("strategy", {})
                build_configs.append({
                    "name": bc["metadata"]["name"],
                    "namespace": bc["metadata"].get("namespace", ""),
                    "strategy_type": strategy.get("type", ""),
                    "last_version": status.get("lastVersion", 0),
                    "status": status.get("phase", "Unknown"),
                })
            return QueryResult(
                data=build_configs,
                total_available=len(build_configs),
                returned=len(build_configs),
            )
        except Exception as e:
            logger.error("Failed to list BuildConfigs: %s", e)
            return QueryResult()

    async def get_image_streams(self, namespace: str = "") -> QueryResult:
        """OpenShift-specific: list ImageStreams."""
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            if namespace:
                result = await self._run_sync(
                    custom_api.list_namespaced_custom_object,
                    "image.openshift.io", "v1", namespace, "imagestreams"
                )
            else:
                result = await self._run_sync(
                    custom_api.list_cluster_custom_object,
                    "image.openshift.io", "v1", "imagestreams"
                )
            image_streams = []
            for istream in result.get("items", []):
                tags = []
                for tag in istream.get("status", {}).get("tags", []):
                    conditions = tag.get("conditions", [])
                    import_failed = any(
                        c.get("type") == "ImportSuccess" and c.get("status") == "False"
                        for c in conditions
                    )
                    tags.append({
                        "tag": tag.get("tag", ""),
                        "import_status": "failed" if import_failed else "ok",
                    })
                image_streams.append({
                    "name": istream["metadata"]["name"],
                    "namespace": istream["metadata"].get("namespace", ""),
                    "tags": tags,
                })
            return QueryResult(
                data=image_streams,
                total_available=len(image_streams),
                returned=len(image_streams),
            )
        except Exception as e:
            logger.error("Failed to list ImageStreams: %s", e)
            return QueryResult()

    async def get_machine_config_pools(self) -> QueryResult:
        """OpenShift-specific: list MachineConfigPools."""
        if self._platform != "openshift":
            return QueryResult()
        self._ensure_client()
        try:
            custom_api = client.CustomObjectsApi(self._api_client)
            result = await self._run_sync(
                custom_api.list_cluster_custom_object,
                "machineconfiguration.openshift.io", "v1", "machineconfigpools"
            )
            pools = []
            for mcp in result.get("items", []):
                status = mcp.get("status", {})
                conditions = {
                    c["type"]: c["status"]
                    for c in status.get("conditions", [])
                }
                pools.append({
                    "name": mcp["metadata"]["name"],
                    "degraded": conditions.get("Degraded") == "True",
                    "updating": conditions.get("Updating") == "True",
                    "machine_count": status.get("machineCount", 0),
                    "ready_count": status.get("readyMachineCount", 0),
                    "updated_count": status.get("updatedMachineCount", 0),
                    "unavailable_count": status.get("unavailableMachineCount", 0),
                })
            return QueryResult(
                data=pools,
                total_available=len(pools),
                returned=len(pools),
            )
        except Exception as e:
            logger.error("Failed to list MachineConfigPools: %s", e)
            return QueryResult()

    async def list_roles(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            rbac_api = client.RbacAuthorizationV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(rbac_api.list_namespaced_role, namespace)
            else:
                result = await self._run_sync(rbac_api.list_role_for_all_namespaces)
            roles = [
                {
                    "name": r.metadata.name,
                    "namespace": r.metadata.namespace,
                    "rules_count": len(r.rules or []),
                    "rules": [
                        {
                            "api_groups": rule.api_groups or [],
                            "resources": rule.resources or [],
                            "verbs": rule.verbs or [],
                        }
                        for rule in (r.rules or [])
                    ],
                }
                for r in result.items
            ]
            return QueryResult(data=roles, total_available=len(roles), returned=len(roles))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="roles")
            logger.error("Failed to list roles: %s", e)
            return QueryResult()

    async def list_role_bindings(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            rbac_api = client.RbacAuthorizationV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(rbac_api.list_namespaced_role_binding, namespace)
            else:
                result = await self._run_sync(rbac_api.list_role_binding_for_all_namespaces)
            bindings = [
                {
                    "name": rb.metadata.name,
                    "namespace": rb.metadata.namespace,
                    "role_ref": {
                        "kind": rb.role_ref.kind,
                        "name": rb.role_ref.name,
                        "api_group": rb.role_ref.api_group,
                    },
                    "subjects": [
                        {
                            "kind": s.kind,
                            "name": s.name,
                            "namespace": getattr(s, "namespace", None) or "",
                        }
                        for s in (rb.subjects or [])
                    ],
                }
                for rb in result.items
            ]
            return QueryResult(data=bindings, total_available=len(bindings), returned=len(bindings))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="rolebindings")
            logger.error("Failed to list role bindings: %s", e)
            return QueryResult()

    async def list_cluster_roles(self) -> QueryResult:
        self._ensure_client()
        try:
            rbac_api = client.RbacAuthorizationV1Api(self._api_client)
            result = await self._run_sync(rbac_api.list_cluster_role)
            cluster_roles = [
                {
                    "name": cr.metadata.name,
                    "rules_count": len(cr.rules or []),
                    "is_aggregate": bool(cr.aggregation_rule),
                    "rules": [
                        {
                            "api_groups": rule.api_groups or [],
                            "resources": rule.resources or [],
                            "verbs": rule.verbs or [],
                        }
                        for rule in (cr.rules or [])
                    ],
                }
                for cr in result.items
            ]
            return QueryResult(data=cluster_roles, total_available=len(cluster_roles), returned=len(cluster_roles))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="clusterroles")
            logger.error("Failed to list cluster roles: %s", e)
            return QueryResult()

    async def list_service_accounts(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            if namespace:
                result = await self._run_sync(self._core_api.list_namespaced_service_account, namespace)
            else:
                result = await self._run_sync(self._core_api.list_service_account_for_all_namespaces)
            service_accounts = [
                {
                    "name": sa.metadata.name,
                    "namespace": sa.metadata.namespace,
                    "secrets_count": len(sa.secrets or []),
                    "automount_token": sa.automount_service_account_token if sa.automount_service_account_token is not None else True,
                }
                for sa in result.items
            ]
            return QueryResult(data=service_accounts, total_available=len(service_accounts), returned=len(service_accounts))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="serviceaccounts")
            logger.error("Failed to list service accounts: %s", e)
            return QueryResult()

    async def list_jobs(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            batch_api = client.BatchV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(batch_api.list_namespaced_job, namespace)
            else:
                result = await self._run_sync(batch_api.list_job_for_all_namespaces)
            jobs = []
            for job in result.items:
                conditions = job.status.conditions or []
                backoff_exceeded = any(
                    c.type == "Failed" and c.reason == "BackoffLimitExceeded" and c.status == "True"
                    for c in conditions
                )
                deadline_exceeded = any(
                    c.type == "Failed" and c.reason == "DeadlineExceeded" and c.status == "True"
                    for c in conditions
                )
                jobs.append({
                    "name": job.metadata.name,
                    "namespace": job.metadata.namespace,
                    "completions": job.spec.completions or 1,
                    "succeeded": job.status.succeeded or 0,
                    "failed": job.status.failed or 0,
                    "active": job.status.active or 0,
                    "backoff_limit_exceeded": backoff_exceeded,
                    "active_deadline_exceeded": deadline_exceeded,
                    "age": job.metadata.creation_timestamp.isoformat() if job.metadata.creation_timestamp else "",
                })
            return QueryResult(data=jobs, total_available=len(jobs), returned=len(jobs))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="jobs")
            logger.error("Failed to list jobs: %s", e)
            return QueryResult()

    async def list_cronjobs(self, namespace: str = "") -> QueryResult:
        self._ensure_client()
        try:
            batch_api = client.BatchV1Api(self._api_client)
            if namespace:
                result = await self._run_sync(batch_api.list_namespaced_cron_job, namespace)
            else:
                result = await self._run_sync(batch_api.list_cron_job_for_all_namespaces)
            cronjobs = []
            for cj in result.items:
                cronjobs.append({
                    "name": cj.metadata.name,
                    "namespace": cj.metadata.namespace,
                    "schedule": cj.spec.schedule or "",
                    "suspend": cj.spec.suspend or False,
                    "last_schedule_time": cj.status.last_schedule_time.isoformat() if cj.status and cj.status.last_schedule_time else "",
                    "active_count": len(cj.status.active or []) if cj.status else 0,
                    "age": cj.metadata.creation_timestamp.isoformat() if cj.metadata.creation_timestamp else "",
                })
            return QueryResult(data=cronjobs, total_available=len(cronjobs), returned=len(cronjobs))
        except ApiException as e:
            if e.status == 403:
                return QueryResult(permission_denied=True, denied_resource="cronjobs")
            logger.error("Failed to list cronjobs: %s", e)
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
