"""
Credential resolver that auto-detects the storage backend and provides
a unified interface for encrypting and decrypting integration credentials.
"""

import logging
import os

from .secret_store import FernetSecretStore, K8sSecretStore, SecretStore

logger = logging.getLogger(__name__)


class CredentialResolver:
    """Resolves credentials from the appropriate secret store.

    Auto-detects environment:
    - If KUBERNETES_SERVICE_HOST is set -> K8sSecretStore
    - Otherwise -> FernetSecretStore
    """

    def __init__(self, store: SecretStore | None = None):
        if store:
            self._store = store
        elif os.environ.get("KUBERNETES_SERVICE_HOST"):
            logger.info("K8s environment detected, using K8sSecretStore")
            self._store = K8sSecretStore()
        else:
            logger.info("Local environment detected, using FernetSecretStore")
            self._store = FernetSecretStore()

    @property
    def store(self) -> SecretStore:
        return self._store

    def encrypt_and_store(
        self, integration_id: str, credential_type: str, plaintext: str
    ) -> str:
        """Encrypt a credential and return an opaque handle."""
        return self._store.store_secret(integration_id, credential_type, plaintext)

    def resolve(
        self, integration_id: str, credential_type: str, encrypted_handle: str
    ) -> str:
        """Decrypt a credential handle back to plaintext."""
        return self._store.retrieve_secret(
            integration_id, credential_type, encrypted_handle
        )

    def delete(self, integration_id: str, credential_type: str) -> None:
        """Delete stored credentials."""
        self._store.delete_secret(integration_id, credential_type)

    def rotate(
        self, integration_id: str, credential_type: str, new_plaintext: str
    ) -> str:
        """Rotate a credential, returning the new handle."""
        return self._store.rotate_secret(
            integration_id, credential_type, new_plaintext
        )


# Module-level singleton for convenience
_resolver: CredentialResolver | None = None


def get_credential_resolver() -> CredentialResolver:
    """Get or create the singleton CredentialResolver."""
    global _resolver
    if _resolver is None:
        _resolver = CredentialResolver()
    return _resolver
