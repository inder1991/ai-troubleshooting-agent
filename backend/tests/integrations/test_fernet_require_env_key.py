"""FernetSecretStore — FERNET_REQUIRE_ENV_KEY production guard (PR-A).

Locks the PR-A fix for SDET-audit Bug #3: ephemeral containers must not
silently auto-generate a key when DEBUGDUCK_MASTER_KEY is missing — that
orphans every credential encrypted with the previous key.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cryptography.fernet import Fernet

from src.integrations.secret_store import (
    FernetKeyMissingError,
    FernetSecretStore,
)


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("DEBUGDUCK_MASTER_KEY", raising=False)
    monkeypatch.delenv("FERNET_REQUIRE_ENV_KEY", raising=False)
    yield monkeypatch


@pytest.fixture
def isolated_dev_key_path(tmp_path, monkeypatch):
    """Redirect the dev-key path to a tmpdir so tests don't share state
    with the real on-disk key at data/.fernet_dev_key."""
    new_path = tmp_path / "dev_key"
    monkeypatch.setattr(
        FernetSecretStore, "_DEV_KEY_PATH", str(new_path),
    )
    yield new_path


# ── Dev mode (flag off) — existing behavior preserved ────────────────


def test_dev_mode_auto_generates_key_when_none(clean_env, isolated_dev_key_path):
    """With the flag off (default), missing env key still auto-generates
    and persists — zero behavior change for single-tenant dev."""
    store = FernetSecretStore()
    assert store._is_env_key is False
    assert isolated_dev_key_path.exists()


def test_dev_mode_reuses_persisted_dev_key(clean_env, isolated_dev_key_path):
    """Second construction with the same disk key reuses it — round-
    trip decrypt proves the key is stable."""
    first = FernetSecretStore()
    handle = first.store_secret("integ", "api", "sekret")
    # Fresh instance, no env key — loads from the same dev-key file.
    second = FernetSecretStore()
    assert second.retrieve_secret("integ", "api", handle) == "sekret"


def test_dev_mode_honors_env_key_when_set(clean_env, isolated_dev_key_path):
    env_key = Fernet.generate_key().decode()
    clean_env.setenv("DEBUGDUCK_MASTER_KEY", env_key)
    store = FernetSecretStore()
    assert store._is_env_key is True


# ── Production mode (flag on) — fail-fast guard ─────────────────────


def test_prod_mode_raises_when_env_key_missing(clean_env, isolated_dev_key_path):
    clean_env.setenv("FERNET_REQUIRE_ENV_KEY", "on")
    with pytest.raises(FernetKeyMissingError) as exc_info:
        FernetSecretStore()
    # Error message must name the env var + point to the migration doc.
    assert "DEBUGDUCK_MASTER_KEY" in str(exc_info.value)
    assert "fernet-key-env-migration" in str(exc_info.value)


def test_prod_mode_raises_even_when_dev_key_file_exists(
    clean_env, isolated_dev_key_path,
):
    """The dev-key-file fallback is specifically the failure mode we're
    eliminating. Even with the file present, refuse if env is missing."""
    clean_env.setenv("FERNET_REQUIRE_ENV_KEY", "on")
    # Pre-seed a dev key on disk
    isolated_dev_key_path.write_text(Fernet.generate_key().decode())
    with pytest.raises(FernetKeyMissingError):
        FernetSecretStore()


def test_prod_mode_passes_when_env_key_set(clean_env, isolated_dev_key_path):
    clean_env.setenv("FERNET_REQUIRE_ENV_KEY", "on")
    clean_env.setenv("DEBUGDUCK_MASTER_KEY", Fernet.generate_key().decode())
    store = FernetSecretStore()
    assert store._is_env_key is True


def test_prod_mode_round_trip(clean_env, isolated_dev_key_path):
    """Production path encrypts + decrypts as normal when key is set."""
    clean_env.setenv("FERNET_REQUIRE_ENV_KEY", "on")
    clean_env.setenv("DEBUGDUCK_MASTER_KEY", Fernet.generate_key().decode())
    store = FernetSecretStore()
    handle = store.store_secret("integ", "api", "sekret-prod")
    assert store.retrieve_secret("integ", "api", handle) == "sekret-prod"


def test_prod_mode_case_insensitive(clean_env, isolated_dev_key_path):
    clean_env.setenv("FERNET_REQUIRE_ENV_KEY", "ON")
    with pytest.raises(FernetKeyMissingError):
        FernetSecretStore()
