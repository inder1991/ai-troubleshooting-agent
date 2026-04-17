"""K.5 — per-backend verify-SSL defaults + env override."""
from __future__ import annotations

import os
from unittest.mock import patch

from src.integrations.http_clients import _VERIFY_SSL_DEFAULT, _verify_for


class TestVerifySSLDefaults:
    def test_ticketing_backends_default_to_insecure(self):
        # Matches pre-migration behaviour (verify=False per call).
        assert _VERIFY_SSL_DEFAULT["jira"] is False
        assert _VERIFY_SSL_DEFAULT["confluence"] is False
        assert _VERIFY_SSL_DEFAULT["remedy"] is False

    def test_infrastructure_backends_default_to_secure(self):
        assert _VERIFY_SSL_DEFAULT["elasticsearch"] is True
        assert _VERIFY_SSL_DEFAULT["prometheus"] is True
        assert _VERIFY_SSL_DEFAULT["kubernetes"] is True
        assert _VERIFY_SSL_DEFAULT["github"] is True


class TestVerifyFor:
    def test_default_when_no_env_var(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VERIFY_SSL_JIRA", None)
            assert _verify_for("jira") is False
            assert _verify_for("github") is True

    def test_env_var_overrides_default_true(self):
        with patch.dict(os.environ, {"VERIFY_SSL_JIRA": "true"}):
            assert _verify_for("jira") is True

    def test_env_var_overrides_default_false(self):
        with patch.dict(os.environ, {"VERIFY_SSL_GITHUB": "false"}):
            assert _verify_for("github") is False

    def test_env_var_accepts_truthy_variants(self):
        for val in ("1", "true", "TRUE", "yes", "on"):
            with patch.dict(os.environ, {"VERIFY_SSL_JIRA": val}):
                assert _verify_for("jira") is True, val

    def test_env_var_accepts_falsy_variants(self):
        for val in ("0", "false", "FALSE", "no", "off"):
            with patch.dict(os.environ, {"VERIFY_SSL_GITHUB": val}):
                assert _verify_for("github") is False, val

    def test_unknown_backend_defaults_to_secure(self):
        assert _verify_for("never_heard_of_it") is True
