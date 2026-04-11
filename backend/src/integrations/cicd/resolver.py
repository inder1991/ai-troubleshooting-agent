"""
Resolve CI/CD clients for the active cluster.

Reads GlobalIntegration rows for jenkins + argocd, filters by cluster linkage
(`config.cluster_ids`), resolves credentials via credential_resolver, and
returns concrete JenkinsClient/ArgoCDClient instances. Failure of any single
instance is isolated — it becomes an InstanceError and does not block siblings.
"""
from __future__ import annotations

import logging

from src.integrations.cicd.argocd_client import ArgoCDClient
from src.integrations.cicd.base import InstanceError, ResolveResult
from src.integrations.cicd.jenkins_client import JenkinsClient
from src.integrations.credential_resolver import get_credential_resolver
from src.integrations.profile_store import GlobalIntegrationStore

logger = logging.getLogger(__name__)


def _linked(gi, active_cluster_id: str | None) -> bool:
    """True if this GI applies to the active cluster (empty list = global)."""
    cluster_ids = (gi.config or {}).get("cluster_ids") or []
    if not cluster_ids:
        return True  # global
    if active_cluster_id is None:
        return True  # no active cluster specified => include everything
    return active_cluster_id in cluster_ids


def _resolve_credential(gi) -> str:
    """Decrypt the integration's credential handle. Raises ValueError if missing."""
    if not gi.auth_credential_handle:
        raise ValueError(f"missing credential handle for {gi.name}")
    return get_credential_resolver().resolve(
        gi.id, "credential", gi.auth_credential_handle
    )


async def resolve_cicd_clients(
    active_cluster_id: str | None,
) -> ResolveResult:
    """Resolve all CI/CD clients linked to the active cluster.

    Args:
        active_cluster_id: ClusterProfile.id of the active cluster, or None to
            include all configured instances.

    Returns:
        ResolveResult with separate jenkins/argocd lists plus per-instance
        errors. Never raises — every failure is captured as an InstanceError.
    """
    store = GlobalIntegrationStore()
    jenkins_clients: list = []
    argocd_clients: list = []
    errors: list[InstanceError] = []

    # --- Jenkins ---
    for gi in store.list_by_service_type("jenkins"):
        if not _linked(gi, active_cluster_id):
            continue
        try:
            resolved = _resolve_credential(gi)
            # Jenkins stores "username:api_token" in the credential blob.
            username, _, api_token = resolved.partition(":")
            client = JenkinsClient(
                base_url=gi.url,
                username=username,
                api_token=api_token,
                instance_name=gi.name,
            )
            jenkins_clients.append(client)
        except Exception as exc:  # noqa: BLE001 — failure isolation
            logger.warning("jenkins instance %s failed to resolve: %s", gi.name, exc)
            errors.append(
                InstanceError(name=gi.name, source="jenkins", message=str(exc))
            )

    # --- ArgoCD (REST mode only for Phase A resolver) ---
    # TODO(phase-b): kubeconfig auto-discovery via ClusterProfile
    for gi in store.list_by_service_type("argocd"):
        if not _linked(gi, active_cluster_id):
            continue
        try:
            token = _resolve_credential(gi)
            client = ArgoCDClient.from_rest(
                base_url=gi.url, token=token, instance_name=gi.name,
            )
            argocd_clients.append(client)
        except Exception as exc:  # noqa: BLE001 — failure isolation
            logger.warning("argocd instance %s failed to resolve: %s", gi.name, exc)
            errors.append(
                InstanceError(name=gi.name, source="argocd", message=str(exc))
            )

    return ResolveResult(
        jenkins=jenkins_clients, argocd=argocd_clients, errors=errors
    )
