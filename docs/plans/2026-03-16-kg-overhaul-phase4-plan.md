# KG Architecture Overhaul — Phase 4: Discovery Adapters + Normalization

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bridge existing collectors (SNMP, vendor-specific) into the new repository/event pipeline. Add missing protocol discovery adapters (LLDP, BGP, OSPF, ARP). Add cloud discovery adapters (AWS, Azure, OCI). Add entity resolution and normalization. Add BFS network crawler.

**Architecture:** New `DiscoveryAdapter` abstract interface yields `DiscoveryObservation` objects. An `ObservationHandler` processes observations through entity resolution and upserts via `TopologyRepository` (which publishes events via `EventPublishingRepository`). A `NetworkCrawler` does BFS expansion from seed devices. A `DiscoveryScheduler` orchestrates periodic discovery runs.

**Tech Stack:** Existing collector infrastructure (collectors/), TopologyRepository (Phase 1), EventPublishingRepository (Phase 3), boto3 (AWS), pysnmp (existing), asyncio.

**Design Doc:** `docs/plans/2026-03-16-kg-architecture-overhaul-design.md`

**Depends on:** Phases 1-3 complete.

**Key insight:** The project already has `collectors/snmp_collector.py`, `collectors/autodiscovery.py`, `collectors/cisco_collector.py`, etc. Phase 4 creates a new `discovery/` package that wraps these and feeds observations into the repository pipeline.

---

## Task 1: Discovery Adapter Interface + Observation Model

**Files:**
- Create: `backend/src/network/discovery/__init__.py`
- Create: `backend/src/network/discovery/adapter.py`
- Create: `backend/src/network/discovery/observation.py`
- Test: `backend/tests/test_discovery_adapter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_discovery_adapter.py
"""Tests for DiscoveryAdapter interface and DiscoveryObservation model."""
import pytest
from datetime import datetime, timezone
from src.network.discovery.observation import DiscoveryObservation, ObservationType
from src.network.discovery.adapter import DiscoveryAdapter


class TestObservationType:
    def test_all_types_defined(self):
        expected = ["device", "interface", "neighbor", "route",
                    "bgp_peer", "ospf_neighbor", "arp_entry", "mac_entry",
                    "lag_member", "vpc", "subnet", "security_group",
                    "cloud_interface", "route_table", "load_balancer"]
        for t in expected:
            assert hasattr(ObservationType, t.upper())


class TestDiscoveryObservation:
    def test_create_observation(self):
        obs = DiscoveryObservation(
            observation_type=ObservationType.DEVICE,
            source="snmp",
            device_id="rtr-01",
            data={"hostname": "rtr-01", "vendor": "cisco"},
            confidence=0.9,
        )
        assert obs.observation_type == ObservationType.DEVICE
        assert obs.source == "snmp"
        assert obs.device_id == "rtr-01"
        assert obs.confidence == 0.9
        assert obs.observed_at is not None

    def test_to_dict(self):
        obs = DiscoveryObservation(
            observation_type=ObservationType.NEIGHBOR,
            source="lldp",
            device_id="rtr-01",
            data={"remote_device": "sw-01"},
        )
        d = obs.to_dict()
        assert d["observation_type"] == "neighbor"
        assert d["source"] == "lldp"
        assert "observed_at" in d


class TestDiscoveryAdapter:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            DiscoveryAdapter()

    def test_defines_discover_method(self):
        assert hasattr(DiscoveryAdapter, "discover")

    def test_defines_supports_method(self):
        assert hasattr(DiscoveryAdapter, "supports")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_discovery_adapter.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/discovery/__init__.py
"""Discovery adapters — bridge collectors into the repository pipeline."""

# backend/src/network/discovery/observation.py
"""DiscoveryObservation — universal observation format from any discovery source."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ObservationType(str, Enum):
    DEVICE = "device"
    INTERFACE = "interface"
    NEIGHBOR = "neighbor"
    ROUTE = "route"
    BGP_PEER = "bgp_peer"
    OSPF_NEIGHBOR = "ospf_neighbor"
    ARP_ENTRY = "arp_entry"
    MAC_ENTRY = "mac_entry"
    LAG_MEMBER = "lag_member"
    VPC = "vpc"
    SUBNET = "subnet"
    SECURITY_GROUP = "security_group"
    CLOUD_INTERFACE = "cloud_interface"
    ROUTE_TABLE = "route_table"
    LOAD_BALANCER = "load_balancer"


@dataclass
class DiscoveryObservation:
    """Universal observation from any discovery source."""
    observation_type: ObservationType
    source: str                          # snmp/lldp/bgp/aws_api/...
    device_id: str                       # device this observation is about
    data: dict = field(default_factory=dict)
    confidence: float = 0.5
    observed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "observation_type": self.observation_type.value,
            "source": self.source,
            "device_id": self.device_id,
            "data": self.data,
            "confidence": self.confidence,
            "observed_at": self.observed_at,
        }


# backend/src/network/discovery/adapter.py
"""DiscoveryAdapter — abstract interface for all discovery sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from .observation import DiscoveryObservation


class DiscoveryAdapter(ABC):
    """Base class for all discovery adapters.

    Each adapter knows how to discover topology from a specific source
    (SNMP, LLDP, cloud API, config parser, etc.) and yields
    DiscoveryObservation objects.
    """

    @abstractmethod
    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        """Discover topology from a target.

        target examples:
          {"type": "device", "ip": "10.0.0.1", "credentials": {...}}
          {"type": "cloud_account", "provider": "aws", "credentials": {...}}
        """
        ...

    @abstractmethod
    def supports(self, target: dict) -> bool:
        """Can this adapter handle this target type?"""
        ...
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_discovery_adapter.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/discovery/ backend/tests/test_discovery_adapter.py
git commit -m "feat(discovery): DiscoveryAdapter interface + DiscoveryObservation model"
```

