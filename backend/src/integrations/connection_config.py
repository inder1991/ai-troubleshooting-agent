"""
Resolved connection configuration for agents.

Decrypts credentials from the active profile and provides a frozen config
object that agents use at runtime. Plaintext lives only in memory.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("connection_config")


@dataclass(frozen=True)
class ResolvedConnectionConfig:
    """Immutable connection config resolved from a profile.

    All credentials are decrypted plaintext - lives only in memory.
    """
    # Cluster
    cluster_url: str = ""
    cluster_token: str = ""
    cluster_type: str = "openshift"
    namespace: str = "default"
    verify_ssl: bool = False

    # Prometheus
    prometheus_url: str = ""
    prometheus_auth_method: str = "none"
    prometheus_credentials: str = ""

    # Elasticsearch
    elasticsearch_url: str = ""
    elasticsearch_auth_method: str = "none"
    elasticsearch_credentials: str = ""

    # Jaeger
    jaeger_url: str = ""
    jaeger_auth_method: str = "none"
    jaeger_credentials: str = ""

    # Global integrations
    jira_url: str = ""
    jira_credentials: str = ""
    confluence_url: str = ""
    confluence_credentials: str = ""


def resolve_active_profile(profile_id: Optional[str] = None) -> ResolvedConnectionConfig:
    """Resolve a connection config from a profile, falling back to env vars.

    Args:
        profile_id: Specific profile to resolve. If None, uses active profile.

    Returns:
        ResolvedConnectionConfig with decrypted credentials.
    """
    from src.integrations.profile_store import ProfileStore, GlobalIntegrationStore
    from src.integrations.credential_resolver import get_credential_resolver

    store = ProfileStore()
    store._ensure_tables()

    # Try to get profile
    profile = None
    if profile_id:
        profile = store.get(profile_id)
    if not profile:
        profile = store.get_active_profile()

    if not profile:
        logger.info("No active profile found, falling back to environment variables")
        return _config_from_env()

    resolver = get_credential_resolver()

    # Decrypt cluster credentials
    cluster_token = ""
    if profile.auth_credential_handle:
        try:
            cluster_token = resolver.resolve(
                profile.id, "cluster_token", profile.auth_credential_handle
            )
        except Exception as e:
            logger.warning("Failed to decrypt cluster token: %s", e)

    # Decrypt endpoint credentials
    prom_url = ""
    prom_auth = "none"
    prom_creds = ""
    if profile.endpoints.prometheus:
        prom_url = profile.endpoints.prometheus.url
        prom_auth = profile.endpoints.prometheus.auth_method
        if profile.endpoints.prometheus.auth_credential_handle:
            try:
                prom_creds = resolver.resolve(
                    profile.id, "prometheus",
                    profile.endpoints.prometheus.auth_credential_handle,
                )
            except Exception:
                pass

    jaeger_url = ""
    jaeger_auth = "none"
    jaeger_creds = ""
    if profile.endpoints.jaeger:
        jaeger_url = profile.endpoints.jaeger.url
        jaeger_auth = profile.endpoints.jaeger.auth_method
        if profile.endpoints.jaeger.auth_credential_handle:
            try:
                jaeger_creds = resolver.resolve(
                    profile.id, "jaeger",
                    profile.endpoints.jaeger.auth_credential_handle,
                )
            except Exception:
                pass

    # Resolve global integrations
    gi_store = GlobalIntegrationStore()
    gi_store._ensure_tables()

    elk_url = ""
    elk_auth = "none"
    elk_creds = ""
    elk = gi_store.get_by_service_type("elk")
    if elk and elk.url:
        elk_url = elk.url
        elk_auth = elk.auth_method
        if elk.auth_credential_handle:
            try:
                elk_creds = resolver.resolve(elk.id, "credential", elk.auth_credential_handle)
            except Exception:
                pass

    jira_url = ""
    jira_creds = ""
    jira = gi_store.get_by_service_type("jira")
    if jira and jira.url:
        jira_url = jira.url
        if jira.auth_credential_handle:
            try:
                jira_creds = resolver.resolve(jira.id, "credential", jira.auth_credential_handle)
            except Exception:
                pass

    confluence_url = ""
    confluence_creds = ""
    confluence = gi_store.get_by_service_type("confluence")
    if confluence and confluence.url:
        confluence_url = confluence.url
        if confluence.auth_credential_handle:
            try:
                confluence_creds = resolver.resolve(
                    confluence.id, "credential", confluence.auth_credential_handle
                )
            except Exception:
                pass

    return ResolvedConnectionConfig(
        cluster_url=profile.cluster_url,
        cluster_token=cluster_token,
        cluster_type=profile.cluster_type,
        namespace="default",
        verify_ssl=False,
        prometheus_url=prom_url or os.getenv("PROMETHEUS_URL", ""),
        prometheus_auth_method=prom_auth,
        prometheus_credentials=prom_creds,
        elasticsearch_url=elk_url or os.getenv("ELASTICSEARCH_URL", ""),
        elasticsearch_auth_method=elk_auth,
        elasticsearch_credentials=elk_creds,
        jaeger_url=jaeger_url or os.getenv("TRACING_URL", ""),
        jaeger_auth_method=jaeger_auth,
        jaeger_credentials=jaeger_creds,
        jira_url=jira_url,
        jira_credentials=jira_creds,
        confluence_url=confluence_url,
        confluence_credentials=confluence_creds,
    )


def _config_from_env() -> ResolvedConnectionConfig:
    """Build config from environment variables (legacy fallback)."""
    return ResolvedConnectionConfig(
        cluster_url=os.getenv("OPENSHIFT_API_URL", ""),
        cluster_token=os.getenv("OPENSHIFT_TOKEN", ""),
        cluster_type="openshift",
        namespace=os.getenv("K8S_NAMESPACE", "default"),
        verify_ssl=os.getenv("K8S_VERIFY_SSL", "false").lower() == "true",
        prometheus_url=os.getenv("PROMETHEUS_URL", "http://localhost:9090"),
        elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
        jaeger_url=os.getenv("TRACING_URL", "http://localhost:16686"),
    )
