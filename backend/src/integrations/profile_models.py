"""
Profile-based integration models.

Two entity types:
- ClusterProfile: Per-cluster config with local endpoints (OpenShift API, Prometheus, Jaeger)
- GlobalIntegration: Shared ecosystem services (ELK, Jira, Confluence, Remedy)
"""

import uuid
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field


class EndpointConfig(BaseModel):
    """Configuration for a single endpoint within a cluster profile."""
    url: str = ""
    auth_method: Literal[
        "none", "bearer_token", "api_key", "basic_auth",
        "cloud_id", "oauth2", "certificate", "tls_cert"
    ] = "none"
    auth_credential_handle: Optional[str] = None
    verified: bool = False
    last_verified: Optional[datetime] = None
    status: Literal[
        "unknown", "healthy", "testing", "degraded", "unreachable", "connection_failed"
    ] = "unknown"

    def to_safe_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("auth_credential_handle", None)
        d["has_credentials"] = self.auth_credential_handle is not None
        return d


class ClusterEndpoints(BaseModel):
    """Local endpoints for a cluster profile."""
    openshift_api: Optional[EndpointConfig] = None
    prometheus: Optional[EndpointConfig] = None
    jaeger: Optional[EndpointConfig] = None

    def to_safe_dict(self) -> dict:
        return {
            "openshift_api": self.openshift_api.to_safe_dict() if self.openshift_api else None,
            "prometheus": self.prometheus.to_safe_dict() if self.prometheus else None,
            "jaeger": self.jaeger.to_safe_dict() if self.jaeger else None,
        }


class ClusterProfile(BaseModel):
    """A cluster profile with identity, auth, and endpoint configuration."""
    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    display_name: Optional[str] = None
    cluster_type: Literal["openshift", "kubernetes"] = "openshift"
    cluster_url: str = ""

    # Environment
    environment: Literal["prod", "staging", "dev"] = "dev"
    role: str = ""   # RBAC role metadata, e.g. "cluster-admin", "view", "edit"

    # Auth (cluster-level)
    auth_method: Literal[
        "kubeconfig", "token", "service_account", "none"
    ] = "token"
    auth_credential_handle: Optional[str] = None
    auth_storage_type: Literal["fernet", "k8s", "none"] = "fernet"

    # Endpoints
    endpoints: ClusterEndpoints = Field(default_factory=ClusterEndpoints)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_synced: Optional[datetime] = None
    status: Literal["connected", "warning", "unreachable", "pending_setup"] = "pending_setup"
    cluster_version: Optional[str] = None
    is_active: bool = False

    def to_safe_dict(self) -> dict:
        """Return dict with all credential handles stripped."""
        d = self.model_dump(mode="json")
        d.pop("auth_credential_handle", None)
        d["has_cluster_credentials"] = self.auth_credential_handle is not None
        d["endpoints"] = self.endpoints.to_safe_dict()
        return d


class GlobalIntegration(BaseModel):
    """A global ecosystem integration (ELK, Jira, Confluence, Remedy)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    service_type: Literal["elk", "jira", "confluence", "remedy", "github",
                           "aws", "azure", "oracle", "gcp"]
    name: str
    category: str = ""
    url: str = ""
    auth_method: Literal[
        "basic_auth", "bearer_token", "api_key", "cloud_id",
        "api_token", "oauth2", "certificate", "none",
        "iam_role", "azure_sp", "oci_config", "gcp_sa",
    ] = "none"
    auth_credential_handle: Optional[str] = None
    config: dict = Field(default_factory=dict)  # Service-specific settings, e.g. {"orgs": ["org-a"]}
    status: Literal["connected", "not_validated", "not_linked", "conn_error"] = "not_linked"
    last_verified: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def to_safe_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("auth_credential_handle", None)
        d["has_credentials"] = self.auth_credential_handle is not None
        return d


# Default global integrations to seed on first run
DEFAULT_GLOBAL_INTEGRATIONS = [
    {
        "id": "global-elk",
        "service_type": "elk",
        "name": "ELK / Log Stack",
        "category": "Log Aggregation",
    },
    {
        "id": "global-jira",
        "service_type": "jira",
        "name": "Atlassian Jira",
        "category": "Ticketing System",
    },
    {
        "id": "global-confluence",
        "service_type": "confluence",
        "name": "Confluence",
        "category": "Documentation",
    },
    {
        "id": "global-remedy",
        "service_type": "remedy",
        "name": "BMC Remedy",
        "category": "Change Management",
    },
    {
        "id": "global-github",
        "service_type": "github",
        "name": "GitHub Enterprise",
        "category": "Version Control",
    },
    {
        "id": "cloud-aws",
        "name": "Amazon Web Services",
        "service_type": "aws",
        "enabled": False,
        "base_url": "",
        "auth_method": "iam_role",
        "auth_credential_handle": None,
        "config": {
            "auth_method": "iam_role",
            "role_arn": "",
            "external_id": "",
            "regions": [],
            "org_management": False,
            "sync_config": {
                "tier_1_interval": 600,
                "tier_2_interval": 1800,
                "tier_3_interval": 21600,
            },
        },
    },
    {
        "id": "cloud-azure",
        "name": "Microsoft Azure",
        "service_type": "azure",
        "enabled": False,
        "base_url": "",
        "auth_method": "azure_sp",
        "auth_credential_handle": None,
        "config": {
            "tenant_id": "",
            "client_id": "",
            "subscriptions": [],
        },
    },
    {
        "id": "cloud-oracle",
        "name": "Oracle Cloud Infrastructure",
        "service_type": "oracle",
        "enabled": False,
        "base_url": "",
        "auth_method": "oci_config",
        "auth_credential_handle": None,
        "config": {
            "tenancy_ocid": "",
            "user_ocid": "",
            "regions": [],
        },
    },
    {
        "id": "cloud-gcp",
        "name": "Google Cloud Platform",
        "service_type": "gcp",
        "enabled": False,
        "base_url": "",
        "auth_method": "gcp_sa",
        "auth_credential_handle": None,
        "config": {
            "project_id": "",
            "regions": [],
        },
    },
]