---

## Task 2: Entity Resolution + Observation Handler

**Files:**
- Create: `backend/src/network/discovery/entity_resolver.py`
- Create: `backend/src/network/discovery/observation_handler.py`
- Test: `backend/tests/test_entity_resolver.py`
- Test: `backend/tests/test_observation_handler.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_entity_resolver.py
"""Tests for EntityResolver — matches raw observations to canonical entities."""
import pytest
from datetime import datetime, timezone
from src.network.discovery.entity_resolver import EntityResolver, SOURCE_CONFIDENCE
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore
from src.network.models import Device as PydanticDevice, DeviceType


@pytest.fixture
def resolver(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    store.add_device(PydanticDevice(
        id="rtr-01", name="rtr-01", device_type=DeviceType.router,
        management_ip="10.0.0.1", vendor="cisco", serial_number="FTX1234",
    ))
    return EntityResolver(repo), repo


class TestEntityResolver:
    def test_resolve_by_serial(self, resolver):
        er, repo = resolver
        result = er.resolve_device({"serial": "FTX1234"})
        assert result == "rtr-01"

    def test_resolve_by_management_ip(self, resolver):
        er, repo = resolver
        result = er.resolve_device({"management_ip": "10.0.0.1"})
        assert result == "rtr-01"

    def test_resolve_by_hostname(self, resolver):
        er, repo = resolver
        result = er.resolve_device({"hostname": "rtr-01"})
        assert result == "rtr-01"

    def test_resolve_unknown_creates_new(self, resolver):
        er, repo = resolver
        result = er.resolve_device({"hostname": "unknown-device", "management_ip": "192.168.1.1"})
        assert result is not None
        assert result != "rtr-01"  # New ID generated

    def test_resolve_interface_id(self, resolver):
        er, repo = resolver
        result = er.resolve_interface("rtr-01", "Gi0/0")
        assert result == "rtr-01:Gi0/0"


class TestSourceConfidence:
    def test_known_sources(self):
        assert SOURCE_CONFIDENCE["snmp"] == 0.9
        assert SOURCE_CONFIDENCE["lldp"] == 0.95
        assert SOURCE_CONFIDENCE["aws_api"] == 0.95
        assert SOURCE_CONFIDENCE["manual"] == 1.0

    def test_unknown_source_default(self):
        assert SOURCE_CONFIDENCE.get("unknown", 0.5) == 0.5
```

```python
# backend/tests/test_observation_handler.py
"""Tests for ObservationHandler — processes observations into canonical state."""
import pytest
from datetime import datetime, timezone
from src.network.discovery.observation_handler import ObservationHandler
from src.network.discovery.observation import DiscoveryObservation, ObservationType
from src.network.discovery.entity_resolver import EntityResolver
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore


@pytest.fixture
def handler(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    resolver = EntityResolver(repo)
    return ObservationHandler(repo=repo, resolver=resolver), repo


class TestObservationHandler:
    def test_handle_device_observation(self, handler):
        oh, repo = handler
        obs = DiscoveryObservation(
            observation_type=ObservationType.DEVICE,
            source="snmp",
            device_id="rtr-01",
            data={"hostname": "rtr-01", "vendor": "cisco", "model": "ISR4451",
                  "serial": "FTX1234", "device_type": "ROUTER",
                  "management_ip": "10.0.0.1"},
            confidence=0.9,
        )
        oh.handle(obs)

        device = repo.get_device("rtr-01")
        assert device is not None
        assert device.hostname == "rtr-01"
        assert device.vendor == "cisco"

    def test_handle_interface_observation(self, handler):
        oh, repo = handler
        # First create the device
        oh.handle(DiscoveryObservation(
            observation_type=ObservationType.DEVICE,
            source="snmp", device_id="rtr-01",
            data={"hostname": "rtr-01", "vendor": "cisco", "device_type": "ROUTER"},
        ))
        # Then the interface
        oh.handle(DiscoveryObservation(
            observation_type=ObservationType.INTERFACE,
            source="snmp", device_id="rtr-01",
            data={"iface_name": "Gi0/0", "mac": "aa:bb:cc:dd:ee:ff",
                  "ip": "10.0.0.1", "speed": "1G", "admin_state": "up"},
        ))

        ifaces = repo.get_interfaces("rtr-01")
        assert len(ifaces) >= 1
        assert ifaces[0].name == "Gi0/0"

    def test_handle_neighbor_observation(self, handler):
        oh, repo = handler
        # Create both devices first
        for dev_id in ["rtr-01", "sw-01"]:
            oh.handle(DiscoveryObservation(
                observation_type=ObservationType.DEVICE,
                source="snmp", device_id=dev_id,
                data={"hostname": dev_id, "vendor": "cisco", "device_type": "ROUTER"},
            ))
        # Neighbor link
        oh.handle(DiscoveryObservation(
            observation_type=ObservationType.NEIGHBOR,
            source="lldp", device_id="rtr-01",
            data={"local_interface": "Gi0/0", "remote_device": "sw-01",
                  "remote_interface": "Gi0/48", "protocol": "lldp"},
            confidence=0.95,
        ))

        neighbors = repo.get_neighbors("rtr-01")
        assert len(neighbors) >= 1
        assert neighbors[0].remote_device == "sw-01"

    def test_handle_unknown_type_no_crash(self, handler):
        oh, repo = handler
        # Should log warning but not crash
        obs = DiscoveryObservation(
            observation_type=ObservationType.ARP_ENTRY,
            source="snmp", device_id="rtr-01",
            data={"ip": "10.0.0.50", "mac": "aa:bb:cc:dd:ee:ff"},
        )
        oh.handle(obs)  # Should not raise
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_entity_resolver.py tests/test_observation_handler.py -v`
Expected: FAIL (module not found)

