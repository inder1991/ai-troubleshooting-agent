# KG Architecture Overhaul — Phase 1: Canonical Data Model + Repository Layer

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple the Knowledge Graph from direct SQLite access by introducing a TopologyRepository abstraction, canonical domain models, interface-level graph nodes, persisted neighbor links, and topology validation — all without breaking the existing system.

**Architecture:** New `repository/` package sits between API/KG and storage. Domain models are pure Python dataclasses (separate from Pydantic API models). Repository interface is abstract; concrete `SQLiteRepository` wraps existing `TopologyStore`. Existing code migrates incrementally — old imports still work during transition.

**Tech Stack:** Python 3.11+, pytest, dataclasses, abc, SQLite (existing TopologyStore), NetworkX (existing)

**Design Doc:** `docs/plans/2026-03-16-kg-architecture-overhaul-design.md`

---

## Task 1: Domain Models — Core Entities

**Files:**
- Create: `backend/src/network/repository/__init__.py`
- Create: `backend/src/network/repository/domain.py`
- Test: `backend/tests/test_repository_domain.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_repository_domain.py
"""Tests for canonical domain models."""
import pytest
from src.network.repository.domain import (
    Device, Interface, IPAddress, NeighborLink, VRFInstance, Route,
    Site, Zone, VLAN, Subnet,
)


class TestDevice:
    def test_create_device(self):
        d = Device(
            id="rtr-core-01",
            hostname="rtr-core-01",
            vendor="cisco",
            model="ISR4451",
            serial="FTX1234",
            device_type="ROUTER",
            site_id="dc-east",
            sources=["snmp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
            confidence=0.9,
        )
        assert d.id == "rtr-core-01"
        assert d.device_type == "ROUTER"
        assert d.confidence == 0.9

    def test_device_defaults(self):
        d = Device(
            id="sw-01", hostname="sw-01", vendor="cisco", model="C9300",
            serial="", device_type="SWITCH", site_id="",
            sources=[], first_seen="", last_seen="", confidence=0.5,
        )
        assert d.managed_by is None
        assert d.mode is None
        assert d.ha_mode is None
        assert d.state_sync is False


class TestInterface:
    def test_stable_id_format(self):
        """Interface ID must be device_id:name for deterministic upserts."""
        iface = Interface(
            id="rtr-core-01:GigabitEthernet0/0",
            device_id="rtr-core-01",
            name="GigabitEthernet0/0",
            sources=["snmp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
            confidence=0.9,
        )
        assert iface.id == "rtr-core-01:GigabitEthernet0/0"
        assert iface.device_id == "rtr-core-01"

    def test_interface_defaults(self):
        iface = Interface(
            id="sw-01:Gi0/1", device_id="sw-01", name="Gi0/1",
            sources=[], first_seen="", last_seen="", confidence=0.5,
        )
        assert iface.mac is None
        assert iface.admin_state == "up"
        assert iface.oper_state == "up"
        assert iface.speed is None
        assert iface.mtu is None
        assert iface.duplex is None
        assert iface.port_channel_id is None
        assert iface.description is None
        assert iface.vrf_instance_id is None
        assert iface.vlan_membership == []


class TestIPAddress:
    def test_create_ip(self):
        ip = IPAddress(
            id="rtr-core-01:Gi0/0:10.0.0.1",
            ip="10.0.0.1",
            prefix_len=30,
            assigned_to="rtr-core-01:Gi0/0",
            sources=["snmp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
            confidence=0.9,
        )
        assert ip.ip == "10.0.0.1"
        assert ip.assigned_to == "rtr-core-01:Gi0/0"


class TestNeighborLink:
    def test_create_neighbor(self):
        link = NeighborLink(
            id="rtr-core-01:Gi0/0--sw-dist-01:Gi0/48",
            device_id="rtr-core-01",
            local_interface="rtr-core-01:Gi0/0",
            remote_device="sw-dist-01",
            remote_interface="sw-dist-01:Gi0/48",
            protocol="lldp",
            sources=["lldp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
            confidence=0.95,
        )
        assert link.protocol == "lldp"
        assert link.confidence == 0.95


class TestVRFInstance:
    def test_create_vrf_instance(self):
        vrf = VRFInstance(
            id="rtr-core-01:default",
            vrf_id="default",
            device_id="rtr-core-01",
            sources=["config_parser"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
        )
        assert vrf.vrf_id == "default"
        assert vrf.device_id == "rtr-core-01"


class TestRoute:
    def test_create_route_with_ecmp(self):
        route = Route(
            id="rtr-core-01:default:0.0.0.0/0",
            device_id="rtr-core-01",
            vrf_instance_id="rtr-core-01:default",
            destination_cidr="0.0.0.0/0",
            prefix_len=0,
            protocol="bgp",
            admin_distance=20,
            metric=100,
            next_hop_refs=[
                {"ref": "rtr-core-01:Gi0/1", "weight": 1},
                {"ref": "rtr-core-01:Gi0/2", "weight": 1},
            ],
            sources=["snmp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
        )
        assert len(route.next_hop_refs) == 2
        assert route.protocol == "bgp"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_repository_domain.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.network.repository'`

**Step 3: Write minimal implementation**

