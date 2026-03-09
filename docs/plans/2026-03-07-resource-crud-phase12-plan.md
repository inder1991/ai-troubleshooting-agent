# Phase 12: Complete Resource CRUD API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose all TopologyStore CRUD methods as REST API endpoints for the 15+ resource types that currently have store methods but no API surface.

**Architecture:** Three new thin endpoint files grouping related resources. Each endpoint wraps existing TopologyStore `add_*`/`list_*`/`delete_*` methods. No new business logic needed.

**Tech Stack:** FastAPI (existing), Pydantic models (existing), TopologyStore (existing)

---

### Task 1: Core Resource CRUD (Subnet, Interface, Route, Zone)

**Files:**
- Create: `backend/src/api/resource_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_resource_crud.py`

**Context:**
- These 4 resources already have `add_*`, `list_*`, `delete_*` in TopologyStore
- API currently has DELETE for all 4, GET list for subnets/interfaces/routes, but NO POST (create) and NO GET single
- Store methods: `add_subnet(Subnet)`, `add_interface(Interface)`, `add_route(Route)`, `add_zone(Zone)`
- Models are Pydantic BaseModel with validators (e.g., Subnet validates CIDR, Interface validates IP)
- Follow same module-level `_topology_store` pattern as other endpoint files

**Endpoints to create (all under `/api/v4/network/resources`):**

```
POST /subnets          — create subnet (body: Subnet model fields)
GET  /subnets/{id}     — get single subnet (query store.list_subnets(), filter by id)
POST /interfaces       — create interface
GET  /interfaces/{id}  — get single interface
POST /routes           — create route
GET  /routes/{id}      — get single route (from list_routes, filter)
POST /zones            — create zone
GET  /zones            — list zones
GET  /zones/{id}       — get single zone
DELETE /zones/{zone_id} — delete zone (move from network_endpoints.py or duplicate)
```

**Step 1: Write the failing tests**

Create `backend/tests/test_resource_crud.py`:

```python
"""Tests for core resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore
from src.network.models import Device, DeviceType


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    store.add_device(Device(id="d1", name="Router1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))

    from src.api.main import app
    from src.api import resource_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestSubnetCRUD:
    def test_create_subnet(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/subnets", json={
            "id": "sub1", "cidr": "10.0.0.0/24", "description": "Test subnet"
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "sub1"

    def test_create_subnet_invalid_cidr(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/subnets", json={
            "id": "sub1", "cidr": "not-a-cidr"
        })
        assert resp.status_code == 422

    def test_list_subnets(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Subnet
        store.add_subnet(Subnet(id="sub1", cidr="10.0.0.0/24"))
        resp = client.get("/api/v4/network/resources/subnets")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestInterfaceCRUD:
    def test_create_interface(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/interfaces", json={
            "id": "if1", "device_id": "d1", "name": "eth0", "ip": "10.0.0.1"
        })
        assert resp.status_code == 201

    def test_list_interfaces(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Interface
        store.add_interface(Interface(id="if1", device_id="d1", name="eth0"))
        resp = client.get("/api/v4/network/resources/interfaces")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestRouteCRUD:
    def test_create_route(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/routes", json={
            "id": "rt1", "device_id": "d1", "destination": "0.0.0.0/0",
            "next_hop": "10.0.0.1", "protocol": "static"
        })
        assert resp.status_code == 201

    def test_list_routes(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Route
        store.add_route(Route(id="rt1", device_id="d1", destination="0.0.0.0/0", next_hop="10.0.0.1"))
        resp = client.get("/api/v4/network/resources/routes")
        assert resp.status_code == 200


class TestZoneCRUD:
    def test_create_zone(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/resources/zones", json={
            "id": "z1", "name": "DMZ", "security_level": 50
        })
        assert resp.status_code == 201

    def test_list_zones(self, store_and_client):
        store, client = store_and_client
        from src.network.models import Zone
        store.add_zone(Zone(id="z1", name="DMZ"))
        resp = client.get("/api/v4/network/resources/zones")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_resource_crud.py -v`

**Step 3: Implement**

Create `backend/src/api/resource_endpoints.py`:

