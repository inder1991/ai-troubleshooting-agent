"""Tests for secret store and credential resolver."""

import os
import pytest
from unittest.mock import patch

from cryptography.fernet import Fernet

from src.integrations.secret_store import FernetSecretStore
from src.integrations.credential_resolver import CredentialResolver


class TestFernetSecretStore:
    def setup_method(self):
        key = Fernet.generate_key().decode()
        self.store = FernetSecretStore(master_key=key)

    def test_encrypt_decrypt_roundtrip(self):
        plaintext = "sha256~my-secret-token-12345"
        handle = self.store.store_secret("int-1", "cluster_token", plaintext)
        result = self.store.retrieve_secret("int-1", "cluster_token", handle)
        assert result == plaintext

    def test_encrypted_data_differs_from_plaintext(self):
        plaintext = "my-secret-password"
        handle = self.store.store_secret("int-2", "password", plaintext)
        assert plaintext not in handle

    def test_handle_format(self):
        handle = self.store.store_secret("int-3", "token", "secret")
        assert handle.startswith("fernet://int-3/token/")

    def test_different_secrets_produce_different_handles(self):
        h1 = self.store.store_secret("int-4", "token", "secret1")
        h2 = self.store.store_secret("int-4", "token", "secret2")
        assert h1 != h2

    def test_rotate_secret(self):
        original = "old-secret"
        handle1 = self.store.store_secret("int-5", "token", original)
        new_handle = self.store.rotate_secret("int-5", "token", "new-secret")
        result = self.store.retrieve_secret("int-5", "token", new_handle)
        assert result == "new-secret"
        assert new_handle != handle1


class TestCredentialResolver:
    def test_auto_detects_fernet_when_no_k8s(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove KUBERNETES_SERVICE_HOST if present
            os.environ.pop("KUBERNETES_SERVICE_HOST", None)
            resolver = CredentialResolver()
            assert isinstance(resolver.store, FernetSecretStore)

    def test_encrypt_and_resolve_roundtrip(self):
        key = Fernet.generate_key().decode()
        store = FernetSecretStore(master_key=key)
        resolver = CredentialResolver(store=store)

        plaintext = "super-secret-token"
        handle = resolver.encrypt_and_store("profile-1", "cluster_token", plaintext)
        result = resolver.resolve("profile-1", "cluster_token", handle)
        assert result == plaintext

    def test_rotate(self):
        key = Fernet.generate_key().decode()
        store = FernetSecretStore(master_key=key)
        resolver = CredentialResolver(store=store)

        handle = resolver.encrypt_and_store("profile-2", "token", "old")
        new_handle = resolver.rotate("profile-2", "token", "new")
        result = resolver.resolve("profile-2", "token", new_handle)
        assert result == "new"