```python
# backend/src/network/repository/__init__.py
"""Topology Repository — decouples graph/business logic from storage."""

# backend/src/network/repository/domain.py
"""Canonical domain models — pure Python, no DB dependency."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Device:
    id: str
    hostname: str
    vendor: str
    model: str
    serial: str
    device_type: str
    site_id: str
    sources: list[str]
    first_seen: str
    last_seen: str
    confidence: float
    managed_by: Optional[str] = None
    mode: Optional[str] = None          # routed/transparent (firewalls)
    ha_mode: Optional[str] = None
    state_sync: bool = False


@dataclass
class Interface:
    id: str                             # device_id:name (deterministic)
    device_id: str
    name: str
    sources: list[str]
    first_seen: str
    last_seen: str
    confidence: float
    mac: Optional[str] = None
    admin_state: str = "up"
    oper_state: str = "up"
    speed: Optional[int] = None
    mtu: Optional[int] = None
    duplex: Optional[str] = None
    port_channel_id: Optional[str] = None
    description: Optional[str] = None
    vrf_instance_id: Optional[str] = None
    vlan_membership: list[str] = field(default_factory=list)


@dataclass
class IPAddress:
    id: str
    ip: str
    assigned_to: str                    # interface_id
    sources: list[str]
    first_seen: str
    last_seen: str
    confidence: float
    prefix_len: Optional[int] = None
    assigned_from: Optional[str] = None
    lease_ts: Optional[str] = None


@dataclass
class Subnet:
    id: str
    cidr: str
    sources: list[str]
    first_seen: str
    last_seen: str
    vpc_id: Optional[str] = None
    vrf_id: Optional[str] = None
    purpose: Optional[str] = None
    owner: Optional[str] = None


@dataclass
class VLAN:
    id: str
    vlan_id: int
    name: str
    site_id: Optional[str] = None


@dataclass
class Site:
    id: str
    name: str
    location: Optional[str] = None
    site_type: Optional[str] = None     # dc/branch/colo


@dataclass
class Zone:
    id: str
    name: str
    security_level: int = 0
    zone_type: Optional[str] = None     # management/data/dmz


@dataclass
class VRFInstance:
    id: str                             # device_id:vrf_name
    vrf_id: str
    device_id: str
    sources: list[str]
    first_seen: str
    last_seen: str
    table_id: Optional[str] = None


@dataclass
class Route:
    id: str
    device_id: str
    vrf_instance_id: str
    destination_cidr: str
    prefix_len: int
    protocol: str
    sources: list[str]
    first_seen: str
    last_seen: str
    admin_distance: Optional[int] = None
    metric: Optional[int] = None
    next_hop_type: Optional[str] = None
    next_hop_refs: list[dict] = field(default_factory=list)  # [{ref, weight}]


@dataclass
class NeighborLink:
    id: str
    device_id: str
    local_interface: str                # interface id
    remote_device: str
    remote_interface: str               # interface id
    protocol: str                       # lldp/cdp
    sources: list[str]
    first_seen: str
    last_seen: str
    confidence: float


@dataclass
class SecurityPolicy:
    id: str
    device_id: str
    rule_order: int
    name: str
    action: str                         # permit/deny/drop/reset
    sources: list[str]
    first_seen: str
    last_seen: str
    src_zone: Optional[str] = None
    dst_zone: Optional[str] = None
    src_ip: Optional[str] = None
    dst_ip: Optional[str] = None
    src_port_range: Optional[tuple] = None
    dst_port_range: Optional[tuple] = None
    protocol: Optional[str] = None
    log: bool = False
    stateful: bool = True


@dataclass
class NATRule:
    id: str
    device_id: str
    nat_type: str                       # SNAT/DNAT/PAT/twice_nat
    priority: int
    sources: list[str]
    first_seen: str
    last_seen: str
    original_src: Optional[str] = None
    original_dst: Optional[str] = None
    translated_src: Optional[str] = None
    translated_dst: Optional[str] = None
    original_port: Optional[int] = None
    translated_port: Optional[int] = None
    direction: Optional[str] = None     # inbound/outbound
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_repository_domain.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/__init__.py backend/src/network/repository/domain.py backend/tests/test_repository_domain.py
git commit -m "feat(repository): add canonical domain models for topology entities"
```

---

## Task 2: Repository Interface (Abstract)

**Files:**
- Create: `backend/src/network/repository/interface.py`
- Test: `backend/tests/test_repository_interface.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_repository_interface.py
"""Tests for TopologyRepository interface contract."""
import pytest
from src.network.repository.interface import TopologyRepository
from src.network.repository.domain import Device


class TestRepositoryInterface:
    def test_cannot_instantiate_abstract(self):
        """TopologyRepository is abstract — must subclass."""
        with pytest.raises(TypeError):
            TopologyRepository()

    def test_defines_read_methods(self):
        """Interface must define all read methods."""
        required_reads = [
            "get_device", "get_devices", "get_interfaces",
            "get_ip_addresses", "get_routes", "get_neighbors",
            "get_security_policies", "find_device_by_ip",
            "find_device_by_serial", "find_device_by_hostname",
        ]
        for method in required_reads:
            assert hasattr(TopologyRepository, method), f"Missing: {method}"

    def test_defines_write_methods(self):
        """Interface must define all write methods."""
        required_writes = [
            "upsert_device", "upsert_interface", "upsert_ip_address",
            "upsert_neighbor_link", "upsert_route",
            "upsert_security_policy", "mark_stale",
        ]
        for method in required_writes:
            assert hasattr(TopologyRepository, method), f"Missing: {method}"

    def test_defines_graph_query_methods(self):
        """Interface must define graph query methods."""
        required_queries = [
            "find_paths", "blast_radius",
            "get_topology_export",
        ]
        for method in required_queries:
            assert hasattr(TopologyRepository, method), f"Missing: {method}"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_repository_interface.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/network/repository/interface.py
"""TopologyRepository — abstract interface that decouples business logic from storage."""
from abc import ABC, abstractmethod
from typing import Optional
from .domain import (
    Device, Interface, IPAddress, NeighborLink, VRFInstance, Route,
    SecurityPolicy, NATRule, Subnet, Site, Zone,
)


class TopologyRepository(ABC):
    """Abstract interface for all topology data access.

    Write path: callers upsert through this interface.
    Read path: callers query through this interface.
    Graph queries: path analysis, blast radius, export.

    Concrete implementations decide where data lives
    (SQLite, Postgres, Neo4j, etc).
    """

    # ── Reads ──

    @abstractmethod
    def get_device(self, device_id: str) -> Optional[Device]:
        ...

    @abstractmethod
    def get_devices(self, site_id: str = None, device_type: str = None) -> list[Device]:
        ...

    @abstractmethod
    def get_interfaces(self, device_id: str) -> list[Interface]:
        ...

    @abstractmethod
    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        ...

    @abstractmethod
    def get_routes(self, device_id: str, vrf_instance_id: str = None) -> list[Route]:
        ...

    @abstractmethod
    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        ...

    @abstractmethod
    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        ...

    @abstractmethod
    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        ...

    @abstractmethod
    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        ...

    @abstractmethod
    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        ...

    # ── Writes ──

    @abstractmethod
    def upsert_device(self, device: Device) -> Device:
        ...

    @abstractmethod
    def upsert_interface(self, interface: Interface) -> Interface:
        ...

    @abstractmethod
    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        ...

    @abstractmethod
    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        ...

    @abstractmethod
    def upsert_route(self, route: Route) -> Route:
        ...

    @abstractmethod
    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        ...

    @abstractmethod
    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        ...

    # ── Graph queries ──

    @abstractmethod
    def find_paths(self, src_ip: str, dst_ip: str,
                   vrf: str = "default", k: int = 3) -> list[dict]:
        ...

    @abstractmethod
    def blast_radius(self, device_id: str) -> dict:
        ...

    @abstractmethod
    def get_topology_export(self, site_id: str = None) -> dict:
        ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_repository_interface.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/interface.py backend/tests/test_repository_interface.py
git commit -m "feat(repository): add abstract TopologyRepository interface"
```