```python
"""CRUD endpoints for core network resources (subnet, interface, route, zone)."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.network.models import Subnet, Interface, Route, Zone
from src.utils.logger import get_logger

logger = get_logger(__name__)

resource_router = APIRouter(prefix="/api/v4/network/resources", tags=["resources"])

_topology_store = None


def init_resource_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


# ── Subnets ──

@resource_router.post("/subnets", status_code=201)
def create_subnet(subnet: Subnet):
    _store().add_subnet(subnet)
    return subnet.model_dump()


@resource_router.get("/subnets")
def list_subnets():
    return _store().list_subnets()


# ── Interfaces ──

@resource_router.post("/interfaces", status_code=201)
def create_interface(iface: Interface):
    _store().add_interface(iface)
    return iface.model_dump()


@resource_router.get("/interfaces")
def list_interfaces(device_id: str = None):
    return _store().list_interfaces(device_id=device_id)


# ── Routes ──

@resource_router.post("/routes", status_code=201)
def create_route(route: Route):
    _store().add_route(route)
    return route.model_dump()


@resource_router.get("/routes")
def list_routes(device_id: str = None):
    return _store().list_routes(device_id=device_id)


# ── Zones ──

@resource_router.post("/zones", status_code=201)
def create_zone(zone: Zone):
    _store().add_zone(zone)
    return zone.model_dump()


@resource_router.get("/zones")
def list_zones():
    return _store().list_zones()
```

Modify `backend/src/api/main.py` — add import and registration:

```python
from .resource_endpoints import resource_router, init_resource_endpoints
app.include_router(resource_router)
# In startup: init_resource_endpoints(topo_store)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_resource_crud.py -v`

**Step 5: Commit**

```bash
cd backend && git add src/api/resource_endpoints.py tests/test_resource_crud.py src/api/main.py
git commit -m "feat(api): add CRUD endpoints for subnet, interface, route, zone"
```

---

### Task 2: Cloud & Connectivity Resource CRUD

**Files:**
- Create: `backend/src/api/cloud_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_cloud_crud.py`

**Context:**
- Resources: VPC (complete CRUD), RouteTable, VPCPeering, TransitGateway, VPNTunnel, DirectConnect
- All have `add_*` and `list_*` in TopologyStore, some have `get_*` and `delete_*`
- VPC already has GET list and DELETE in network_endpoints.py but NO POST create
- Models all have `id`, `name`, and type-specific fields
- Follow same pattern as Task 1

**Endpoints (all under `/api/v4/network/cloud`):**

```
POST /vpcs                — create VPC
GET  /vpcs                — list VPCs
POST /route-tables        — create route table
GET  /route-tables        — list route tables (optional ?vpc_id= filter)
POST /vpc-peerings        — create VPC peering
GET  /vpc-peerings        — list VPC peerings
POST /transit-gateways    — create transit gateway
GET  /transit-gateways    — list transit gateways
POST /vpn-tunnels         — create VPN tunnel
GET  /vpn-tunnels         — list VPN tunnels
POST /direct-connects     — create direct connect
GET  /direct-connects     — list direct connects
```

**Step 1: Write the failing tests**

Create `backend/tests/test_cloud_crud.py`:

```python
"""Tests for cloud & connectivity resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))

    from src.api.main import app
    from src.api import cloud_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestVPCCRUD:
    def test_create_vpc(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpcs", json={
            "id": "vpc-1", "name": "Production", "cidr": "10.0.0.0/16",
            "cloud_provider": "aws", "region": "us-east-1"
        })
        assert resp.status_code == 201

    def test_list_vpcs(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/vpcs", json={
            "id": "vpc-1", "name": "Prod", "cidr": "10.0.0.0/16"
        })
        resp = client.get("/api/v4/network/cloud/vpcs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestRouteTableCRUD:
    def test_create_route_table(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/route-tables", json={
            "id": "rtb-1", "name": "MainRT", "vpc_id": "vpc-1"
        })
        assert resp.status_code == 201

    def test_list_route_tables(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/route-tables", json={
            "id": "rtb-1", "name": "MainRT", "vpc_id": "vpc-1"
        })
        resp = client.get("/api/v4/network/cloud/route-tables")
        assert resp.status_code == 200


class TestVPCPeeringCRUD:
    def test_create_peering(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpc-peerings", json={
            "id": "pcx-1", "requester_vpc_id": "vpc-1",
            "accepter_vpc_id": "vpc-2", "status": "active"
        })
        assert resp.status_code == 201

    def test_list_peerings(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/vpc-peerings", json={
            "id": "pcx-1", "requester_vpc_id": "vpc-1",
            "accepter_vpc_id": "vpc-2", "status": "active"
        })
        resp = client.get("/api/v4/network/cloud/vpc-peerings")
        assert resp.status_code == 200


class TestTransitGatewayCRUD:
    def test_create_tgw(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/transit-gateways", json={
            "id": "tgw-1", "name": "Hub-TGW", "region": "us-east-1"
        })
        assert resp.status_code == 201

    def test_list_tgws(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/transit-gateways", json={
            "id": "tgw-1", "name": "Hub-TGW"
        })
        resp = client.get("/api/v4/network/cloud/transit-gateways")
        assert resp.status_code == 200


class TestVPNTunnelCRUD:
    def test_create_vpn(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/vpn-tunnels", json={
            "id": "vpn-1", "name": "Site-A", "tunnel_type": "ipsec",
            "local_ip": "203.0.113.1", "remote_ip": "198.51.100.1"
        })
        assert resp.status_code == 201

    def test_list_vpns(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/vpn-tunnels", json={
            "id": "vpn-1", "name": "Site-A", "tunnel_type": "ipsec",
            "local_ip": "203.0.113.1", "remote_ip": "198.51.100.1"
        })
        resp = client.get("/api/v4/network/cloud/vpn-tunnels")
        assert resp.status_code == 200


class TestDirectConnectCRUD:
    def test_create_dx(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/cloud/direct-connects", json={
            "id": "dx-1", "name": "DC-Link", "provider": "aws_dx",
            "bandwidth": "1Gbps", "location": "EqDC2"
        })
        assert resp.status_code == 201

    def test_list_dx(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/cloud/direct-connects", json={
            "id": "dx-1", "name": "DC-Link", "provider": "aws_dx"
        })
        resp = client.get("/api/v4/network/cloud/direct-connects")
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cloud_crud.py -v`

