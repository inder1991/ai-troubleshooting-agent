"""Tests for Pydantic field validators on network models."""
import pytest
from pydantic import ValidationError
from src.network.models import Device, Subnet, Flow, DeviceType


class TestDeviceValidation:
    def test_valid_device(self):
        d = Device(id="d1", name="fw-01", management_ip="10.0.0.1")
        assert d.management_ip == "10.0.0.1"

    def test_empty_ip_allowed(self):
        d = Device(id="d1", name="fw-01", management_ip="")
        assert d.management_ip == ""

    def test_invalid_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Device(id="d1", name="fw-01", management_ip="999.999.999.999")

    def test_garbage_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Device(id="d1", name="fw-01", management_ip="not-an-ip")

    def test_valid_vlan(self):
        d = Device(id="d1", name="fw-01", vlan_id=100)
        assert d.vlan_id == 100

    def test_vlan_zero_allowed(self):
        d = Device(id="d1", name="fw-01", vlan_id=0)
        assert d.vlan_id == 0

    def test_vlan_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="VLAN"):
            Device(id="d1", name="fw-01", vlan_id=5000)

    def test_negative_vlan_rejected(self):
        with pytest.raises(ValidationError, match="VLAN"):
            Device(id="d1", name="fw-01", vlan_id=-1)


class TestSubnetValidation:
    def test_valid_cidr(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24")
        assert s.cidr == "10.0.0.0/24"

    def test_invalid_cidr_rejected(self):
        with pytest.raises(ValidationError, match="Invalid CIDR"):
            Subnet(id="s1", cidr="not-a-cidr")

    def test_empty_gateway_allowed(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="")
        assert s.gateway_ip == ""

    def test_valid_gateway(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1")
        assert s.gateway_ip == "10.0.0.1"

    def test_invalid_gateway_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="bad-ip")


class TestFlowValidation:
    def test_valid_flow(self):
        f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=443)
        assert f.port == 443

    def test_invalid_src_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Flow(id="f1", src_ip="bad", dst_ip="10.0.0.2", port=443)

    def test_port_out_of_range(self):
        with pytest.raises(ValidationError, match="port"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=99999)

    def test_negative_port_rejected(self):
        with pytest.raises(ValidationError, match="port"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=-1)

    def test_invalid_protocol_rejected(self):
        with pytest.raises(ValidationError, match="protocol"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=80, protocol="ftp")

    def test_valid_protocols(self):
        for proto in ("tcp", "udp", "icmp", "any"):
            f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=80, protocol=proto)
            assert f.protocol == proto


class TestDiagnoseRequestValidation:
    def test_valid_request(self):
        from src.api.network_models import DiagnoseRequest
        r = DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.0.2", port=443)
        assert r.protocol == "tcp"

    def test_invalid_src_ip(self):
        from src.api.network_models import DiagnoseRequest
        with pytest.raises(ValidationError, match="Invalid IP"):
            DiagnoseRequest(src_ip="bad", dst_ip="10.0.0.2")

    def test_port_out_of_range(self):
        from src.api.network_models import DiagnoseRequest
        with pytest.raises(ValidationError, match="port"):
            DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.0.2", port=70000)