---

## Task 3: SQLite Repository — Read Operations

**Files:**
- Create: `backend/src/network/repository/sqlite_repository.py`
- Test: `backend/tests/test_sqlite_repository.py`

This wraps the existing `TopologyStore` behind the new repository interface.

**Step 1: Write the failing test**

```python
# backend/tests/test_sqlite_repository.py
"""Tests for SQLiteRepository — wraps existing TopologyStore."""
import os
import pytest
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import Device, Interface, NeighborLink
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device as PydanticDevice, DeviceType, Interface as PydanticInterface,
    Subnet, Zone,
)


@pytest.fixture
def repo(tmp_path):
    """Create a SQLiteRepository backed by a temp SQLite database."""
    db_path = str(tmp_path / "test.db")
    store = TopologyStore(db_path)
    return SQLiteRepository(store)


@pytest.fixture
def seeded_repo(repo):
    """Repository with sample devices and interfaces loaded."""
    store = repo._store

    store.add_device(PydanticDevice(
        id="rtr-core-01", name="rtr-core-01", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco", model="ISR4451",
        serial_number="FTX1234", role="core", site_id="dc-east",
    ))
    store.add_device(PydanticDevice(
        id="fw-perim-01", name="fw-perim-01", device_type=DeviceType.firewall,
        management_ip="10.0.0.2", vendor="palo_alto", model="PA-5260",
        serial_number="PA5260-001", role="perimeter", site_id="dc-east",
    ))

    store.add_interface(PydanticInterface(
        id="rtr-core-01:Gi0/0", device_id="rtr-core-01",
        name="Gi0/0", ip="10.0.0.1/30", role="core",
    ))
    store.add_interface(PydanticInterface(
        id="rtr-core-01:Gi0/1", device_id="rtr-core-01",
        name="Gi0/1", ip="10.0.1.1/30", role="distribution",
    ))
    store.add_interface(PydanticInterface(
        id="fw-perim-01:eth1/1", device_id="fw-perim-01",
        name="eth1/1", ip="10.0.0.2/30", role="outside",
    ))

    return repo


class TestSQLiteRepositoryReads:
    def test_get_device(self, seeded_repo):
        device = seeded_repo.get_device("rtr-core-01")
        assert device is not None
        assert isinstance(device, Device)
        assert device.hostname == "rtr-core-01"
        assert device.vendor == "cisco"
        assert device.device_type == "router"

    def test_get_device_not_found(self, seeded_repo):
        assert seeded_repo.get_device("nonexistent") is None

    def test_get_devices_all(self, seeded_repo):
        devices = seeded_repo.get_devices()
        assert len(devices) == 2
        assert all(isinstance(d, Device) for d in devices)

    def test_get_devices_by_type(self, seeded_repo):
        firewalls = seeded_repo.get_devices(device_type="firewall")
        assert len(firewalls) == 1
        assert firewalls[0].id == "fw-perim-01"

    def test_get_interfaces(self, seeded_repo):
        ifaces = seeded_repo.get_interfaces("rtr-core-01")
        assert len(ifaces) == 2
        assert all(isinstance(i, Interface) for i in ifaces)
        assert ifaces[0].device_id == "rtr-core-01"

    def test_get_interfaces_empty(self, seeded_repo):
        ifaces = seeded_repo.get_interfaces("nonexistent")
        assert ifaces == []

    def test_find_device_by_ip(self, seeded_repo):
        device = seeded_repo.find_device_by_ip("10.0.0.1")
        assert device is not None
        assert device.id == "rtr-core-01"

    def test_find_device_by_ip_not_found(self, seeded_repo):
        assert seeded_repo.find_device_by_ip("192.168.99.99") is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sqlite_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.network.repository.sqlite_repository'`

**Step 3: Write minimal implementation**

