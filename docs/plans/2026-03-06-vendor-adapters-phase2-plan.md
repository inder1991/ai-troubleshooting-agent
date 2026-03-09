# Phase 2: Vendor Adapters — Cisco, F5, Checkpoint

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add three vendor firewall/network adapters (Cisco IOS-XE, F5 BIG-IP, Check Point) to match the existing adapter pattern (PanoramaAdapter, ZscalerAdapter), closing the multi-vendor gap identified in the Datadog comparison.

**Architecture:** Each adapter inherits from `FirewallAdapter` (base.py), implements the 5 abstract fetch methods + `simulate_flow`, uses optional SDK imports with graceful degradation, and normalizes vendor-specific data to the common models (`FirewallRule`, `NATRule`, `Zone`, `Route`, `DeviceInterface`). The factory and models are extended with new enum values. Tests follow the Zscaler test pattern: inject cached rules directly, verify simulation logic without live API calls.

**Tech Stack:** Python, httpx (REST APIs for Cisco/F5/Checkpoint), existing Pydantic models, pytest + pytest-asyncio

---

### Task 1: Add CISCO, F5, CHECKPOINT to FirewallVendor Enum

**Files:**
- Modify: `backend/src/network/models.py:58-63`

**What:** Add three new enum values to `FirewallVendor`.

**Step 1: Add enum values**

In `backend/src/network/models.py`, find the `FirewallVendor` enum and add three entries:

```python
class FirewallVendor(str, Enum):
    PALO_ALTO = "palo_alto"
    AZURE_NSG = "azure_nsg"
    AWS_SG = "aws_sg"
    ORACLE_NSG = "oracle_nsg"
    ZSCALER = "zscaler"
    CISCO = "cisco"
    F5 = "f5"
    CHECKPOINT = "checkpoint"
```

**Step 2: Verify**

Run: `cd backend && python3 -c "from src.network.models import FirewallVendor; print([v.value for v in FirewallVendor])"`
Expected: list includes `'cisco'`, `'f5'`, `'checkpoint'`

**Step 3: Run existing tests**

Run: `cd backend && python3 -m pytest tests/test_adapter_factory.py tests/test_adapter_registry.py -v`
Expected: All pass (no existing code breaks)

**Step 4: Commit**

```bash
git add backend/src/network/models.py
git commit -m "feat(adapters): add CISCO, F5, CHECKPOINT to FirewallVendor enum"
```

---

### Task 2: Cisco IOS-XE / RESTCONF Adapter

**Files:**
- Create: `backend/src/network/adapters/cisco_adapter.py`
- Test: `backend/tests/test_cisco_adapter.py`

**What:** Adapter for Cisco IOS-XE devices using the RESTCONF API (RFC 8040). Fetches ACLs, interfaces, routing table, and zones via `https://<host>/restconf/data/...` YANG endpoints. Falls back to mock when httpx is unavailable.

**Step 1: Write the test file**

Create `backend/tests/test_cisco_adapter.py`:

```python
"""Tests for Cisco IOS-XE adapter."""
import pytest
import time
from src.network.adapters.cisco_adapter import CiscoAdapter
from src.network.models import (
    FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor,
    NATRule, NATDirection,
)


@pytest.fixture
def adapter():
    return CiscoAdapter(
        hostname="192.168.1.1",
        username="admin",
        password="cisco123",
    )


class TestCiscoAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.CISCO
        assert adapter.api_endpoint == "https://192.168.1.1"

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="acl-1", device_id="192.168.1.1",
                rule_name="permit-web",
                src_ips=["10.0.0.0/8"], dst_ips=["any"],
                ports=[80, 443], protocol="tcp",
                action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.match_type == VerdictMatchType.EXACT
        assert verdict.confidence == 0.90

    @pytest.mark.asyncio
    async def test_simulate_deny(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="acl-2", device_id="192.168.1.1",
                rule_name="deny-all",
                src_ips=["any"], dst_ips=["any"],
                ports=[], protocol="any",
                action=PolicyAction.DENY, order=999,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DENY

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        adapter = CiscoAdapter(hostname="", username="", password="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"

    def test_normalize_acl_permit(self, adapter):
        raw = {
            "name": "permit-ssh",
            "sequence": 20,
            "action": "permit",
            "source": "10.0.0.0 0.0.0.255",
            "destination": "any",
            "protocol": "tcp",
            "destination-port": "22",
        }
        rule = adapter._normalize_ace(raw, "ACL-MGMT", 0)
        assert rule.action == PolicyAction.ALLOW
        assert rule.src_ips == ["10.0.0.0/24"]
        assert 22 in rule.ports

    def test_normalize_acl_deny(self, adapter):
        raw = {
            "name": "deny-telnet",
            "sequence": 30,
            "action": "deny",
            "source": "any",
            "destination": "any",
            "protocol": "tcp",
            "destination-port": "23",
        }
        rule = adapter._normalize_ace(raw, "ACL-MGMT", 1)
        assert rule.action == PolicyAction.DENY

    def test_wildcard_to_cidr(self, adapter):
        assert adapter._wildcard_to_cidr("10.0.0.0 0.0.0.255") == "10.0.0.0/24"
        assert adapter._wildcard_to_cidr("192.168.1.0 0.0.0.0") == "192.168.1.0/32"
        assert adapter._wildcard_to_cidr("any") == "any"
        assert adapter._wildcard_to_cidr("host 10.0.0.1") == "10.0.0.1/32"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_cisco_adapter.py -v`
Expected: ImportError — module not found

**Step 3: Write the adapter**

Create `backend/src/network/adapters/cisco_adapter.py`:

```python
"""Cisco IOS-XE RESTCONF adapter.

Fetches ACLs, interfaces, routes, and zones from Cisco IOS-XE devices
via the RESTCONF API (RFC 8040).

All diagnostic reads operate against a locally-cached snapshot.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface, VRF
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType, NATDirection,
    AdapterHealth, AdapterHealthStatus,
)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

_RESTCONF_HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _stable_id(*parts: str) -> str:
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class CiscoAdapter(FirewallAdapter):
    """Adapter for Cisco IOS-XE devices via RESTCONF.

    Parameters
    ----------
    hostname : str
        Device management IP or FQDN.
    username : str
        RESTCONF username.
    password : str
        RESTCONF password.
    verify_ssl : bool
        Whether to verify TLS certificates (default False for lab devices).
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.CISCO,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={"username": username, "verify_ssl": verify_ssl},
        )
        self._hostname = hostname
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl

    # ── RESTCONF client helper ─────────────────────────────────────────

    def _client(self) -> "httpx.AsyncClient":
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Cisco RESTCONF. Install: pip install httpx"
            )
        return httpx.AsyncClient(
            base_url=f"https://{self._hostname}",
            auth=(self._username, self._password),
            headers=_RESTCONF_HEADERS,
            verify=self._verify_ssl,
            timeout=30,
        )

    # ── Flow simulation ────────────────────────────────────────────────

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp",
    ) -> PolicyVerdict:
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = (
                rule.protocol.lower() in (protocol.lower(), "any")
                or protocol.lower() == "any"
            )
            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.90,
                    details=f"Matched Cisco ACE '{rule.rule_name}' (seq {rule.order})",
                )

        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.85,
            details="No matching ACE; Cisco implicit deny at end of ACL",
        )

    # ── Fetch methods ──────────────────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch extended ACLs via RESTCONF."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        rules: list[FirewallRule] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/Cisco-IOS-XE-native:native/ip/access-list"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            # Navigate extended ACL structure
            acl_cfg = data.get("Cisco-IOS-XE-native:access-list", {})
            extended = acl_cfg.get("Cisco-IOS-XE-acl:extended", [])
            for acl in extended:
                acl_name = acl.get("name", "")
                for idx, ace in enumerate(acl.get("access-list-seq-rule", [])):
                    entry = ace.get("ace-rule", {})
                    if entry:
                        rules.append(self._normalize_ace(entry, acl_name, idx))

        logger.info("Fetched %d ACL rules from %s", len(rules), self._hostname)
        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch static NAT entries via RESTCONF."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        nat_rules: list[NATRule] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/Cisco-IOS-XE-native:native/ip/nat"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            static_entries = (
                data.get("Cisco-IOS-XE-native:nat", {})
                .get("inside", {})
                .get("source", {})
                .get("static", [])
            )
            for idx, entry in enumerate(static_entries):
                local_ip = entry.get("local-ip", "")
                global_ip = entry.get("global-ip", "")
                nat_rules.append(NATRule(
                    id=_stable_id(self._hostname, "nat-static", str(idx)),
                    device_id=self._hostname,
                    original_src=local_ip,
                    translated_src=global_ip,
                    direction=NATDirection.SNAT,
                    description=f"Static NAT {local_ip} -> {global_ip}",
                ))

        logger.info("Fetched %d NAT rules from %s", len(nat_rules), self._hostname)
        return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch interfaces via RESTCONF ietf-interfaces."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        interfaces: list[DeviceInterface] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/ietf-interfaces:interfaces"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for iface in data.get("ietf-interfaces:interfaces", {}).get("interface", []):
                name = iface.get("name", "")
                enabled = iface.get("enabled", True)
                ip_data = (
                    iface.get("ietf-ip:ipv4", {})
                    .get("address", [])
                )
                ip_str = ip_data[0].get("ip", "") if ip_data else ""
                interfaces.append(DeviceInterface(
                    name=name,
                    ip=ip_str,
                    status="up" if enabled else "down",
                ))

        logger.info("Fetched %d interfaces from %s", len(interfaces), self._hostname)
        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Fetch routing table via RESTCONF."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        routes: list[Route] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/ietf-routing:routing/routing-instance=default/ribs/rib=ipv4-default/routes"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for rt in data.get("ietf-routing:routes", {}).get("route", []):
                prefix = rt.get("destination-prefix", "")
                nh = rt.get("next-hop", {})
                next_hop_ip = nh.get("next-hop-address", "") if isinstance(nh, dict) else ""
                iface = nh.get("outgoing-interface", "") if isinstance(nh, dict) else ""
                source_proto = rt.get("source-protocol", "static")
                routes.append(Route(
                    id=_stable_id(self._hostname, prefix),
                    device_id=self._hostname,
                    destination_cidr=prefix,
                    next_hop=next_hop_ip,
                    interface=iface,
                    protocol=source_proto.split(":")[-1] if ":" in source_proto else source_proto,
                ))

        logger.info("Fetched %d routes from %s", len(routes), self._hostname)
        return routes

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch zone-based firewall zones via RESTCONF.

        Cisco IOS-XE uses zone-based policy firewall (ZBFW). If not configured,
        returns an empty list.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        zones: list[Zone] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/Cisco-IOS-XE-native:native/zone/security"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for z in data.get("Cisco-IOS-XE-native:security", []):
                name = z.get("id", "")
                zones.append(Zone(
                    id=_stable_id(self._hostname, name),
                    name=name,
                    firewall_id=self._hostname,
                ))

        logger.info("Fetched %d zones from %s", len(zones), self._hostname)
        return zones

    # ── VRF support ────────────────────────────────────────────────────

    async def get_vrfs(self) -> list[VRF]:
        """Fetch VRF definitions via RESTCONF."""
        if not _HTTPX_AVAILABLE:
            return []
        vrfs: list[VRF] = []
        async with self._client() as client:
            resp = await client.get(
                "/restconf/data/Cisco-IOS-XE-native:native/vrf/definition"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for v in data.get("Cisco-IOS-XE-native:definition", []):
                name = v.get("name", "")
                rd = v.get("rd", "")
                vrfs.append(VRF(name=name, rd=rd))

        return vrfs

    # ── ACE normalization ──────────────────────────────────────────────

    def _normalize_ace(self, raw: dict, acl_name: str, index: int) -> FirewallRule:
        """Convert a RESTCONF ACE dict to a FirewallRule."""
        action_str = raw.get("action", "deny").lower()
        action = PolicyAction.ALLOW if action_str == "permit" else PolicyAction.DENY

        src_raw = raw.get("source", "any")
        dst_raw = raw.get("destination", "any")
        src_ips = [self._wildcard_to_cidr(src_raw)]
        dst_ips = [self._wildcard_to_cidr(dst_raw)]

        ports: list[int] = []
        dst_port = raw.get("destination-port", "")
        if dst_port:
            try:
                ports.append(int(dst_port))
            except ValueError:
                pass

        protocol = raw.get("protocol", "ip")
        if protocol == "ip":
            protocol = "any"

        seq = raw.get("sequence", index * 10 + 10)

        return FirewallRule(
            id=_stable_id(self._hostname, acl_name, str(seq)),
            device_id=self._hostname,
            rule_name=raw.get("name", f"{acl_name}-seq-{seq}"),
            src_zone="",
            dst_zone="",
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            protocol=protocol,
            action=action,
            logged="log" in raw,
            order=int(seq),
        )

    @staticmethod
    def _wildcard_to_cidr(addr: str) -> str:
        """Convert Cisco wildcard mask notation to CIDR.

        Examples:
            '10.0.0.0 0.0.0.255' -> '10.0.0.0/24'
            'host 10.0.0.1' -> '10.0.0.1/32'
            'any' -> 'any'
        """
        if not addr or addr.lower() == "any":
            return "any"
        if addr.lower().startswith("host "):
            return f"{addr.split()[1]}/32"
        parts = addr.split()
        if len(parts) == 2:
            ip, wildcard = parts
            try:
                wc_octets = [int(o) for o in wildcard.split(".")]
                mask_bits = sum(bin(255 - o).count("1") for o in wc_octets)
                return f"{ip}/{mask_bits}"
            except (ValueError, IndexError):
                return addr
        return addr
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_cisco_adapter.py -v`
Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add backend/src/network/adapters/cisco_adapter.py backend/tests/test_cisco_adapter.py
git commit -m "feat(adapters): add Cisco IOS-XE RESTCONF adapter"
```

---

### Task 3: F5 BIG-IP iControl REST Adapter

**Files:**
- Create: `backend/src/network/adapters/f5_adapter.py`
- Test: `backend/tests/test_f5_adapter.py`

**What:** Adapter for F5 BIG-IP LTM/AFM using the iControl REST API. Fetches firewall policies (AFM), virtual servers, NAT pools, self IPs, and route domains. F5 is primarily a load balancer but AFM provides L4 firewall capabilities.

**Step 1: Write the test file**

Create `backend/tests/test_f5_adapter.py`:

```python
"""Tests for F5 BIG-IP adapter."""
import pytest
import time
from src.network.adapters.f5_adapter import F5Adapter
from src.network.models import (
    FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor,
)