**Step 3: Implement**

Create `backend/src/api/cloud_endpoints.py`:

```python
"""CRUD endpoints for cloud & connectivity resources."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.network.models import VPC, RouteTable, VPCPeering, TransitGateway, VPNTunnel, DirectConnect
from src.utils.logger import get_logger

logger = get_logger(__name__)

cloud_router = APIRouter(prefix="/api/v4/network/cloud", tags=["cloud"])

_topology_store = None


def init_cloud_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


@cloud_router.post("/vpcs", status_code=201)
def create_vpc(vpc: VPC):
    _store().add_vpc(vpc)
    return vpc.model_dump()

@cloud_router.get("/vpcs")
def list_vpcs():
    return _store().list_vpcs()

@cloud_router.post("/route-tables", status_code=201)
def create_route_table(rt: RouteTable):
    _store().add_route_table(rt)
    return rt.model_dump()

@cloud_router.get("/route-tables")
def list_route_tables(vpc_id: str = None):
    return _store().list_route_tables(vpc_id=vpc_id)

@cloud_router.post("/vpc-peerings", status_code=201)
def create_vpc_peering(p: VPCPeering):
    _store().add_vpc_peering(p)
    return p.model_dump()

@cloud_router.get("/vpc-peerings")
def list_vpc_peerings():
    return _store().list_vpc_peerings()

@cloud_router.post("/transit-gateways", status_code=201)
def create_transit_gateway(tgw: TransitGateway):
    _store().add_transit_gateway(tgw)
    return tgw.model_dump()

@cloud_router.get("/transit-gateways")
def list_transit_gateways():
    return _store().list_transit_gateways()

@cloud_router.post("/vpn-tunnels", status_code=201)
def create_vpn_tunnel(vpn: VPNTunnel):
    _store().add_vpn_tunnel(vpn)
    return vpn.model_dump()

@cloud_router.get("/vpn-tunnels")
def list_vpn_tunnels():
    return _store().list_vpn_tunnels()

@cloud_router.post("/direct-connects", status_code=201)
def create_direct_connect(dx: DirectConnect):
    _store().add_direct_connect(dx)
    return dx.model_dump()

@cloud_router.get("/direct-connects")
def list_direct_connects():
    return _store().list_direct_connects()
```

Register in main.py:

```python
from .cloud_endpoints import cloud_router, init_cloud_endpoints
app.include_router(cloud_router)
# In startup: init_cloud_endpoints(topo_store)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_cloud_crud.py -v`

**Step 5: Commit**

```bash
cd backend && git add src/api/cloud_endpoints.py tests/test_cloud_crud.py src/api/main.py
git commit -m "feat(api): add CRUD endpoints for VPC, route-table, peering, TGW, VPN, DirectConnect"
```

---

### Task 3: Security & Infrastructure Resource CRUD