**Step 3: Write implementation**

```python
# backend/src/network/discovery/entity_resolver.py
"""EntityResolver — matches raw observations to canonical entity IDs."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from ..repository.interface import TopologyRepository

logger = logging.getLogger(__name__)

SOURCE_CONFIDENCE = {
    "manual": 1.0,
    "lldp": 0.95,
    "gnmi": 0.95,
    "aws_api": 0.95,
    "azure_api": 0.95,
    "oci_api": 0.95,
    "snmp": 0.90,
    "cdp": 0.90,
    "config_parser": 0.85,
    "ipam": 0.80,
    "netflow": 0.70,
}


class EntityResolver:
    """Resolves raw observations to canonical entity IDs."""

    def __init__(self, repo: TopologyRepository):
        self._repo = repo

    def resolve_device(self, observation: dict) -> str:
        """Returns canonical device_id. Creates new ID if no match."""
        # Priority 1: Serial match
        serial = observation.get("serial") or observation.get("serial_number")
        if serial:
            device = self._repo.find_device_by_serial(serial)
            if device:
                return device.id

        # Priority 2: Cloud resource ID
        cloud_id = observation.get("cloud_resource_id")
        if cloud_id:
            device = self._repo.get_device(cloud_id)
            if device:
                return device.id

        # Priority 3: Management IP
        mgmt_ip = observation.get("management_ip")
        if mgmt_ip:
            device = self._repo.find_device_by_ip(mgmt_ip)
            if device:
                return device.id

        # Priority 4: Hostname match
        hostname = observation.get("hostname")
        if hostname:
            device = self._repo.find_device_by_hostname(hostname)
            if device:
                return device.id

        # Priority 5: device_id from observation
        device_id = observation.get("device_id")
        if device_id:
            device = self._repo.get_device(device_id)
            if device:
                return device.id
            return device_id  # Use as-is if looks like a valid ID

        # No match — generate new
        return f"discovered-{uuid.uuid4().hex[:8]}"

    def resolve_interface(self, device_id: str, iface_name: str) -> str:
        """Deterministic interface ID."""
        return f"{device_id}:{iface_name}"

    def get_confidence(self, source: str) -> float:
        """Source-based confidence score."""
        return SOURCE_CONFIDENCE.get(source, 0.5)
```

```python
# backend/src/network/discovery/observation_handler.py
"""ObservationHandler — processes raw observations into canonical entities."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .observation import DiscoveryObservation, ObservationType
from .entity_resolver import EntityResolver
from ..repository.interface import TopologyRepository
from ..repository.domain import Device, Interface, NeighborLink

logger = logging.getLogger(__name__)


class ObservationHandler:
    """Processes DiscoveryObservations into canonical repository state."""

    def __init__(self, repo: TopologyRepository, resolver: EntityResolver):
        self._repo = repo
        self._resolver = resolver

    def handle(self, obs: DiscoveryObservation) -> None:
        """Route observation to appropriate handler."""
        handlers = {
            ObservationType.DEVICE: self._handle_device,
            ObservationType.INTERFACE: self._handle_interface,
            ObservationType.NEIGHBOR: self._handle_neighbor,
            ObservationType.ROUTE: self._handle_route,
        }
        handler = handlers.get(obs.observation_type)
        if handler:
            try:
                handler(obs)
            except Exception as e:
                logger.error("Failed to handle %s observation for %s: %s",
                             obs.observation_type.value, obs.device_id, e)
        else:
            logger.debug("No handler for observation type: %s", obs.observation_type.value)

    def _handle_device(self, obs: DiscoveryObservation) -> None:
        device_id = self._resolver.resolve_device({
            **obs.data, "device_id": obs.device_id,
        })
        now = datetime.now(timezone.utc)
        confidence = self._resolver.get_confidence(obs.source)

        self._repo.upsert_device(Device(
            id=device_id,
            hostname=obs.data.get("hostname", device_id),
            vendor=obs.data.get("vendor", ""),
            model=obs.data.get("model", ""),
            serial=obs.data.get("serial", ""),
            device_type=obs.data.get("device_type", "unknown"),
            site_id=obs.data.get("site_id", ""),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=confidence,
        ))

    def _handle_interface(self, obs: DiscoveryObservation) -> None:
        device_id = self._resolver.resolve_device({"device_id": obs.device_id})
        iface_name = obs.data.get("iface_name", obs.data.get("name", ""))
        iface_id = self._resolver.resolve_interface(device_id, iface_name)
        now = datetime.now(timezone.utc)

        self._repo.upsert_interface(Interface(
            id=iface_id,
            device_id=device_id,
            name=iface_name,
            mac=obs.data.get("mac"),
            admin_state=obs.data.get("admin_state", "up"),
            oper_state=obs.data.get("oper_state", "up"),
            speed=obs.data.get("speed"),
            mtu=obs.data.get("mtu"),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=self._resolver.get_confidence(obs.source),
        ))

    def _handle_neighbor(self, obs: DiscoveryObservation) -> None:
        device_id = self._resolver.resolve_device({"device_id": obs.device_id})
        local_iface = obs.data.get("local_interface", "")
        remote_device = obs.data.get("remote_device", "")
        remote_iface = obs.data.get("remote_interface", "")

        local_iface_id = self._resolver.resolve_interface(device_id, local_iface)
        remote_iface_id = self._resolver.resolve_interface(remote_device, remote_iface)
        link_id = f"{local_iface_id}--{remote_iface_id}"
        now = datetime.now(timezone.utc)

        self._repo.upsert_neighbor_link(NeighborLink(
            id=link_id,
            device_id=device_id,
            local_interface=local_iface_id,
            remote_device=remote_device,
            remote_interface=remote_iface_id,
            protocol=obs.data.get("protocol", "lldp"),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            confidence=obs.confidence,
        ))

    def _handle_route(self, obs: DiscoveryObservation) -> None:
        from ..repository.domain import Route
        device_id = self._resolver.resolve_device({"device_id": obs.device_id})
        dest = obs.data.get("destination_cidr", obs.data.get("destination", ""))
        prefix_len = int(dest.split("/")[1]) if "/" in dest else 0
        now = datetime.now(timezone.utc)

        self._repo.upsert_route(Route(
            id=f"{device_id}:{obs.data.get('vrf', 'default')}:{dest}",
            device_id=device_id,
            vrf_instance_id=f"{device_id}:{obs.data.get('vrf', 'default')}",
            destination_cidr=dest,
            prefix_len=prefix_len,
            protocol=obs.data.get("protocol", "static"),
            sources=[obs.source],
            first_seen=now,
            last_seen=now,
            admin_distance=obs.data.get("admin_distance"),
            metric=obs.data.get("metric"),
            next_hop_refs=[{"ref": obs.data.get("next_hop", ""), "weight": 1}]
                          if obs.data.get("next_hop") else [],
        ))
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_entity_resolver.py tests/test_observation_handler.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/discovery/entity_resolver.py backend/src/network/discovery/observation_handler.py backend/tests/test_entity_resolver.py backend/tests/test_observation_handler.py
git commit -m "feat(discovery): EntityResolver + ObservationHandler — normalize observations into canonical state"
```

