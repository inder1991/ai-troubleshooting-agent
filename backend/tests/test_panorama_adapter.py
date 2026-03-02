"""Tests for Palo Alto Panorama adapter."""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from src.network.adapters.panorama_adapter import (
    PanoramaAdapter,
    _action_from_panos,
    _ports_from_applications,
    _ports_from_services,
    _stable_id,
    HAS_PANOS,
)
from src.network.models import (
    PolicyAction, VerdictMatchType, FirewallVendor,
    FirewallRule, NATRule, Zone, Route, NATDirection,
    AdapterHealthStatus,
)
from src.network.adapters.base import DeviceInterface, VirtualRouter


@pytest.fixture
def adapter():
    return PanoramaAdapter(
        hostname="panorama.example.com",
        api_key="test-key",
        device_group="DC-Firewalls",
    )


@pytest.fixture
def standalone_adapter():
    """Adapter configured for a standalone firewall (no device group)."""
    return PanoramaAdapter(
        hostname="fw01.example.com",
        api_key="test-key",
        device_group="",
        vsys="vsys1",
    )


# ── Helper function tests ──


class TestHelperFunctions:
    def test_action_from_panos_allow(self):
        assert _action_from_panos("allow") == PolicyAction.ALLOW

    def test_action_from_panos_deny(self):
        assert _action_from_panos("deny") == PolicyAction.DENY

    def test_action_from_panos_drop(self):
        assert _action_from_panos("drop") == PolicyAction.DROP

    def test_action_from_panos_reset_variants(self):
        assert _action_from_panos("reset-client") == PolicyAction.DENY
        assert _action_from_panos("reset-server") == PolicyAction.DENY
        assert _action_from_panos("reset-both") == PolicyAction.DENY

    def test_action_from_panos_unknown_defaults_deny(self):
        assert _action_from_panos("") == PolicyAction.DENY
        assert _action_from_panos("something-unknown") == PolicyAction.DENY

    def test_stable_id_deterministic(self):
        id1 = _stable_id("fw1", "rule-a")
        id2 = _stable_id("fw1", "rule-a")
        assert id1 == id2
        assert len(id1) == 12

    def test_stable_id_different_inputs(self):
        id1 = _stable_id("fw1", "rule-a")
        id2 = _stable_id("fw1", "rule-b")
        assert id1 != id2

    def test_ports_from_applications_known(self):
        assert _ports_from_applications(["web-browsing"]) == [80]
        assert _ports_from_applications(["ssl"]) == [443]
        assert _ports_from_applications(["ssh"]) == [22]

    def test_ports_from_applications_any(self):
        assert _ports_from_applications(["any"]) == []
        assert _ports_from_applications([]) == []
        assert _ports_from_applications(None) == []

    def test_ports_from_applications_multiple(self):
        ports = _ports_from_applications(["web-browsing", "ssl"])
        assert 80 in ports
        assert 443 in ports

    def test_ports_from_applications_unknown_app(self):
        assert _ports_from_applications(["custom-app-xyz"]) == []

    def test_ports_from_services_any(self):
        assert _ports_from_services(["any"]) == []
        assert _ports_from_services(["application-default"]) == []
        assert _ports_from_services(None) == []

    def test_ports_from_services_tcp_port(self):
        assert _ports_from_services(["tcp/443"]) == [443]

    def test_ports_from_services_port_range(self):
        ports = _ports_from_services(["tcp/80-82"])
        assert ports == [80, 81, 82]


# ── Adapter initialization tests ──


class TestPanoramaAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.PALO_ALTO
        assert adapter.api_endpoint == "panorama.example.com"
        assert adapter._device_group == "DC-Firewalls"
        assert adapter._vsys == "vsys1"

    def test_init_standalone(self, standalone_adapter):
        assert standalone_adapter.vendor == FirewallVendor.PALO_ALTO
        assert standalone_adapter.api_endpoint == "fw01.example.com"
        assert standalone_adapter._device_group == ""

    def test_default_vsys(self):
        adapter = PanoramaAdapter(hostname="fw.test", api_key="key")
        assert adapter._vsys == "vsys1"

    def test_snapshot_initially_empty(self, adapter):
        assert adapter._rules_cache == []
        assert adapter._nat_cache == []
        assert adapter._zones_cache == []
        assert adapter._routes_cache == []
        assert adapter._interfaces_cache == []
        assert adapter.snapshot_age_seconds() == float("inf")