```python
# backend/src/network/repository/sqlite_repository.py
"""SQLiteRepository — wraps existing TopologyStore behind the TopologyRepository interface."""
from typing import Optional
from .interface import TopologyRepository
from .domain import (
    Device, Interface, IPAddress, NeighborLink, VRFInstance, Route,
    SecurityPolicy, NATRule,
)
from ..topology_store import TopologyStore


class SQLiteRepository(TopologyRepository):
    """Concrete repository backed by existing SQLite TopologyStore.

    Translates between Pydantic models (TopologyStore) and
    domain dataclasses (repository layer).
    """

    def __init__(self, store: TopologyStore):
        self._store = store

    # ── Helpers: convert Pydantic → domain ──

    def _to_domain_device(self, pydantic_device) -> Device:
        d = pydantic_device
        return Device(
            id=d.id,
            hostname=d.name,
            vendor=d.vendor or "",
            model=d.model or "",
            serial=d.serial_number or "",
            device_type=d.device_type.value if hasattr(d.device_type, 'value') else str(d.device_type),
            site_id=d.site_id or "",
            managed_by=None,
            mode=None,
            ha_mode=d.ha_role,
            state_sync=False,
            sources=["topology_store"],
            first_seen=d.discovered_at or "",
            last_seen=d.last_seen or "",
            confidence=0.9,
        )

    def _to_domain_interface(self, pydantic_iface) -> Interface:
        i = pydantic_iface
        return Interface(
            id=i.id,
            device_id=i.device_id,
            name=i.name,
            mac=i.mac,
            admin_state=i.admin_status or "up",
            oper_state=i.oper_status or "up",
            speed=None,  # parse from i.speed if available
            mtu=i.mtu,
            duplex=i.duplex,
            port_channel_id=i.channel_group,
            description=None,
            vrf_instance_id=i.vrf,
            vlan_membership=[],
            sources=["topology_store"],
            first_seen="",
            last_seen="",
            confidence=0.9,
        )

    # ── Reads ──

    def get_device(self, device_id: str) -> Optional[Device]:
        devices = self._store.list_devices()
        for d in devices:
            if d.id == device_id:
                return self._to_domain_device(d)
        return None

    def get_devices(self, site_id: str = None, device_type: str = None) -> list[Device]:
        devices = self._store.list_devices()
        result = [self._to_domain_device(d) for d in devices]
        if site_id:
            result = [d for d in result if d.site_id == site_id]
        if device_type:
            result = [d for d in result if d.device_type == device_type]
        return result

    def get_interfaces(self, device_id: str) -> list[Interface]:
        try:
            ifaces = self._store.list_interfaces(device_id=device_id)
            return [self._to_domain_interface(i) for i in ifaces]
        except Exception:
            return []

    def get_ip_addresses(self, interface_id: str) -> list[IPAddress]:
        # Current TopologyStore doesn't have separate IP table
        # Extract from interface.ip field
        parts = interface_id.split(":", 1)
        if len(parts) != 2:
            return []
        device_id, iface_name = parts
        ifaces = self._store.list_interfaces(device_id=device_id)
        for iface in ifaces:
            if iface.id == interface_id and iface.ip:
                ip_str = iface.ip.split("/")[0] if "/" in iface.ip else iface.ip
                prefix = int(iface.ip.split("/")[1]) if "/" in iface.ip else None
                return [IPAddress(
                    id=f"{interface_id}:{ip_str}",
                    ip=ip_str,
                    prefix_len=prefix,
                    assigned_to=interface_id,
                    sources=["topology_store"],
                    first_seen="", last_seen="",
                    confidence=0.9,
                )]
        return []

    def get_routes(self, device_id: str, vrf_instance_id: str = None) -> list[Route]:
        routes = self._store.list_routes()
        result = []
        for r in routes:
            if r.device_id != device_id:
                continue
            result.append(Route(
                id=f"{r.device_id}:{r.vrf or 'default'}:{r.destination_cidr}",
                device_id=r.device_id,
                vrf_instance_id=f"{r.device_id}:{r.vrf or 'default'}",
                destination_cidr=r.destination_cidr,
                prefix_len=int(r.destination_cidr.split("/")[1]) if "/" in r.destination_cidr else 0,
                protocol=r.protocol,
                admin_distance=None,
                metric=r.metric,
                next_hop_refs=[{"ref": r.next_hop, "weight": 1}] if r.next_hop else [],
                sources=["topology_store"],
                first_seen="", last_seen="",
            ))
        return result

    def get_neighbors(self, device_id: str) -> list[NeighborLink]:
        # Will be implemented in Task 5 (neighbor_links table)
        return []

    def get_security_policies(self, device_id: str) -> list[SecurityPolicy]:
        rules = self._store.list_firewall_rules(device_id=device_id)
        result = []
        for idx, r in enumerate(rules):
            result.append(SecurityPolicy(
                id=r.id if hasattr(r, 'id') else f"{device_id}:rule-{idx}",
                device_id=r.device_id,
                rule_order=r.order if hasattr(r, 'order') else idx,
                name=r.rule_name if hasattr(r, 'rule_name') else "",
                action=r.action.value if hasattr(r.action, 'value') else str(r.action),
                src_zone=r.src_zone if hasattr(r, 'src_zone') else None,
                dst_zone=r.dst_zone if hasattr(r, 'dst_zone') else None,
                sources=["topology_store"],
                first_seen="", last_seen="",
            ))
        return result

    def find_device_by_ip(self, ip: str) -> Optional[Device]:
        devices = self._store.list_devices()
        for d in devices:
            if d.management_ip == ip:
                return self._to_domain_device(d)
        # Also check interface IPs
        for d in devices:
            ifaces = self._store.list_interfaces(device_id=d.id)
            for iface in ifaces:
                if iface.ip:
                    bare_ip = iface.ip.split("/")[0] if "/" in iface.ip else iface.ip
                    if bare_ip == ip:
                        return self._to_domain_device(d)
        return None

    def find_device_by_serial(self, serial: str) -> Optional[Device]:
        if not serial:
            return None
        devices = self._store.list_devices()
        for d in devices:
            if d.serial_number == serial:
                return self._to_domain_device(d)
        return None

    def find_device_by_hostname(self, hostname: str) -> Optional[Device]:
        if not hostname:
            return None
        devices = self._store.list_devices()
        for d in devices:
            if d.name == hostname:
                return self._to_domain_device(d)
        return None

    # ── Writes (delegate to existing store) ──

    def upsert_device(self, device: Device) -> Device:
        from ..models import Device as PydanticDevice, DeviceType
        pd = PydanticDevice(
            id=device.id,
            name=device.hostname,
            device_type=device.device_type,
            management_ip="",
            vendor=device.vendor,
            model=device.model,
            serial_number=device.serial,
            role="",
            site_id=device.site_id,
            ha_role=device.ha_mode,
        )
        self._store.add_device(pd)
        return device

    def upsert_interface(self, interface: Interface) -> Interface:
        from ..models import Interface as PydanticInterface
        pi = PydanticInterface(
            id=interface.id,
            device_id=interface.device_id,
            name=interface.name,
            mac=interface.mac,
            admin_status=interface.admin_state,
            oper_status=interface.oper_state,
            mtu=interface.mtu,
            duplex=interface.duplex,
            vrf=interface.vrf_instance_id,
            channel_group=interface.port_channel_id,
        )
        self._store.add_interface(pi)
        return interface

    def upsert_ip_address(self, ip_address: IPAddress) -> IPAddress:
        # IP stored as part of interface in current schema
        return ip_address

    def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
        # Will be implemented in Task 5 (neighbor_links table)
        return link

    def upsert_route(self, route: Route) -> Route:
        from ..models import Route as PydanticRoute
        next_hop = route.next_hop_refs[0]["ref"] if route.next_hop_refs else ""
        pr = PydanticRoute(
            device_id=route.device_id,
            destination_cidr=route.destination_cidr,
            next_hop=next_hop,
            protocol=route.protocol,
            metric=route.metric,
            vrf=route.vrf_instance_id.split(":")[-1] if ":" in route.vrf_instance_id else route.vrf_instance_id,
        )
        self._store.add_route(pr)
        return route

    def upsert_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        return policy

    def mark_stale(self, entity_type: str, entity_id: str) -> None:
        pass  # SQLite store doesn't support stale marking yet

    # ── Graph queries (delegate to existing KG for now) ──

    def find_paths(self, src_ip: str, dst_ip: str,
                   vrf: str = "default", k: int = 3) -> list[dict]:
        return []  # Will be wired to KG in Task 7

    def blast_radius(self, device_id: str) -> dict:
        return {"affected_devices": [], "affected_tunnels": [],
                "affected_sites": [], "affected_vpcs": [], "severed_paths": 0}

    def get_topology_export(self, site_id: str = None) -> dict:
        return {"nodes": [], "edges": [], "groups": []}  # Will be wired in Task 7
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_sqlite_repository.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/sqlite_repository.py backend/tests/test_sqlite_repository.py
git commit -m "feat(repository): SQLiteRepository wrapping existing TopologyStore"
```