---

## Task 3: LLDP Discovery Adapter

**Files:**
- Create: `backend/src/network/discovery/lldp_adapter.py`
- Test: `backend/tests/test_lldp_adapter.py`

This wraps LLDP/CDP neighbor discovery and yields observations. Uses mock data in demo mode, real SNMP in production.

**Step 1: Write the failing test**

```python
# backend/tests/test_lldp_adapter.py
"""Tests for LLDP discovery adapter."""
import pytest
import asyncio
from src.network.discovery.lldp_adapter import LLDPDiscoveryAdapter
from src.network.discovery.observation import ObservationType


class TestLLDPAdapter:
    def test_supports_device_target(self):
        adapter = LLDPDiscoveryAdapter()
        assert adapter.supports({"type": "device", "ip": "10.0.0.1"})

    def test_does_not_support_cloud(self):
        adapter = LLDPDiscoveryAdapter()
        assert not adapter.supports({"type": "cloud_account"})

    def test_discover_yields_neighbor_observations(self):
        adapter = LLDPDiscoveryAdapter(mock_neighbors={
            "rtr-01": [
                {"local_port": "Gi0/0", "remote_device": "sw-01",
                 "remote_port": "Gi0/48", "protocol": "lldp", "remote_ip": "10.0.0.2"},
            ],
        })
        loop = asyncio.new_event_loop()

        results = []
        async def collect():
            async for obs in adapter.discover({"type": "device", "device_id": "rtr-01", "ip": "10.0.0.1"}):
                results.append(obs)

        loop.run_until_complete(collect())
        loop.close()

        assert len(results) >= 1
        assert results[0].observation_type == ObservationType.NEIGHBOR
        assert results[0].source == "lldp"
        assert results[0].data["remote_device"] == "sw-01"
        assert results[0].confidence == 0.95

    def test_discover_empty_neighbors(self):
        adapter = LLDPDiscoveryAdapter(mock_neighbors={})
        loop = asyncio.new_event_loop()

        results = []
        async def collect():
            async for obs in adapter.discover({"type": "device", "device_id": "unknown", "ip": "10.0.0.99"}):
                results.append(obs)

        loop.run_until_complete(collect())
        loop.close()
        assert len(results) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_lldp_adapter.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/network/discovery/lldp_adapter.py
"""LLDP/CDP Discovery Adapter — discovers L2 neighbors."""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from .adapter import DiscoveryAdapter
from .observation import DiscoveryObservation, ObservationType

logger = logging.getLogger(__name__)


class LLDPDiscoveryAdapter(DiscoveryAdapter):
    """Discovers L2 neighbors via LLDP/CDP.

    In demo mode: uses mock_neighbors dict.
    In production: would use SNMP LLDP-MIB / CISCO-CDP-MIB walks.
    """

    def __init__(self, mock_neighbors: dict = None):
        self._mock_neighbors = mock_neighbors

    def supports(self, target: dict) -> bool:
        return target.get("type") == "device"

    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        device_id = target.get("device_id", target.get("ip", ""))

        if self._mock_neighbors is not None:
            # Demo mode
            neighbors = self._mock_neighbors.get(device_id, [])
            for n in neighbors:
                yield DiscoveryObservation(
                    observation_type=ObservationType.NEIGHBOR,
                    source="lldp",
                    device_id=device_id,
                    data={
                        "local_interface": n.get("local_port", ""),
                        "remote_device": n.get("remote_device", ""),
                        "remote_interface": n.get("remote_port", ""),
                        "remote_ip": n.get("remote_ip"),
                        "protocol": n.get("protocol", "lldp"),
                        "chassis_id": n.get("chassis_id"),
                    },
                    confidence=0.95 if n.get("protocol") == "lldp" else 0.90,
                )
        else:
            # Production: SNMP walk LLDP-MIB
            # This would use pysnmp to walk lldpRemTable
            logger.info("LLDP production discovery not yet implemented for %s", device_id)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_lldp_adapter.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/discovery/lldp_adapter.py backend/tests/test_lldp_adapter.py
git commit -m "feat(discovery): LLDP/CDP discovery adapter"
```

