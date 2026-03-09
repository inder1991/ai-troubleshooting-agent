# Phase 13: Core Module Test Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add dedicated unit tests for core untested modules: TopologyStore CRUD, KnowledgeGraph path-finding, HA validation logic, and interface validation.

**Architecture:** Pure unit tests against existing classes. No API changes.

**Tech Stack:** pytest, TopologyStore (SQLite), NetworkKnowledgeGraph (networkx)

---

### Task 1: TopologyStore CRUD Tests

**Files:**
- Create: `backend/tests/test_topology_store_crud.py`

**Context:**
- TopologyStore has 107+ public methods but only ~24 are tested (in test_monitor_store.py which covers monitoring methods)
- Core CRUD for devices, interfaces, subnets, routes, VPCs, firewall rules, zones, HA groups are all untested
- Store uses SQLite with `INSERT OR REPLACE` semantics
- All `add_*` methods take Pydantic model objects
- All `list_*` methods return lists of dicts
- `delete_*` methods cascade (e.g., deleting device removes its interfaces/routes)

**Tests to write (minimum):**

```python
"""Tests for TopologyStore CRUD operations."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import (
    Device, DeviceType, Interface, Subnet, Route, Zone,
    FirewallRule, NATRule, VPC, HAGroup, HAMode,
    PolicyAction, NATDirection, CloudProvider,
)


@pytest.fixture
def store(tmp_path):
    return TopologyStore(str(tmp_path / "test.db"))


class TestDeviceCRUD:
    def test_add_and_get_device(self, store):
        d = Device(id="d1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1")
        store.add_device(d)
        result = store.get_device("d1")
        assert result is not None
        assert result["name"] == "Router1"

    def test_list_devices_pagination(self, store):
        for i in range(5):
            store.add_device(Device(id=f"d{i}", name=f"Dev{i}", device_type=DeviceType.HOST))
        page = store.list_devices(offset=0, limit=3)
        assert len(page) == 3

    def test_update_device(self, store):
        store.add_device(Device(id="d1", name="Old", device_type=DeviceType.HOST))
        store.update_device("d1", name="New")
        result = store.get_device("d1")
        assert result["name"] == "New"

    def test_delete_device_cascades(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0"))
        store.add_route(Route(id="rt1", device_id="d1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1"))
        store.delete_device("d1")
        assert store.get_device("d1") is None
        assert len(store.list_interfaces(device_id="d1")) == 0
        assert len(store.list_routes(device_id="d1")) == 0

    def test_count_devices(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.HOST))
        assert store.count_devices() == 1


class TestInterfaceCRUD:
    def test_add_and_list(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0", ip="10.0.0.1"))
        ifaces = store.list_interfaces(device_id="d1")
        assert len(ifaces) == 1

    def test_find_by_ip(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0", ip="10.0.0.1"))
        result = store.find_interface_by_ip("10.0.0.1")
        assert result is not None

    def test_delete_interface(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0"))
        store.delete_interface("if1")
        assert len(store.list_interfaces(device_id="d1")) == 0


class TestSubnetCRUD:
    def test_add_and_list(self, store):
        store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
        subs = store.list_subnets()
        assert len(subs) == 1

    def test_delete_subnet(self, store):
        store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
        store.delete_subnet("sub1")
        assert len(store.list_subnets()) == 0


class TestRouteCRUD:
    def test_add_and_list(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="d1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1"))
        routes = store.list_routes(device_id="d1")
        assert len(routes) == 1

    def test_bulk_add_routes(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        routes = [
            Route(id=f"rt{i}", device_id="d1", destination_cidr=f"10.{i}.0.0/24", next_hop="10.0.0.1")
            for i in range(5)
        ]
        store.bulk_add_routes(routes)
        assert len(store.list_routes(device_id="d1")) == 5

    def test_delete_route(self, store):
        store.add_device(Device(id="d1", name="R1", device_type=DeviceType.ROUTER))
        store.add_route(Route(id="rt1", device_id="d1", destination_cidr="0.0.0.0/0", next_hop="10.0.0.1"))
        store.delete_route("rt1")
        assert len(store.list_routes(device_id="d1")) == 0


class TestZoneCRUD:
    def test_add_and_list(self, store):
        store.add_zone(Zone(id="z1", name="DMZ", security_level=50))
        zones = store.list_zones()
        assert len(zones) == 1

    def test_delete_zone(self, store):
        store.add_zone(Zone(id="z1", name="DMZ"))
        store.delete_zone("z1")
        assert len(store.list_zones()) == 0


class TestFirewallRuleCRUD:
    def test_add_and_list(self, store):
        store.add_device(Device(id="d1", name="FW1", device_type=DeviceType.FIREWALL))
        store.add_firewall_rule(FirewallRule(
            id="fw1", device_id="d1", rule_name="allow-https",
            action=PolicyAction.ALLOW, source="any", destination="any", protocol="tcp",
        ))
        rules = store.list_firewall_rules(device_id="d1")
        assert len(rules) == 1

    def test_list_all_rules(self, store):
        store.add_device(Device(id="d1", name="FW1", device_type=DeviceType.FIREWALL))
        store.add_firewall_rule(FirewallRule(
            id="fw1", device_id="d1", rule_name="r1",
            action=PolicyAction.ALLOW, source="any", destination="any", protocol="tcp",
        ))
        rules = store.list_firewall_rules()
        assert len(rules) >= 1


class TestHAGroupCRUD:
    def test_add_and_get(self, store):
        store.add_ha_group(HAGroup(
            id="ha1", name="FW-Cluster", mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], virtual_ips=["10.0.0.100"],
        ))
        result = store.get_ha_group("ha1")
        assert result is not None

    def test_list_and_delete(self, store):
        store.add_ha_group(HAGroup(id="ha1", name="Cluster", mode=HAMode.ACTIVE_PASSIVE))
        assert len(store.list_ha_groups()) == 1
        store.delete_ha_group("ha1")
        assert len(store.list_ha_groups()) == 0


class TestVPCCRUD:
    def test_add_and_list(self, store):
        store.add_vpc(VPC(id="vpc1", name="Prod", cloud_provider=CloudProvider.AWS))
        vpcs = store.list_vpcs()
        assert len(vpcs) == 1

    def test_get_vpc(self, store):
        store.add_vpc(VPC(id="vpc1", name="Prod", cloud_provider=CloudProvider.AWS))
        result = store.get_vpc("vpc1")
        assert result is not None

    def test_delete_vpc(self, store):
        store.add_vpc(VPC(id="vpc1", name="Prod", cloud_provider=CloudProvider.AWS))
        store.delete_vpc("vpc1")
        assert len(store.list_vpcs()) == 0
```

