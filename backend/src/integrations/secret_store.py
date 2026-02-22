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

    Key resolution order:
    1. Explicit master_key argument
    2. DEBUGDUCK_MASTER_KEY environment variable
    3. Persisted dev key from data/.fernet_dev_key (survives restarts)
    4. Auto-generate new dev key and persist it
    """

    _DEV_KEY_PATH = os.path.join("data", ".fernet_dev_key")

    def __init__(self, master_key: Optional[str] = None):
        env_key = master_key or os.environ.get("DEBUGDUCK_MASTER_KEY")
        dev_key = self._load_dev_key()

        if env_key:
            key = env_key
            self._is_env_key = True
            # Keep dev key fernet for migration if credentials were saved with it
            self._dev_fernet = Fernet(dev_key.encode()) if dev_key and dev_key != env_key else None
        elif dev_key:
            key = dev_key
            self._is_env_key = False
            self._dev_fernet = None
            logger.warning(
                "DEBUGDUCK_MASTER_KEY not set. Using persisted dev key from %s. "
                "DO NOT use in production.", self._DEV_KEY_PATH,
            )
        else:
            key = Fernet.generate_key().decode()
            self._persist_dev_key(key)
            self._is_env_key = False
            self._dev_fernet = None
            logger.warning(
                "DEBUGDUCK_MASTER_KEY not set. Generated and persisted dev key at %s. "
                "DO NOT use in production.", self._DEV_KEY_PATH,
            )

        if isinstance(key, str):
            key_bytes = key.encode()
        else:
            key_bytes = key
        self._fernet = Fernet(key_bytes)

    @classmethod
    def _load_dev_key(cls) -> Optional[str]:
        """Load persisted dev key if it exists."""
        try:
            if os.path.isfile(cls._DEV_KEY_PATH):
                with open(cls._DEV_KEY_PATH, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return None

    @classmethod
    def _persist_dev_key(cls, key: str) -> None:
        """Persist auto-generated dev key so it survives restarts."""
        try:
            os.makedirs(os.path.dirname(cls._DEV_KEY_PATH), exist_ok=True)
            with open(cls._DEV_KEY_PATH, "w") as f:
                f.write(key)
            logger.info("Dev encryption key persisted to %s", cls._DEV_KEY_PATH)
        except Exception as e:
            logger.error("Failed to persist dev key: %s", e)

    def store_secret(self, integration_id: str, key: str, value: str) -> str:
        encrypted = self._fernet.encrypt(value.encode())
        handle = base64.urlsafe_b64encode(encrypted).decode()
        return f"fernet://{integration_id}/{key}/{handle}"

    def retrieve_secret(self, integration_id: str, key: str, handle: str) -> str:
        prefix = f"fernet://{integration_id}/{key}/"
        if handle.startswith(prefix):
            encoded = handle[len(prefix):]
        else:
            encoded = handle
        encrypted = base64.urlsafe_b64decode(encoded.encode())

        # Try primary key first
        try:
            return self._fernet.decrypt(encrypted).decode()
        except Exception:
            pass

        # If env key is set and a dev key exists, try the old dev key
        if self._dev_fernet:
            try:
                plaintext = self._dev_fernet.decrypt(encrypted).decode()
                logger.info(
                    "Decrypted %s/%s with old dev key — re-encrypting with DEBUGDUCK_MASTER_KEY",
                    integration_id, key,
                )
                return plaintext
            except Exception:
                pass

        raise DecryptionError(
            f"Cannot decrypt credential for {integration_id}/{key}. "
            f"The encryption key has changed since this credential was saved. "
            f"Please re-save the credential in Settings > Integrations."
        )

    def delete_secret(self, integration_id: str, key: str) -> None:
        pass

    def rotate_secret(self, integration_id: str, key: str, new_value: str) -> str:
        return self.store_secret(integration_id, key, new_value)


class DecryptionError(Exception):
    """Raised when a credential cannot be decrypted (key mismatch)."""
    pass


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
