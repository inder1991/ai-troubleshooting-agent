"""Mock ClusterClient that returns fixture data for demo/dev/testing."""

from __future__ import annotations
import json
import os
from typing import Any
from src.agents.cluster_client.base import ClusterClient, QueryResult, OBJECT_CAPS
import asyncio

# Realistic demo delays to simulate K8s API latency
_DEMO_DELAYS = {
    "detect_platform": 0.5,
    "list_namespaces": 0.8,
    "list_nodes": 2.0,
    "list_pods": 2.5,
    "list_events": 1.5,
    "list_pvcs": 1.0,
    "get_api_health": 1.0,
    "query_prometheus": 1.5,
    "query_logs": 1.0,
    "list_deployments": 1.2,
    "list_statefulsets": 0.8,
    "list_daemonsets": 0.8,
    "list_services": 1.0,
    "list_endpoints": 0.8,
    "list_pdbs": 0.5,
    "list_network_policies": 0.5,
    "list_hpas": 0.5,
    "get_cluster_operators": 1.5,
    "get_machine_config_pools": 1.0,
    "get_cluster_version": 0.5,
    "list_machines": 0.8,
    "list_subscriptions": 0.5,
    "list_csvs": 0.5,
    "get_routes": 0.8,
    "list_roles": 0.5,
    "list_role_bindings": 0.5,
    "list_cluster_roles": 0.5,
    "list_service_accounts": 0.5,
    "list_jobs": 0.5,
    "list_cronjobs": 0.5,
    "list_tls_secrets": 0.5,
    "get_security_context_constraints": 0.5,
    "get_proxy_config": 0.3,
    "list_install_plans": 0.3,
    "get_build_configs": 0.5,
    "get_image_streams": 0.5,
    "get_machine_sets": 0.5,
    "list_vpas": 0.3,
}

async def _demo_delay(method_name: str) -> None:
    """Add realistic delay for demo mode."""
    delay = _DEMO_DELAYS.get(method_name, 0.5)
    if delay > 0:
        await asyncio.sleep(delay)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def _load_fixture(name: str) -> dict:
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r") as f:
        return json.load(f)