---

## Task 4: Neighbor Links Table

**Files:**
- Modify: `backend/src/network/topology_store.py`
- Modify: `backend/src/network/repository/sqlite_repository.py`
- Test: `backend/tests/test_neighbor_links.py`

This adds a `neighbor_links` table to SQLite so LLDP/CDP discovery results are persisted, not imported at runtime from discovery_scheduler.

**Step 1: Write the failing test**

```python
# backend/tests/test_neighbor_links.py
"""Tests for persisted neighbor links in TopologyStore."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import NeighborLink
from src.network.models import Device as PydanticDevice, DeviceType


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


@pytest.fixture
def repo(store):
    return SQLiteRepository(store)


@pytest.fixture
def seeded(store, repo):
    store.add_device(PydanticDevice(
        id="rtr-01", name="rtr-01", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco",
    ))
    store.add_device(PydanticDevice(
        id="sw-01", name="sw-01", device_type=DeviceType.switch,
        management_ip="10.0.0.2", vendor="cisco",
    ))
    return repo


class TestNeighborLinks:
    def test_upsert_and_read(self, seeded):
        link = NeighborLink(
            id="rtr-01:Gi0/0--sw-01:Gi0/48",
            device_id="rtr-01",
            local_interface="rtr-01:Gi0/0",
            remote_device="sw-01",
            remote_interface="sw-01:Gi0/48",
            protocol="lldp",
            sources=["lldp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T00:00:00Z",
            confidence=0.95,
        )
        seeded.upsert_neighbor_link(link)

        neighbors = seeded.get_neighbors("rtr-01")
        assert len(neighbors) == 1
        assert neighbors[0].remote_device == "sw-01"
        assert neighbors[0].protocol == "lldp"
        assert neighbors[0].confidence == 0.95

    def test_upsert_idempotent(self, seeded):
        link = NeighborLink(
            id="rtr-01:Gi0/0--sw-01:Gi0/48",
            device_id="rtr-01",
            local_interface="rtr-01:Gi0/0",
            remote_device="sw-01",
            remote_interface="sw-01:Gi0/48",
            protocol="lldp",
            sources=["lldp"],
            first_seen="2026-03-16T00:00:00Z",
            last_seen="2026-03-16T01:00:00Z",
            confidence=0.95,
        )
        seeded.upsert_neighbor_link(link)
        seeded.upsert_neighbor_link(link)

        neighbors = seeded.get_neighbors("rtr-01")
        assert len(neighbors) == 1  # Not duplicated

    def test_get_neighbors_empty(self, seeded):
        assert seeded.get_neighbors("nonexistent") == []

    def test_multiple_neighbors(self, seeded):
        seeded._store.add_device(PydanticDevice(
            id="sw-02", name="sw-02", device_type=DeviceType.switch,
            management_ip="10.0.0.3", vendor="cisco",
        ))
        for remote in ["sw-01", "sw-02"]:
            seeded.upsert_neighbor_link(NeighborLink(
                id=f"rtr-01:Gi0/0--{remote}:Gi0/48",
                device_id="rtr-01",
                local_interface=f"rtr-01:Gi0/0",
                remote_device=remote,
                remote_interface=f"{remote}:Gi0/48",
                protocol="lldp",
                sources=["lldp"],
                first_seen="", last_seen="", confidence=0.95,
            ))
        neighbors = seeded.get_neighbors("rtr-01")
        assert len(neighbors) == 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_neighbor_links.py -v`