**Files:**
- Create: `backend/src/api/security_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Create: `backend/tests/test_security_crud.py`

**Context:**
- Resources: FirewallRule, NATRule, NACL, NACLRule, LoadBalancer, LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone
- All have `add_*` and `list_*` in TopologyStore
- Some list methods accept filters (e.g., `list_firewall_rules(device_id=)`, `list_nacl_rules(nacl_id=)`)
- No API endpoints exist for ANY of these

**Endpoints (under `/api/v4/network/security`):**

```
POST /firewall-rules     — create firewall rule
GET  /firewall-rules     — list rules (optional ?device_id= filter)
POST /nat-rules          — create NAT rule
GET  /nat-rules          — list NAT rules (optional ?device_id= filter)
POST /nacls              — create NACL
GET  /nacls              — list NACLs (optional ?vpc_id= filter)
POST /nacl-rules         — create NACL rule
GET  /nacl-rules         — list NACL rules (?nacl_id= required)
POST /load-balancers     — create load balancer
GET  /load-balancers     — list load balancers
POST /vlans              — create VLAN
GET  /vlans              — list VLANs
POST /mpls-circuits      — create MPLS circuit
GET  /mpls-circuits      — list MPLS circuits
POST /compliance-zones   — create compliance zone
GET  /compliance-zones   — list compliance zones
```

**Step 1: Write the failing tests**

Create `backend/tests/test_security_crud.py`:

```python
"""Tests for security & infrastructure resource CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient

from src.network.topology_store import TopologyStore


@pytest.fixture
def store_and_client(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))

    from src.api.main import app
    from src.api import security_endpoints as ep
    orig = ep._topology_store
    ep._topology_store = store
    client = TestClient(app)
    yield store, client
    ep._topology_store = orig


class TestFirewallRuleCRUD:
    def test_create_rule(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/firewall-rules", json={
            "id": "fw1", "device_id": "d1", "action": "allow",
            "source": "10.0.0.0/24", "destination": "any",
            "protocol": "tcp", "port": "443", "priority": 100
        })
        assert resp.status_code == 201

    def test_list_rules(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/firewall-rules", json={
            "id": "fw1", "device_id": "d1", "action": "allow",
            "source": "any", "destination": "any", "protocol": "any"
        })
        resp = client.get("/api/v4/network/security/firewall-rules")
        assert resp.status_code == 200


class TestNATRuleCRUD:
    def test_create_nat_rule(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/nat-rules", json={
            "id": "nat1", "device_id": "d1", "direction": "snat",
            "original_source": "10.0.0.0/24", "translated_source": "203.0.113.1"
        })
        assert resp.status_code == 201

    def test_list_nat_rules(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/nat-rules", json={
            "id": "nat1", "device_id": "d1", "direction": "snat",
            "original_source": "10.0.0.0/24", "translated_source": "203.0.113.1"
        })
        resp = client.get("/api/v4/network/security/nat-rules")
        assert resp.status_code == 200


class TestNACLCRUD:
    def test_create_nacl(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/nacls", json={
            "id": "nacl-1", "name": "Web-NACL", "vpc_id": "vpc-1"
        })
        assert resp.status_code == 201

    def test_list_nacls(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/nacls", json={
            "id": "nacl-1", "name": "Web-NACL", "vpc_id": "vpc-1"
        })
        resp = client.get("/api/v4/network/security/nacls")
        assert resp.status_code == 200


class TestLoadBalancerCRUD:
    def test_create_lb(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/load-balancers", json={
            "id": "lb-1", "name": "Web-LB", "lb_type": "alb", "scheme": "internet_facing"
        })
        assert resp.status_code == 201

    def test_list_lbs(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/load-balancers", json={
            "id": "lb-1", "name": "Web-LB", "lb_type": "alb", "scheme": "internet_facing"
        })
        resp = client.get("/api/v4/network/security/load-balancers")
        assert resp.status_code == 200


class TestVLANCRUD:
    def test_create_vlan(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/vlans", json={
            "id": "vlan-100", "vlan_id": 100, "name": "Management"
        })
        assert resp.status_code == 201

    def test_list_vlans(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/vlans", json={
            "id": "vlan-100", "vlan_id": 100, "name": "Management"
        })
        resp = client.get("/api/v4/network/security/vlans")
        assert resp.status_code == 200


class TestMPLSCRUD:
    def test_create_mpls(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/mpls-circuits", json={
            "id": "mpls-1", "label": 1001, "name": "DC-to-DC"
        })
        assert resp.status_code == 201

    def test_list_mpls(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/mpls-circuits", json={
            "id": "mpls-1", "label": 1001, "name": "DC-to-DC"
        })
        resp = client.get("/api/v4/network/security/mpls-circuits")
        assert resp.status_code == 200


class TestComplianceZoneCRUD:
    def test_create_zone(self, store_and_client):
        _, client = store_and_client
        resp = client.post("/api/v4/network/security/compliance-zones", json={
            "id": "cz-1", "name": "PCI-Zone", "standard": "pci_dss"
        })
        assert resp.status_code == 201

    def test_list_zones(self, store_and_client):
        _, client = store_and_client
        client.post("/api/v4/network/security/compliance-zones", json={
            "id": "cz-1", "name": "PCI-Zone", "standard": "pci_dss"
        })
        resp = client.get("/api/v4/network/security/compliance-zones")
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_security_crud.py -v`

**Step 3: Implement**

Create `backend/src/api/security_endpoints.py`:

```python
"""CRUD endpoints for security & infrastructure resources."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from src.network.models import (
    FirewallRule, NATRule, NACL, NACLRule,
    LoadBalancer, LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