@pytest.fixture
def adapter():
    return F5Adapter(
        hostname="192.168.1.245",
        username="admin",
        password="admin",
    )


class TestF5Adapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.F5
        assert "192.168.1.245" in adapter.api_endpoint

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="afm-1", device_id="192.168.1.245",
                rule_name="allow-https",
                src_ips=["10.0.0.0/8"], dst_ips=["any"],
                ports=[443], protocol="tcp",
                action=PolicyAction.ALLOW, order=1,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.90

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_simulate_order_matters(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="afm-deny", device_id="192.168.1.245",
                rule_name="deny-all", src_ips=["any"], dst_ips=["any"],
                ports=[], protocol="any", action=PolicyAction.DENY, order=100,
            ),
            FirewallRule(
                id="afm-allow", device_id="192.168.1.245",
                rule_name="allow-web", src_ips=["any"], dst_ips=["any"],
                ports=[80], protocol="tcp", action=PolicyAction.ALLOW, order=10,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.1", "10.0.0.2", 80, "tcp")
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.rule_name == "allow-web"

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        adapter = F5Adapter(hostname="", username="", password="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"

    def test_normalize_afm_rule(self, adapter):
        raw = {
            "name": "allow_dns",
            "action": "accept",
            "ipProtocol": "udp",
            "source": {"addresses": [{"name": "10.0.0.0/24"}]},
            "destination": {"addresses": [{"name": "any"}], "ports": [{"name": "53"}]},
            "log": "yes",
        }
        rule = adapter._normalize_afm_rule(raw, "global-policy", 0)
        assert rule.action == PolicyAction.ALLOW
        assert rule.protocol == "udp"
        assert 53 in rule.ports
        assert rule.src_ips == ["10.0.0.0/24"]
        assert rule.logged is True

    def test_normalize_afm_drop(self, adapter):
        raw = {
            "name": "drop_telnet",
            "action": "drop",
            "ipProtocol": "tcp",
            "source": {"addresses": [{"name": "any"}]},
            "destination": {"addresses": [{"name": "any"}], "ports": [{"name": "23"}]},
        }
        rule = adapter._normalize_afm_rule(raw, "global-policy", 1)
        assert rule.action == PolicyAction.DROP
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_f5_adapter.py -v`
Expected: ImportError

**Step 3: Write the adapter**

Create `backend/src/network/adapters/f5_adapter.py`:

```python
"""F5 BIG-IP iControl REST adapter.

Fetches AFM firewall rules, virtual servers (as pseudo-rules), self IPs,
route domains, and NAT pools from F5 BIG-IP via the iControl REST API.

All diagnostic reads operate against a locally-cached snapshot.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType, NATDirection,
    AdapterHealth, AdapterHealthStatus,
)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


def _stable_id(*parts: str) -> str:
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class F5Adapter(FirewallAdapter):
    """Adapter for F5 BIG-IP via iControl REST API.

    Parameters
    ----------
    hostname : str
        BIG-IP management IP or FQDN.
    username : str
        iControl REST username.
    password : str
        iControl REST password.
    partition : str
        BIG-IP partition (default 'Common').
    verify_ssl : bool
        Whether to verify TLS certificates.
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        partition: str = "Common",
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.F5,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={"username": username, "partition": partition},
        )
        self._hostname = hostname
        self._username = username
        self._password = password
        self._partition = partition
        self._verify_ssl = verify_ssl

    # ── REST client helper ─────────────────────────────────────────────

    def _client(self) -> "httpx.AsyncClient":
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for F5 iControl REST. Install: pip install httpx"
            )
        return httpx.AsyncClient(
            base_url=f"https://{self._hostname}",
            auth=(self._username, self._password),
            headers={"Content-Type": "application/json"},
            verify=self._verify_ssl,
            timeout=30,
        )

    # ── Flow simulation ────────────────────────────────────────────────

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp",
    ) -> PolicyVerdict:
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = (
                rule.protocol.lower() in (protocol.lower(), "any")
                or protocol.lower() == "any"
            )
            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.90,
                    details=f"Matched F5 AFM rule '{rule.rule_name}' (order {rule.order})",
                )

        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="afm-implicit-deny",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.80,
            details="No matching AFM rule; F5 implicit deny",
        )

    # ── Fetch methods ──────────────────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch AFM firewall rules via iControl REST."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        rules: list[FirewallRule] = []
        async with self._client() as client:
            # AFM firewall policies
            resp = await client.get(
                f"/mgmt/tm/security/firewall/policy"
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for policy in data.get("items", []):
                policy_name = policy.get("name", "")
                rules_ref = policy.get("rulesReference", {}).get("link", "")
                if rules_ref:
                    # Fetch individual rules for this policy
                    rules_url = rules_ref.replace("https://localhost", "")
                    r_resp = await client.get(rules_url)
                    if r_resp.status_code == 200:
                        for idx, raw_rule in enumerate(r_resp.json().get("items", [])):
                            rules.append(
                                self._normalize_afm_rule(raw_rule, policy_name, idx)
                            )

        logger.info("Fetched %d AFM rules from %s", len(rules), self._hostname)
        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch SNAT pools and NAT policies from F5."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        nat_rules: list[NATRule] = []
        async with self._client() as client:
            resp = await client.get("/mgmt/tm/ltm/snatpool")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for idx, pool in enumerate(data.get("items", [])):
                name = pool.get("name", "")
                members = pool.get("members", [])
                for member in members:
                    nat_rules.append(NATRule(
                        id=_stable_id(self._hostname, "snat", name, member),
                        device_id=self._hostname,
                        translated_src=member.replace("/Common/", ""),
                        direction=NATDirection.SNAT,
                        description=f"SNAT pool '{name}'",
                    ))

        logger.info("Fetched %d NAT entries from %s", len(nat_rules), self._hostname)
        return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch self IPs as logical interfaces from F5."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        interfaces: list[DeviceInterface] = []
        async with self._client() as client:
            resp = await client.get("/mgmt/tm/net/self")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for self_ip in data.get("items", []):
                name = self_ip.get("name", "")
                address = self_ip.get("address", "")
                ip_part = address.split("/")[0] if "/" in address else address
                vlan = self_ip.get("vlan", "")
                interfaces.append(DeviceInterface(
                    name=name,
                    ip=ip_part,
                    zone=vlan.replace("/Common/", "") if vlan else "",
                    status="up",
                ))

        logger.info("Fetched %d self IPs from %s", len(interfaces), self._hostname)
        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Fetch static routes from F5 route domain."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        routes: list[Route] = []
        async with self._client() as client:
            resp = await client.get("/mgmt/tm/net/route")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for rt in data.get("items", []):
                name = rt.get("name", "")
                network = rt.get("network", "")
                gw = rt.get("gw", "")
                routes.append(Route(
                    id=_stable_id(self._hostname, name),
                    device_id=self._hostname,
                    destination_cidr=network,
                    next_hop=gw,
                    protocol="static",
                ))

        logger.info("Fetched %d routes from %s", len(routes), self._hostname)
        return routes

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch route domains as security zones from F5.

        F5 route domains provide network segmentation similar to
        security zones on traditional firewalls.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        zones: list[Zone] = []
        async with self._client() as client:
            resp = await client.get("/mgmt/tm/net/route-domain")
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()

            for rd in data.get("items", []):
                name = rd.get("name", "")
                rd_id = rd.get("id", 0)
                zones.append(Zone(
                    id=_stable_id(self._hostname, str(rd_id)),
                    name=f"route-domain-{name}",
                    description=f"Route domain ID {rd_id}",
                    firewall_id=self._hostname,
                ))

        logger.info("Fetched %d route domains from %s", len(zones), self._hostname)
        return zones

    # ── AFM rule normalization ─────────────────────────────────────────

    def _normalize_afm_rule(
        self, raw: dict, policy_name: str, index: int
    ) -> FirewallRule:
        """Convert an F5 AFM rule JSON dict to a FirewallRule.

        AFM rule structure (simplified):
        {
            "name": "allow_dns",
            "action": "accept" | "drop" | "reject" | "accept-decisively",
            "ipProtocol": "tcp" | "udp" | "any",
            "source": {"addresses": [{"name": "10.0.0.0/24"}]},
            "destination": {
                "addresses": [{"name": "any"}],
                "ports": [{"name": "53"}]
            },
            "log": "yes" | "no"
        }
        """
        action_str = raw.get("action", "drop").lower()
        if action_str in ("accept", "accept-decisively"):
            action = PolicyAction.ALLOW
        elif action_str == "drop":
            action = PolicyAction.DROP
        else:
            action = PolicyAction.DENY

        # Source addresses
        src_addrs = raw.get("source", {}).get("addresses", [])
        src_ips = [a.get("name", "any") for a in src_addrs] if src_addrs else ["any"]

        # Destination addresses and ports
        dst_section = raw.get("destination", {})
        dst_addrs = dst_section.get("addresses", [])
        dst_ips = [a.get("name", "any") for a in dst_addrs] if dst_addrs else ["any"]

        ports: list[int] = []
        for p in dst_section.get("ports", []):
            port_name = p.get("name", "")
            try:
                ports.append(int(port_name))
            except ValueError:
                pass

        protocol = raw.get("ipProtocol", "any").lower()
        logged = raw.get("log", "no").lower() == "yes"

        return FirewallRule(
            id=_stable_id(self._hostname, policy_name, raw.get("name", str(index))),
            device_id=self._hostname,
            rule_name=raw.get("name", f"{policy_name}-rule-{index}"),
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            protocol=protocol,
            action=action,
            logged=logged,
            order=index,
        )
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_f5_adapter.py -v`
Expected: All 7 tests pass

**Step 5: Commit**

```bash
git add backend/src/network/adapters/f5_adapter.py backend/tests/test_f5_adapter.py
git commit -m "feat(adapters): add F5 BIG-IP iControl REST adapter"
```

---

### Task 4: Check Point Management API Adapter

**Files:**
- Create: `backend/src/network/adapters/checkpoint_adapter.py`
- Test: `backend/tests/test_checkpoint_adapter.py`

**What:** Adapter for Check Point firewalls using the Management API (SmartConsole API). Fetches access rules, NAT rules, gateways, and network objects via JSON-RPC over HTTPS. Auth uses session-based login with API key or username/password.

**Step 1: Write the test file**

Create `backend/tests/test_checkpoint_adapter.py`:

```python
"""Tests for Check Point Management API adapter."""
import pytest
import time
from src.network.adapters.checkpoint_adapter import CheckpointAdapter
from src.network.models import (
    FirewallRule, PolicyAction, VerdictMatchType, FirewallVendor,
)


@pytest.fixture
def adapter():
    return CheckpointAdapter(
        hostname="192.168.1.100",
        username="admin",
        password="cpw0rd!",
    )


class TestCheckpointAdapter:
    def test_init(self, adapter):
        assert adapter.vendor == FirewallVendor.CHECKPOINT
        assert "192.168.1.100" in adapter.api_endpoint

    @pytest.mark.asyncio
    async def test_simulate_allow(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="cp-1", device_id="192.168.1.100",
                rule_name="Allow Web",
                src_ips=["10.0.0.0/8"], dst_ips=["any"],
                ports=[80, 443], protocol="tcp",
                action=PolicyAction.ALLOW, order=1,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 443)
        assert verdict.action == PolicyAction.ALLOW
        assert verdict.confidence == 0.90

    @pytest.mark.asyncio
    async def test_simulate_drop(self, adapter):
        adapter._rules_cache = [
            FirewallRule(
                id="cp-2", device_id="192.168.1.100",
                rule_name="Drop All",
                src_ips=["any"], dst_ips=["any"],
                ports=[], protocol="any",
                action=PolicyAction.DROP, order=999,
            ),
        ]
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DROP

    @pytest.mark.asyncio
    async def test_simulate_implicit_deny(self, adapter):
        adapter._rules_cache = []
        adapter._snapshot_time = time.time()
        verdict = await adapter.simulate_flow("10.0.0.5", "172.16.0.1", 22)
        assert verdict.action == PolicyAction.DENY
        assert verdict.match_type == VerdictMatchType.IMPLICIT_DENY

    @pytest.mark.asyncio
    async def test_health_not_configured(self):
        adapter = CheckpointAdapter(hostname="", username="", password="")
        health = await adapter.health_check()
        assert health.status.value == "not_configured"

    def test_normalize_access_rule(self, adapter):
        raw = {
            "uid": "abc-123",
            "name": "Allow DNS",
            "action": {"name": "Accept"},
            "source": [{"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24}],
            "destination": [{"type": "CpmiAnyObject", "name": "Any"}],
            "service": [{"type": "service-tcp", "port": "53"}],
            "track": {"type": {"name": "Log"}},
        }
        rule = adapter._normalize_access_rule(raw, "Standard", 0)
        assert rule.action == PolicyAction.ALLOW
        assert rule.src_ips == ["10.0.0.0/24"]
        assert 53 in rule.ports
        assert rule.logged is True

    def test_normalize_drop_rule(self, adapter):
        raw = {
            "uid": "def-456",
            "name": "Cleanup",
            "action": {"name": "Drop"},
            "source": [{"type": "CpmiAnyObject", "name": "Any"}],
            "destination": [{"type": "CpmiAnyObject", "name": "Any"}],
            "service": [{"type": "CpmiAnyObject", "name": "Any"}],
            "track": {"type": {"name": "None"}},
        }
        rule = adapter._normalize_access_rule(raw, "Standard", 99)
        assert rule.action == PolicyAction.DROP
        assert rule.logged is False

    def test_extract_ip_from_object(self, adapter):
        assert adapter._extract_ip({"type": "host", "ipv4-address": "10.0.0.1"}) == "10.0.0.1/32"
        assert adapter._extract_ip({"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24}) == "10.0.0.0/24"
        assert adapter._extract_ip({"type": "CpmiAnyObject", "name": "Any"}) == "any"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_checkpoint_adapter.py -v`
Expected: ImportError

**Step 3: Write the adapter**

Create `backend/src/network/adapters/checkpoint_adapter.py`:

```python
"""Check Point Management API adapter.

Fetches access rules, NAT rules, gateways, and network objects from
Check Point firewalls via the Management API (SmartConsole API).

Authentication uses session-based login. All diagnostic reads operate
against a locally-cached snapshot.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional

from .base import FirewallAdapter, DeviceInterface
from ..models import (
    PolicyVerdict, FirewallVendor, FirewallRule, NATRule, Zone, Route,
    PolicyAction, VerdictMatchType, NATDirection,
    AdapterHealth, AdapterHealthStatus,
)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

# Check Point Management API default port
_MGMT_PORT = 443


def _stable_id(*parts: str) -> str:
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class CheckpointAdapter(FirewallAdapter):
    """Adapter for Check Point firewalls via Management API.

    Parameters
    ----------
    hostname : str
        Management server IP or FQDN.
    username : str
        SmartConsole / API username.
    password : str
        SmartConsole / API password.
    domain : str
        MDS domain name (empty for standalone).
    port : int
        Management API port (default 443).
    verify_ssl : bool
        Whether to verify TLS certificates.
    """

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        domain: str = "",
        port: int = _MGMT_PORT,
        verify_ssl: bool = False,
    ) -> None:
        api_endpoint = f"https://{hostname}:{port}" if hostname else ""
        super().__init__(
            vendor=FirewallVendor.CHECKPOINT,
            api_endpoint=api_endpoint,
            api_key="",
            extra_config={"username": username, "domain": domain},
        )
        self._hostname = hostname
        self._port = port
        self._username = username
        self._password = password
        self._domain = domain
        self._verify_ssl = verify_ssl
        self._session_id: Optional[str] = None
        self._session_ts: float = 0

    # ── Session management ─────────────────────────────────────────────

    _SESSION_TTL = 500  # CP sessions expire in ~600s

    async def _login(self) -> None:
        """Authenticate to Check Point Management API."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError(
                "httpx is required for Check Point API. Install: pip install httpx"
            )
        payload: dict = {
            "user": self._username,
            "password": self._password,
        }
        if self._domain:
            payload["domain"] = self._domain

        async with httpx.AsyncClient(
            verify=self._verify_ssl, timeout=30
        ) as client:
            resp = await client.post(
                f"{self.api_endpoint}/web_api/login",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            self._session_id = data.get("sid", "")
            self._session_ts = time.time()

    async def _ensure_session(self) -> None:
        if (
            not self._session_id
            or (time.time() - self._session_ts) > self._SESSION_TTL
        ):
            await self._login()

    def _api_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-chkp-sid": self._session_id or "",
        }

    async def _api_call(self, command: str, payload: dict = None) -> dict:
        """Make a Check Point Management API call."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        await self._ensure_session()
        async with httpx.AsyncClient(
            verify=self._verify_ssl, timeout=30
        ) as client:
            resp = await client.post(
                f"{self.api_endpoint}/web_api/{command}",
                json=payload or {},
                headers=self._api_headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Flow simulation ────────────────────────────────────────────────

    async def simulate_flow(
        self, src_ip: str, dst_ip: str, port: int, protocol: str = "tcp",
    ) -> PolicyVerdict:
        await self._ensure_snapshot()

        for rule in sorted(self._rules_cache, key=lambda r: r.order):
            src_match = self._match_ip(src_ip, rule.src_ips)
            dst_match = self._match_ip(dst_ip, rule.dst_ips)
            port_match = self._match_port(port, rule.ports)
            proto_match = (
                rule.protocol.lower() in (protocol.lower(), "any")
                or protocol.lower() == "any"
            )
            if src_match and dst_match and port_match and proto_match:
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.90,
                    details=f"Matched Check Point rule '{rule.rule_name}' (order {rule.order})",
                )

        # Check Point "Cleanup Rule" — implicit drop at bottom
        return PolicyVerdict(
            action=PolicyAction.DENY,
            rule_name="cleanup-rule",
            match_type=VerdictMatchType.IMPLICIT_DENY,
            confidence=0.85,
            details="No matching rule; Check Point implicit cleanup drop",
        )

    # ── Fetch methods ──────────────────────────────────────────────────

    async def _fetch_rules(self) -> list[FirewallRule]:
        """Fetch access rules from Check Point via show-access-rulebase."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        rules: list[FirewallRule] = []

        data = await self._api_call("show-access-rulebase", {
            "name": "Network",
            "details-level": "full",
            "limit": 500,
            "offset": 0,
            "use-object-dictionary": True,
        })

        for idx, raw in enumerate(data.get("rulebase", [])):
            if raw.get("type") == "access-section":
                section_name = raw.get("name", "")
                for sub_idx, sub_rule in enumerate(raw.get("rulebase", [])):
                    rules.append(
                        self._normalize_access_rule(sub_rule, section_name, len(rules))
                    )
            elif raw.get("type") == "access-rule":
                rules.append(
                    self._normalize_access_rule(raw, "Global", idx)
                )

        logger.info("Fetched %d access rules from %s", len(rules), self._hostname)
        return rules

    async def _fetch_nat_rules(self) -> list[NATRule]:
        """Fetch NAT rules via show-nat-rulebase."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        nat_rules: list[NATRule] = []

        data = await self._api_call("show-nat-rulebase", {
            "package": "standard",
            "details-level": "full",
            "limit": 500,
            "offset": 0,
        })

        for idx, raw in enumerate(data.get("rulebase", [])):
            if raw.get("type") != "nat-rule":
                continue
            orig_src = self._extract_ip(raw.get("original-source", {}))
            orig_dst = self._extract_ip(raw.get("original-destination", {}))
            trans_src = self._extract_ip(raw.get("translated-source", {}))
            trans_dst = self._extract_ip(raw.get("translated-destination", {}))

            is_dnat = trans_dst not in ("any", "")
            nat_rules.append(NATRule(
                id=_stable_id(self._hostname, "nat", str(idx)),
                device_id=self._hostname,
                original_src=orig_src,
                original_dst=orig_dst,
                translated_src=trans_src,
                translated_dst=trans_dst,
                direction=NATDirection.DNAT if is_dnat else NATDirection.SNAT,
            ))

        logger.info("Fetched %d NAT rules from %s", len(nat_rules), self._hostname)
        return nat_rules

    async def _fetch_interfaces(self) -> list[DeviceInterface]:
        """Fetch gateway interfaces via show-gateways-and-servers."""
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        interfaces: list[DeviceInterface] = []

        data = await self._api_call("show-gateways-and-servers", {
            "details-level": "full",
            "limit": 50,
        })

        for gw in data.get("objects", []):
            for iface in gw.get("interfaces", []):
                name = iface.get("name", "")
                ip = iface.get("ipv4-address", "")
                interfaces.append(DeviceInterface(
                    name=name,
                    ip=ip,
                    status="up",
                ))

        logger.info("Fetched %d interfaces from %s", len(interfaces), self._hostname)
        return interfaces

    async def _fetch_routes(self) -> list[Route]:
        """Check Point Management API doesn't expose routing tables directly.

        Returns empty; routes are typically on Gaia OS (not Management API).
        """
        return []

    async def _fetch_zones(self) -> list[Zone]:
        """Fetch security zones (topology-based) from Check Point.

        Maps Check Point 'simple-gateways' topology zones to our Zone model.
        """
        if not _HTTPX_AVAILABLE:
            raise NotImplementedError("httpx required")
        zones: list[Zone] = []

        data = await self._api_call("show-gateways-and-servers", {
            "details-level": "full",
            "limit": 50,
        })

        seen: set[str] = set()
        for gw in data.get("objects", []):
            for iface in gw.get("interfaces", []):
                topology = iface.get("topology", "")
                if topology and topology not in seen:
                    seen.add(topology)
                    zones.append(Zone(
                        id=_stable_id(self._hostname, topology),
                        name=topology,
                        firewall_id=self._hostname,
                    ))

        logger.info("Fetched %d zones from %s", len(zones), self._hostname)
        return zones

    # ── Health check override ──────────────────────────────────────────

    async def health_check(self) -> AdapterHealth:
        if not self._hostname:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.NOT_CONFIGURED,
                message="No Check Point hostname configured",
            )
        if not _HTTPX_AVAILABLE:
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message="httpx library is not installed",
            )
        try:
            await self._login()
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.CONNECTED,
                snapshot_age_seconds=self.snapshot_age_seconds(),
                last_refresh=self._format_snapshot_time(),
                message="Management API session established",
            )
        except Exception as e:
            err = str(e).lower()
            if "auth" in err or "401" in err or "403" in err or "wrong" in err:
                return AdapterHealth(
                    vendor=self.vendor,
                    status=AdapterHealthStatus.AUTH_FAILED,
                    message=str(e),
                )
            return AdapterHealth(
                vendor=self.vendor,
                status=AdapterHealthStatus.UNREACHABLE,
                message=str(e),
            )

    # ── Rule normalization ─────────────────────────────────────────────

    def _normalize_access_rule(
        self, raw: dict, section_name: str, index: int
    ) -> FirewallRule:
        """Convert a Check Point access rule to FirewallRule.

        CP rule structure (simplified):
        {
            "uid": "abc-123",
            "name": "Allow Web",
            "action": {"name": "Accept" | "Drop" | "Reject"},
            "source": [<network-object>...],
            "destination": [<network-object>...],
            "service": [<service-object>...],
            "track": {"type": {"name": "Log" | "None"}}
        }
        """
        action_obj = raw.get("action", {})
        action_name = action_obj.get("name", "Drop") if isinstance(action_obj, dict) else str(action_obj)
        action_lower = action_name.lower()
        if action_lower == "accept":
            action = PolicyAction.ALLOW
        elif action_lower == "drop":
            action = PolicyAction.DROP
        else:
            action = PolicyAction.DENY

        # Extract source/destination IPs
        src_objects = raw.get("source", [])
        dst_objects = raw.get("destination", [])
        src_ips = [self._extract_ip(o) for o in src_objects] if src_objects else ["any"]
        dst_ips = [self._extract_ip(o) for o in dst_objects] if dst_objects else ["any"]

        # Extract ports from service objects
        ports: list[int] = []
        protocol = "any"
        for svc in raw.get("service", []):
            svc_type = svc.get("type", "")
            if "CpmiAnyObject" in svc_type:
                continue
            port_str = svc.get("port", "")
            if port_str:
                try:
                    ports.append(int(port_str))
                except ValueError:
                    pass
            if "tcp" in svc_type.lower():
                protocol = "tcp"
            elif "udp" in svc_type.lower():
                protocol = "udp"

        # Track/logging
        track = raw.get("track", {})
        track_type = track.get("type", {}) if isinstance(track, dict) else {}
        track_name = track_type.get("name", "None") if isinstance(track_type, dict) else "None"
        logged = track_name.lower() not in ("none", "")

        return FirewallRule(
            id=raw.get("uid", _stable_id(self._hostname, section_name, str(index))),
            device_id=self._hostname,
            rule_name=raw.get("name", f"{section_name}-rule-{index}"),
            src_ips=src_ips,
            dst_ips=dst_ips,
            ports=ports,
            protocol=protocol,
            action=action,
            logged=logged,
            order=index,
        )

    @staticmethod
    def _extract_ip(obj: dict) -> str:
        """Extract IP/CIDR from a Check Point network object.

        Object types:
        - host: {"type": "host", "ipv4-address": "10.0.0.1"}
        - network: {"type": "network", "subnet4": "10.0.0.0", "mask-length4": 24}
        - CpmiAnyObject: any
        - group: uses name as fallback
        """
        obj_type = obj.get("type", "")
        if "CpmiAnyObject" in obj_type or obj.get("name", "").lower() == "any":
            return "any"
        if obj_type == "host":
            ip = obj.get("ipv4-address", "")
            return f"{ip}/32" if ip else "any"
        if obj_type == "network":
            subnet = obj.get("subnet4", "")
            mask = obj.get("mask-length4", 32)
            return f"{subnet}/{mask}" if subnet else "any"
        # address-range or group — use name as fallback
        name = obj.get("name", "")
        return name if name else "any"
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_checkpoint_adapter.py -v`
Expected: All 8 tests pass

**Step 5: Commit**

```bash
git add backend/src/network/adapters/checkpoint_adapter.py backend/tests/test_checkpoint_adapter.py
git commit -m "feat(adapters): add Check Point Management API adapter"
```

---

### Task 5: Wire New Adapters into Factory

**Files:**
- Modify: `backend/src/network/adapters/factory.py`
- Modify: `backend/tests/test_adapter_factory.py`

**What:** Add factory branches for CISCO, F5, and CHECKPOINT vendors so `create_adapter()` can instantiate them. Add tests confirming factory returns correct types.

**Step 1: Add factory tests**

Append to `backend/tests/test_adapter_factory.py`:

```python
def test_factory_cisco_returns_adapter():
    adapter = create_adapter(
        FirewallVendor.CISCO,
        api_endpoint="192.168.1.1",
        api_key="",
        extra_config={"username": "admin", "password": "cisco"},
    )
    assert isinstance(adapter, FirewallAdapter)
    assert adapter.vendor == FirewallVendor.CISCO


def test_factory_f5_returns_adapter():
    adapter = create_adapter(
        FirewallVendor.F5,
        api_endpoint="192.168.1.245",
        api_key="",
        extra_config={"username": "admin", "password": "admin"},
    )
    assert isinstance(adapter, FirewallAdapter)
    assert adapter.vendor == FirewallVendor.F5


def test_factory_checkpoint_returns_adapter():
    adapter = create_adapter(
        FirewallVendor.CHECKPOINT,
        api_endpoint="192.168.1.100",
        api_key="",
        extra_config={"username": "admin", "password": "cpw0rd"},
    )
    assert isinstance(adapter, FirewallAdapter)
    assert adapter.vendor == FirewallVendor.CHECKPOINT
```

**Step 2: Run tests to see them fail**

Run: `cd backend && python3 -m pytest tests/test_adapter_factory.py -v`
Expected: New tests fail (factory falls through to mock, but vendor assertion passes since mock preserves vendor)

**Step 3: Add factory branches**

In `backend/src/network/adapters/factory.py`, add three new `elif` branches before the `else` clause (line 99):

```python
    elif vendor == FirewallVendor.CISCO:
        try:
            from .cisco_adapter import CiscoAdapter
            username = extra.get("username", "")
            password = extra.get("password", "")
            if api_endpoint and username:
                return CiscoAdapter(
                    hostname=api_endpoint,
                    username=username,
                    password=password,
                    verify_ssl=extra.get("verify_ssl", False),
                )
        except Exception as e:
            logger.warning("Failed to create CiscoAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.F5:
        try:
            from .f5_adapter import F5Adapter
            username = extra.get("username", "")
            password = extra.get("password", "")
            if api_endpoint and username:
                return F5Adapter(
                    hostname=api_endpoint,
                    username=username,
                    password=password,
                    partition=extra.get("partition", "Common"),
                    verify_ssl=extra.get("verify_ssl", False),
                )
        except Exception as e:
            logger.warning("Failed to create F5Adapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.CHECKPOINT:
        try:
            from .checkpoint_adapter import CheckpointAdapter
            username = extra.get("username", "")
            password = extra.get("password", "")
            if api_endpoint and username:
                return CheckpointAdapter(
                    hostname=api_endpoint,
                    username=username,
                    password=password,
                    domain=extra.get("domain", ""),
                    port=extra.get("port", 443),
                    verify_ssl=extra.get("verify_ssl", False),
                )
        except Exception as e:
            logger.warning("Failed to create CheckpointAdapter: %s, falling back to mock", e)
```

**Step 4: Run all factory tests**

Run: `cd backend && python3 -m pytest tests/test_adapter_factory.py -v`
Expected: All tests pass (6 total: 3 existing + 3 new)

**Step 5: Commit**

```bash
git add backend/src/network/adapters/factory.py backend/tests/test_adapter_factory.py
git commit -m "feat(adapters): wire Cisco, F5, Checkpoint into adapter factory"
```

---

### Task 6: Final Verification

**Files:**
- All modified/created adapter files

**Step 1: Run ALL adapter tests together**

Run:
```bash
cd backend && python3 -m pytest tests/test_cisco_adapter.py tests/test_f5_adapter.py tests/test_checkpoint_adapter.py tests/test_adapter_factory.py tests/test_adapter_registry.py tests/test_zscaler_adapter.py tests/test_panorama_adapter.py -v
```
Expected: All pass

**Step 2: Verify vendor enum completeness**

Run:
```bash
cd backend && python3 -c "
from src.network.models import FirewallVendor
vendors = [v.value for v in FirewallVendor]
assert 'cisco' in vendors, 'Missing CISCO'
assert 'f5' in vendors, 'Missing F5'
assert 'checkpoint' in vendors, 'Missing CHECKPOINT'
print(f'All {len(vendors)} vendors registered: {vendors}')
"
```
Expected: `All 8 vendors registered: ['palo_alto', 'azure_nsg', 'aws_sg', 'oracle_nsg', 'zscaler', 'cisco', 'f5', 'checkpoint']`

**Step 3: Verify factory creates correct adapter types**

Run:
```bash
cd backend && python3 -c "
from src.network.adapters.factory import create_adapter
from src.network.models import FirewallVendor
from src.network.adapters.cisco_adapter import CiscoAdapter
from src.network.adapters.f5_adapter import F5Adapter
from src.network.adapters.checkpoint_adapter import CheckpointAdapter

c = create_adapter(FirewallVendor.CISCO, '10.0.0.1', '', {'username': 'a', 'password': 'b'})
assert isinstance(c, CiscoAdapter), f'Expected CiscoAdapter, got {type(c)}'

f = create_adapter(FirewallVendor.F5, '10.0.0.2', '', {'username': 'a', 'password': 'b'})
assert isinstance(f, F5Adapter), f'Expected F5Adapter, got {type(f)}'

p = create_adapter(FirewallVendor.CHECKPOINT, '10.0.0.3', '', {'username': 'a', 'password': 'b'})
assert isinstance(p, CheckpointAdapter), f'Expected CheckpointAdapter, got {type(p)}'

print('All 3 adapters created with correct types')
"
```
Expected: `All 3 adapters created with correct types`

**Step 4: TypeScript check (frontend unchanged but verify)**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

---

## Execution Order

```
Task 1: Add enum values             (models.py — 1 min)
Task 2: Cisco adapter               (new file + tests — independent)
Task 3: F5 adapter                  (new file + tests — independent)
Task 4: Checkpoint adapter          (new file + tests — independent)
Task 5: Wire into factory           (factory.py — depends on Tasks 1-4)
Task 6: Final verification          (all files — depends on Task 5)
```

Tasks 2, 3, 4 are fully independent and can run in parallel after Task 1.
Task 5 depends on all adapters being created.
Task 6 is the final gate.

Recommended: 1 → (2 + 3 + 4 parallel) → 5 → 6