Expected: FAIL (neighbors returns empty list — no table yet)

**Step 3: Write minimal implementation**

Add to `topology_store.py` — the `_create_tables` method (find it and add the new table):

```python
# Add to TopologyStore._create_tables() method body:
cursor.execute("""
    CREATE TABLE IF NOT EXISTS neighbor_links (
        id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        local_interface TEXT NOT NULL,
        remote_device TEXT NOT NULL,
        remote_interface TEXT NOT NULL,
        protocol TEXT NOT NULL,
        sources TEXT DEFAULT '[]',
        first_seen TEXT DEFAULT '',
        last_seen TEXT DEFAULT '',
        confidence REAL DEFAULT 0.5,
        UNIQUE(device_id, local_interface, remote_device, remote_interface)
    )
""")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_neighbor_device ON neighbor_links(device_id)")
```

Add methods to `TopologyStore`:

```python
def upsert_neighbor_link(self, link_id: str, device_id: str, local_interface: str,
                         remote_device: str, remote_interface: str, protocol: str,
                         sources: str = "[]", first_seen: str = "", last_seen: str = "",
                         confidence: float = 0.5) -> None:
    conn = self._get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO neighbor_links
            (id, device_id, local_interface, remote_device, remote_interface,
             protocol, sources, first_seen, last_seen, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (link_id, device_id, local_interface, remote_device, remote_interface,
              protocol, sources, first_seen, last_seen, confidence))
        conn.commit()
    finally:
        self._return_conn(conn)

def list_neighbor_links(self, device_id: str = None) -> list[dict]:
    conn = self._get_conn()
    try:
        if device_id:
            rows = conn.execute(
                "SELECT * FROM neighbor_links WHERE device_id = ?", (device_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM neighbor_links").fetchall()
        cols = ["id", "device_id", "local_interface", "remote_device",
                "remote_interface", "protocol", "sources", "first_seen",
                "last_seen", "confidence"]
        return [dict(zip(cols, row)) for row in rows]
    finally:
        self._return_conn(conn)
```

Update `SQLiteRepository` — replace the stub `upsert_neighbor_link` and `get_neighbors`:

```python
def upsert_neighbor_link(self, link: NeighborLink) -> NeighborLink:
    import json
    self._store.upsert_neighbor_link(
        link_id=link.id,
        device_id=link.device_id,
        local_interface=link.local_interface,
        remote_device=link.remote_device,
        remote_interface=link.remote_interface,
        protocol=link.protocol,
        sources=json.dumps(link.sources),
        first_seen=link.first_seen,
        last_seen=link.last_seen,
        confidence=link.confidence,
    )
    return link

def get_neighbors(self, device_id: str) -> list[NeighborLink]:
    import json
    rows = self._store.list_neighbor_links(device_id=device_id)
    return [
        NeighborLink(
            id=r["id"],
            device_id=r["device_id"],
            local_interface=r["local_interface"],
            remote_device=r["remote_device"],
            remote_interface=r["remote_interface"],
            protocol=r["protocol"],
            sources=json.loads(r["sources"]) if r["sources"] else [],
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            confidence=r["confidence"],
        )
        for r in rows
    ]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_neighbor_links.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/topology_store.py backend/src/network/repository/sqlite_repository.py backend/tests/test_neighbor_links.py
git commit -m "feat(repository): persist neighbor links in SQLite, stop importing from discovery_scheduler"
```

---

## Task 5: Topology Validation

**Files:**
- Create: `backend/src/network/repository/validation.py`
- Test: `backend/tests/test_topology_validation.py`

Detects duplicate IPs, subnet conflicts, missing interfaces, routing loops.

**Step 1: Write the failing test**

