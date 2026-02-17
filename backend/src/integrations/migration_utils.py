"""
Migration utility to convert v1 IntegrationConfig entries to v2 ClusterProfile format.
"""

import logging
from datetime import datetime

from .models import IntegrationConfig
from .profile_models import ClusterProfile, ClusterEndpoints, EndpointConfig
from .store import IntegrationStore
from .profile_store import ProfileStore
from .credential_resolver import CredentialResolver

logger = logging.getLogger(__name__)


def migrate_v1_to_v2(
    old_store: IntegrationStore,
    new_store: ProfileStore,
    resolver: CredentialResolver,
) -> int:
    """Migrate v1 IntegrationConfig entries to v2 ClusterProfile.

    Returns the number of entries migrated.
    """
    migrated = 0
    old_entries = old_store.list_all()

    for old in old_entries:
        # Check if already migrated
        if new_store.get(old.id):
            logger.info("Profile %s already exists, skipping", old.id)
            continue

        # Encrypt auth_data
        auth_handle = None
        if old.auth_data:
            auth_handle = resolver.encrypt_and_store(
                old.id, "cluster_token", old.auth_data
            )

        # Build endpoints from discovered URLs
        endpoints = ClusterEndpoints()
        if old.prometheus_url:
            endpoints.prometheus = EndpointConfig(
                url=old.prometheus_url,
                status="healthy" if old.status == "active" else "unknown",
            )
        if old.elasticsearch_url:
            endpoints.openshift_api = EndpointConfig(
                url=old.cluster_url,
                status="healthy" if old.status == "active" else "unknown",
            )

        # Map old status to new
        status_map = {
            "active": "connected",
            "unreachable": "unreachable",
            "expired": "warning",
        }

        profile = ClusterProfile(
            id=old.id,
            name=old.name,
            cluster_type=old.cluster_type,
            cluster_url=old.cluster_url,
            auth_method=old.auth_method,
            auth_credential_handle=auth_handle,
            endpoints=endpoints,
            created_at=old.created_at,
            updated_at=datetime.now(),
            last_synced=old.last_verified,
            status=status_map.get(old.status, "pending_setup"),
            cluster_version=old.auto_discovered.get("cluster_version"),
        )

        new_store.add(profile)
        migrated += 1
        logger.info("Migrated integration '%s' (id=%s) to profile", old.name, old.id)

    return migrated