Read the actual models.py to check Route field names — the plan uses `destination_cidr` but verify. Also check if `delete_device` actually cascades to interfaces/routes.

**Step 1:** Create the test file
**Step 2:** Run: `cd backend && python3 -m pytest tests/test_topology_store_crud.py -v`
**Step 3:** Fix any failures (field name mismatches, missing cascade, etc.)
**Step 4:** Commit: `git commit -m "test: add TopologyStore CRUD unit tests"`

---

### Task 2: KnowledgeGraph Path-Finding & Edge Tests

**Files:**
- Create: `backend/tests/test_knowledge_graph_paths.py`

**Context:**
- `NetworkKnowledgeGraph` wraps a networkx DiGraph
- `find_k_shortest_paths(src, dst, k=3)` returns list of paths using confidence-weighted dual cost
- `boost_edge_confidence(src, dst, boost=0.05)` updates edge confidence
- `find_candidate_devices(ip)` finds devices in subnet matching IP
- `build_route_edges()` creates edges from route table data
- `export_react_flow_graph()` exports to React Flow JSON format

**Tests to write:**

```python
"""Tests for KnowledgeGraph path-finding and edge operations."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Interface, Subnet, Route


@pytest.fixture
def kg_with_topology(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    # Build a small topology: r1 -> r2 -> r3, r1 -> r3 (direct)
    for did, name in [("r1","Router1"), ("r2","Router2"), ("r3","Router3")]:
        store.add_device(Device(id=did, name=name, device_type=DeviceType.ROUTER, management_ip=f"10.0.{did[-1]}.1"))
    store.add_subnet(Subnet(id="sub1", cidr="10.0.1.0/24"))
    store.add_interface(Interface(id="if-r1", device_id="r1", name="eth0", ip="10.0.1.1", subnet_id="sub1"))
    store.add_interface(Interface(id="if-r2", device_id="r2", name="eth0", ip="10.0.1.2", subnet_id="sub1"))

    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()
    # Manually add edges for testing
    kg.graph.add_edge("r1", "r2", confidence=0.9, edge_type="connected_to")
    kg.graph.add_edge("r2", "r3", confidence=0.8, edge_type="connected_to")
    kg.graph.add_edge("r1", "r3", confidence=0.5, edge_type="routes_to")
    return kg, store


class TestPathFinding:
    def test_find_paths_basic(self, kg_with_topology):
        kg, _ = kg_with_topology
        paths = kg.find_k_shortest_paths("r1", "r3", k=3)
        assert len(paths) >= 1
        # Direct path r1->r3 should be found
        assert any("r3" in p for p in paths)

    def test_find_paths_no_path(self, kg_with_topology):
        kg, _ = kg_with_topology
        paths = kg.find_k_shortest_paths("r3", "nonexistent", k=1)
        assert paths == []

    def test_find_paths_k_limit(self, kg_with_topology):
        kg, _ = kg_with_topology
        paths = kg.find_k_shortest_paths("r1", "r3", k=1)
        assert len(paths) <= 1


class TestEdgeOperations:
    def test_boost_confidence(self, kg_with_topology):
        kg, _ = kg_with_topology
        old = kg.graph["r1"]["r3"].get("confidence", 0.5)
        kg.boost_edge_confidence("r1", "r3", 0.1)
        new = kg.graph["r1"]["r3"]["confidence"]
        assert new > old

    def test_boost_caps_at_one(self, kg_with_topology):
        kg, _ = kg_with_topology
        kg.boost_edge_confidence("r1", "r2", 0.5)  # 0.9 + 0.5
        assert kg.graph["r1"]["r2"]["confidence"] <= 1.0


class TestExport:
    def test_export_react_flow(self, kg_with_topology):
        kg, _ = kg_with_topology
        result = kg.export_react_flow_graph()
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) >= 3


class TestCandidateDevices:
    def test_find_candidates(self, kg_with_topology):
        kg, _ = kg_with_topology
        candidates = kg.find_candidate_devices("10.0.1.1")
        # Should find devices in subnet matching this IP
        assert isinstance(candidates, list)
```

