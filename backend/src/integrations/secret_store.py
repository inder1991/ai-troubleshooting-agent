"""
Secret store abstraction for encrypted credential management.

Two implementations:
- FernetSecretStore: Local encryption using Fernet symmetric encryption
- K8sSecretStore: Kubernetes Secrets-backed storage
"""

import base64
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class SecretStore(ABC):
    """Abstract base for secret storage backends."""

    @abstractmethod
    def store_secret(self, integration_id: str, key: str, value: str) -> str:
        """Encrypt and store a secret. Returns an opaque handle string."""

    @abstractmethod
    def retrieve_secret(self, integration_id: str, key: str, handle: str) -> str:
        """Retrieve and decrypt a secret by its handle."""

    @abstractmethod
    def delete_secret(self, integration_id: str, key: str) -> None:
        """Delete a stored secret."""

    @abstractmethod
    def rotate_secret(self, integration_id: str, key: str, new_value: str) -> str:
        """Replace a secret with a new value. Returns new handle."""


class FernetSecretStore(SecretStore):
    """Fernet-based local encryption store.

    Master key sourced from DEBUGDUCK_MASTER_KEY env var.
    Auto-generates a key in dev if unset (with warning).
    """

    def __init__(self, master_key: Optional[str] = None):
        key = master_key or os.environ.get("DEBUGDUCK_MASTER_KEY")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning(
                "DEBUGDUCK_MASTER_KEY not set. Auto-generated dev key. "
                "DO NOT use in production."
            )
        # Ensure the key is bytes
        if isinstance(key, str):
            key_bytes = key.encode()
        else:
            key_bytes = key
        self._fernet = Fernet(key_bytes)

    def store_secret(self, integration_id: str, key: str, value: str) -> str:
        encrypted = self._fernet.encrypt(value.encode())
        handle = base64.urlsafe_b64encode(encrypted).decode()
        return f"fernet://{integration_id}/{key}/{handle}"

    def retrieve_secret(self, integration_id: str, key: str, handle: str) -> str:
        # Extract the encrypted payload from the handle
        prefix = f"fernet://{integration_id}/{key}/"
        if handle.startswith(prefix):
            encoded = handle[len(prefix):]
        else:
            encoded = handle
        encrypted = base64.urlsafe_b64decode(encoded.encode())
        return self._fernet.decrypt(encrypted).decode()

    def delete_secret(self, integration_id: str, key: str) -> None:
        # Fernet is stateless - deletion is a no-op (handle becomes invalid)
        pass

    def rotate_secret(self, integration_id: str, key: str, new_value: str) -> str:
        return self.store_secret(integration_id, key, new_value)


class K8sSecretStore(SecretStore):
    """Kubernetes Secrets-backed storage.

    Creates K8s Secrets in the debug-duck namespace.
    """

    NAMESPACE = "debug-duck"
    SECRET_PREFIX = "debugduck-cred"

    def __init__(self):
        try:
            from kubernetes import client, config as k8s_config

            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()
            self._v1 = client.CoreV1Api()
        except Exception as e:
            logger.error("Failed to initialize K8s client: %s", e)
            raise

    def _secret_name(self, integration_id: str) -> str:
        return f"{self.SECRET_PREFIX}-{integration_id}"

    def store_secret(self, integration_id: str, key: str, value: str) -> str:
        from kubernetes import client
        from kubernetes.client.rest import ApiException

        secret_name = self._secret_name(integration_id)
        encoded_value = base64.b64encode(value.encode()).decode()

        body = client.V1Secret(
            metadata=client.V1ObjectMeta(name=secret_name),
            data={key: encoded_value},
        )

        try:
            # Try to read existing secret and patch it
            existing = self._v1.read_namespaced_secret(secret_name, self.NAMESPACE)
            if existing.data is None:
                existing.data = {}
            existing.data[key] = encoded_value
            self._v1.replace_namespaced_secret(secret_name, self.NAMESPACE, existing)
        except ApiException as e:
            if e.status == 404:
                self._v1.create_namespaced_secret(self.NAMESPACE, body)
            else:
                raise

        return f"k8s://{self.NAMESPACE}/{secret_name}/{key}"

    def retrieve_secret(self, integration_id: str, key: str, handle: str) -> str:
        secret_name = self._secret_name(integration_id)
        secret = self._v1.read_namespaced_secret(secret_name, self.NAMESPACE)
        if secret.data and key in secret.data:
            return base64.b64decode(secret.data[key]).decode()
        raise KeyError(f"Key '{key}' not found in secret '{secret_name}'")

    def delete_secret(self, integration_id: str, key: str) -> None:
        from kubernetes.client.rest import ApiException

        secret_name = self._secret_name(integration_id)
        try:
            self._v1.delete_namespaced_secret(secret_name, self.NAMESPACE)
        except ApiException as e:
            if e.status != 404:
                raise

    def rotate_secret(self, integration_id: str, key: str, new_value: str) -> str:
        return self.store_secret(integration_id, key, new_value)