security_router = APIRouter(prefix="/api/v4/network/security", tags=["security"])

_topology_store = None


def init_security_endpoints(topology_store):
    global _topology_store
    _topology_store = topology_store


def _store():
    if not _topology_store:
        raise HTTPException(503, "Store not initialized")
    return _topology_store


# ── Firewall Rules ──

@security_router.post("/firewall-rules", status_code=201)
def create_firewall_rule(rule: FirewallRule):
    _store().add_firewall_rule(rule)
    return rule.model_dump()

@security_router.get("/firewall-rules")
def list_firewall_rules(device_id: str = None):
    return _store().list_firewall_rules(device_id=device_id)


# ── NAT Rules ──

@security_router.post("/nat-rules", status_code=201)
def create_nat_rule(rule: NATRule):
    _store().add_nat_rule(rule)
    return rule.model_dump()

@security_router.get("/nat-rules")
def list_nat_rules(device_id: str = None):
    return _store().list_nat_rules(device_id=device_id)


# ── NACLs ──

@security_router.post("/nacls", status_code=201)
def create_nacl(nacl: NACL):
    _store().add_nacl(nacl)
    return nacl.model_dump()

@security_router.get("/nacls")
def list_nacls(vpc_id: str = None):
    return _store().list_nacls(vpc_id=vpc_id)


# ── NACL Rules ──

@security_router.post("/nacl-rules", status_code=201)
def create_nacl_rule(rule: NACLRule):
    _store().add_nacl_rule(rule)
    return rule.model_dump()

@security_router.get("/nacl-rules")
def list_nacl_rules(nacl_id: str = Query(...)):
    return _store().list_nacl_rules(nacl_id=nacl_id)


# ── Load Balancers ──

@security_router.post("/load-balancers", status_code=201)
def create_load_balancer(lb: LoadBalancer):
    _store().add_load_balancer(lb)
    return lb.model_dump()

@security_router.get("/load-balancers")
def list_load_balancers():
    return _store().list_load_balancers()


# ── VLANs ──

@security_router.post("/vlans", status_code=201)
def create_vlan(vlan: VLAN):
    _store().add_vlan(vlan)
    return vlan.model_dump()

@security_router.get("/vlans")
def list_vlans():
    return _store().list_vlans()


# ── MPLS Circuits ──

@security_router.post("/mpls-circuits", status_code=201)
def create_mpls_circuit(mpls: MPLSCircuit):
    _store().add_mpls_circuit(mpls)
    return mpls.model_dump()

@security_router.get("/mpls-circuits")
def list_mpls_circuits():
    return _store().list_mpls_circuits()


# ── Compliance Zones ──

@security_router.post("/compliance-zones", status_code=201)
def create_compliance_zone(cz: ComplianceZone):
    _store().add_compliance_zone(cz)
    return cz.model_dump()

@security_router.get("/compliance-zones")
def list_compliance_zones():
    return _store().list_compliance_zones()
```

Register in main.py:

```python
from .security_endpoints import security_router, init_security_endpoints
app.include_router(security_router)
# In startup: init_security_endpoints(topo_store)
```

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_security_crud.py -v`

**Step 5: Commit**

```bash
cd backend && git add src/api/security_endpoints.py tests/test_security_crud.py src/api/main.py
git commit -m "feat(api): add CRUD endpoints for firewall, NAT, NACL, LB, VLAN, MPLS, compliance"
```

---

### Task 4: Final Verification

**Step 1: Run all Phase 12 tests**

```bash
cd backend && python3 -m pytest tests/test_resource_crud.py tests/test_cloud_crud.py tests/test_security_crud.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**Step 3: Verify imports**

```bash
python3 -c "
from src.api.resource_endpoints import resource_router
from src.api.cloud_endpoints import cloud_router
from src.api.security_endpoints import security_router
print('Resource endpoints:', len(resource_router.routes))
print('Cloud endpoints:', len(cloud_router.routes))
print('Security endpoints:', len(security_router.routes))
print('All Phase 12 imports verified')
"
```