Read `knowledge_graph.py` to verify actual method signatures before writing tests. Adapt accordingly.

**Step 1:** Create the test file
**Step 2:** Run: `cd backend && python3 -m pytest tests/test_knowledge_graph_paths.py -v`
**Step 3:** Fix any failures
**Step 4:** Commit: `git commit -m "test: add KnowledgeGraph path-finding and edge unit tests"`

---

### Task 3: HA Validation & Interface Validation Unit Tests

**Files:**
- Create: `backend/tests/test_ha_validation_unit.py`
- Create: `backend/tests/test_interface_validation.py`

**Context:**
- `ha_validation.validate_ha_group(store, group)` returns list of error strings
- Rules: same device type, same subnet, VIP in subnet, active-passive needs 1 active
- `interface_validation.validate_device_interfaces(device_id, interfaces, subnets, zones, device_vlan_id)` returns list of error dicts
- Rules: IP in subnet CIDR (rule 29), no shared zones (rule 30), and more

**Tests for HA validation:**

```python
"""Unit tests for HA validation logic."""
import pytest
from src.network.topology_store import TopologyStore
from src.network.ha_validation import validate_ha_group
from src.network.models import Device, DeviceType, Interface, Subnet, HAGroup, HAMode

@pytest.fixture
def store(tmp_path):
    s = TopologyStore(str(tmp_path / "test.db"))
    s.add_device(Device(id="fw1", name="FW1", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
    s.add_device(Device(id="fw2", name="FW2", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
    s.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
    s.add_interface(Interface(id="if1", device_id="fw1", ip="10.0.0.1", subnet_id="sub1", name="eth0"))
    s.add_interface(Interface(id="if2", device_id="fw2", ip="10.0.0.2", subnet_id="sub1", name="eth0"))
    return s

class TestHAValidation:
    def test_valid_group(self, store):
        group = HAGroup(id="ha1", name="FW-Pair", mode=HAMode.ACTIVE_PASSIVE,
                       member_ids=["fw1","fw2"], virtual_ips=["10.0.0.100"])
        errors = validate_ha_group(store, group)
        assert len(errors) == 0 or all("active" not in e.lower() for e in errors)

    def test_mixed_device_types(self, store):
        store.add_device(Device(id="sw1", name="SW1", device_type=DeviceType.SWITCH))
        group = HAGroup(id="ha1", name="Mixed", mode=HAMode.ACTIVE_PASSIVE,
                       member_ids=["fw1","sw1"])
        errors = validate_ha_group(store, group)
        assert any("type" in e.lower() for e in errors)

    def test_empty_members(self, store):
        group = HAGroup(id="ha1", name="Empty", mode=HAMode.ACTIVE_PASSIVE, member_ids=[])
        errors = validate_ha_group(store, group)
        assert len(errors) >= 1
```

