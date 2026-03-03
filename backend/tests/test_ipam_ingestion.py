"""Tests for IPAM ingestion."""
import os
from unittest.mock import patch, MagicMock
import pytest
from src.network.ipam_ingestion import parse_ipam_csv, parse_ipam_excel, _infer_device_type
from src.network.topology_store import TopologyStore
from src.network.models import DeviceType


@pytest.fixture
def tmp_store(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    return TopologyStore(db_path=db_path)


# Keep old fixture name as alias so pre-existing callers still work
@pytest.fixture
def store(tmp_store):
    return tmp_store


class TestIPAMIngestion:
    def test_basic_csv(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,Core router
10.0.0.2,10.0.0.0/24,Switch1,trust,100,Access switch
10.0.1.1,10.0.1.0/24,Firewall1,dmz,200,DMZ firewall"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 3
        assert stats["subnets_added"] == 2
        assert stats["interfaces_added"] == 3
        assert len(stats["errors"]) == 0

    def test_dedup_devices(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,
10.0.0.2,10.0.0.0/24,Router1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 1
        assert stats["interfaces_added"] == 2

    def test_dedup_subnets(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,
10.0.0.2,10.0.0.0/24,Switch1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["subnets_added"] == 1

    def test_empty_rows_skipped(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
,,,,,,
10.0.0.1,10.0.0.0/24,Router1,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["devices_added"] == 1

    def test_missing_device_no_interface(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,,trust,100,"""
        stats = parse_ipam_csv(csv_content, store)
        assert stats["subnets_added"] == 1
        assert stats["devices_added"] == 0
        assert stats["interfaces_added"] == 0

    def test_data_persisted(self, store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Router1,trust,100,Core"""
        parse_ipam_csv(csv_content, store)
        devices = store.list_devices()
        assert len(devices) == 1
        assert devices[0].name == "Router1"
        subnets = store.list_subnets()
        assert len(subnets) == 1
        interfaces = store.list_interfaces()
        assert len(interfaces) == 1
        assert interfaces[0].ip == "10.0.0.1"


# ── New tests for Task 1 ──


class TestValidCSVImport:
    """test_valid_csv_import — happy path with valid data."""

    def test_valid_csv_import(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.1.1.1,10.1.1.0/24,web-server-01,dmz,100,Web server
10.1.1.2,10.1.1.0/24,db-server-01,trust,100,Database
10.2.0.1,10.2.0.0/16,core-rtr-01,core,200,Core router"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert stats["devices_added"] == 3
        assert stats["subnets_added"] == 2
        assert stats["interfaces_added"] == 3
        assert len(stats["errors"]) == 0


class TestInvalidIPRejected:
    """test_invalid_ip_rejected — '999.999.999.999' produces error, row skipped."""

    def test_invalid_ip_rejected(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
999.999.999.999,10.0.0.0/24,BadDevice,trust,100,Invalid IP
10.0.0.1,10.0.0.0/24,GoodDevice,trust,100,Valid IP"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        # Invalid IP row should be skipped
        assert stats["devices_added"] == 1
        assert stats["interfaces_added"] == 1
        assert len(stats["errors"]) == 1
        assert "Invalid IP" in stats["errors"][0]
        assert "999.999.999.999" in stats["errors"][0]


class TestInvalidCIDRRejected:
    """test_invalid_cidr_rejected — 'not-a-cidr' produces error."""

    def test_invalid_cidr_rejected(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,not-a-cidr,Device1,trust,100,Bad CIDR
10.0.0.2,10.0.0.0/24,Device2,trust,100,Good CIDR"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        # First row has invalid CIDR, entire row skipped
        assert len(stats["errors"]) == 1
        assert "Invalid CIDR" in stats["errors"][0]
        assert "not-a-cidr" in stats["errors"][0]
        # Only the second row should succeed
        assert stats["devices_added"] == 1
        assert stats["interfaces_added"] == 1


class TestDuplicateIPDetected:
    """test_duplicate_ip_detected — same IP in 2 rows, second skipped with warning."""

    def test_duplicate_ip_detected(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,100,First
10.0.0.1,10.0.0.0/24,Device2,trust,100,Duplicate"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        # First row succeeds, second is a duplicate
        assert stats["interfaces_added"] == 1
        assert len(stats["errors"]) == 1
        assert "Duplicate IP" in stats["errors"][0]
        assert "10.0.0.1" in stats["errors"][0]


class TestDeviceTypeInferred:
    """test_device_type_inferred — 'core-fw-01' -> FIREWALL, 'web-server' -> HOST."""

    def test_device_type_inferred(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,core-fw-01,trust,100,Firewall
10.0.0.2,10.0.0.0/24,web-server,trust,100,Web host
10.0.0.3,10.0.0.0/24,edge-rtr-01,trust,100,Router
10.0.0.4,10.0.0.0/24,dist-sw-01,trust,100,Switch
10.0.0.5,10.0.0.0/24,prod-lb-01,trust,100,Load balancer"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert stats["devices_added"] == 5
        assert len(stats["errors"]) == 0

        devices = tmp_store.list_devices()
        device_map = {d.name: d.device_type for d in devices}
        assert device_map["core-fw-01"] == DeviceType.FIREWALL
        assert device_map["web-server"] == DeviceType.HOST
        assert device_map["edge-rtr-01"] == DeviceType.ROUTER
        assert device_map["dist-sw-01"] == DeviceType.SWITCH
        assert device_map["prod-lb-01"] == DeviceType.LOAD_BALANCER


class TestDeviceTypeExplicitColumn:
    """test_device_type_explicit_column — device_type=ROUTER in CSV overrides inference."""

    def test_device_type_explicit_column(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description,device_type
10.0.0.1,10.0.0.0/24,my-host-01,trust,100,Overridden to router,ROUTER
10.0.0.2,10.0.0.0/24,core-fw-01,trust,100,Overridden to switch,SWITCH"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert stats["devices_added"] == 2
        assert len(stats["errors"]) == 0

        devices = tmp_store.list_devices()
        device_map = {d.name: d.device_type for d in devices}
        # Explicit column overrides name-based inference
        assert device_map["my-host-01"] == DeviceType.ROUTER
        assert device_map["core-fw-01"] == DeviceType.SWITCH


class TestExcelUploadHandled:
    """test_excel_upload_handled — .xlsx file routed to parse_ipam_excel()."""

    def test_excel_upload_handled(self, tmp_store):
        # Mock openpyxl to simulate an Excel workbook
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_wb.active = mock_ws
        mock_ws.iter_rows.return_value = [
            ("ip", "subnet", "device", "zone", "vlan", "description"),
            ("10.0.0.1", "10.0.0.0/24", "Router1", "trust", "100", "Core router"),
            ("10.0.0.2", "10.0.0.0/24", "Switch1", "trust", "100", "Access switch"),
        ]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = mock_wb

        with patch.dict("sys.modules", {"openpyxl": mock_openpyxl}):
            stats = parse_ipam_excel(b"fake-xlsx-bytes", tmp_store)

        assert stats["devices_added"] == 2
        assert stats["subnets_added"] == 1
        assert stats["interfaces_added"] == 2
        assert len(stats["errors"]) == 0
        # Verify openpyxl.load_workbook was called
        mock_openpyxl.load_workbook.assert_called_once()


class TestCSVUploadStillWorks:
    """test_csv_upload_still_works — existing CSV path unaffected."""

    def test_csv_upload_still_works(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
192.168.1.1,192.168.1.0/24,office-gw-01,office,10,Office gateway
192.168.1.2,192.168.1.0/24,office-sw-01,office,10,Office switch
172.16.0.1,172.16.0.0/16,dc-fw-01,dc,20,DC firewall"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert stats["devices_added"] == 3
        assert stats["subnets_added"] == 2
        assert stats["interfaces_added"] == 3
        assert len(stats["errors"]) == 0

        # Verify data is in the store
        devices = tmp_store.list_devices()
        assert len(devices) == 3
        subnets = tmp_store.list_subnets()
        assert len(subnets) == 2
        interfaces = tmp_store.list_interfaces()
        assert len(interfaces) == 3

        # Verify device types were inferred correctly
        device_map = {d.name: d.device_type for d in devices}
        assert device_map["office-gw-01"] == DeviceType.ROUTER  # "gw" pattern
        assert device_map["office-sw-01"] == DeviceType.SWITCH   # "sw" pattern
        assert device_map["dc-fw-01"] == DeviceType.FIREWALL     # "fw" pattern


class TestInferDeviceTypeFunction:
    """Unit tests for _infer_device_type helper."""

    def test_firewall_patterns(self):
        assert _infer_device_type("core-fw-01", {}) == DeviceType.FIREWALL
        assert _infer_device_type("palo-alto-1", {}) == DeviceType.FIREWALL
        assert _infer_device_type("asa-dmz", {}) == DeviceType.FIREWALL
        assert _infer_device_type("my-firewall", {}) == DeviceType.FIREWALL

    def test_router_patterns(self):
        assert _infer_device_type("edge-rtr-01", {}) == DeviceType.ROUTER
        assert _infer_device_type("core-router", {}) == DeviceType.ROUTER
        assert _infer_device_type("office-gw-01", {}) == DeviceType.ROUTER
        assert _infer_device_type("main-gateway", {}) == DeviceType.ROUTER

    def test_switch_patterns(self):
        assert _infer_device_type("dist-sw-01", {}) == DeviceType.SWITCH
        assert _infer_device_type("access-switch", {}) == DeviceType.SWITCH

    def test_load_balancer_patterns(self):
        assert _infer_device_type("prod-lb-01", {}) == DeviceType.LOAD_BALANCER
        assert _infer_device_type("my-nlb", {}) == DeviceType.LOAD_BALANCER
        assert _infer_device_type("my-alb", {}) == DeviceType.LOAD_BALANCER
        assert _infer_device_type("loadbalancer-1", {}) == DeviceType.LOAD_BALANCER
        assert _infer_device_type("load-balancer-1", {}) == DeviceType.LOAD_BALANCER

    def test_host_fallback(self):
        assert _infer_device_type("web-server", {}) == DeviceType.HOST
        assert _infer_device_type("db-01", {}) == DeviceType.HOST

    def test_explicit_overrides_inference(self):
        assert _infer_device_type("core-fw-01", {"device_type": "ROUTER"}) == DeviceType.ROUTER
        assert _infer_device_type("web-server", {"device_type": "FIREWALL"}) == DeviceType.FIREWALL


# ── Task 2: Device metadata population ──


def test_csv_populates_device_metadata(store):
    csv_content = """ip,subnet,device,zone,vlan,description,vendor,location,device_type
10.0.0.1,10.0.0.0/24,fw-core-01,pci,100,PCI firewall,Palo Alto,NYC-DC1,FIREWALL"""
    stats = parse_ipam_csv(csv_content, store)
    assert stats["devices_added"] == 1
    devices = store.list_devices()
    d = devices[0]
    assert d.management_ip == "10.0.0.1"
    assert d.zone_id == "pci"
    assert d.vlan_id == 100
    assert d.description == "PCI firewall"
    assert d.vendor == "Palo Alto"
    assert d.location == "NYC-DC1"


def test_csv_site_column_populates_location(store):
    csv_content = """ip,subnet,device,zone,vlan,description,vendor,site
10.0.0.1,10.0.0.0/24,fw-01,pci,100,desc,Cisco,LAX-DC2"""
    parse_ipam_csv(csv_content, store)
    d = store.list_devices()[0]
    assert d.location == "LAX-DC2"


def test_device_type_case_insensitive(store):
    csv_content = """ip,subnet,device,zone,vlan,description,device_type
10.0.0.1,10.0.0.0/24,fw-01,trust,100,test,Firewall"""
    stats = parse_ipam_csv(csv_content, store)
    devices = store.list_devices()
    assert devices[0].device_type == DeviceType.FIREWALL


def test_device_type_aliases(store):
    csv_content = """ip,subnet,device,zone,vlan,description,device_type
10.0.0.1,10.0.0.0/24,dev-01,trust,100,test,FW
10.0.0.2,10.0.0.0/24,dev-02,trust,100,test,RTR
10.0.0.3,10.0.0.0/24,dev-03,trust,100,test,SW
10.0.0.4,10.0.0.0/24,dev-04,trust,100,test,LB"""
    stats = parse_ipam_csv(csv_content, store)
    assert stats["devices_added"] == 4
    devices = store.list_devices()
    device_map = {d.name: d.device_type for d in devices}
    assert device_map["dev-01"] == DeviceType.FIREWALL
    assert device_map["dev-02"] == DeviceType.ROUTER
    assert device_map["dev-03"] == DeviceType.SWITCH
    assert device_map["dev-04"] == DeviceType.LOAD_BALANCER


# ── Task 3: IP-in-subnet, gateway, VLAN range, overlapping CIDR validation ──


class TestIPInSubnetValidation:
    """IP must fall within its declared subnet CIDR."""

    def test_ip_outside_subnet_rejected(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
192.168.100.50,10.0.0.0/24,Device1,trust,100,IP not in subnet"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 1
        assert "not within subnet" in stats["errors"][0]
        assert stats["devices_added"] == 0
        assert stats["interfaces_added"] == 0

    def test_ip_inside_subnet_accepted(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.50,10.0.0.0/24,Device1,trust,100,Valid"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0
        assert stats["devices_added"] == 1

    def test_ip_at_network_boundary_accepted(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,100,Valid"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0

    def test_ip_at_broadcast_accepted(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.255,10.0.0.0/24,Device1,trust,100,Broadcast"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0


class TestGatewayValidation:
    """Gateway IP must be within its subnet CIDR if a gateway column is provided."""

    def test_gateway_outside_subnet_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description,gateway
10.0.0.1,10.0.0.0/24,Device1,trust,100,test,192.168.1.1"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert any("gateway" in e.lower() for e in stats["errors"])

    def test_valid_gateway_no_warning(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description,gateway
10.0.0.1,10.0.0.0/24,Device1,trust,100,test,10.0.0.254"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert not any("gateway" in e.lower() for e in stats["errors"])


class TestVLANRangeValidation:
    """VLAN IDs must be 0 (unset) or 1-4094."""

    def test_vlan_out_of_range_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,5000,Bad VLAN"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert any("VLAN" in e for e in stats["errors"])

    def test_vlan_zero_allowed(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,0,No VLAN"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert not any("VLAN" in e for e in stats["errors"])


class TestOverlappingSubnets:
    """Detect overlapping CIDRs in the same import."""

    def test_overlapping_cidrs_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,100,Parent
10.0.0.129,10.0.0.128/25,Device2,trust,100,Overlapping child"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert any("overlap" in e.lower() for e in stats["errors"])