```python
# backend/tests/test_topology_validation.py
"""Tests for topology validation — duplicate IPs, subnet conflicts, missing interfaces."""
import pytest
from src.network.repository.validation import TopologyValidator
from src.network.repository.domain import Device, Interface, IPAddress, Route


class TestTopologyValidator:
    def test_detect_duplicate_ips(self):
        ips = [
            IPAddress(id="a:Gi0/0:10.0.0.1", ip="10.0.0.1", assigned_to="dev-a:Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
            IPAddress(id="b:Gi0/0:10.0.0.1", ip="10.0.0.1", assigned_to="dev-b:Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
        ]
        validator = TopologyValidator()
        issues = validator.check_duplicate_ips(ips)
        assert len(issues) == 1
        assert issues[0]["type"] == "duplicate_ip"
        assert issues[0]["ip"] == "10.0.0.1"

    def test_no_duplicate_ips(self):
        ips = [
            IPAddress(id="a:Gi0/0:10.0.0.1", ip="10.0.0.1", assigned_to="dev-a:Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
            IPAddress(id="b:Gi0/0:10.0.0.2", ip="10.0.0.2", assigned_to="dev-b:Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
        ]
        validator = TopologyValidator()
        issues = validator.check_duplicate_ips(ips)
        assert len(issues) == 0

    def test_detect_orphan_interfaces(self):
        """Interfaces referencing nonexistent devices."""
        devices = [
            Device(id="dev-a", hostname="dev-a", vendor="", model="", serial="",
                   device_type="ROUTER", site_id="", sources=[], first_seen="",
                   last_seen="", confidence=0.9),
        ]
        interfaces = [
            Interface(id="dev-a:Gi0/0", device_id="dev-a", name="Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
            Interface(id="dev-b:Gi0/0", device_id="dev-b", name="Gi0/0",
                      sources=[], first_seen="", last_seen="", confidence=0.9),
        ]
        validator = TopologyValidator()
        issues = validator.check_orphan_interfaces(devices, interfaces)
        assert len(issues) == 1
        assert issues[0]["interface_id"] == "dev-b:Gi0/0"

    def test_detect_subnet_overlap(self):
        """Two subnets with overlapping CIDRs."""
        from src.network.repository.domain import Subnet
        subnets = [
            Subnet(id="s1", cidr="10.0.0.0/24", sources=[], first_seen="", last_seen=""),
            Subnet(id="s2", cidr="10.0.0.0/25", sources=[], first_seen="", last_seen=""),
        ]
        validator = TopologyValidator()
        issues = validator.check_subnet_overlaps(subnets)
        assert len(issues) >= 1
        assert issues[0]["type"] == "subnet_overlap"

    def test_no_subnet_overlap(self):
        from src.network.repository.domain import Subnet
        subnets = [
            Subnet(id="s1", cidr="10.0.0.0/24", sources=[], first_seen="", last_seen=""),
            Subnet(id="s2", cidr="10.0.1.0/24", sources=[], first_seen="", last_seen=""),
        ]
        validator = TopologyValidator()
        issues = validator.check_subnet_overlaps(subnets)
        assert len(issues) == 0

    def test_full_validation(self):
        """Run all checks."""
        validator = TopologyValidator()
        report = validator.validate(
            devices=[],
            interfaces=[],
            ip_addresses=[],
            subnets=[],
            routes=[],
        )
        assert "issues" in report
        assert "issue_count" in report
        assert report["issue_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_topology_validation.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/network/repository/validation.py
"""Topology validation — detects data integrity issues."""
import ipaddress
from collections import defaultdict
from .domain import Device, Interface, IPAddress, Subnet, Route


class TopologyValidator:
    """Validates topology data for integrity issues."""

    def check_duplicate_ips(self, ip_addresses: list[IPAddress]) -> list[dict]:
        seen: dict[str, list[str]] = defaultdict(list)
        for ip in ip_addresses:
            seen[ip.ip].append(ip.assigned_to)

        issues = []
        for ip_str, assignees in seen.items():
            if len(assignees) > 1:
                issues.append({
                    "type": "duplicate_ip",
                    "severity": "critical",
                    "ip": ip_str,
                    "assigned_to": assignees,
                    "message": f"IP {ip_str} assigned to {len(assignees)} interfaces: {assignees}",
                })
        return issues

    def check_orphan_interfaces(self, devices: list[Device],
                                 interfaces: list[Interface]) -> list[dict]:
        device_ids = {d.id for d in devices}
        issues = []
        for iface in interfaces:
            if iface.device_id not in device_ids:
                issues.append({
                    "type": "orphan_interface",
                    "severity": "high",
                    "interface_id": iface.id,
                    "device_id": iface.device_id,
                    "message": f"Interface {iface.id} references nonexistent device {iface.device_id}",
                })
        return issues

    def check_subnet_overlaps(self, subnets: list[Subnet]) -> list[dict]:
        issues = []
        networks = []
        for s in subnets:
            try:
                networks.append((s.id, ipaddress.ip_network(s.cidr, strict=False)))
            except (ValueError, TypeError):
                continue

        for i in range(len(networks)):
            for j in range(i + 1, len(networks)):
                id_a, net_a = networks[i]
                id_b, net_b = networks[j]
                if net_a.overlaps(net_b) and net_a != net_b:
                    issues.append({
                        "type": "subnet_overlap",
                        "severity": "high",
                        "subnet_a": id_a,
                        "subnet_b": id_b,
                        "cidr_a": str(net_a),
                        "cidr_b": str(net_b),
                        "message": f"Subnets {id_a} ({net_a}) and {id_b} ({net_b}) overlap",
                    })
        return issues

    def validate(self, devices: list[Device], interfaces: list[Interface],
                 ip_addresses: list[IPAddress], subnets: list[Subnet],
                 routes: list[Route]) -> dict:
        issues = []
        issues.extend(self.check_duplicate_ips(ip_addresses))
        issues.extend(self.check_orphan_interfaces(devices, interfaces))
        issues.extend(self.check_subnet_overlaps(subnets))

        return {
            "issues": issues,
            "issue_count": len(issues),
            "critical": len([i for i in issues if i.get("severity") == "critical"]),
            "high": len([i for i in issues if i.get("severity") == "high"]),
            "medium": len([i for i in issues if i.get("severity") == "medium"]),
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_topology_validation.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/repository/validation.py backend/tests/test_topology_validation.py
git commit -m "feat(repository): topology validation — duplicate IPs, orphan interfaces, subnet overlaps"
```

---

## Task 6: Wire Repository Into Knowledge Graph

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`
- Test: `backend/tests/test_kg_uses_repository.py`

Replace direct `self.store.list_*` calls with repository calls. This is the migration bridge — KG still works but now reads through the repository.

**Step 1: Write the failing test**

```python
# backend/tests/test_kg_uses_repository.py
"""Test that KnowledgeGraph can be constructed with a TopologyRepository."""
import pytest
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device as PydanticDevice, DeviceType, Interface as PydanticInterface, Subnet