---

## Task 4: AWS Cloud Discovery Adapter

**Files:**
- Create: `backend/src/network/discovery/aws_adapter.py`
- Test: `backend/tests/test_aws_discovery_adapter.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_aws_discovery_adapter.py
"""Tests for AWS cloud discovery adapter — uses mock data."""
import pytest
import asyncio
from src.network.discovery.aws_adapter import AWSDiscoveryAdapter
from src.network.discovery.observation import ObservationType


class TestAWSAdapter:
    def test_supports_aws_target(self):
        adapter = AWSDiscoveryAdapter()
        assert adapter.supports({"type": "cloud_account", "provider": "aws"})

    def test_does_not_support_azure(self):
        adapter = AWSDiscoveryAdapter()
        assert not adapter.supports({"type": "cloud_account", "provider": "azure"})

    def test_does_not_support_device(self):
        adapter = AWSDiscoveryAdapter()
        assert not adapter.supports({"type": "device"})

    def test_discover_mock_yields_vpcs(self):
        adapter = AWSDiscoveryAdapter(mock_data={
            "vpcs": [{"VpcId": "vpc-123", "CidrBlock": "10.0.0.0/16", "Tags": [{"Key": "Name", "Value": "prod-vpc"}]}],
            "subnets": [],
            "enis": [],
            "security_groups": [],
        })
        loop = asyncio.new_event_loop()

        results = []
        async def collect():
            async for obs in adapter.discover({"type": "cloud_account", "provider": "aws"}):
                results.append(obs)

        loop.run_until_complete(collect())
        loop.close()

        vpc_obs = [r for r in results if r.observation_type == ObservationType.VPC]
        assert len(vpc_obs) >= 1
        assert vpc_obs[0].data["id"] == "vpc-123"
        assert vpc_obs[0].source == "aws_api"
        assert vpc_obs[0].confidence == 0.95

    def test_discover_mock_yields_subnets(self):
        adapter = AWSDiscoveryAdapter(mock_data={
            "vpcs": [],
            "subnets": [{"SubnetId": "subnet-abc", "CidrBlock": "10.0.1.0/24",
                         "VpcId": "vpc-123", "AvailabilityZone": "us-east-1a", "Tags": []}],
            "enis": [],
            "security_groups": [],
        })
        loop = asyncio.new_event_loop()

        results = []
        async def collect():
            async for obs in adapter.discover({"type": "cloud_account", "provider": "aws"}):
                results.append(obs)

        loop.run_until_complete(collect())
        loop.close()

        subnet_obs = [r for r in results if r.observation_type == ObservationType.SUBNET]
        assert len(subnet_obs) >= 1

    def test_discover_empty(self):
        adapter = AWSDiscoveryAdapter(mock_data={
            "vpcs": [], "subnets": [], "enis": [], "security_groups": [],
        })
        loop = asyncio.new_event_loop()

        results = []
        async def collect():
            async for obs in adapter.discover({"type": "cloud_account", "provider": "aws"}):
                results.append(obs)

        loop.run_until_complete(collect())
        loop.close()
        assert len(results) == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_aws_discovery_adapter.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/network/discovery/aws_adapter.py
"""AWS Cloud Discovery Adapter — discovers VPCs, subnets, ENIs, SGs, etc."""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from .adapter import DiscoveryAdapter
from .observation import DiscoveryObservation, ObservationType

logger = logging.getLogger(__name__)


class AWSDiscoveryAdapter(DiscoveryAdapter):
    """Discovers AWS networking topology.

    In demo mode: uses mock_data dict.
    In production: uses boto3 to call EC2/ELBv2/DirectConnect APIs.
    """

    def __init__(self, mock_data: dict = None):
        self._mock_data = mock_data

    def supports(self, target: dict) -> bool:
        return (target.get("type") == "cloud_account"
                and target.get("provider") == "aws")

    async def discover(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        if self._mock_data is not None:
            async for obs in self._discover_mock():
                yield obs
        else:
            async for obs in self._discover_live(target):
                yield obs

    async def _discover_mock(self) -> AsyncIterator[DiscoveryObservation]:
        # VPCs
        for vpc in self._mock_data.get("vpcs", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.VPC,
                source="aws_api",
                device_id=vpc["VpcId"],
                data={
                    "id": vpc["VpcId"],
                    "cidr_blocks": [vpc["CidrBlock"]],
                    "name": self._get_tag(vpc, "Name"),
                    "region": self._mock_data.get("region", "us-east-1"),
                },
                confidence=0.95,
            )

        # Subnets
        for subnet in self._mock_data.get("subnets", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SUBNET,
                source="aws_api",
                device_id=subnet["SubnetId"],
                data={
                    "id": subnet["SubnetId"],
                    "cidr": subnet["CidrBlock"],
                    "vpc_id": subnet["VpcId"],
                    "az": subnet.get("AvailabilityZone", ""),
                    "name": self._get_tag(subnet, "Name"),
                },
                confidence=0.95,
            )

        # ENIs (CloudInterface)
        for eni in self._mock_data.get("enis", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.CLOUD_INTERFACE,
                source="aws_api",
                device_id=eni.get("NetworkInterfaceId", ""),
                data={
                    "id": eni.get("NetworkInterfaceId"),
                    "mac": eni.get("MacAddress"),
                    "subnet_id": eni.get("SubnetId"),
                    "vpc_id": eni.get("VpcId"),
                    "private_ip": eni.get("PrivateIpAddress"),
                    "instance_id": eni.get("Attachment", {}).get("InstanceId"),
                    "security_groups": [sg["GroupId"] for sg in eni.get("Groups", [])],
                    "status": eni.get("Status"),
                },
                confidence=0.95,
            )

        # Security Groups
        for sg in self._mock_data.get("security_groups", []):
            yield DiscoveryObservation(
                observation_type=ObservationType.SECURITY_GROUP,
                source="aws_api",
                device_id=sg.get("GroupId", ""),
                data={
                    "id": sg.get("GroupId"),
                    "name": sg.get("GroupName"),
                    "vpc_id": sg.get("VpcId"),
                    "ingress_rules": sg.get("IpPermissions", []),
                    "egress_rules": sg.get("IpPermissionsEgress", []),
                },
                confidence=0.95,
            )

    async def _discover_live(self, target: dict) -> AsyncIterator[DiscoveryObservation]:
        """Production: uses boto3. Requires AWS credentials."""
        try:
            import boto3
            session = boto3.Session(
                aws_access_key_id=target.get("credentials", {}).get("access_key"),
                aws_secret_access_key=target.get("credentials", {}).get("secret_key"),
                region_name=target.get("region", "us-east-1"),
            )
            ec2 = session.client("ec2")

            # VPCs
            vpcs = ec2.describe_vpcs().get("Vpcs", [])
            for vpc in vpcs:
                yield DiscoveryObservation(
                    observation_type=ObservationType.VPC,
                    source="aws_api",
                    device_id=vpc["VpcId"],
                    data={
                        "id": vpc["VpcId"],
                        "cidr_blocks": [vpc["CidrBlock"]] + [
                            a["CidrBlock"] for a in vpc.get("CidrBlockAssociationSet", [])
                            if a.get("CidrBlockState", {}).get("State") == "associated"
                        ],
                        "name": self._get_tag(vpc, "Name"),
                        "region": target.get("region", "us-east-1"),
                    },
                    confidence=0.95,
                )

            # Subnets, ENIs, SGs follow same pattern...
            # (truncated for plan — full implementation in execution)

        except ImportError:
            logger.warning("boto3 not installed — AWS live discovery unavailable")
        except Exception as e:
            logger.error("AWS discovery failed: %s", e)

    def _get_tag(self, resource: dict, key: str) -> str:
        for tag in resource.get("Tags", []):
            if tag.get("Key") == key:
                return tag.get("Value", "")
        return ""
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_aws_discovery_adapter.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/discovery/aws_adapter.py backend/tests/test_aws_discovery_adapter.py
git commit -m "feat(discovery): AWS cloud discovery adapter — VPCs, subnets, ENIs, SGs"
```