class MockClusterClient(ClusterClient):
    def __init__(self, platform: str = "openshift"):
        self._platform = platform

    async def detect_platform(self) -> dict[str, str]:
        await _demo_delay("detect_platform")
        return {"platform": self._platform, "version": "4.14.12" if self._platform == "openshift" else "1.28.3"}

    async def list_namespaces(self) -> QueryResult:
        await _demo_delay("list_namespaces")
        ns = ["default", "kube-system", "openshift-dns", "openshift-ingress",
              "openshift-monitoring", "openshift-machine-config-operator",
              "openshift-cluster-csi-drivers", "openshift-operators",
              "openshift-operators-redhat", "ecommerce-prod", "ecommerce-staging",
              "monitoring", "logging"]
        return QueryResult(data=ns, total_available=len(ns), returned=len(ns))

    async def list_nodes(self) -> QueryResult:
        await _demo_delay("list_nodes")
        data = _load_fixture("cluster_node_mock.json")
        nodes = data["nodes"]
        return QueryResult(data=nodes, total_available=len(nodes), returned=len(nodes))

    async def list_pods(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_pods")
        data = _load_fixture("cluster_node_mock.json")
        pods = data.get("top_pods", [])
        if namespace:
            pods = [p for p in pods if p.get("namespace") == namespace]
        return QueryResult(data=pods, total_available=len(pods), returned=len(pods))

    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        await _demo_delay("list_events")
        data = _load_fixture("cluster_node_mock.json")
        events = data.get("events", [])
        if namespace:
            events = [e for e in events if e.get("namespace") == namespace]
        cap = OBJECT_CAPS["events"]
        truncated = len(events) > cap
        returned = events[:cap]
        return QueryResult(data=returned, total_available=len(events), returned=len(returned), truncated=truncated)

    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_pvcs")
        data = _load_fixture("cluster_storage_mock.json")
        pvcs = data.get("pvcs", [])
        return QueryResult(data=pvcs, total_available=len(pvcs), returned=len(pvcs))

    async def get_api_health(self) -> dict[str, Any]:
        await _demo_delay("get_api_health")
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        return data.get("api_health", {"status": "ok"})

    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        await _demo_delay("query_prometheus")
        if "dns" in query or "coredns" in query:
            data = _load_fixture("cluster_network_mock.json")
            metrics = data.get("dns_metrics", {})
        elif "node" in query or "cpu" in query or "memory" in query:
            data = _load_fixture("cluster_node_mock.json")
            metrics = {"nodes": data.get("nodes", [])}
        else:
            metrics = {"value": 0}
        return QueryResult(data=[metrics], total_available=1, returned=1)

    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        await _demo_delay("query_logs")
        data = _load_fixture("cluster_network_mock.json")
        logs = data.get("logs", [])
        return QueryResult(data=logs, total_available=len(logs), returned=len(logs))

    async def list_deployments(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_deployments")
        deployments = [
            {
                "name": "api-gateway",
                "namespace": "ecommerce-prod",
                "replicas_desired": 3,
                "replicas_ready": 3,
                "replicas_available": 3,
                "replicas_updated": 3,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                    "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
                },
                "stuck_rollout": False,
                "age": "2026-02-01T10:00:00+00:00",
            },
            {
                "name": "order-service",
                "namespace": "ecommerce-prod",
                "replicas_desired": 4,
                "replicas_ready": 2,
                "replicas_available": 2,
                "replicas_updated": 4,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                    "Progressing": {"status": "False", "reason": "ProgressDeadlineExceeded", "message": "ReplicaSet \"order-service-5c7d8\" has timed out progressing."},
                },
                "stuck_rollout": True,
                "age": "2026-03-15T08:30:00+00:00",
            },
            {
                "name": "catalog-service",
                "namespace": "ecommerce-prod",
                "replicas_desired": 2,
                "replicas_ready": 1,
                "replicas_available": 1,
                "replicas_updated": 2,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                    "Progressing": {"status": "True", "reason": "ReplicaSetUpdated", "message": "ReplicaSet is progressing."},
                },
                "stuck_rollout": False,
                "age": "2026-02-20T14:00:00+00:00",
            },
            {
                "name": "payment-gateway",
                "namespace": "ecommerce-prod",
                "replicas_desired": 2,
                "replicas_ready": 0,
                "replicas_available": 0,
                "replicas_updated": 2,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "False", "reason": "MinimumReplicasUnavailable", "message": "Deployment does not have minimum availability."},
                    "Progressing": {"status": "False", "reason": "ProgressDeadlineExceeded", "message": "ReplicaSet has timed out progressing."},
                },
                "stuck_rollout": True,
                "age": "2026-03-10T09:00:00+00:00",
            },
            {
                "name": "cart-service",
                "namespace": "ecommerce-prod",
                "replicas_desired": 2,
                "replicas_ready": 2,
                "replicas_available": 2,
                "replicas_updated": 2,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                    "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
                },
                "stuck_rollout": False,
                "age": "2026-01-20T14:00:00+00:00",
            },
            {
                "name": "user-auth-service",
                "namespace": "ecommerce-prod",
                "replicas_desired": 2,
                "replicas_ready": 2,
                "replicas_available": 2,
                "replicas_updated": 2,
                "strategy": "RollingUpdate",
                "conditions": {
                    "Available": {"status": "True", "reason": "MinimumReplicasAvailable", "message": "Deployment has minimum availability."},
                    "Progressing": {"status": "True", "reason": "NewReplicaSetAvailable", "message": "ReplicaSet has successfully progressed."},
                },
                "stuck_rollout": False,
                "age": "2026-01-15T10:00:00+00:00",
            },
        ]
        if namespace:
            deployments = [d for d in deployments if d["namespace"] == namespace]
        return QueryResult(data=deployments, total_available=len(deployments), returned=len(deployments))

    async def list_statefulsets(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_statefulsets")
        statefulsets = [
            {
                "name": "postgres-primary",
                "namespace": "ecommerce-prod",
                "replicas_desired": 2,
                "replicas_ready": 2,
                "replicas_current": 2,
                "replicas_updated": 2,
                "ordinal_start": 0,
                "conditions": {},
                "stuck_rollout": False,
                "age": "2026-01-10T12:00:00+00:00",
            },
            {
                "name": "redis-cluster",
                "namespace": "ecommerce-prod",
                "replicas_desired": 3,
                "replicas_ready": 3,
                "replicas_current": 3,
                "replicas_updated": 3,
                "ordinal_start": 0,
                "conditions": {},
                "stuck_rollout": False,
                "age": "2026-02-05T16:00:00+00:00",
            },
        ]
        if namespace:
            statefulsets = [s for s in statefulsets if s["namespace"] == namespace]
        return QueryResult(data=statefulsets, total_available=len(statefulsets), returned=len(statefulsets))

    async def list_daemonsets(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_daemonsets")
        daemonsets = [
            {
                "name": "fluentd-logging",
                "namespace": "kube-system",
                "desired_number_scheduled": 5,
                "number_ready": 4,
                "number_unavailable": 1,
                "number_misscheduled": 0,
                "updated_number_scheduled": 5,
                "age": "2026-01-05T10:00:00+00:00",
            },
            {
                "name": "node-exporter",
                "namespace": "monitoring",
                "desired_number_scheduled": 5,
                "number_ready": 4,
                "number_unavailable": 1,
                "number_misscheduled": 0,
                "updated_number_scheduled": 5,
                "age": "2026-01-05T10:00:00+00:00",
            },
            {
                "name": "calico-node",
                "namespace": "kube-system",
                "desired_number_scheduled": 5,
                "number_ready": 5,
                "number_unavailable": 0,
                "number_misscheduled": 0,
                "updated_number_scheduled": 5,
                "age": "2026-01-01T00:00:00+00:00",
            },
        ]
        if namespace:
            daemonsets = [d for d in daemonsets if d["namespace"] == namespace]
        return QueryResult(data=daemonsets, total_available=len(daemonsets), returned=len(daemonsets))

    async def list_services(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_services")
        services = [
            {
                "name": "api-gateway",
                "namespace": "ecommerce-prod",
                "type": "ClusterIP",
                "cluster_ip": "10.96.45.12",
                "ports": [{"port": 80, "target_port": "8080", "protocol": "TCP", "name": "http"}],
                "selector": {"app": "api-gateway"},
                "external_ip": "",
            },
            {
                "name": "order-service",
                "namespace": "ecommerce-prod",
                "type": "ClusterIP",
                "cluster_ip": "10.96.78.34",
                "ports": [{"port": 8080, "target_port": "8080", "protocol": "TCP", "name": "http"}],
                "selector": {"app": "order-service"},
                "external_ip": "",
            },
            {
                "name": "payment-gateway",
                "namespace": "ecommerce-prod",
                "type": "ClusterIP",
                "cluster_ip": "10.96.102.56",
                "ports": [{"port": 8443, "target_port": "8443", "protocol": "TCP", "name": "https"}],
                "selector": {"app": "payment-gateway"},
                "external_ip": "",
            },
            {
                "name": "catalog-service",
                "namespace": "ecommerce-prod",
                "type": "ClusterIP",
                "cluster_ip": "10.96.55.78",
                "ports": [{"port": 8080, "target_port": "8080", "protocol": "TCP", "name": "http"}],
                "selector": {"app": "catalog-service"},
                "external_ip": "",
            },
            {
                "name": "public-lb",
                "namespace": "ecommerce-prod",
                "type": "LoadBalancer",
                "cluster_ip": "10.96.200.1",
                "ports": [{"port": 443, "target_port": "8443", "protocol": "TCP", "name": "https"}],
                "selector": {"app": "api-gateway"},
                "external_ip": "52.23.178.92",
            },
        ]
        if namespace:
            services = [s for s in services if s["namespace"] == namespace]
        return QueryResult(data=services, total_available=len(services), returned=len(services))

    async def list_endpoints(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_endpoints")
        endpoints = [
            {
                "name": "api-gateway",
                "namespace": "ecommerce-prod",
                "subsets": [{"addresses_count": 3, "not_ready_addresses_count": 0, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
                "total_ready_addresses": 3,
                "total_not_ready_addresses": 0,
            },
            {
                "name": "order-service",
                "namespace": "ecommerce-prod",
                "subsets": [{"addresses_count": 2, "not_ready_addresses_count": 2, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
                "total_ready_addresses": 2,
                "total_not_ready_addresses": 2,
            },
            {
                "name": "payment-gateway",
                "namespace": "ecommerce-prod",
                "subsets": [{"addresses_count": 0, "not_ready_addresses_count": 2, "ports": [{"port": 8443, "protocol": "TCP", "name": "https"}]}],
                "total_ready_addresses": 0,
                "total_not_ready_addresses": 2,
            },
            {
                "name": "catalog-service",
                "namespace": "ecommerce-prod",
                "subsets": [{"addresses_count": 1, "not_ready_addresses_count": 1, "ports": [{"port": 8080, "protocol": "TCP", "name": "http"}]}],
                "total_ready_addresses": 1,
                "total_not_ready_addresses": 1,
            },
        ]
        if namespace:
            endpoints = [e for e in endpoints if e["namespace"] == namespace]
        return QueryResult(data=endpoints, total_available=len(endpoints), returned=len(endpoints))

    async def list_pdbs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_pdbs")
        pdbs = [
            {
                "name": "api-gateway-pdb",
                "namespace": "ecommerce-prod",
                "min_available": "2",
                "max_unavailable": "",
                "disruptions_allowed": 1,
                "current_healthy": 3,
                "desired_healthy": 2,
                "expected_pods": 3,
            },
            {
                "name": "redis-cluster-pdb",
                "namespace": "ecommerce-prod",
                "min_available": "4",
                "max_unavailable": "",
                "disruptions_allowed": 0,
                "current_healthy": 4,
                "desired_healthy": 4,
                "expected_pods": 6,
            },
        ]
        if namespace:
            pdbs = [p for p in pdbs if p["namespace"] == namespace]
        return QueryResult(data=pdbs, total_available=len(pdbs), returned=len(pdbs))

    async def list_network_policies(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_network_policies")
        data = _load_fixture("cluster_network_mock.json")
        policies = data.get("network_policies", [])
        if namespace:
            policies = [p for p in policies if p.get("namespace") == namespace]
        return QueryResult(data=policies, total_available=len(policies), returned=len(policies))

    async def list_hpas(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_hpas")
        hpas = [
            {
                "name": "catalog-service-hpa",
                "namespace": "ecommerce-prod",
                "min_replicas": 2,
                "max_replicas": 8,
                "current_replicas": 8,
                "desired_replicas": 12,
                "target_ref": "Deployment/catalog-service",
                "metrics": [
                    {"type": "Resource", "resource_name": "cpu", "target_type": "Utilization", "target_value": 70},
                ],
                "conditions": {
                    "AbleToScale": {"status": "True", "reason": "ReadyForNewScale", "message": "recommended size matches current size"},
                    "ScalingActive": {"status": "True", "reason": "ValidMetricFound", "message": "the HPA was able to successfully calculate a replica count"},
                    "ScalingLimited": {"status": "True", "reason": "TooManyReplicas", "message": "the desired replica count is more than the maximum replica count"},
                },
                "scaling_limited": True,
                "at_max": True,
            },
            {
                "name": "api-gateway-hpa",
                "namespace": "ecommerce-prod",
                "min_replicas": 3,
                "max_replicas": 10,
                "current_replicas": 3,
                "desired_replicas": 3,
                "target_ref": "Deployment/api-gateway",
                "metrics": [
                    {"type": "Resource", "resource_name": "cpu", "target_type": "Utilization", "target_value": 80},
                ],
                "conditions": {
                    "AbleToScale": {"status": "True", "reason": "ReadyForNewScale", "message": "recommended size matches current size"},
                    "ScalingActive": {"status": "True", "reason": "ValidMetricFound", "message": "the HPA was able to successfully calculate a replica count"},
                    "ScalingLimited": {"status": "False", "reason": "DesiredWithinRange", "message": "the desired count is within the acceptable range"},
                },
                "scaling_limited": False,
                "at_max": False,
            },
        ]
        if namespace:
            hpas = [h for h in hpas if h["namespace"] == namespace]
        return QueryResult(data=hpas, total_available=len(hpas), returned=len(hpas))

    async def list_vpas(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_vpas")
        return QueryResult()

    async def get_cluster_operators(self) -> QueryResult:
        await _demo_delay("get_cluster_operators")
        if self._platform != "openshift":
            return QueryResult()
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        ops = data.get("cluster_operators", [])
        return QueryResult(data=ops, total_available=len(ops), returned=len(ops))

    async def get_machine_sets(self) -> QueryResult:
        await _demo_delay("get_machine_sets")
        if self._platform != "openshift":
            return QueryResult()
        return QueryResult(data=[{"name": "worker-us-east-1a", "replicas": 3, "ready": 3}], total_available=1, returned=1)

    async def get_routes(self, namespace: str = "") -> QueryResult:
        await _demo_delay("get_routes")
        if self._platform != "openshift":
            return QueryResult()
        data = _load_fixture("cluster_network_mock.json")
        routes = data.get("routes", [])
        if namespace:
            routes = [r for r in routes if r.get("namespace") == namespace]
        return QueryResult(data=routes, total_available=len(routes), returned=len(routes))

    async def get_security_context_constraints(self) -> QueryResult:
        await _demo_delay("get_security_context_constraints")
        if self._platform != "openshift":
            return QueryResult()
        sccs = [
            {
                "name": "restricted",
                "allowed_capabilities": [],
                "run_as_user_strategy": "MustRunAsRange",
                "volumes": ["configMap", "downwardAPI", "emptyDir", "persistentVolumeClaim", "projected", "secret"],
            },
            {
                "name": "anyuid",
                "allowed_capabilities": [],
                "run_as_user_strategy": "RunAsAny",
                "volumes": ["configMap", "downwardAPI", "emptyDir", "persistentVolumeClaim", "projected", "secret"],
            },
            {
                "name": "privileged",
                "allowed_capabilities": ["*"],
                "run_as_user_strategy": "RunAsAny",
                "volumes": ["*"],
            },
        ]
        return QueryResult(data=sccs, total_available=len(sccs), returned=len(sccs))

    async def get_build_configs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("get_build_configs")
        if self._platform != "openshift":
            return QueryResult()
        build_configs = [
            {
                "name": "api-service-build",
                "namespace": "production",
                "strategy_type": "Docker",
                "last_version": 12,
                "status": "Complete",
            },
            {
                "name": "worker-build",
                "namespace": "production",
                "strategy_type": "Source",
                "last_version": 7,
                "status": "Failed",
            },
        ]
        if namespace:
            build_configs = [bc for bc in build_configs if bc["namespace"] == namespace]
        return QueryResult(data=build_configs, total_available=len(build_configs), returned=len(build_configs))

    async def get_image_streams(self, namespace: str = "") -> QueryResult:
        await _demo_delay("get_image_streams")
        if self._platform != "openshift":
            return QueryResult()
        image_streams = [
            {
                "name": "api-service",
                "namespace": "production",
                "tags": [
                    {"tag": "latest", "import_status": "ok"},
                    {"tag": "v2.1.0", "import_status": "ok"},
                ],
            },
            {
                "name": "worker-service",
                "namespace": "production",
                "tags": [
                    {"tag": "latest", "import_status": "failed"},
                    {"tag": "v1.8.0", "import_status": "ok"},
                ],
            },
        ]
        if namespace:
            image_streams = [i for i in image_streams if i["namespace"] == namespace]
        return QueryResult(data=image_streams, total_available=len(image_streams), returned=len(image_streams))

    async def get_machine_config_pools(self) -> QueryResult:
        await _demo_delay("get_machine_config_pools")
        if self._platform != "openshift":
            return QueryResult()
        pools = [
            {
                "name": "master",
                "degraded": False,
                "updating": False,
                "machine_count": 3,
                "ready_count": 3,
                "updated_count": 3,
                "unavailable_count": 0,
            },
            {
                "name": "worker",
                "degraded": True,
                "updating": True,
                "machine_count": 3,
                "ready_count": 2,
                "updated_count": 2,
                "unavailable_count": 1,
                "message": "Node worker-3.prod-east.internal is reporting Degraded — rendered-worker-9f8a2b failed to apply 99-worker-kernel-params",
            },
        ]
        return QueryResult(data=pools, total_available=len(pools), returned=len(pools))

    async def get_cluster_version(self) -> QueryResult:
        await _demo_delay("get_cluster_version")
        if self._platform != "openshift":
            return QueryResult()
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        cv = data.get("cluster_version", {})
        return QueryResult(data=[cv], total_available=1, returned=1)

    async def list_machines(self) -> QueryResult:
        await _demo_delay("list_machines")
        if self._platform != "openshift":
            return QueryResult()
        machines = [
            {
                "name": "prod-east-master-0",
                "phase": "Running",
                "provider_id": "aws:///us-east-1a/i-0a1b2c3d4e5f60001",
                "node_ref": "master-1.prod-east.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "prod-east-master-1",
                "phase": "Running",
                "provider_id": "aws:///us-east-1b/i-0a1b2c3d4e5f60002",
                "node_ref": "master-2.prod-east.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "prod-east-master-2",
                "phase": "Running",
                "provider_id": "aws:///us-east-1c/i-0a1b2c3d4e5f60003",
                "node_ref": "master-3.prod-east.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "prod-east-worker-1",
                "phase": "Running",
                "provider_id": "aws:///us-east-1a/i-0a1b2c3d4e5f60004",
                "node_ref": "worker-1.prod-east.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "prod-east-worker-2",
                "phase": "Running",
                "provider_id": "aws:///us-east-1b/i-0a1b2c3d4e5f60005",
                "node_ref": "worker-2.prod-east.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "prod-east-worker-3",
                "phase": "Running",
                "provider_id": "aws:///us-east-1c/i-0a1b2c3d4e5f60006",
                "node_ref": "worker-3.prod-east.internal",
                "conditions": [{"type": "NodeHealthy", "status": "False", "reason": "NodeNotReady", "message": "Node worker-3.prod-east.internal is NotReady (DiskPressure)"}],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
        ]
        return QueryResult(data=machines, total_available=len(machines), returned=len(machines))

    async def list_subscriptions(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_subscriptions")
        if self._platform != "openshift":
            return QueryResult()
        subs = [
            {
                "name": "elasticsearch-operator",
                "namespace": "openshift-operators-redhat",
                "package": "elasticsearch-operator",
                "channel": "stable-5.8",
                "currentCSV": "elasticsearch-operator.v5.8.1",
                "installedCSV": "elasticsearch-operator.v5.8.1",
                "state": "AtLatestKnown",
            },
            {
                "name": "jaeger-operator",
                "namespace": "openshift-operators",
                "package": "jaeger-product",
                "channel": "stable",
                "currentCSV": "jaeger-operator.v1.51.0",
                "installedCSV": "jaeger-operator.v1.47.0",
                "state": "UpgradePending",
            },
        ]
        if namespace:
            subs = [s for s in subs if s["namespace"] == namespace]
        return QueryResult(data=subs, total_available=len(subs), returned=len(subs))

    async def list_csvs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_csvs")
        if self._platform != "openshift":
            return QueryResult()
        csvs = [
            {
                "name": "elasticsearch-operator.v5.8.1",
                "namespace": "openshift-operators-redhat",
                "phase": "Succeeded",
                "reason": "InstallSucceeded",
                "message": "install strategy completed with no errors",
            },
            {
                "name": "jaeger-operator.v1.51.0",
                "namespace": "openshift-operators",
                "phase": "Failed",
                "reason": "ComponentFailed",
                "message": "install strategy failed: Deployment not ready",
            },
        ]
        if namespace:
            csvs = [c for c in csvs if c["namespace"] == namespace]
        return QueryResult(data=csvs, total_available=len(csvs), returned=len(csvs))

    async def get_proxy_config(self) -> QueryResult:
        await _demo_delay("get_proxy_config")
        if self._platform != "openshift":
            return QueryResult()
        proxy = {
            "httpProxy": "http://proxy.corp.example.com:3128",
            "httpsProxy": "http://proxy.corp.example.com:3128",
            "noProxy": ".cluster.local,.svc,10.128.0.0/14,172.30.0.0/16,localhost",
            "trustedCA": "user-ca-bundle",
        }
        return QueryResult(data=[proxy], total_available=1, returned=1)

    async def list_install_plans(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_install_plans")
        if self._platform != "openshift":
            return QueryResult()
        plans = [
            {
                "name": "install-abc12",
                "namespace": "openshift-operators",
                "approval": "Manual",
                "approved": False,
                "phase": "RequiresApproval",
                "csv_names": ["jaeger-operator.v1.51.0"],
            },
            {
                "name": "install-def34",
                "namespace": "openshift-operators-redhat",
                "approval": "Automatic",
                "approved": True,
                "phase": "Complete",
                "csv_names": ["elasticsearch-operator.v5.8.1"],
            },
        ]
        if namespace:
            plans = [p for p in plans if p["namespace"] == namespace]
        return QueryResult(data=plans, total_available=len(plans), returned=len(plans))

    async def list_roles(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_roles")
        roles = [
            {
                "name": "pod-reader",
                "namespace": "production",
                "rules_count": 1,
                "rules": [{"api_groups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]}],
            },
            {
                "name": "deployment-manager",
                "namespace": "production",
                "rules_count": 2,
                "rules": [
                    {"api_groups": ["apps"], "resources": ["deployments"], "verbs": ["get", "list", "watch", "update", "patch"]},
                    {"api_groups": [""], "resources": ["pods"], "verbs": ["get", "list"]},
                ],
            },
            {
                "name": "orphaned-legacy-role",
                "namespace": "staging",
                "rules_count": 1,
                "rules": [{"api_groups": [""], "resources": ["configmaps"], "verbs": ["get", "list"]}],
            },
        ]
        if namespace:
            roles = [r for r in roles if r["namespace"] == namespace]
        return QueryResult(data=roles, total_available=len(roles), returned=len(roles))

    async def list_role_bindings(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_role_bindings")
        bindings = [
            {
                "name": "pod-reader-binding",
                "namespace": "production",
                "role_ref": {"kind": "Role", "name": "pod-reader", "api_group": "rbac.authorization.k8s.io"},
                "subjects": [{"kind": "ServiceAccount", "name": "monitoring-sa", "namespace": "production"}],
            },
            {
                "name": "deployment-manager-binding",
                "namespace": "production",
                "role_ref": {"kind": "Role", "name": "deployment-manager", "api_group": "rbac.authorization.k8s.io"},
                "subjects": [{"kind": "ServiceAccount", "name": "ci-deployer", "namespace": "production"}],
            },
            {
                "name": "dangling-binding",
                "namespace": "production",
                "role_ref": {"kind": "Role", "name": "deleted-role", "api_group": "rbac.authorization.k8s.io"},
                "subjects": [{"kind": "ServiceAccount", "name": "old-service", "namespace": "production"}],
            },
            {
                "name": "cluster-admin-binding",
                "namespace": "kube-system",
                "role_ref": {"kind": "ClusterRole", "name": "cluster-admin", "api_group": "rbac.authorization.k8s.io"},
                "subjects": [{"kind": "ServiceAccount", "name": "tiller", "namespace": "kube-system"}],
            },
        ]
        if namespace:
            bindings = [b for b in bindings if b["namespace"] == namespace]
        return QueryResult(data=bindings, total_available=len(bindings), returned=len(bindings))

    async def list_cluster_roles(self) -> QueryResult:
        await _demo_delay("list_cluster_roles")
        cluster_roles = [
            {
                "name": "cluster-admin",
                "rules_count": 1,
                "is_aggregate": False,
                "rules": [{"api_groups": ["*"], "resources": ["*"], "verbs": ["*"]}],
            },
            {
                "name": "view",
                "rules_count": 15,
                "is_aggregate": True,
                "rules": [{"api_groups": [""], "resources": ["pods", "services", "configmaps"], "verbs": ["get", "list", "watch"]}],
            },
            {
                "name": "edit",
                "rules_count": 20,
                "is_aggregate": True,
                "rules": [{"api_groups": ["", "apps"], "resources": ["pods", "deployments", "services"], "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"]}],
            },
        ]
        return QueryResult(data=cluster_roles, total_available=len(cluster_roles), returned=len(cluster_roles))

    async def list_service_accounts(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_service_accounts")
        service_accounts = [
            {"name": "default", "namespace": "ecommerce-prod", "secrets_count": 1, "automount_token": True},
            {"name": "default", "namespace": "kube-system", "secrets_count": 1, "automount_token": True},
            {"name": "deployer-sa", "namespace": "ecommerce-prod", "secrets_count": 1, "automount_token": False},
            {"name": "monitoring-sa", "namespace": "monitoring", "secrets_count": 1, "automount_token": True},
            {"name": "ci-deployer", "namespace": "ecommerce-prod", "secrets_count": 2, "automount_token": False},
        ]
        if namespace:
            service_accounts = [sa for sa in service_accounts if sa["namespace"] == namespace]
        return QueryResult(data=service_accounts, total_available=len(service_accounts), returned=len(service_accounts))

    async def list_jobs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_jobs")
        jobs = [
            {
                "name": "data-migration-job",
                "namespace": "production",
                "completions": 1,
                "succeeded": 0,
                "failed": 6,
                "active": 0,
                "backoff_limit_exceeded": True,
                "active_deadline_exceeded": False,
                "age": "2026-03-14T08:00:00+00:00",
            },
            {
                "name": "report-generator",
                "namespace": "production",
                "completions": 1,
                "succeeded": 1,
                "failed": 0,
                "active": 0,
                "backoff_limit_exceeded": False,
                "active_deadline_exceeded": False,
                "age": "2026-03-14T12:00:00+00:00",
            },
            {
                "name": "cleanup-old-records",
                "namespace": "staging",
                "completions": 1,
                "succeeded": 0,
                "failed": 1,
                "active": 1,
                "backoff_limit_exceeded": False,
                "active_deadline_exceeded": False,
                "age": "2026-03-15T02:00:00+00:00",
            },
        ]
        if namespace:
            jobs = [j for j in jobs if j["namespace"] == namespace]
        return QueryResult(data=jobs, total_available=len(jobs), returned=len(jobs))

    async def list_cronjobs(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_cronjobs")
        cronjobs = [
            {
                "name": "nightly-backup",
                "namespace": "production",
                "schedule": "0 2 * * *",
                "suspend": False,
                "last_schedule_time": "2026-03-15T02:00:00+00:00",
                "active_count": 0,
                "age": "2026-01-01T00:00:00+00:00",
            },
            {
                "name": "report-aggregation",
                "namespace": "production",
                "schedule": "*/30 * * * *",
                "suspend": True,
                "last_schedule_time": "2026-03-10T12:30:00+00:00",
                "active_count": 0,
                "age": "2026-02-01T00:00:00+00:00",
            },
            {
                "name": "log-rotation",
                "namespace": "kube-system",
                "schedule": "0 0 * * *",
                "suspend": False,
                "last_schedule_time": "2026-03-15T00:00:00+00:00",
                "active_count": 0,
                "age": "2026-01-01T00:00:00+00:00",
            },
        ]
        if namespace:
            cronjobs = [cj for cj in cronjobs if cj["namespace"] == namespace]
        return QueryResult(data=cronjobs, total_available=len(cronjobs), returned=len(cronjobs))

    async def list_tls_secrets(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_tls_secrets")
        from datetime import datetime, timedelta
        now = datetime.now()
        secrets = [
            {"name": "api-tls-cert", "namespace": "production", "expiry_date": (now + timedelta(days=12)).isoformat(), "days_to_expiry": 12, "issuer": "letsencrypt"},
            {"name": "internal-ca", "namespace": "kube-system", "expiry_date": (now + timedelta(days=180)).isoformat(), "days_to_expiry": 180, "issuer": "internal-ca"},
            {"name": "payment-tls", "namespace": "production", "expiry_date": (now + timedelta(days=5)).isoformat(), "days_to_expiry": 5, "issuer": "letsencrypt"},
        ]
        return QueryResult(data=secrets, total_available=len(secrets), returned=len(secrets))

    async def list_resource_quotas(self, namespace: str = "") -> QueryResult:
        await _demo_delay("list_resource_quotas")
        quotas = [
            {"name": "production-quota", "namespace": "ecommerce-prod", "hard": {"cpu": "20", "memory": "40Gi", "pods": "100"}, "used": {"cpu": "18", "memory": "35Gi", "pods": "87"}},
            {"name": "staging-quota", "namespace": "ecommerce-staging", "hard": {"cpu": "10", "memory": "20Gi", "pods": "50"}, "used": {"cpu": "3", "memory": "6Gi", "pods": "12"}},
        ]
        return QueryResult(data=quotas, total_available=len(quotas), returned=len(quotas))

    async def get_node_os_info(self) -> QueryResult:
        await _demo_delay("get_node_os_info")
        nodes = [
            {"name": "worker-1", "kernel_version": "5.15.0-91-generic", "os_image": "Ubuntu 22.04.3 LTS", "kubelet_version": "v1.28.3", "creation_timestamp": "2026-01-15T10:00:00Z", "labels": {"node.kubernetes.io/instance-type": "m5.xlarge", "eks.amazonaws.com/nodegroup": "workers"}},
            {"name": "worker-2", "kernel_version": "5.15.0-91-generic", "os_image": "Ubuntu 22.04.3 LTS", "kubelet_version": "v1.28.3", "creation_timestamp": "2026-01-15T10:00:00Z", "labels": {"node.kubernetes.io/instance-type": "m5.xlarge"}},
            {"name": "worker-3", "kernel_version": "5.15.0-76-generic", "os_image": "Ubuntu 22.04.1 LTS", "kubelet_version": "v1.28.3", "creation_timestamp": "2025-11-20T08:00:00Z", "labels": {"node.kubernetes.io/instance-type": "m5.2xlarge"}},
        ]
        return QueryResult(data=nodes, total_available=len(nodes), returned=len(nodes))

    async def list_api_versions_in_use(self) -> QueryResult:
        await _demo_delay("list_api_versions_in_use")
        deprecated = [
            {"api_version": "batch/v1beta1", "group": "batch", "version": "v1beta1", "status": "deprecated"},
            {"api_version": "policy/v1beta1", "group": "policy", "version": "v1beta1", "status": "deprecated"},
        ]
        return QueryResult(data=deprecated, total_available=len(deprecated), returned=len(deprecated))

    async def list_webhooks(self) -> QueryResult:
        await _demo_delay("list_webhooks")
        data = [
            {
                "name": "validation.example.com",
                "kind": "ValidatingWebhookConfiguration",
                "failure_policy": "Fail",
                "timeout_seconds": 30,
                "client_config": {"url": "https://external-webhook.example.com/validate"},
                "rules": [{"apiGroups": [""], "resources": ["pods"], "operations": ["CREATE"]}],
            },
            {
                "name": "mutation.internal.svc",
                "kind": "MutatingWebhookConfiguration",
                "failure_policy": "Ignore",
                "timeout_seconds": 5,
                "client_config": {"service": {"name": "webhook-svc", "namespace": "webhook-system"}},
                "rules": [{"apiGroups": ["apps"], "resources": ["deployments"], "operations": ["CREATE", "UPDATE"]}],
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))

    async def list_routes(self) -> QueryResult:
        await _demo_delay("list_routes")
        data = [
            {
                "name": "app-route",
                "namespace": "production",
                "host": "app.example.com",
                "tls_termination": "edge",
                "backend_service": "app-svc",
                "admitted": True,
            },
            {
                "name": "api-route-broken",
                "namespace": "production",
                "host": "api.example.com",
                "tls_termination": "passthrough",
                "backend_service": "missing-svc",
                "admitted": False,
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))

    async def list_ingresses(self) -> QueryResult:
        await _demo_delay("list_ingresses")
        data = [
            {
                "name": "web-ingress",
                "namespace": "production",
                "hosts": ["web.example.com"],
                "tls_secrets": ["web-tls"],
                "backend_services": ["web-svc"],
                "ingress_class": "nginx",
            },
            {
                "name": "api-ingress-no-class",
                "namespace": "staging",
                "hosts": ["api.staging.example.com"],
                "tls_secrets": [],
                "backend_services": ["api-svc"],
                "ingress_class": None,
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))

    async def build_topology_snapshot(self) -> "TopologySnapshot":
        await _demo_delay("build_topology_snapshot")
        from src.agents.cluster.state import TopologySnapshot, TopologyNode, TopologyEdge
        nodes_result = await self.list_nodes()
        pods_result = await self.list_pods()

        topo_nodes: dict[str, TopologyNode] = {}
        edges: list[TopologyEdge] = []

        for n in nodes_result.data:
            key = f"node/{n['name']}"
            topo_nodes[key] = TopologyNode(kind="node", name=n["name"], status=n.get("status", "Unknown"))

        for p in pods_result.data:
            ns = p.get("namespace", "default")
            key = f"pod/{ns}/{p['name']}"
            node_name = p.get("node", "")
            topo_nodes[key] = TopologyNode(kind="pod", name=p["name"], namespace=ns, status=p.get("status", "Unknown"), node_name=node_name)
            if node_name:
                edges.append(TopologyEdge(from_key=f"node/{node_name}", to_key=key, relation="hosts"))

        # OpenShift operators
        if self._platform == "openshift":
            ops = await self.get_cluster_operators()
            for op in ops.data:
                key = f"operator/{op['name']}"
                status = "Degraded" if op.get("degraded") else ("Available" if op.get("available") else "Unavailable")
                topo_nodes[key] = TopologyNode(kind="operator", name=op["name"], status=status)

        from datetime import datetime, timezone
        return TopologySnapshot(
            nodes=topo_nodes,
            edges=edges,
            built_at=datetime.now(timezone.utc).isoformat(),
        )
