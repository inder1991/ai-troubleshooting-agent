"""Tests for SNMP credential redaction — secrets must never appear in logs."""
import logging
import pytest
from src.api.collector_endpoints import _redact_credentials, _SENSITIVE_FIELDS


class TestCredentialRedaction:
    """Verify that SNMP credentials are properly redacted."""

    def test_redact_community_string(self):
        """community_string field should be replaced with '***'."""
        data = {"community_string": "supersecret", "ip_address": "10.0.0.1"}
        redacted = _redact_credentials(data)
        assert redacted["community_string"] == "***"
        assert redacted["ip_address"] == "10.0.0.1"

    def test_redact_community(self):
        """community field (used in discovery config) should be replaced with '***'."""
        data = {"community": "my_community", "cidr": "10.0.0.0/24"}
        redacted = _redact_credentials(data)
        assert redacted["community"] == "***"

    def test_redact_v3_auth_key(self):
        """v3_auth_key should be replaced with '***'."""
        data = {"v3_auth_key": "auth_secret_123"}
        redacted = _redact_credentials(data)
        assert redacted["v3_auth_key"] == "***"

    def test_redact_v3_priv_key(self):
        """v3_priv_key should be replaced with '***'."""
        data = {"v3_priv_key": "priv_secret_456"}
        redacted = _redact_credentials(data)
        assert redacted["v3_priv_key"] == "***"

    def test_redact_all_sensitive_fields_simultaneously(self):
        """All sensitive fields should be redacted in a single pass."""
        data = {
            "community_string": "secret1",
            "community": "secret2",
            "v3_auth_key": "secret3",
            "v3_priv_key": "secret4",
            "ip_address": "10.0.0.1",
        }
        redacted = _redact_credentials(data)
        for field in _SENSITIVE_FIELDS:
            assert redacted[field] == "***", f"{field} was not redacted"
        assert redacted["ip_address"] == "10.0.0.1"

    def test_redact_preserves_none_values(self):
        """None/empty sensitive fields should not be replaced."""
        data = {"community_string": None, "v3_auth_key": "", "v3_priv_key": None}
        redacted = _redact_credentials(data)
        assert redacted["community_string"] is None
        assert redacted["v3_auth_key"] == ""
        assert redacted["v3_priv_key"] is None

    def test_redact_nested_protocol_credentials(self):
        """Credentials nested inside protocol configs should also be redacted."""
        data = {
            "hostname": "router1",
            "protocols": [
                {
                    "protocol": "snmp",
                    "snmp": {
                        "community": "deep_secret",
                        "v3_auth_key": "nested_auth",
                        "v3_priv_key": "nested_priv",
                        "version": "2c",
                    },
                }
            ],
        }
        redacted = _redact_credentials(data)
        snmp = redacted["protocols"][0]["snmp"]
        assert snmp["community"] == "***"
        assert snmp["v3_auth_key"] == "***"
        assert snmp["v3_priv_key"] == "***"
        assert snmp["version"] == "2c"

    def test_credentials_not_logged(self, caplog):
        """SNMP credentials should never appear in log output."""
        logger = logging.getLogger("src.api.collector_endpoints")
        secret_community = "supersecret_community_xyz"
        secret_auth = "auth_key_abc123"
        secret_priv = "priv_key_def456"

        device_data = {
            "hostname": "test-router",
            "community_string": secret_community,
            "v3_auth_key": secret_auth,
            "v3_priv_key": secret_priv,
            "ip_address": "10.0.0.1",
            "protocols": [
                {
                    "protocol": "snmp",
                    "snmp": {
                        "community": secret_community,
                        "v3_auth_key": secret_auth,
                        "v3_priv_key": secret_priv,
                    },
                }
            ],
        }

        with caplog.at_level(logging.DEBUG, logger="src.api.collector_endpoints"):
            redacted = _redact_credentials(device_data)
            logger.info("Device added: %s", redacted)

        # Verify no secret value appears in any log record
        full_log = caplog.text
        assert secret_community not in full_log, "community_string leaked into logs"
        assert secret_auth not in full_log, "v3_auth_key leaked into logs"
        assert secret_priv not in full_log, "v3_priv_key leaked into logs"
        # But the redacted marker should be present
        assert "***" in full_log

    def test_sensitive_fields_constant(self):
        """Verify the sensitive fields set contains expected fields."""
        assert "community_string" in _SENSITIVE_FIELDS
        assert "community" in _SENSITIVE_FIELDS
        assert "v3_auth_key" in _SENSITIVE_FIELDS
        assert "v3_priv_key" in _SENSITIVE_FIELDS