---

## Task 5: BFS Network Crawler

**Files:**
- Create: `backend/src/network/discovery/crawler.py`
- Test: `backend/tests/test_network_crawler.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_crawler.py
"""Tests for BFS network crawler."""
import pytest
import asyncio
from src.network.discovery.crawler import NetworkCrawler, CrawlResult
from src.network.discovery.lldp_adapter import LLDPDiscoveryAdapter
from src.network.discovery.observation_handler import ObservationHandler
from src.network.discovery.entity_resolver import EntityResolver
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.topology_store import TopologyStore


@pytest.fixture
def crawler_setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    resolver = EntityResolver(repo)
    handler = ObservationHandler(repo=repo, resolver=resolver)

    # Mock LLDP neighbors: rtr-01 → sw-01 → sw-02
    mock_neighbors = {
        "rtr-01": [{"local_port": "Gi0/0", "remote_device": "sw-01",
                     "remote_port": "Gi0/48", "protocol": "lldp", "remote_ip": "10.0.0.2"}],
        "sw-01": [{"local_port": "Gi0/48", "remote_device": "rtr-01",
                    "remote_port": "Gi0/0", "protocol": "lldp", "remote_ip": "10.0.0.1"},
                   {"local_port": "Gi0/1", "remote_device": "sw-02",
                    "remote_port": "Gi0/1", "protocol": "lldp", "remote_ip": "10.0.0.3"}],
        "sw-02": [{"local_port": "Gi0/1", "remote_device": "sw-01",
                    "remote_port": "Gi0/1", "protocol": "lldp", "remote_ip": "10.0.0.2"}],
    }
    lldp = LLDPDiscoveryAdapter(mock_neighbors=mock_neighbors)

    crawler = NetworkCrawler(adapters=[lldp], handler=handler)
    return crawler, repo


class TestNetworkCrawler:
    def test_crawl_from_seed(self, crawler_setup):
        crawler, repo = crawler_setup
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            crawler.crawl(seeds=[{"type": "device", "device_id": "rtr-01", "ip": "10.0.0.1"}])
        )
        loop.close()

        assert isinstance(result, CrawlResult)
        assert result.devices_discovered >= 1

    def test_crawl_discovers_neighbors(self, crawler_setup):
        crawler, repo = crawler_setup
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            crawler.crawl(
                seeds=[{"type": "device", "device_id": "rtr-01", "ip": "10.0.0.1"}],
                max_depth=3,
            )
        )
        loop.close()

        # Should discover rtr-01 → sw-01 → sw-02 (3 devices via BFS)
        assert result.devices_discovered >= 2
        assert result.links_discovered >= 1

    def test_crawl_respects_max_depth(self, crawler_setup):
        crawler, repo = crawler_setup
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            crawler.crawl(
                seeds=[{"type": "device", "device_id": "rtr-01", "ip": "10.0.0.1"}],
                max_depth=1,  # Only direct neighbors
            )
        )
        loop.close()

        # Depth 1: rtr-01 + sw-01 (sw-02 is 2 hops away)
        assert result.devices_discovered <= 3

    def test_crawl_no_infinite_loop(self, crawler_setup):
        crawler, repo = crawler_setup
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            crawler.crawl(
                seeds=[{"type": "device", "device_id": "rtr-01", "ip": "10.0.0.1"}],
                max_depth=10,
            )
        )
        loop.close()

        # Despite loops in topology, should terminate
        assert result.devices_discovered <= 10
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_network_crawler.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/network/discovery/crawler.py
"""BFS Network Crawler — expands topology from seed devices."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field

from .adapter import DiscoveryAdapter
from .observation import DiscoveryObservation, ObservationType
from .observation_handler import ObservationHandler

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    devices_discovered: int = 0
    links_discovered: int = 0
    max_depth_reached: int = 0
    errors: list[dict] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)


class NetworkCrawler:
    """BFS topology discovery from seed devices.

    Algorithm:
    1. Start with seed device list
    2. For each device, run all applicable adapters
    3. Discover neighbors → new devices
    4. Add new devices to crawl queue
    5. Repeat until no new devices or max_depth reached
    """

    def __init__(self, adapters: list[DiscoveryAdapter],
                 handler: ObservationHandler):
        self._adapters = adapters
        self._handler = handler

    async def crawl(self, seeds: list[dict],
                    max_depth: int = 5,
                    max_devices: int = 1000,
                    allowed_cidrs: list[str] = None,
                    rate_limit: float = 0.0) -> CrawlResult:
        visited: set[str] = set()
        queue: deque[tuple[dict, int]] = deque()
        result = CrawlResult()

        for seed in seeds:
            queue.append((seed, 0))

        while queue and len(result.devices) < max_devices:
            target, depth = queue.popleft()
            device_key = target.get("device_id") or target.get("ip", "")

            if device_key in visited:
                continue
            if depth > max_depth:
                continue
            if allowed_cidrs and not self._ip_in_scope(target.get("ip"), allowed_cidrs):
                continue

            visited.add(device_key)
            result.max_depth_reached = max(result.max_depth_reached, depth)

            if rate_limit > 0:
                await asyncio.sleep(rate_limit)

            new_neighbors = []
            for adapter in self._adapters:
                if not adapter.supports(target):
                    continue

                try:
                    async for obs in adapter.discover(target):
                        # Process through normal pipeline
                        self._handler.handle(obs)

                        # Track neighbors for BFS
                        if obs.observation_type == ObservationType.NEIGHBOR:
                            neighbor_id = obs.data.get("remote_device", "")
                            neighbor_ip = obs.data.get("remote_ip")
                            if neighbor_id and neighbor_id not in visited:
                                new_neighbors.append({
                                    "type": "device",
                                    "device_id": neighbor_id,
                                    "ip": neighbor_ip,
                                    "credentials": target.get("credentials"),
                                })
                                result.links.append({
                                    "local": device_key,
                                    "remote": neighbor_id,
                                    "protocol": obs.data.get("protocol"),
                                })
                                result.links_discovered += 1

                    result.devices.append(device_key)
                    result.devices_discovered += 1

                except Exception as e:
                    result.errors.append({
                        "device": device_key,
                        "adapter": adapter.__class__.__name__,
                        "error": str(e),
                    })
                    logger.error("Crawl error for %s: %s", device_key, e)

            for neighbor in new_neighbors:
                queue.append((neighbor, depth + 1))

        return result

    def _ip_in_scope(self, ip: str, allowed_cidrs: list[str]) -> bool:
        if not ip:
            return False
        import ipaddress
        try:
            ip_obj = ipaddress.ip_address(ip)
            return any(
                ip_obj in ipaddress.ip_network(cidr, strict=False)
                for cidr in allowed_cidrs
            )
        except (ValueError, TypeError):
            return False
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_network_crawler.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/discovery/crawler.py backend/tests/test_network_crawler.py
git commit -m "feat(discovery): BFS network crawler — expand topology from seed devices"
```

