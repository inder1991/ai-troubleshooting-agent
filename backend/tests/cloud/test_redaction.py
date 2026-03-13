"""Tests for sensitive data redaction and compression."""
import gzip
import json

import pytest

from src.cloud.redaction import redact_raw, compress_raw, decompress_raw


class TestRedaction:
    def test_redacts_password_fields(self):
        raw = {"Name": "test", "Password": "secret123", "Config": {"AuthToken": "tok"}}
        result = redact_raw(raw)
        assert result["Name"] == "test"
        assert result["Password"] == "***REDACTED***"
        assert result["Config"]["AuthToken"] == "***REDACTED***"

    def test_redacts_nested_dicts(self):
        raw = {"Level1": {"Level2": {"SecretKey": "abc"}}}
        result = redact_raw(raw)
        assert result["Level1"]["Level2"]["SecretKey"] == "***REDACTED***"

    def test_redacts_in_lists(self):
        raw = {"Items": [{"Name": "a", "AccessKey": "key1"}, {"Name": "b"}]}
        result = redact_raw(raw)
        assert result["Items"][0]["AccessKey"] == "***REDACTED***"
        assert result["Items"][1]["Name"] == "b"

    def test_leaves_safe_fields_alone(self):
        raw = {"VpcId": "vpc-123", "CidrBlock": "10.0.0.0/16", "Tags": []}
        result = redact_raw(raw)
        assert result == raw

    def test_empty_dict(self):
        assert redact_raw({}) == {}

    def test_case_sensitive_matching(self):
        raw = {"password": "safe", "Password": "redact"}
        result = redact_raw(raw)
        assert result["password"] == "safe"
        assert result["Password"] == "***REDACTED***"


class TestCompression:
    def test_compress_decompress_roundtrip(self):
        # Use a realistically sized payload so gzip overhead is outweighed
        raw = {
            "VpcId": "vpc-abc",
            "CidrBlock": "10.0.0.0/16",
            "Tags": [{"Key": "env", "Value": "prod"}],
            "Subnets": [
                {"SubnetId": f"subnet-{i:04d}", "CidrBlock": f"10.0.{i}.0/24", "AvailabilityZone": "us-east-1a"}
                for i in range(20)
            ],
        }
        compressed = compress_raw(raw)
        assert isinstance(compressed, bytes)
        assert len(compressed) < len(json.dumps(raw).encode())
        decompressed = decompress_raw(compressed)
        assert decompressed == raw

    def test_compress_produces_valid_gzip(self):
        raw = {"test": "data"}
        compressed = compress_raw(raw)
        decompressed_bytes = gzip.decompress(compressed)
        assert json.loads(decompressed_bytes) == raw

    def test_compress_deterministic(self):
        raw = {"b": 2, "a": 1}
        c1 = compress_raw(raw)
        c2 = compress_raw(raw)
        assert c1 == c2  # sort_keys ensures determinism

    def test_raw_preview(self):
        from src.cloud.redaction import make_raw_preview
        raw = {"VpcId": "vpc-abc", "CidrBlock": "10.0.0.0/16"}
        preview = make_raw_preview(raw, max_len=30)
        assert len(preview) <= 30
        assert preview.startswith("{")
