"""Abstract ClusterClient — platform adapter for K8s and OpenShift."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.agents.cluster.state import TopologySnapshot

from pydantic import BaseModel, Field


# Object count caps from design doc
OBJECT_CAPS = {
    "events": 500,
    "pods": 1000,
    "log_lines": 2000,
    "metric_points": 500,
    "nodes": 500,
    "pvcs": 500,
}


class QueryResult(BaseModel):
    """Standard result wrapper with truncation tracking."""
    data: list[Any] = Field(default_factory=list)
    total_available: int = 0
    returned: int = 0
    truncated: bool = False
    sort_order: str = "severity_desc"
    permission_denied: bool = False
    denied_resource: str = ""


class ClusterClient(ABC):
    """Abstract base class for cluster interaction. Read-only contract."""

    @abstractmethod
    async def detect_platform(self) -> dict[str, str]:
        """Return {"platform": "kubernetes"|"openshift", "version": "1.28.3"}."""
        ...

    @abstractmethod
    async def list_namespaces(self) -> QueryResult:
        ...

    @abstractmethod
    async def list_nodes(self) -> QueryResult:
        ...

    @abstractmethod
    async def list_pods(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def get_api_health(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        ...

    @abstractmethod
    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        ...

    async def get_pod_logs(self, name: str, namespace: str, tail_lines: int = 100) -> QueryResult:
        """Fetch pod logs. Default returns empty; K8s client overrides."""
        return QueryResult()

    # Workload queries (Deployments, StatefulSets, DaemonSets)
    @abstractmethod
    async def list_deployments(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_statefulsets(self, namespace: str = "") -> QueryResult:
        ...

    @abstractmethod
    async def list_daemonsets(self, namespace: str = "") -> QueryResult:
        ...

    # HPA/VPA — non-abstract, not all clusters have these
    async def list_hpas(self, namespace: str = "") -> QueryResult:
        """List HorizontalPodAutoscalers. Returns empty by default."""
        return QueryResult()

    async def list_vpas(self, namespace: str = "") -> QueryResult:
        """List VerticalPodAutoscalers. Returns empty by default."""
        return QueryResult()

    # OpenShift-specific (return empty on vanilla K8s)
    async def get_cluster_operators(self) -> QueryResult:
        return QueryResult()

    async def get_machine_sets(self) -> QueryResult:
        return QueryResult()

    async def get_routes(self, namespace: str = "") -> QueryResult:
        return QueryResult()

    async def get_security_context_constraints(self) -> QueryResult:
        """OpenShift SCCs."""
        return QueryResult()

    async def get_build_configs(self, namespace: str = "") -> QueryResult:
        """OpenShift BuildConfigs."""
        return QueryResult()

    async def get_image_streams(self, namespace: str = "") -> QueryResult:
        """OpenShift ImageStreams."""
        return QueryResult()

    async def get_machine_config_pools(self) -> QueryResult:
        """OpenShift MachineConfigPools."""
        return QueryResult()

    async def get_cluster_version(self) -> QueryResult:
        """OpenShift ClusterVersion object."""
        return QueryResult()

    async def list_machines(self) -> QueryResult:
        """OpenShift Machines (machine.openshift.io/v1beta1)."""
        return QueryResult()

    async def list_subscriptions(self, namespace: str = "") -> QueryResult:
        """OLM Subscriptions (operators.coreos.com/v1alpha1)."""
        return QueryResult()

    async def list_csvs(self, namespace: str = "") -> QueryResult:
        """OLM ClusterServiceVersions (operators.coreos.com/v1alpha1)."""
        return QueryResult()

    async def list_install_plans(self, namespace: str = "") -> QueryResult:
        """OLM InstallPlans (operators.coreos.com/v1alpha1)."""
        return QueryResult()

    async def get_proxy_config(self) -> QueryResult:
        """OpenShift cluster-wide Proxy config (config.openshift.io/v1)."""
        return QueryResult()

    # RBAC resources — non-abstract, not all agents need these
    async def list_roles(self, namespace: str = "") -> QueryResult:
        """List Roles. Returns empty by default."""
        return QueryResult()

    async def list_role_bindings(self, namespace: str = "") -> QueryResult:
        """List RoleBindings. Returns empty by default."""
        return QueryResult()

    async def list_cluster_roles(self) -> QueryResult:
        """List ClusterRoles. Returns empty by default."""
        return QueryResult()

    async def list_service_accounts(self, namespace: str = "") -> QueryResult:
        """List ServiceAccounts. Returns empty by default."""
        return QueryResult()

    # Services & Endpoints — non-abstract, not all agents need these
    async def list_services(self, namespace: str = "") -> QueryResult:
        """List Services. Returns empty by default."""
        return QueryResult()

    async def list_endpoints(self, namespace: str = "") -> QueryResult:
        """List Endpoints. Returns empty by default."""
        return QueryResult()

    # PodDisruptionBudgets — non-abstract, not all agents need these
    async def list_pdbs(self, namespace: str = "") -> QueryResult:
        """List PodDisruptionBudgets. Returns empty by default."""
        return QueryResult()

    # NetworkPolicies — non-abstract, not all agents need these
    async def list_network_policies(self, namespace: str = "") -> QueryResult:
        """List NetworkPolicies. Returns empty by default."""
        return QueryResult()

    # Batch resources — non-abstract, not all agents need these
    async def list_jobs(self, namespace: str = "") -> QueryResult:
        """List Jobs. Returns empty by default."""
        return QueryResult()

    async def list_cronjobs(self, namespace: str = "") -> QueryResult:
        """List CronJobs. Returns empty by default."""
        return QueryResult()

    # Recommendation analysis methods
    async def list_tls_secrets(self, namespace: str = "") -> QueryResult:
        """List TLS secrets with certificate expiry information."""
        return QueryResult()

    async def list_resource_quotas(self, namespace: str = "") -> QueryResult:
        """List ResourceQuotas with usage vs hard limits."""
        return QueryResult()

    async def get_node_os_info(self) -> QueryResult:
        """List nodes with OS/kernel info and creation dates."""
        return QueryResult()

    async def list_api_versions_in_use(self) -> QueryResult:
        """Scan common resources for apiVersion usage to detect deprecations."""
        return QueryResult()

    async def list_webhooks(self) -> QueryResult:
        """List ValidatingWebhookConfiguration + MutatingWebhookConfiguration."""
        return QueryResult()

    async def list_routes(self, namespace: str = "") -> QueryResult:
        """List OpenShift Routes."""
        return QueryResult()

    async def list_ingresses(self, namespace: str = "") -> QueryResult:
        """List Kubernetes Ingresses."""
        return QueryResult()

    async def build_topology_snapshot(self) -> "TopologySnapshot":
        """Build resource dependency graph from cluster state."""
        from src.agents.cluster.state import TopologySnapshot
        return TopologySnapshot()

    async def close(self) -> None:
        pass