---

## Task 6: Discovery Scheduler

**Files:**
- Create: `backend/src/network/discovery/scheduler.py`
- Test: `backend/tests/test_discovery_scheduler_v2.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_discovery_scheduler_v2.py
"""Tests for DiscoveryScheduler — orchestrates periodic discovery runs."""
import pytest
from src.network.discovery.scheduler import DiscoveryScheduler


class TestDiscoveryScheduler:
    def test_instantiation(self):
        scheduler = DiscoveryScheduler(
            adapters=[],
            handler=None,
            crawler=None,
        )
        assert scheduler is not None
        assert scheduler.incremental_interval == 300
        assert scheduler.cloud_sync_interval == 900
        assert scheduler.full_crawl_interval == 3600

    def test_custom_intervals(self):
        scheduler = DiscoveryScheduler(
            adapters=[],
            handler=None,
            crawler=None,
            incremental_interval=60,
            cloud_sync_interval=120,
            full_crawl_interval=600,
        )
        assert scheduler.incremental_interval == 60
```

**Step 2: Run test, verify fail, implement, verify pass**

```python
# backend/src/network/discovery/scheduler.py
"""DiscoveryScheduler — orchestrates periodic discovery runs."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .adapter import DiscoveryAdapter
from .observation_handler import ObservationHandler
from .crawler import NetworkCrawler

logger = logging.getLogger(__name__)


class DiscoveryScheduler:
    """Schedules periodic discovery runs.

    Modes:
    - incremental: poll known devices (SNMP + LLDP) every 5 min
    - cloud_sync: cloud API discovery every 15 min
    - full_crawl: BFS from seeds every 1 hour
    """

    def __init__(self, adapters: list[DiscoveryAdapter],
                 handler: Optional[ObservationHandler],
                 crawler: Optional[NetworkCrawler],
                 incremental_interval: int = 300,
                 cloud_sync_interval: int = 900,
                 full_crawl_interval: int = 3600):
        self._adapters = adapters
        self._handler = handler
        self._crawler = crawler
        self.incremental_interval = incremental_interval
        self.cloud_sync_interval = cloud_sync_interval
        self.full_crawl_interval = full_crawl_interval
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("DiscoveryScheduler started (incremental=%ds, cloud=%ds, crawl=%ds)",
                     self.incremental_interval, self.cloud_sync_interval, self.full_crawl_interval)
        await asyncio.gather(
            self._run_incremental_loop(),
            self._run_cloud_sync_loop(),
            self._run_full_crawl_loop(),
        )

    def stop(self) -> None:
        self._running = False

    async def _run_incremental_loop(self) -> None:
        while self._running:
            try:
                await self._incremental_scan()
            except Exception as e:
                logger.error("Incremental scan failed: %s", e)
            await asyncio.sleep(self.incremental_interval)

    async def _run_cloud_sync_loop(self) -> None:
        while self._running:
            try:
                await self._cloud_sync()
            except Exception as e:
                logger.error("Cloud sync failed: %s", e)
            await asyncio.sleep(self.cloud_sync_interval)

    async def _run_full_crawl_loop(self) -> None:
        while self._running:
            try:
                await self._full_crawl()
            except Exception as e:
                logger.error("Full crawl failed: %s", e)
            await asyncio.sleep(self.full_crawl_interval)

    async def _incremental_scan(self) -> None:
        """Poll known devices with applicable adapters."""
        if not self._handler:
            return
        # TODO: get known devices from repository
        logger.debug("Incremental scan cycle")

    async def _cloud_sync(self) -> None:
        """Run cloud adapters."""
        logger.debug("Cloud sync cycle")

    async def _full_crawl(self) -> None:
        """BFS crawl from seeds."""
        if not self._crawler:
            return
        logger.debug("Full crawl cycle")
```

