"""Tests for input validation on API endpoint request models and network models."""
import pytest
from pydantic import ValidationError


# ── AddDeviceRequest validation ──


class TestAddDeviceRequestValidation:
    """Validate AddDeviceRequest model validators."""

    def _make(self, **overrides):
        from src.api.collector_endpoints import AddDeviceRequest

        defaults = {"ip_address": "10.0.0.1"}
        defaults.update(overrides)
        return AddDeviceRequest(**defaults)

    def test_valid_ip_passes(self):
        req = self._make(ip_address="192.168.1.1")
        assert req.ip_address == "192.168.1.1"

    def test_valid_ipv6_passes(self):
        req = self._make(ip_address="::1")
        assert req.ip_address == "::1"

    def test_invalid_ip_raises(self):
        with pytest.raises(ValidationError, match="Invalid IP address"):
            self._make(ip_address="999.999.999.999")

    def test_invalid_ip_text_raises(self):
        with pytest.raises(ValidationError, match="Invalid IP address"):
            self._make(ip_address="not-an-ip")

    def test_empty_ip_raises(self):
        with pytest.raises(ValidationError):
            self._make(ip_address="")

    def test_valid_port_passes(self):
        req = self._make(port=161)
        assert req.port == 161

    def test_port_zero_rejects(self):
        with pytest.raises(ValidationError, match="Port must be 1-65535"):
            self._make(port=0)

    def test_port_65536_rejects(self):
        with pytest.raises(ValidationError, match="Port must be 1-65535"):
            self._make(port=65536)

    def test_port_1_passes(self):
        req = self._make(port=1)
        assert req.port == 1

    def test_port_65535_passes(self):
        req = self._make(port=65535)
        assert req.port == 65535

    def test_valid_snmp_version_2c(self):
        req = self._make(snmp_version="2c")
        assert req.snmp_version == "2c"

    def test_valid_snmp_version_1(self):
        req = self._make(snmp_version="1")
        assert req.snmp_version == "1"

    def test_valid_snmp_version_3(self):
        req = self._make(snmp_version="3")
        assert req.snmp_version == "3"

    def test_invalid_snmp_version_rejects(self):
        with pytest.raises(ValidationError):
            self._make(snmp_version="4")

    def test_invalid_snmp_version_v2_rejects(self):
        with pytest.raises(ValidationError):
            self._make(snmp_version="v2c")

    def test_hostname_max_length_253(self):
        req = self._make(hostname="a" * 253)
        assert len(req.hostname) == 253

    def test_hostname_too_long_rejects(self):
        with pytest.raises(ValidationError):
            self._make(hostname="a" * 254)

    def test_community_string_max_length_255(self):
        req = self._make(community_string="x" * 255)
        assert len(req.community_string) == 255

    def test_community_string_too_long_rejects(self):
        with pytest.raises(ValidationError):
            self._make(community_string="x" * 256)


# ── AddDiscoveryRequest validation ──


class TestAddDiscoveryRequestValidation:
    """Validate AddDiscoveryRequest model validators."""

    def _make(self, **overrides):
        from src.api.collector_endpoints import AddDiscoveryRequest

        defaults = {"cidr": "10.0.0.0/24"}
        defaults.update(overrides)
        return AddDiscoveryRequest(**defaults)

    def test_valid_cidr_passes(self):
        req = self._make(cidr="192.168.1.0/24")
        assert req.cidr == "192.168.1.0/24"

    def test_cidr_prefix_8_passes(self):
        req = self._make(cidr="10.0.0.0/8")
        assert req.cidr == "10.0.0.0/8"

    def test_cidr_prefix_32_passes(self):
        req = self._make(cidr="10.0.0.1/32")
        assert req.cidr == "10.0.0.1/32"

    def test_cidr_prefix_0_rejects(self):
        with pytest.raises(ValidationError, match="prefix length must be 8-32"):
            self._make(cidr="0.0.0.0/0")

    def test_cidr_prefix_7_rejects(self):
        with pytest.raises(ValidationError, match="prefix length must be 8-32"):
            self._make(cidr="0.0.0.0/7")

    def test_invalid_cidr_rejects(self):
        with pytest.raises(ValidationError, match="Invalid CIDR"):
            self._make(cidr="not-a-cidr")

    def test_port_zero_rejects(self):
        with pytest.raises(ValidationError, match="Port must be 1-65535"):
            self._make(port=0)

    def test_port_65536_rejects(self):
        with pytest.raises(ValidationError, match="Port must be 1-65535"):
            self._make(port=65536)

    def test_invalid_snmp_version_rejects(self):
        with pytest.raises(ValidationError):
            self._make(snmp_version="5")

    def test_excluded_ips_valid(self):
        req = self._make(excluded_ips=["10.0.0.1", "10.0.0.2"])
        assert len(req.excluded_ips) == 2

    def test_excluded_ips_invalid_rejects(self):
        with pytest.raises(ValidationError, match="Invalid excluded IP"):
            self._make(excluded_ips=["not-an-ip"])

    def test_community_max_length_255(self):
        req = self._make(community="c" * 255)
        assert len(req.community) == 255

    def test_community_too_long_rejects(self):
        with pytest.raises(ValidationError):
            self._make(community="c" * 256)