@pytest.fixture
def kg_with_repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = TopologyStore(db_path)
    repo = SQLiteRepository(store)

    # Seed data
    store.add_device(PydanticDevice(
        id="rtr-01", name="rtr-01", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco",
    ))
    store.add_device(PydanticDevice(
        id="sw-01", name="sw-01", device_type=DeviceType.switch,
        management_ip="10.0.0.2", vendor="cisco",
    ))
    store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30", gateway_ip="10.0.0.1"))
    store.add_interface(PydanticInterface(
        id="rtr-01:Gi0/0", device_id="rtr-01", name="Gi0/0", ip="10.0.0.1/30",
    ))
    store.add_interface(PydanticInterface(
        id="sw-01:Gi0/48", device_id="sw-01", name="Gi0/48", ip="10.0.0.2/30",
    ))

    kg = NetworkKnowledgeGraph(store)
    kg.repo = repo  # Attach repository
    kg.load_from_store()
    return kg, repo


class TestKGUsesRepository:
    def test_kg_has_repo(self, kg_with_repo):
        kg, repo = kg_with_repo
        assert kg.repo is not None

    def test_kg_still_builds_graph(self, kg_with_repo):
        kg, repo = kg_with_repo
        assert kg.graph.number_of_nodes() > 0

    def test_repo_can_read_devices(self, kg_with_repo):
        kg, repo = kg_with_repo
        devices = repo.get_devices()
        assert len(devices) == 2

    def test_repo_can_read_interfaces(self, kg_with_repo):
        kg, repo = kg_with_repo
        ifaces = repo.get_interfaces("rtr-01")
        assert len(ifaces) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_kg_uses_repository.py -v`
Expected: FAIL (KG doesn't have `repo` attribute by default)

**Step 3: Write minimal implementation**

Add to `NetworkKnowledgeGraph.__init__`:

```python
def __init__(self, store: TopologyStore):
    self.store = store
    self.graph = nx.MultiDiGraph()
    self.ip_resolver = IPResolver()
    self._device_index: dict[str, str] = {}
    self.repo = None  # Optional TopologyRepository — set externally for migration
```

No other changes needed for Task 6. The `repo` attribute is available but `load_from_store` still uses `self.store` directly. Incremental migration happens in Phase 2 when we swap individual `self.store.list_*` calls to `self.repo.get_*`.

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_kg_uses_repository.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/tests/test_kg_uses_repository.py
git commit -m "feat(repository): wire TopologyRepository into KnowledgeGraph as optional attribute"
```

---

## Task 7: Wire Repository Into API Endpoints

**Files:**
- Modify: `backend/src/api/network_endpoints.py`
- Test: `backend/tests/test_repository_api_wiring.py`

Create the repository at app startup and make it available to endpoints. Existing endpoints continue working — repository is additive.

**Step 1: Write the failing test**

```python
# backend/tests/test_repository_api_wiring.py
"""Test that API can access TopologyRepository."""
import pytest
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.domain import Device


class TestRepositoryAPIWiring:
    def test_sqlite_repository_instantiation(self, tmp_path):
        """Repository can be created from TopologyStore."""
        from src.network.topology_store import TopologyStore
        store = TopologyStore(str(tmp_path / "test.db"))
        repo = SQLiteRepository(store)
        assert repo is not None
        assert isinstance(repo.get_devices(), list)

    def test_repository_validation_endpoint_data(self, tmp_path):
        """Repository + validator produces a report."""
        from src.network.topology_store import TopologyStore
        from src.network.repository.validation import TopologyValidator

        store = TopologyStore(str(tmp_path / "test.db"))
        repo = SQLiteRepository(store)
        validator = TopologyValidator()

        devices = repo.get_devices()
        report = validator.validate(
            devices=devices,
            interfaces=[],
            ip_addresses=[],
            subnets=[],
            routes=[],
        )
        assert report["issue_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_repository_api_wiring.py -v`
Expected: Should PASS if Tasks 1-5 are complete. If not, fix import paths.

**Step 3: No new code needed — this validates integration**

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_repository_api_wiring.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/tests/test_repository_api_wiring.py
git commit -m "test(repository): validate API wiring with SQLiteRepository"
```

---

## Task 8: Run Full Test Suite — Verify No Regressions

**Files:** None (verification only)

**Step 1: Run the existing test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short -x 2>&1 | tail -50`
Expected: All existing tests pass. No regressions from the repository layer.

**Step 2: Run the new repository tests**

Run: `cd backend && python -m pytest tests/test_repository_domain.py tests/test_repository_interface.py tests/test_sqlite_repository.py tests/test_neighbor_links.py tests/test_topology_validation.py tests/test_kg_uses_repository.py tests/test_repository_api_wiring.py -v`
Expected: ALL PASS

**Step 3: Commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: resolve test regressions from repository layer introduction"
```

---

## Summary

| Task | What it does | Files created/modified |
|------|--------------|-----------------------|
| 1 | Domain models (Device, Interface, IPAddress, etc.) | `repository/domain.py` |
| 2 | Abstract TopologyRepository interface | `repository/interface.py` |
| 3 | SQLiteRepository (wraps TopologyStore) | `repository/sqlite_repository.py` |
| 4 | Persist neighbor links (stop importing from scheduler) | `topology_store.py`, `sqlite_repository.py` |
| 5 | Topology validation (duplicate IPs, overlaps) | `repository/validation.py` |
| 6 | Wire repository into KnowledgeGraph | `knowledge_graph.py` |
| 7 | Wire repository into API endpoints | Test validates integration |
| 8 | Full regression test | No new files |

**After Phase 1 is complete:**
- Repository abstraction exists and is tested
- Neighbor links are persisted in SQLite
- Topology validation catches data integrity issues
- Existing system works unchanged
- Ready for Phase 2: Neo4j integration (behind the same repository interface)