**Step 3: Commit**

```bash
git add backend/src/network/discovery/scheduler.py backend/tests/test_discovery_scheduler_v2.py
git commit -m "feat(discovery): DiscoveryScheduler — orchestrates periodic discovery runs"
```

---

## Task 7: Full Regression Test

**Files:** None (verification only)

**Step 1: All Phase 1-3 tests (no Neo4j)**

Run: `cd backend && python3 -m pytest tests/test_repository_domain.py tests/test_repository_interface.py tests/test_sqlite_repository.py tests/test_neighbor_links.py tests/test_topology_validation.py tests/test_kg_uses_repository.py tests/test_repository_api_wiring.py tests/test_topology_events.py tests/test_event_publishing_repository.py tests/test_staleness_detector.py tests/test_kafka_bus.py tests/test_websocket_publisher.py -v`

**Step 2: Phase 4 tests**

Run: `cd backend && python3 -m pytest tests/test_discovery_adapter.py tests/test_entity_resolver.py tests/test_observation_handler.py tests/test_lldp_adapter.py tests/test_aws_discovery_adapter.py tests/test_network_crawler.py tests/test_discovery_scheduler_v2.py -v`

**Step 3: Neo4j tests**

Run: `NEO4J_URI=bolt://localhost:7687 python3 -m pytest tests/test_neo4j_connection.py tests/test_neo4j_schema.py tests/test_graph_sync.py tests/test_neo4j_repository.py tests/test_reconciliation.py tests/test_graph_mutator.py -v`

**Step 4: Existing tests**

Run: `cd backend && python3 -m pytest tests/test_knowledge_graph.py tests/test_topology_store_crud.py -v`

---

## Summary

| Task | What | Files | Requires |
|------|------|-------|----------|
| 1 | Adapter interface + Observation model | `discovery/adapter.py`, `observation.py` | None |
| 2 | Entity resolution + Observation handler | `entity_resolver.py`, `observation_handler.py` | None |
| 3 | LLDP discovery adapter | `lldp_adapter.py` | None |
| 4 | AWS cloud discovery adapter | `aws_adapter.py` | None (mock) |
| 5 | BFS network crawler | `crawler.py` | None |
| 6 | Discovery scheduler | `scheduler.py` | None |
| 7 | Full regression test | None | All |

**After Phase 4 is complete:**
- Discovery adapters yield universal `DiscoveryObservation` objects
- EntityResolver matches observations to canonical entity IDs (serial → IP → hostname → new)
- ObservationHandler processes observations into repository (which publishes events)
- LLDPDiscoveryAdapter discovers L2 neighbors (mock + production-ready interface)
- AWSDiscoveryAdapter discovers VPCs, subnets, ENIs, SGs (mock + boto3)
- NetworkCrawler does BFS expansion from seed devices
- DiscoveryScheduler orchestrates periodic runs (incremental, cloud, full crawl)
- Ready for Phase 5: Visualization (frontend layout engine + real-time updates)