# ── Flow simulation tests (pre-populated cache) ──


class TestSimulateFlow:
    @pytest.mark.asyncio
    async def test_simulate_flow_allow(self, adapter):
        # Pre-populate cache to avoid actual API calls
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="fw1", rule_name="allow-web",
                src_ips=["10.0.0.0/8"], dst_ips=["any"], ports=[443],
                action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.95
        assert verdict.match_type == VerdictMatchType.EXACT
        assert verdict.rule_name == "allow-web"

    @pytest.mark.asyncio
    async def test_simulate_flow_deny_explicit(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="fw1", rule_name="deny-ssh",
                src_ips=["any"], dst_ips=["any"], ports=[22],
                action=PolicyAction.DENY, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.EXACT

    @pytest.mark.asyncio
    async def test_simulate_flow_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY
        assert "interzone-default" in verdict.rule_name

    @pytest.mark.asyncio
    async def test_simulate_flow_rule_priority_order(self, adapter):
        """Lower order number = higher priority; deny-specific should win."""
        adapter._rules_cache = [
            FirewallRule(
                id="r-low", device_id="fw1", rule_name="allow-all",
                src_ips=["any"], dst_ips=["any"], ports=[],
                action=PolicyAction.ALLOW, order=100,
            ),
            FirewallRule(
                id="r-high", device_id="fw1", rule_name="deny-specific",
                src_ips=["10.0.0.5"], dst_ips=["any"], ports=[443],
                action=PolicyAction.DENY, order=5,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.rule_name == "deny-specific"

    @pytest.mark.asyncio
    async def test_simulate_flow_port_mismatch(self, adapter):
        """Rule for port 443 should not match port 80."""
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="fw1", rule_name="allow-https",
                src_ips=["any"], dst_ips=["any"], ports=[443],
                action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 80)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_simulate_flow_any_port(self, adapter):
        """Rule with empty ports list matches any port."""
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="fw1", rule_name="allow-all-ports",
                src_ips=["any"], dst_ips=["any"], ports=[],
                action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 9999)
        assert verdict.action == PolicyAction.ALLOW

    @pytest.mark.asyncio
    async def test_simulate_flow_cidr_matching(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="r1", device_id="fw1", rule_name="allow-subnet",
                src_ips=["192.168.1.0/24"], dst_ips=["10.0.0.0/16"],
                ports=[80], action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()

        # IP within CIDR - should match
        verdict = await adapter.simulate_flow("192.168.1.50", "10.0.5.1", 80)
        assert verdict.action == PolicyAction.ALLOW

        # IP outside CIDR - should not match
        verdict = await adapter.simulate_flow("192.168.2.50", "10.0.5.1", 80)
        assert verdict.action == PolicyAction.DENY


# ── Health check tests ──


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_not_configured(self):
        adapter = PanoramaAdapter(hostname="", api_key="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"
        assert health.status == AdapterHealthStatus.NOT_CONFIGURED

    @pytest.mark.asyncio
    async def test_health_check_not_configured_no_key(self):
        adapter = PanoramaAdapter(hostname="", api_key="some-key")
        health = await adapter.health_check()
        assert health.status == AdapterHealthStatus.NOT_CONFIGURED


# ── Connection tests (mocked panos) ──


class TestConnection:
    @patch("src.network.adapters.panorama_adapter.HAS_PANOS", True)
    @patch("src.network.adapters.panorama_adapter.panos")
    def test_connect_panorama_with_device_group(self, mock_panos, adapter):
        mock_panorama_cls = MagicMock()
        mock_panos.panorama.Panorama = mock_panorama_cls

        device = adapter._connect()

        mock_panorama_cls.assert_called_once_with(
            "panorama.example.com", api_key="test-key",
        )
        assert device == mock_panorama_cls.return_value

    @patch("src.network.adapters.panorama_adapter.HAS_PANOS", True)
    @patch("src.network.adapters.panorama_adapter.panos")
    def test_connect_standalone_firewall(self, mock_panos, standalone_adapter):
        mock_fw_cls = MagicMock()
        mock_panos.firewall.Firewall = mock_fw_cls

        device = standalone_adapter._connect()

        mock_fw_cls.assert_called_once_with(
            "fw01.example.com", api_key="test-key", vsys="vsys1",
        )
        assert device == mock_fw_cls.return_value

    @patch("src.network.adapters.panorama_adapter.HAS_PANOS", True)
    @patch("src.network.adapters.panorama_adapter.panos")
    def test_connect_cached(self, mock_panos, adapter):
        """Second call to _connect should return cached device."""
        mock_panorama_cls = MagicMock()
        mock_panos.panorama.Panorama = mock_panorama_cls

        device1 = adapter._connect()
        device2 = adapter._connect()

        assert device1 is device2
        assert mock_panorama_cls.call_count == 1

    def test_connect_without_panos_raises(self, adapter):
        """When pan-os-python is not installed, _connect raises."""
        # Force HAS_PANOS to False
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError, match="pan-os-python"):
                adapter._connect()


# ── Fetch methods with mocked panos SDK ──


class TestFetchRules:
    @pytest.mark.asyncio
    async def test_fetch_rules_returns_normalized(self, adapter):
        """Mocked SecurityRule.refreshall returns panos rule objects
        that are normalized to FirewallRule models."""
        mock_rule = MagicMock()
        mock_rule.name = "allow-web"
        mock_rule.source = ["10.0.0.0/8"]
        mock_rule.destination = ["any"]
        mock_rule.fromzone = ["trust"]
        mock_rule.tozone = ["untrust"]
        mock_rule.application = ["web-browsing", "ssl"]
        mock_rule.service = ["application-default"]
        mock_rule.action = "allow"
        mock_rule.log_end = True
        mock_rule.log_start = False

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.policies.SecurityRule.refreshall.return_value = [mock_rule]
            mock_panos.panorama.Panorama.return_value = MagicMock()
            mock_panos.panorama.DeviceGroup.return_value = MagicMock()
            adapter._panos_device = MagicMock()

            rules = await adapter._fetch_rules()

        assert len(rules) == 1
        rule = rules[0]
        assert isinstance(rule, FirewallRule)
        assert rule.rule_name == "allow-web"
        assert rule.src_ips == ["10.0.0.0/8"]
        assert rule.dst_ips == ["any"]
        assert rule.src_zone == "trust"
        assert rule.dst_zone == "untrust"
        assert rule.action == PolicyAction.ALLOW
        assert rule.logged is True
        assert 80 in rule.ports  # from web-browsing
        assert 443 in rule.ports  # from ssl

    @pytest.mark.asyncio
    async def test_fetch_rules_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter._fetch_rules()


class TestFetchNATRules:
    @pytest.mark.asyncio
    async def test_fetch_nat_dnat(self, adapter):
        mock_nat = MagicMock()
        mock_nat.name = "dnat-web"
        mock_nat.source = ["any"]
        mock_nat.destination = ["203.0.113.10"]
        mock_nat.source_translation_translated_addresses = None
        mock_nat.destination_translated_address = "10.0.0.100"
        mock_nat.destination_translated_port = 8080
        mock_nat.description = "DNAT to internal web"

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.policies.NatRule.refreshall.return_value = [mock_nat]
            mock_panos.panorama.DeviceGroup.return_value = MagicMock()
            adapter._panos_device = MagicMock()

            nat_rules = await adapter._fetch_nat_rules()

        assert len(nat_rules) == 1
        nr = nat_rules[0]
        assert isinstance(nr, NATRule)
        assert nr.direction == NATDirection.DNAT
        assert nr.translated_dst == "10.0.0.100"
        assert nr.translated_port == 8080

    @pytest.mark.asyncio
    async def test_fetch_nat_snat(self, adapter):
        mock_nat = MagicMock()
        mock_nat.name = "snat-outbound"
        mock_nat.source = ["10.0.0.0/24"]
        mock_nat.destination = ["any"]
        mock_nat.source_translation_translated_addresses = ["203.0.113.1"]
        mock_nat.destination_translated_address = None
        mock_nat.destination_translated_port = 0
        mock_nat.description = ""

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.policies.NatRule.refreshall.return_value = [mock_nat]
            mock_panos.panorama.DeviceGroup.return_value = MagicMock()
            adapter._panos_device = MagicMock()

            nat_rules = await adapter._fetch_nat_rules()

        assert len(nat_rules) == 1
        nr = nat_rules[0]
        assert nr.direction == NATDirection.SNAT
        assert nr.translated_src == "203.0.113.1"

    @pytest.mark.asyncio
    async def test_fetch_nat_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter._fetch_nat_rules()


class TestFetchZones:
    @pytest.mark.asyncio
    async def test_fetch_zones(self, adapter):
        mock_zone = MagicMock()
        mock_zone.name = "trust"
        mock_zone.mode = "layer3"

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.network.Zone.refreshall.return_value = [mock_zone]
            adapter._panos_device = MagicMock()

            zones = await adapter._fetch_zones()

        assert len(zones) == 1
        z = zones[0]
        assert isinstance(z, Zone)
        assert z.name == "trust"
        assert "layer3" in z.description

    @pytest.mark.asyncio
    async def test_fetch_zones_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter._fetch_zones()


class TestFetchInterfaces:
    @pytest.mark.asyncio
    async def test_fetch_interfaces(self, adapter):
        mock_iface = MagicMock()
        mock_iface.name = "ethernet1/1"
        mock_iface.ip = ["10.0.0.1/24"]
        mock_iface.zone = "trust"
        mock_iface.comment = ""
        mock_iface.link_state = "up"

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.network.EthernetInterface.refreshall.return_value = [mock_iface]
            adapter._panos_device = MagicMock()

            interfaces = await adapter._fetch_interfaces()

        assert len(interfaces) == 1
        iface = interfaces[0]
        assert isinstance(iface, DeviceInterface)
        assert iface.name == "ethernet1/1"
        assert iface.ip == "10.0.0.1/24"
        assert iface.zone == "trust"
        assert iface.status == "up"

    @pytest.mark.asyncio
    async def test_fetch_interfaces_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter._fetch_interfaces()


class TestFetchRoutes:
    @pytest.mark.asyncio
    async def test_fetch_routes(self, adapter):
        mock_vr = MagicMock()
        mock_vr.name = "default"

        mock_route = MagicMock()
        mock_route.name = "default-route"
        mock_route.destination = "0.0.0.0/0"
        mock_route.nexthop = "10.0.0.1"
        mock_route.interface = "ethernet1/1"
        mock_route.metric = 10

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.network.VirtualRouter.refreshall.return_value = [mock_vr]
            mock_panos.network.StaticRoute.refreshall.return_value = [mock_route]
            adapter._panos_device = MagicMock()

            routes = await adapter._fetch_routes()

        assert len(routes) == 1
        r = routes[0]
        assert isinstance(r, Route)
        assert r.destination_cidr == "0.0.0.0/0"
        assert r.next_hop == "10.0.0.1"
        assert r.interface == "ethernet1/1"
        assert r.vrf == "default"
        assert r.protocol == "static"

    @pytest.mark.asyncio
    async def test_fetch_routes_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter._fetch_routes()


class TestGetVirtualRouters:
    @pytest.mark.asyncio
    async def test_get_virtual_routers(self, adapter):
        mock_vr = MagicMock()
        mock_vr.name = "default"
        mock_vr.interface = ["ethernet1/1", "ethernet1/2"]

        mock_route = MagicMock()
        mock_route.name = "default-route"
        mock_route.destination = "0.0.0.0/0"
        mock_route.nexthop = "10.0.0.1"
        mock_route.metric = 10

        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", True), \
             patch("src.network.adapters.panorama_adapter.panos") as mock_panos:
            mock_panos.network.VirtualRouter.refreshall.return_value = [mock_vr]
            mock_panos.network.StaticRoute.refreshall.return_value = [mock_route]
            adapter._panos_device = MagicMock()

            vrs = await adapter.get_virtual_routers()

        assert len(vrs) == 1
        vr = vrs[0]
        assert isinstance(vr, VirtualRouter)
        assert vr.name == "default"
        assert vr.interfaces == ["ethernet1/1", "ethernet1/2"]
        assert len(vr.static_routes) == 1
        assert vr.static_routes[0]["destination"] == "0.0.0.0/0"

    @pytest.mark.asyncio
    async def test_get_virtual_routers_no_panos_raises(self, adapter):
        with patch("src.network.adapters.panorama_adapter.HAS_PANOS", False):
            with pytest.raises(NotImplementedError):
                await adapter.get_virtual_routers()