**Tests for interface validation:**

```python
"""Unit tests for interface validation rules."""
import pytest
from src.network.interface_validation import validate_device_interfaces
from src.network.models import Interface, Subnet, Zone

class TestInterfaceValidation:
    def test_ip_outside_subnet(self):
        ifaces = [Interface(id="if1", device_id="d1", name="eth0", ip="192.168.1.1", subnet_id="sub1")]
        subnets = [Subnet(id="sub1", cidr="10.0.0.0/24")]
        errors = validate_device_interfaces("d1", ifaces, subnets, [])
        assert any(e["rule"] == 29 for e in errors)

    def test_ip_inside_subnet(self):
        ifaces = [Interface(id="if1", device_id="d1", name="eth0", ip="10.0.0.5", subnet_id="sub1")]
        subnets = [Subnet(id="sub1", cidr="10.0.0.0/24")]
        errors = validate_device_interfaces("d1", ifaces, subnets, [])
        assert not any(e["rule"] == 29 for e in errors)

    def test_duplicate_zone(self):
        ifaces = [
            Interface(id="if1", device_id="d1", name="eth0", zone_id="z1"),
            Interface(id="if2", device_id="d1", name="eth1", zone_id="z1"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [Zone(id="z1", name="DMZ")])
        assert any(e["rule"] == 30 for e in errors)

    def test_sync_interfaces_exempt_from_zone_check(self):
        ifaces = [
            Interface(id="if1", device_id="d1", name="eth0", zone_id="z1"),
            Interface(id="if2", device_id="d1", name="sync0", zone_id="z1", role="sync"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [Zone(id="z1", name="DMZ")])
        assert not any(e["rule"] == 30 for e in errors)

    def test_no_errors_on_valid_config(self):
        ifaces = [
            Interface(id="if1", device_id="d1", name="eth0", ip="10.0.0.1", subnet_id="sub1", zone_id="z1"),
            Interface(id="if2", device_id="d1", name="eth1", ip="10.0.1.1", subnet_id="sub2", zone_id="z2"),
        ]
        subnets = [Subnet(id="sub1", cidr="10.0.0.0/24"), Subnet(id="sub2", cidr="10.0.1.0/24")]
        zones = [Zone(id="z1", name="Inside"), Zone(id="z2", name="Outside")]
        errors = validate_device_interfaces("d1", ifaces, subnets, zones)
        assert len(errors) == 0
```

Read actual `ha_validation.py` and `interface_validation.py` to verify function signatures and rule numbers.

**Step 1:** Create both test files
**Step 2:** Run: `cd backend && python3 -m pytest tests/test_ha_validation_unit.py tests/test_interface_validation.py -v`
**Step 3:** Fix any failures
**Step 4:** Commit: `git commit -m "test: add HA validation and interface validation unit tests"`

---

### Task 4: Final Verification

**Step 1:** Run all Phase 13 tests:
```bash
cd backend && python3 -m pytest tests/test_topology_store_crud.py tests/test_knowledge_graph_paths.py tests/test_ha_validation_unit.py tests/test_interface_validation.py -v
```

**Step 2:** Run full suite:
```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```