# ── Network model Flow port validation ──


class TestFlowModelValidation:
    """Validate Flow model from network models."""

    def _make(self, **overrides):
        from src.network.models import Flow

        defaults = {
            "id": "f1",
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "port": 80,
        }
        defaults.update(overrides)
        return Flow(**defaults)

    def test_valid_flow_passes(self):
        f = self._make()
        assert f.port == 80

    def test_port_zero_rejects(self):
        with pytest.raises(ValidationError, match="port must be 1-65535"):
            self._make(port=0)

    def test_port_65536_rejects(self):
        with pytest.raises(ValidationError, match="port must be 1-65535"):
            self._make(port=65536)

    def test_invalid_src_ip_rejects(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            self._make(src_ip="bad-ip")

    def test_invalid_dst_ip_rejects(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            self._make(dst_ip="bad-ip")


# ── CIDR prefix length validation in network models ──


class TestCIDRValidation:
    """Validate CIDR prefix length enforcement in network models."""

    def test_subnet_valid_cidr(self):
        from src.network.models import Subnet

        s = Subnet(id="s1", cidr="10.0.0.0/24")
        assert s.cidr == "10.0.0.0/24"

    def test_subnet_cidr_prefix_0_rejects(self):
        from src.network.models import Subnet

        with pytest.raises(ValidationError, match="prefix length must be 8-32"):
            Subnet(id="s1", cidr="0.0.0.0/0")

    def test_address_block_cidr_prefix_0_rejects(self):
        from src.network.models import AddressBlock

        with pytest.raises(ValidationError, match="prefix length must be 8-32"):
            AddressBlock(id="ab1", cidr="0.0.0.0/0")

    def test_address_block_valid_cidr(self):
        from src.network.models import AddressBlock

        ab = AddressBlock(id="ab1", cidr="10.0.0.0/8")
        assert ab.cidr == "10.0.0.0/8"


# ── DNS model validation ──


class TestDNSModelValidation:
    """Validate DNS model validators."""

    def test_dns_server_valid(self):
        from src.network.models import DNSServerConfig

        s = DNSServerConfig(id="d1", name="primary", ip="8.8.8.8")
        assert s.port == 53

    def test_dns_server_invalid_ip(self):
        from src.network.models import DNSServerConfig

        with pytest.raises(ValidationError, match="Invalid IP"):
            DNSServerConfig(id="d1", name="primary", ip="not-valid")

    def test_dns_server_port_zero(self):
        from src.network.models import DNSServerConfig

        with pytest.raises(ValidationError, match="port must be 1-65535"):
            DNSServerConfig(id="d1", name="primary", ip="8.8.8.8", port=0)

    def test_dns_hostname_max_length(self):
        from src.network.models import DNSWatchedHostname

        with pytest.raises(ValidationError):
            DNSWatchedHostname(hostname="a" * 254)


# ── Flow endpoint window validation ──


class TestFlowWindowValidation:
    """Validate flow endpoint window parameter validation."""

    def test_valid_windows(self):
        from src.api.flow_endpoints import _validate_window

        assert _validate_window("5m") == "5m"
        assert _validate_window("1h") == "1h"
        assert _validate_window("30s") == "30s"
        assert _validate_window("7d") == "7d"
        assert _validate_window("100m") == "100m"

    def test_invalid_window_no_unit(self):
        from fastapi import HTTPException
        from src.api.flow_endpoints import _validate_window

        with pytest.raises(HTTPException) as exc_info:
            _validate_window("5")
        assert exc_info.value.status_code == 422

    def test_invalid_window_bad_unit(self):
        from fastapi import HTTPException
        from src.api.flow_endpoints import _validate_window

        with pytest.raises(HTTPException) as exc_info:
            _validate_window("5x")
        assert exc_info.value.status_code == 422

    def test_invalid_window_letters_only(self):
        from fastapi import HTTPException
        from src.api.flow_endpoints import _validate_window

        with pytest.raises(HTTPException) as exc_info:
            _validate_window("abc")
        assert exc_info.value.status_code == 422

    def test_invalid_window_empty(self):
        from fastapi import HTTPException
        from src.api.flow_endpoints import _validate_window

        with pytest.raises(HTTPException) as exc_info:
            _validate_window("")
        assert exc_info.value.status_code == 422

    def test_invalid_window_special_chars(self):
        from fastapi import HTTPException
        from src.api.flow_endpoints import _validate_window

        with pytest.raises(HTTPException) as exc_info:
            _validate_window("5m; DROP TABLE")
        assert exc_info.value.status_code == 422
