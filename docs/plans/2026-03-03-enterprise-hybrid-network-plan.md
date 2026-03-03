# Enterprise Hybrid Network Topology — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add VPC, VPN, Direct Connect, NACL, Load Balancer, MPLS, VLAN, Transit Gateway, and compliance zone support across the full stack — models, store, knowledge graph, diagnosis pipeline, topology UI, and War Room.

**Architecture:** Layered extension of existing patterns. New Pydantic models in `models.py`, new SQLite tables + CRUD in `topology_store.py`, new node/edge types in `knowledge_graph.py`, new `nacl_evaluator` pipeline node, updated pathfinder/synthesizer/report_generator, new React Flow node components, and new War Room evidence panels.

**Tech Stack:** Python 3.14, Pydantic v2, SQLite, NetworkX, LangGraph, React 18, TypeScript, ReactFlow, Tailwind CSS

---

## Task 1: New Enums + Pydantic Models

**Files:**
- Modify: `backend/src/network/models.py`
- Create: `backend/tests/test_enterprise_models.py`

**Context:** `models.py` has existing enums (DeviceType, FirewallVendor, etc.) at lines 11-74, infrastructure entities at lines 79-121, and relationship models at lines 126-163. New models follow the same Pydantic BaseModel pattern.

**Changes:**

1. Add new enums after existing enums (~line 74):

```python
class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OCI = "oci"

class TunnelType(str, Enum):
    IPSEC = "ipsec"
    GRE = "gre"
    SSL = "ssl"

class DirectConnectProvider(str, Enum):
    AWS_DX = "aws_dx"
    AZURE_ER = "azure_er"
    OCI_FC = "oci_fc"

class LBType(str, Enum):
    ALB = "alb"
    NLB = "nlb"
    AZURE_LB = "azure_lb"
    HAPROXY = "haproxy"

class LBScheme(str, Enum):
    INTERNET_FACING = "internet_facing"
    INTERNAL = "internal"

class ComplianceStandard(str, Enum):
    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    CUSTOM = "custom"

class NACLDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"

class ConnectivityStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
```

2. Add to existing `DeviceType` enum (~line 11):

```python
VPC = "vpc"
TRANSIT_GATEWAY = "transit_gateway"
LOAD_BALANCER = "load_balancer"
VPN_GATEWAY = "vpn_gateway"
DIRECT_CONNECT = "direct_connect"
NACL = "nacl"
```

3. Add new infrastructure models after `Workload` (~line 121):

```python
class VPC(BaseModel):
    id: str
    name: str
    cloud_provider: CloudProvider = CloudProvider.AWS
    region: str = ""
    cidr_blocks: list[str] = Field(default_factory=list)
    account_id: str = ""
    compliance_zone: str = ""

class RouteTable(BaseModel):
    id: str
    vpc_id: str
    name: str = ""
    is_main: bool = False

class VPCPeering(BaseModel):
    id: str
    requester_vpc_id: str
    accepter_vpc_id: str
    status: str = "active"
    cidr_routes: list[str] = Field(default_factory=list)

class TransitGateway(BaseModel):
    id: str
    name: str
    cloud_provider: CloudProvider = CloudProvider.AWS
    region: str = ""
    attached_vpc_ids: list[str] = Field(default_factory=list)
    route_table_id: str = ""

class VPNTunnel(BaseModel):
    id: str
    name: str
    tunnel_type: TunnelType = TunnelType.IPSEC
    local_gateway_id: str = ""
    remote_gateway_ip: str = ""
    local_cidrs: list[str] = Field(default_factory=list)
    remote_cidrs: list[str] = Field(default_factory=list)
    encryption: str = "AES-256-GCM"
    ike_version: str = "IKEv2"
    status: ConnectivityStatus = ConnectivityStatus.UP

class DirectConnect(BaseModel):
    id: str
    name: str
    provider: DirectConnectProvider = DirectConnectProvider.AWS_DX
    bandwidth_mbps: int = 1000
    location: str = ""
    vlan_id: int = 0
    bgp_asn: int = 0
    status: ConnectivityStatus = ConnectivityStatus.UP

class NACL(BaseModel):
    id: str
    name: str
    vpc_id: str = ""
    subnet_ids: list[str] = Field(default_factory=list)
    is_default: bool = False

class NACLRule(BaseModel):
    id: str
    nacl_id: str
    direction: NACLDirection = NACLDirection.INBOUND
    rule_number: int = 100
    protocol: str = "tcp"
    cidr: str = "0.0.0.0/0"
    port_range_from: int = 0
    port_range_to: int = 65535
    action: PolicyAction = PolicyAction.ALLOW

class LoadBalancer(BaseModel):
    id: str
    name: str
    lb_type: LBType = LBType.ALB
    scheme: LBScheme = LBScheme.INTERNAL
    vpc_id: str = ""
    listeners: list[dict] = Field(default_factory=list)
    health_check_path: str = "/health"

class LBTargetGroup(BaseModel):
    id: str
    lb_id: str
    name: str = ""
    protocol: str = "tcp"
    port: int = 80
    target_ids: list[str] = Field(default_factory=list)
    health_status: str = "healthy"

class VLAN(BaseModel):
    id: str
    vlan_number: int
    name: str = ""
    trunk_ports: list[str] = Field(default_factory=list)
    access_ports: list[str] = Field(default_factory=list)
    site: str = ""

class MPLSCircuit(BaseModel):
    id: str
    name: str
    label: int = 0
    provider: str = ""
    bandwidth_mbps: int = 100
    endpoints: list[str] = Field(default_factory=list)
    qos_class: str = ""

class ComplianceZone(BaseModel):
    id: str
    name: str
    standard: ComplianceStandard = ComplianceStandard.PCI_DSS
    description: str = ""
    subnet_ids: list[str] = Field(default_factory=list)
    vpc_ids: list[str] = Field(default_factory=list)
```

**Tests (`backend/tests/test_enterprise_models.py`):**

```python
import pytest
from src.network.models import (
    VPC, CloudProvider, TransitGateway, VPNTunnel, TunnelType,
    DirectConnect, DirectConnectProvider, NACL, NACLRule, NACLDirection,
    LoadBalancer, LBType, LBScheme, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone, ComplianceStandard,
    VPCPeering, RouteTable, DeviceType, ConnectivityStatus, PolicyAction,
)


def test_vpc_defaults():
    vpc = VPC(id="vpc-1", name="prod-vpc")
    assert vpc.cloud_provider == CloudProvider.AWS
    assert vpc.cidr_blocks == []


def test_vpc_with_cidrs():
    vpc = VPC(id="vpc-1", name="prod", cidr_blocks=["10.0.0.0/16", "10.1.0.0/16"])
    assert len(vpc.cidr_blocks) == 2


def test_vpn_tunnel_defaults():
    vpn = VPNTunnel(id="vpn-1", name="site-to-cloud")
    assert vpn.tunnel_type == TunnelType.IPSEC
    assert vpn.encryption == "AES-256-GCM"
    assert vpn.status == ConnectivityStatus.UP


def test_direct_connect_provider():
    dx = DirectConnect(id="dx-1", name="prod-dx", provider=DirectConnectProvider.AZURE_ER)
    assert dx.provider == DirectConnectProvider.AZURE_ER
    assert dx.bandwidth_mbps == 1000


def test_nacl_rule_ordering():
    r1 = NACLRule(id="r1", nacl_id="nacl-1", rule_number=100, action=PolicyAction.ALLOW)
    r2 = NACLRule(id="r2", nacl_id="nacl-1", rule_number=200, action=PolicyAction.DENY)
    assert r1.rule_number < r2.rule_number


def test_load_balancer_defaults():
    lb = LoadBalancer(id="lb-1", name="api-lb")
    assert lb.lb_type == LBType.ALB
    assert lb.scheme == LBScheme.INTERNAL


def test_compliance_zone():
    cz = ComplianceZone(id="cz-1", name="CDE", standard=ComplianceStandard.PCI_DSS, subnet_ids=["s1", "s2"])
    assert len(cz.subnet_ids) == 2
    assert cz.standard == ComplianceStandard.PCI_DSS


def test_device_type_new_values():
    assert DeviceType.VPC == "vpc"
    assert DeviceType.TRANSIT_GATEWAY == "transit_gateway"
    assert DeviceType.LOAD_BALANCER == "load_balancer"
    assert DeviceType.NACL == "nacl"


def test_transit_gateway():
    tgw = TransitGateway(id="tgw-1", name="main-hub", attached_vpc_ids=["vpc-1", "vpc-2"])
    assert len(tgw.attached_vpc_ids) == 2


def test_vlan():
    vlan = VLAN(id="vlan-100", vlan_number=100, name="mgmt", site="dc-east")
    assert vlan.vlan_number == 100


def test_mpls_circuit():
    mpls = MPLSCircuit(id="mpls-1", name="wan-backbone", label=1000, bandwidth_mbps=10000)
    assert mpls.label == 1000


def test_vpc_peering():
    p = VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2")
    assert p.status == "active"


def test_route_table():
    rt = RouteTable(id="rt-1", vpc_id="vpc-1", name="main", is_main=True)
    assert rt.is_main is True
```

**Run:** `cd backend && python3 -m pytest tests/test_enterprise_models.py -v`

**Commit:** `git commit -m "feat(models): add enterprise hybrid network entity models"`

---

## Task 2: Topology Store — New Tables + CRUD

**Files:**
- Modify: `backend/src/network/topology_store.py`
- Modify: `backend/src/network/models.py` (import updates only)
- Create: `backend/tests/test_enterprise_store.py`

**Context:** `topology_store.py` has `_init_tables()` at line 31 creating all existing tables (lines 33-114). CRUD methods follow the pattern: `add_X()` → INSERT OR REPLACE, `list_X()` → SELECT all, `get_X()` → SELECT by id. Lists with JSON columns (like `src_ips` in firewall_rules) use `json.dumps()`/`json.loads()`.

**Changes:**

1. Add imports at top of `topology_store.py` (~line 7):

```python
from .models import (
    Device, Interface, Subnet, Zone, Workload,
    Route, NATRule, FirewallRule,
    Flow, Trace, TraceHop, FlowVerdict,
    AdapterConfig,
    VPC, RouteTable, VPCPeering, TransitGateway,
    VPNTunnel, DirectConnect,
    NACL, NACLRule,
    LoadBalancer, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone,
)
```

2. Add new CREATE TABLE statements inside `_init_tables()` (after line 113, before the final `"""`):

```sql
CREATE TABLE IF NOT EXISTS vpcs (
    id TEXT PRIMARY KEY, name TEXT, cloud_provider TEXT,
    region TEXT, cidr_blocks TEXT, account_id TEXT, compliance_zone TEXT
);
CREATE TABLE IF NOT EXISTS route_tables (
    id TEXT PRIMARY KEY, vpc_id TEXT, name TEXT, is_main INTEGER,
    FOREIGN KEY (vpc_id) REFERENCES vpcs(id)
);
CREATE TABLE IF NOT EXISTS vpc_peerings (
    id TEXT PRIMARY KEY, requester_vpc_id TEXT, accepter_vpc_id TEXT,
    status TEXT, cidr_routes TEXT
);
CREATE TABLE IF NOT EXISTS transit_gateways (
    id TEXT PRIMARY KEY, name TEXT, cloud_provider TEXT,
    region TEXT, attached_vpc_ids TEXT, route_table_id TEXT
);
CREATE TABLE IF NOT EXISTS vpn_tunnels (
    id TEXT PRIMARY KEY, name TEXT, tunnel_type TEXT,
    local_gateway_id TEXT, remote_gateway_ip TEXT,
    local_cidrs TEXT, remote_cidrs TEXT,
    encryption TEXT, ike_version TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS direct_connects (
    id TEXT PRIMARY KEY, name TEXT, provider TEXT,
    bandwidth_mbps INTEGER, location TEXT, vlan_id INTEGER,
    bgp_asn INTEGER, status TEXT
);
CREATE TABLE IF NOT EXISTS nacls (
    id TEXT PRIMARY KEY, name TEXT, vpc_id TEXT,
    subnet_ids TEXT, is_default INTEGER
);
CREATE TABLE IF NOT EXISTS nacl_rules (
    id TEXT PRIMARY KEY, nacl_id TEXT, direction TEXT,
    rule_number INTEGER, protocol TEXT, cidr TEXT,
    port_range_from INTEGER, port_range_to INTEGER, action TEXT,
    FOREIGN KEY (nacl_id) REFERENCES nacls(id)
);
CREATE TABLE IF NOT EXISTS load_balancers (
    id TEXT PRIMARY KEY, name TEXT, lb_type TEXT,
    scheme TEXT, vpc_id TEXT, listeners TEXT, health_check_path TEXT
);
CREATE TABLE IF NOT EXISTS lb_target_groups (
    id TEXT PRIMARY KEY, lb_id TEXT, name TEXT,
    protocol TEXT, port INTEGER, target_ids TEXT, health_status TEXT,
    FOREIGN KEY (lb_id) REFERENCES load_balancers(id)
);
CREATE TABLE IF NOT EXISTS vlans (
    id TEXT PRIMARY KEY, vlan_number INTEGER, name TEXT,
    trunk_ports TEXT, access_ports TEXT, site TEXT
);
CREATE TABLE IF NOT EXISTS mpls_circuits (
    id TEXT PRIMARY KEY, name TEXT, label INTEGER,
    provider TEXT, bandwidth_mbps INTEGER, endpoints TEXT, qos_class TEXT
);
CREATE TABLE IF NOT EXISTS compliance_zones (
    id TEXT PRIMARY KEY, name TEXT, standard TEXT,
    description TEXT, subnet_ids TEXT, vpc_ids TEXT
);
CREATE INDEX IF NOT EXISTS idx_nacl_rules_nacl ON nacl_rules(nacl_id);
CREATE INDEX IF NOT EXISTS idx_lb_targets_lb ON lb_target_groups(lb_id);
CREATE INDEX IF NOT EXISTS idx_route_tables_vpc ON route_tables(vpc_id);
```

3. Add CRUD methods. These follow the exact same patterns as existing methods. Add after `list_flows()` at end of file (~line 441):

```python
# ── VPC CRUD ──
def add_vpc(self, vpc: VPC) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO vpcs VALUES (?,?,?,?,?,?,?)",
        (vpc.id, vpc.name, vpc.cloud_provider.value, vpc.region,
         json.dumps(vpc.cidr_blocks), vpc.account_id, vpc.compliance_zone),
    )
    conn.commit(); conn.close()

def list_vpcs(self) -> list[VPC]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM vpcs").fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["cidr_blocks"] = json.loads(d["cidr_blocks"]) if d["cidr_blocks"] else []
        results.append(VPC(**d))
    return results

def get_vpc(self, vpc_id: str) -> Optional[VPC]:
    conn = self._conn()
    row = conn.execute("SELECT * FROM vpcs WHERE id=?", (vpc_id,)).fetchone()
    conn.close()
    if not row: return None
    d = dict(row)
    d["cidr_blocks"] = json.loads(d["cidr_blocks"]) if d["cidr_blocks"] else []
    return VPC(**d)

# ── Route Table CRUD ──
def add_route_table(self, rt: RouteTable) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO route_tables VALUES (?,?,?,?)",
        (rt.id, rt.vpc_id, rt.name, int(rt.is_main)),
    )
    conn.commit(); conn.close()

def list_route_tables(self, vpc_id: Optional[str] = None) -> list[RouteTable]:
    conn = self._conn()
    if vpc_id:
        rows = conn.execute("SELECT * FROM route_tables WHERE vpc_id=?", (vpc_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM route_tables").fetchall()
    conn.close()
    return [RouteTable(**{**dict(r), "is_main": bool(r["is_main"])}) for r in rows]

# ── VPC Peering CRUD ──
def add_vpc_peering(self, p: VPCPeering) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO vpc_peerings VALUES (?,?,?,?,?)",
        (p.id, p.requester_vpc_id, p.accepter_vpc_id, p.status,
         json.dumps(p.cidr_routes)),
    )
    conn.commit(); conn.close()

def list_vpc_peerings(self) -> list[VPCPeering]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM vpc_peerings").fetchall()
    conn.close()
    return [VPCPeering(**{**dict(r), "cidr_routes": json.loads(r["cidr_routes"]) if r["cidr_routes"] else []}) for r in rows]

# ── Transit Gateway CRUD ──
def add_transit_gateway(self, tgw: TransitGateway) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO transit_gateways VALUES (?,?,?,?,?,?)",
        (tgw.id, tgw.name, tgw.cloud_provider.value, tgw.region,
         json.dumps(tgw.attached_vpc_ids), tgw.route_table_id),
    )
    conn.commit(); conn.close()

def list_transit_gateways(self) -> list[TransitGateway]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM transit_gateways").fetchall()
    conn.close()
    return [TransitGateway(**{**dict(r), "attached_vpc_ids": json.loads(r["attached_vpc_ids"]) if r["attached_vpc_ids"] else []}) for r in rows]

# ── VPN Tunnel CRUD ──
def add_vpn_tunnel(self, vpn: VPNTunnel) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO vpn_tunnels VALUES (?,?,?,?,?,?,?,?,?,?)",
        (vpn.id, vpn.name, vpn.tunnel_type.value, vpn.local_gateway_id,
         vpn.remote_gateway_ip, json.dumps(vpn.local_cidrs), json.dumps(vpn.remote_cidrs),
         vpn.encryption, vpn.ike_version, vpn.status.value),
    )
    conn.commit(); conn.close()

def list_vpn_tunnels(self) -> list[VPNTunnel]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM vpn_tunnels").fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["local_cidrs"] = json.loads(d["local_cidrs"]) if d["local_cidrs"] else []
        d["remote_cidrs"] = json.loads(d["remote_cidrs"]) if d["remote_cidrs"] else []
        results.append(VPNTunnel(**d))
    return results

# ── Direct Connect CRUD ──
def add_direct_connect(self, dx: DirectConnect) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO direct_connects VALUES (?,?,?,?,?,?,?,?)",
        (dx.id, dx.name, dx.provider.value, dx.bandwidth_mbps,
         dx.location, dx.vlan_id, dx.bgp_asn, dx.status.value),
    )
    conn.commit(); conn.close()

def list_direct_connects(self) -> list[DirectConnect]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM direct_connects").fetchall()
    conn.close()
    return [DirectConnect(**dict(r)) for r in rows]

# ── NACL CRUD ──
def add_nacl(self, nacl: NACL) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO nacls VALUES (?,?,?,?,?)",
        (nacl.id, nacl.name, nacl.vpc_id, json.dumps(nacl.subnet_ids), int(nacl.is_default)),
    )
    conn.commit(); conn.close()

def list_nacls(self, vpc_id: Optional[str] = None) -> list[NACL]:
    conn = self._conn()
    if vpc_id:
        rows = conn.execute("SELECT * FROM nacls WHERE vpc_id=?", (vpc_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM nacls").fetchall()
    conn.close()
    return [NACL(**{**dict(r), "subnet_ids": json.loads(r["subnet_ids"]) if r["subnet_ids"] else [], "is_default": bool(r["is_default"])}) for r in rows]

# ── NACL Rule CRUD ──
def add_nacl_rule(self, rule: NACLRule) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO nacl_rules VALUES (?,?,?,?,?,?,?,?,?)",
        (rule.id, rule.nacl_id, rule.direction.value, rule.rule_number,
         rule.protocol, rule.cidr, rule.port_range_from, rule.port_range_to,
         rule.action.value),
    )
    conn.commit(); conn.close()

def list_nacl_rules(self, nacl_id: str) -> list[NACLRule]:
    conn = self._conn()
    rows = conn.execute(
        "SELECT * FROM nacl_rules WHERE nacl_id=? ORDER BY rule_number",
        (nacl_id,),
    ).fetchall()
    conn.close()
    return [NACLRule(**dict(r)) for r in rows]

# ── Load Balancer CRUD ──
def add_load_balancer(self, lb: LoadBalancer) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO load_balancers VALUES (?,?,?,?,?,?,?)",
        (lb.id, lb.name, lb.lb_type.value, lb.scheme.value, lb.vpc_id,
         json.dumps(lb.listeners), lb.health_check_path),
    )
    conn.commit(); conn.close()

def list_load_balancers(self) -> list[LoadBalancer]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM load_balancers").fetchall()
    conn.close()
    return [LoadBalancer(**{**dict(r), "listeners": json.loads(r["listeners"]) if r["listeners"] else []}) for r in rows]

# ── LB Target Group CRUD ──
def add_lb_target_group(self, tg: LBTargetGroup) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO lb_target_groups VALUES (?,?,?,?,?,?,?)",
        (tg.id, tg.lb_id, tg.name, tg.protocol, tg.port,
         json.dumps(tg.target_ids), tg.health_status),
    )
    conn.commit(); conn.close()

def list_lb_target_groups(self, lb_id: Optional[str] = None) -> list[LBTargetGroup]:
    conn = self._conn()
    if lb_id:
        rows = conn.execute("SELECT * FROM lb_target_groups WHERE lb_id=?", (lb_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM lb_target_groups").fetchall()
    conn.close()
    return [LBTargetGroup(**{**dict(r), "target_ids": json.loads(r["target_ids"]) if r["target_ids"] else []}) for r in rows]

# ── VLAN CRUD ──
def add_vlan(self, vlan: VLAN) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO vlans VALUES (?,?,?,?,?,?)",
        (vlan.id, vlan.vlan_number, vlan.name,
         json.dumps(vlan.trunk_ports), json.dumps(vlan.access_ports), vlan.site),
    )
    conn.commit(); conn.close()

def list_vlans(self) -> list[VLAN]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM vlans").fetchall()
    conn.close()
    return [VLAN(**{**dict(r), "trunk_ports": json.loads(r["trunk_ports"]) if r["trunk_ports"] else [], "access_ports": json.loads(r["access_ports"]) if r["access_ports"] else []}) for r in rows]

# ── MPLS Circuit CRUD ──
def add_mpls_circuit(self, mpls: MPLSCircuit) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO mpls_circuits VALUES (?,?,?,?,?,?,?)",
        (mpls.id, mpls.name, mpls.label, mpls.provider,
         mpls.bandwidth_mbps, json.dumps(mpls.endpoints), mpls.qos_class),
    )
    conn.commit(); conn.close()

def list_mpls_circuits(self) -> list[MPLSCircuit]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM mpls_circuits").fetchall()
    conn.close()
    return [MPLSCircuit(**{**dict(r), "endpoints": json.loads(r["endpoints"]) if r["endpoints"] else []}) for r in rows]

# ── Compliance Zone CRUD ──
def add_compliance_zone(self, cz: ComplianceZone) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO compliance_zones VALUES (?,?,?,?,?,?)",
        (cz.id, cz.name, cz.standard.value, cz.description,
         json.dumps(cz.subnet_ids), json.dumps(cz.vpc_ids)),
    )
    conn.commit(); conn.close()

def list_compliance_zones(self) -> list[ComplianceZone]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM compliance_zones").fetchall()
    conn.close()
    return [ComplianceZone(**{**dict(r), "subnet_ids": json.loads(r["subnet_ids"]) if r["subnet_ids"] else [], "vpc_ids": json.loads(r["vpc_ids"]) if r["vpc_ids"] else []}) for r in rows]
```

**Tests (`backend/tests/test_enterprise_store.py`):**

```python
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.models import (
    VPC, CloudProvider, VPCPeering, TransitGateway, RouteTable,
    VPNTunnel, TunnelType, DirectConnect, DirectConnectProvider,
    NACL, NACLRule, NACLDirection, PolicyAction,
    LoadBalancer, LBType, LBScheme, LBTargetGroup,
    VLAN, MPLSCircuit, ComplianceZone, ComplianceStandard,
)


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=str(tmp_path / "test.db"))


def test_vpc_crud(store):
    vpc = VPC(id="vpc-1", name="prod", cloud_provider=CloudProvider.AWS,
              cidr_blocks=["10.0.0.0/16"])
    store.add_vpc(vpc)
    result = store.get_vpc("vpc-1")
    assert result.name == "prod"
    assert result.cidr_blocks == ["10.0.0.0/16"]
    all_vpcs = store.list_vpcs()
    assert len(all_vpcs) == 1


def test_transit_gateway_crud(store):
    tgw = TransitGateway(id="tgw-1", name="hub", attached_vpc_ids=["vpc-1", "vpc-2"])
    store.add_transit_gateway(tgw)
    result = store.list_transit_gateways()
    assert len(result) == 1
    assert result[0].attached_vpc_ids == ["vpc-1", "vpc-2"]


def test_vpn_tunnel_crud(store):
    vpn = VPNTunnel(id="vpn-1", name="site-vpn", tunnel_type=TunnelType.IPSEC,
                    local_cidrs=["10.0.0.0/16"], remote_cidrs=["172.16.0.0/12"])
    store.add_vpn_tunnel(vpn)
    result = store.list_vpn_tunnels()
    assert len(result) == 1
    assert result[0].local_cidrs == ["10.0.0.0/16"]


def test_direct_connect_crud(store):
    dx = DirectConnect(id="dx-1", name="prod-dx", provider=DirectConnectProvider.AWS_DX,
                       bandwidth_mbps=10000)
    store.add_direct_connect(dx)
    result = store.list_direct_connects()
    assert result[0].bandwidth_mbps == 10000


def test_nacl_and_rules_crud(store):
    nacl = NACL(id="nacl-1", name="prod-nacl", vpc_id="vpc-1", subnet_ids=["s1"])
    store.add_nacl(nacl)
    r1 = NACLRule(id="nr-1", nacl_id="nacl-1", rule_number=100,
                  direction=NACLDirection.INBOUND, action=PolicyAction.ALLOW,
                  cidr="10.0.0.0/16", port_range_from=443, port_range_to=443)
    r2 = NACLRule(id="nr-2", nacl_id="nacl-1", rule_number=200,
                  direction=NACLDirection.INBOUND, action=PolicyAction.DENY)
    store.add_nacl_rule(r1)
    store.add_nacl_rule(r2)
    rules = store.list_nacl_rules("nacl-1")
    assert len(rules) == 2
    assert rules[0].rule_number == 100  # Ordered


def test_load_balancer_crud(store):
    lb = LoadBalancer(id="lb-1", name="api-lb", lb_type=LBType.ALB,
                      listeners=[{"port": 443, "protocol": "https"}])
    store.add_load_balancer(lb)
    tg = LBTargetGroup(id="tg-1", lb_id="lb-1", port=8080, target_ids=["d-1", "d-2"])
    store.add_lb_target_group(tg)
    lbs = store.list_load_balancers()
    assert lbs[0].listeners[0]["port"] == 443
    tgs = store.list_lb_target_groups(lb_id="lb-1")
    assert len(tgs[0].target_ids) == 2


def test_vlan_crud(store):
    vlan = VLAN(id="vlan-100", vlan_number=100, name="mgmt", trunk_ports=["ge-0/0/1"])
    store.add_vlan(vlan)
    result = store.list_vlans()
    assert result[0].vlan_number == 100


def test_mpls_crud(store):
    mpls = MPLSCircuit(id="mpls-1", name="wan", label=1000,
                       endpoints=["dc-east", "dc-west"])
    store.add_mpls_circuit(mpls)
    result = store.list_mpls_circuits()
    assert result[0].endpoints == ["dc-east", "dc-west"]


def test_compliance_zone_crud(store):
    cz = ComplianceZone(id="cz-1", name="CDE", standard=ComplianceStandard.PCI_DSS,
                        subnet_ids=["s1", "s2"], vpc_ids=["vpc-1"])
    store.add_compliance_zone(cz)
    result = store.list_compliance_zones()
    assert result[0].standard == ComplianceStandard.PCI_DSS
    assert len(result[0].subnet_ids) == 2


def test_vpc_peering_crud(store):
    p = VPCPeering(id="pcx-1", requester_vpc_id="vpc-1", accepter_vpc_id="vpc-2",
                   cidr_routes=["10.0.0.0/16"])
    store.add_vpc_peering(p)
    result = store.list_vpc_peerings()
    assert result[0].cidr_routes == ["10.0.0.0/16"]


def test_route_table_crud(store):
    rt = RouteTable(id="rt-1", vpc_id="vpc-1", name="main", is_main=True)
    store.add_route_table(rt)
    result = store.list_route_tables(vpc_id="vpc-1")
    assert result[0].is_main is True
```

**Run:** `cd backend && python3 -m pytest tests/test_enterprise_store.py -v`

**Commit:** `git commit -m "feat(store): add enterprise hybrid network tables and CRUD"`

---

## Task 3: Knowledge Graph — New Node/Edge Types + Topology Penalties

**Files:**
- Modify: `backend/src/network/knowledge_graph.py`
- Create: `backend/tests/test_enterprise_graph.py`

**Context:** `NetworkKnowledgeGraph` (knowledge_graph.py) loads entities from `TopologyStore` in `load_from_store()` (lines 32-69). Nodes have `node_type` attribute. Edges have `edge_type`, `confidence`, `source` attributes. `find_k_shortest_paths()` at line 160 uses a dual cost model with `_TOPOLOGY_PENALTIES` dict at line 11.

**Changes:**

1. Update `_TOPOLOGY_PENALTIES` (line 11):

```python
_TOPOLOGY_PENALTIES = {
    "vrf_boundary": 0.3,
    "inter_site": 0.2,
    "overlay_tunnel": 0.15,
    "vpn_tunnel": 0.15,
    "direct_connect": 0.05,
    "mpls_circuit": 0.05,
    "cross_vpc": 0.25,
    "transit_gateway": 0.1,
    "load_balancer": 0.1,
    "low_bandwidth": 0.1,
}
```

2. Update imports (line 5):

```python
from .models import (
    Device, Subnet, Zone, Interface, EdgeMetadata, EdgeSource, Route,
    VPC, TransitGateway, VPNTunnel, DirectConnect, NACL, LoadBalancer,
    LBTargetGroup, VLAN, MPLSCircuit, ComplianceZone, VPCPeering,
)
```

3. Extend `load_from_store()` (after line 69, before the method ends):

```python
# Load VPCs
for vpc in self.store.list_vpcs():
    self.graph.add_node(vpc.id, **vpc.model_dump(), node_type="vpc")
    # VPC contains subnets — find subnets whose CIDR falls within VPC CIDRs
    for s in subnets:
        for vpc_cidr in vpc.cidr_blocks:
            try:
                import ipaddress
                if ipaddress.ip_network(s.cidr, strict=False).subnet_of(
                    ipaddress.ip_network(vpc_cidr, strict=False)
                ):
                    self.graph.add_edge(vpc.id, s.id, edge_type="vpc_contains",
                                        confidence=1.0, source=EdgeSource.MANUAL.value)
            except (ValueError, TypeError):
                pass

# Load VPC peerings
for p in self.store.list_vpc_peerings():
    self.graph.add_edge(p.requester_vpc_id, p.accepter_vpc_id,
                        edge_type="peered_to", confidence=0.95,
                        source=EdgeSource.API.value, peering_id=p.id)
    self.graph.add_edge(p.accepter_vpc_id, p.requester_vpc_id,
                        edge_type="peered_to", confidence=0.95,
                        source=EdgeSource.API.value, peering_id=p.id)

# Load Transit Gateways
for tgw in self.store.list_transit_gateways():
    self.graph.add_node(tgw.id, **tgw.model_dump(), node_type="transit_gateway")
    for vpc_id in tgw.attached_vpc_ids:
        self.graph.add_edge(vpc_id, tgw.id, edge_type="attached_to",
                            confidence=0.95, source=EdgeSource.API.value)
        self.graph.add_edge(tgw.id, vpc_id, edge_type="attached_to",
                            confidence=0.95, source=EdgeSource.API.value)

# Load VPN Tunnels
for vpn in self.store.list_vpn_tunnels():
    self.graph.add_node(vpn.id, **vpn.model_dump(), node_type="vpn_tunnel")
    if vpn.local_gateway_id:
        self.graph.add_edge(vpn.local_gateway_id, vpn.id, edge_type="tunnel_to",
                            confidence=0.9, source=EdgeSource.API.value)
        self.graph.add_edge(vpn.id, vpn.local_gateway_id, edge_type="tunnel_to",
                            confidence=0.9, source=EdgeSource.API.value)

# Load Direct Connects
for dx in self.store.list_direct_connects():
    self.graph.add_node(dx.id, **dx.model_dump(), node_type="direct_connect")

# Load NACLs
for nacl in self.store.list_nacls():
    self.graph.add_node(nacl.id, **nacl.model_dump(), node_type="nacl")
    for sid in nacl.subnet_ids:
        self.graph.add_edge(nacl.id, sid, edge_type="nacl_guards",
                            confidence=1.0, source=EdgeSource.API.value)

# Load Load Balancers
for lb in self.store.list_load_balancers():
    self.graph.add_node(lb.id, **lb.model_dump(), node_type="load_balancer")
    for tg in self.store.list_lb_target_groups(lb_id=lb.id):
        for target_id in tg.target_ids:
            self.graph.add_edge(lb.id, target_id, edge_type="load_balances",
                                confidence=0.9, source=EdgeSource.API.value,
                                port=tg.port, protocol=tg.protocol)

# Load VLANs
for vlan in self.store.list_vlans():
    self.graph.add_node(vlan.id, **vlan.model_dump(), node_type="vlan")

# Load MPLS Circuits
for mpls in self.store.list_mpls_circuits():
    self.graph.add_node(mpls.id, **mpls.model_dump(), node_type="mpls")
    # Connect endpoints
    endpoints = mpls.endpoints
    for i in range(len(endpoints) - 1):
        self.graph.add_edge(endpoints[i], endpoints[i + 1],
                            edge_type="mpls_path", confidence=0.95,
                            source=EdgeSource.API.value, label=mpls.label)

# Load Compliance Zones
for cz in self.store.list_compliance_zones():
    self.graph.add_node(cz.id, **cz.model_dump(), node_type="compliance_zone")
```

4. Update `find_k_shortest_paths()` (line 160) — add new penalty cases in the cost calculation loop (~line 173):

```python
if data.get("edge_type") == "tunnel_to":
    penalty += _TOPOLOGY_PENALTIES["vpn_tunnel"]
if data.get("edge_type") == "attached_to":
    penalty += _TOPOLOGY_PENALTIES["transit_gateway"]
if data.get("edge_type") == "load_balances":
    penalty += _TOPOLOGY_PENALTIES["load_balancer"]
if data.get("edge_type") == "peered_to":
    penalty += _TOPOLOGY_PENALTIES["cross_vpc"]
if data.get("edge_type") == "mpls_path":
    penalty += _TOPOLOGY_PENALTIES["mpls_circuit"]
```

**Tests (`backend/tests/test_enterprise_graph.py`):**

Test that VPCs, peerings, TGWs, tunnels, LBs, NACLs are loaded into graph with correct node_types and edge_types. Test that paths through VPC peering have `cross_vpc` penalty. Test that VPN tunnel paths have `vpn_tunnel` penalty.

**Run:** `cd backend && python3 -m pytest tests/test_enterprise_graph.py -v`

**Commit:** `git commit -m "feat(graph): add enterprise entity loading and topology penalties"`

---

## Task 4: Pipeline State + NACL Evaluator + Graph Rewiring

**Files:**
- Modify: `backend/src/agents/network/state.py`
- Create: `backend/src/agents/network/nacl_evaluator.py`
- Modify: `backend/src/agents/network/graph.py`
- Modify: `backend/src/agents/network/graph_pathfinder.py`
- Create: `backend/tests/test_nacl_evaluator.py`

**Context:** `NetworkPipelineState` (state.py) is a TypedDict at line 7. The pipeline graph (graph.py) wires: `input_resolver → pathfinder → traceroute → hop_attributor → firewall_evaluator → nat_resolver → synthesizer → report_generator`. Pathfinder (graph_pathfinder.py) only identifies firewalls in path (lines 56-65).

**Changes:**

1. **`state.py`** — Add new fields after line 51:

```python
# Enterprise constructs in path
nacls_in_path: list[dict]
load_balancers_in_path: list[dict]
vpn_segments: list[dict]
nacl_verdicts: Annotated[list[dict], operator.add]
vpc_boundary_crossings: list[dict]
```

2. **`graph_pathfinder.py`** — Update the path node identification loop (lines 56-65) to also detect NACLs, LBs, VPN tunnels, and VPC crossings:

```python
# After existing firewall detection (keep existing code), add:
nacls = []
lbs = []
vpn_segs = []
vpc_crossings = []
seen_nacls = set()
seen_lbs = set()

for i, path in enumerate(paths):
    prev_vpc = None
    for node_id in path:
        node_data = kg.graph.nodes.get(node_id, {})
        nt = node_data.get("node_type", "")
        dt = node_data.get("device_type", "")

        if nt == "nacl" and node_id not in seen_nacls:
            nacls.append({"device_id": node_id, "device_name": node_data.get("name", ""), "device_type": "nacl"})
            seen_nacls.add(node_id)

        if (nt == "load_balancer" or dt == "load_balancer") and node_id not in seen_lbs:
            lbs.append({"device_id": node_id, "device_name": node_data.get("name", ""), "device_type": "load_balancer"})
            seen_lbs.add(node_id)

        if nt == "vpn_tunnel":
            vpn_segs.append({"device_id": node_id, "name": node_data.get("name", ""),
                             "tunnel_type": node_data.get("tunnel_type", ""), "encryption": node_data.get("encryption", "")})

        if nt == "vpc":
            if prev_vpc and prev_vpc != node_id:
                vpc_crossings.append({"from_vpc": prev_vpc, "to_vpc": node_id})
            prev_vpc = node_id
```

Add to return dict:
```python
"nacls_in_path": nacls,
"load_balancers_in_path": lbs,
"vpn_segments": vpn_segs,
"vpc_boundary_crossings": vpc_crossings,
```

3. **`nacl_evaluator.py`** — New file:

```python
"""NACL evaluator node — stateless rule evaluation for NACLs in path."""
import ipaddress
from src.network.topology_store import TopologyStore
from src.network.models import NACLDirection, PolicyAction


def nacl_evaluator(state: dict, *, store: TopologyStore) -> dict:
    """Evaluate flow against NACLs in path.

    NACLs are stateless: rules are evaluated in order (lowest rule_number first).
    Both INBOUND and OUTBOUND must be checked. First match wins.
    No match = implicit deny.
    """
    nacls = state.get("nacls_in_path", [])
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")
    port = state.get("port", 0)
    protocol = state.get("protocol", "tcp")

    if not nacls:
        return {"nacl_verdicts": [], "evidence": [{"type": "nacl", "detail": "No NACLs in path"}]}

    verdicts = []
    for nacl_info in nacls:
        nacl_id = nacl_info.get("device_id", "")
        rules = store.list_nacl_rules(nacl_id)

        inbound_result = _evaluate_rules(
            [r for r in rules if r.direction == NACLDirection.INBOUND],
            src_ip, dst_ip, port, protocol,
        )
        outbound_result = _evaluate_rules(
            [r for r in rules if r.direction == NACLDirection.OUTBOUND],
            dst_ip, src_ip, port, protocol,  # Outbound: reverse src/dst perspective
        )

        overall = "allow" if inbound_result["action"] == "allow" and outbound_result["action"] == "allow" else "deny"

        verdicts.append({
            "nacl_id": nacl_id,
            "nacl_name": nacl_info.get("device_name", ""),
            "action": overall,
            "inbound": inbound_result,
            "outbound": outbound_result,
        })

    any_deny = any(v["action"] == "deny" for v in verdicts)
    return {
        "nacl_verdicts": verdicts,
        "evidence": [{"type": "nacl",
                       "detail": f"NACL evaluation: {'BLOCKED' if any_deny else 'ALLOWED'} — {len(verdicts)} NACLs checked"}],
    }


def _evaluate_rules(rules: list, src_ip: str, dst_ip: str, port: int, protocol: str) -> dict:
    """Evaluate ordered NACL rules. First match wins."""
    for rule in sorted(rules, key=lambda r: r.rule_number):
        if rule.protocol != "-1" and rule.protocol != protocol:
            continue
        if not _ip_matches(src_ip, rule.cidr) and not _ip_matches(dst_ip, rule.cidr):
            continue
        if rule.protocol != "-1" and not (rule.port_range_from <= port <= rule.port_range_to):
            continue
        return {
            "action": rule.action.value,
            "rule_number": rule.rule_number,
            "matched_rule_id": rule.id,
        }
    # Implicit deny
    return {"action": "deny", "rule_number": -1, "matched_rule_id": "implicit_deny"}


def _ip_matches(ip: str, cidr: str) -> bool:
    if cidr == "0.0.0.0/0":
        return True
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False
```

4. **`graph.py`** — Wire NACL evaluator into the pipeline. Add import and bind:

```python
from src.agents.network.nacl_evaluator import nacl_evaluator
```

In `build_network_diagnostic_graph()` (~line 94), add:

```python
bound_nacl_evaluator = functools.partial(nacl_evaluator, store=kg.store)
async_nacl_evaluator = _make_async_wrapper(bound_nacl_evaluator)
graph.add_node("nacl_evaluator", async_nacl_evaluator)
```

Change edge wiring from sequential to parallel fan-out after hop_attributor:
- Remove: `graph.add_edge("hop_attributor", "firewall_evaluator")`
- Remove: `graph.add_edge("firewall_evaluator", "nat_resolver")`
- Add:
```python
graph.add_edge("hop_attributor", "firewall_evaluator")
graph.add_edge("hop_attributor", "nacl_evaluator")
graph.add_edge("firewall_evaluator", "nat_resolver")
graph.add_edge("nacl_evaluator", "nat_resolver")
```

**Tests (`backend/tests/test_nacl_evaluator.py`):**

```python
import pytest
from src.agents.network.nacl_evaluator import nacl_evaluator, _evaluate_rules
from src.network.models import NACLRule, NACLDirection, PolicyAction


def test_evaluate_rules_allow():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="10.0.0.0/8",
                 port_range_from=443, port_range_to=443),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "allow"
    assert result["rule_number"] == 100


def test_evaluate_rules_deny():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=50, action=PolicyAction.DENY, cidr="10.0.1.0/24",
                 port_range_from=0, port_range_to=65535),
        NACLRule(id="r2", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="10.0.0.0/8",
                 port_range_from=443, port_range_to=443),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "deny"  # Rule 50 matches first


def test_evaluate_rules_implicit_deny():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="192.168.0.0/16",
                 port_range_from=80, port_range_to=80),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "deny"
    assert result["rule_number"] == -1


def test_evaluate_rules_all_traffic():
    rules = [
        NACLRule(id="r1", nacl_id="n1", direction=NACLDirection.INBOUND,
                 rule_number=100, action=PolicyAction.ALLOW, cidr="0.0.0.0/0",
                 protocol="-1", port_range_from=0, port_range_to=65535),
    ]
    result = _evaluate_rules(rules, "10.0.1.5", "10.0.2.10", 443, "tcp")
    assert result["action"] == "allow"


def test_nacl_evaluator_no_nacls():
    state = {"nacls_in_path": [], "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "port": 443, "protocol": "tcp"}
    result = nacl_evaluator(state, store=None)
    assert result["nacl_verdicts"] == []
```

**Run:** `cd backend && python3 -m pytest tests/test_nacl_evaluator.py -v`

**Commit:** `git commit -m "feat(pipeline): add NACL evaluator and wire into diagnosis graph"`

---

## Task 5: Path Synthesizer + NAT Resolver + Report Generator Updates

**Files:**
- Modify: `backend/src/agents/network/path_synthesizer.py`
- Modify: `backend/src/agents/network/nat_resolver.py`
- Modify: `backend/src/agents/network/report_generator.py`
- Create: `backend/tests/test_enterprise_pipeline.py`

**Context:** `path_synthesizer.py` (lines 12-109) merges paths and computes confidence. `nat_resolver.py` (lines 6-105) tracks SNAT/DNAT through firewalls. `report_generator.py` (lines 4-58) builds summary/next_steps.

**Changes:**

1. **`path_synthesizer.py`** — Add VPN/LB annotations to `final_path` dict (after line 98):

```python
final_path = {
    "hops": final_hops,
    "source": path_source,
    "hop_count": len(final_hops),
    "has_nat": len(nat_translations) > 0,
    "blocked": any_deny,
    "vpn_segments": state.get("vpn_segments", []),
    "vpc_crossings": state.get("vpc_boundary_crossings", []),
    "load_balancers": state.get("load_balancers_in_path", []),
}
```

Also factor NACL verdicts into `any_deny` (before line 60):
```python
nacl_verdicts = state.get("nacl_verdicts", [])
nacl_deny = any(v.get("action") == "deny" for v in nacl_verdicts)
```
Update `any_deny` to: `any_deny = any_deny or nacl_deny`

2. **`nat_resolver.py`** — Add LB DNAT handling. After processing firewalls (line 82), add:

```python
# Handle Load Balancer DNAT (VIP -> backend)
for lb in state.get("load_balancers_in_path", []):
    lb_id = lb.get("device_id", "")
    translations.append({
        "device_id": lb_id,
        "direction": "dnat",
        "original_dst": current_dst,
        "translated_dst": "(backend target)",
        "type": "load_balancer",
    })
    identity_chain.append({
        "stage": f"post-lb-{lb_id}",
        "ip": current_dst,
        "port": current_port,
        "device_id": lb_id,
    })
```

3. **`report_generator.py`** — Include NACL verdicts, VPN segments, VPC crossings in summary. Add after line 17:

```python
nacl_verdicts = state.get("nacl_verdicts", [])
vpn_segments = state.get("vpn_segments", [])
vpc_crossings = state.get("vpc_boundary_crossings", [])
lbs_in_path = state.get("load_balancers_in_path", [])
```

Add NACL-specific next_steps (after line 28):
```python
nacl_deny = [v["nacl_name"] for v in nacl_verdicts if v.get("action") == "deny"]
for nacl_name in nacl_deny:
    next_steps.append(f"Review NACL rules on {nacl_name}")
```

Add to executive summary construction — append VPN/VPC info:
```python
if vpn_segments:
    vpn_names = ", ".join(s.get("name", "unknown") for s in vpn_segments)
    summary += f" Path traverses VPN tunnel(s): {vpn_names}."
if vpc_crossings:
    summary += f" Path crosses {len(vpc_crossings)} VPC boundary(ies)."
if lbs_in_path:
    lb_names = ", ".join(lb.get("device_name", "unknown") for lb in lbs_in_path)
    summary += f" Load balancer(s) in path: {lb_names}."
```

**Tests (`backend/tests/test_enterprise_pipeline.py`):**

Tests that NACL deny blocks path, VPN segments appear in final_path, VPC crossings appear in final_path, LB DNAT is recorded in nat_translations, and report includes NACL/VPN/VPC info.

**Run:** `cd backend && python3 -m pytest tests/test_enterprise_pipeline.py -v`

**Commit:** `git commit -m "feat(pipeline): update synthesizer, NAT resolver, report gen for enterprise constructs"`

---

## Task 6: Frontend Types + Topology Palette + DeviceNode Updates

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/TopologyEditor/NodePalette.tsx`
- Modify: `frontend/src/components/TopologyEditor/DeviceNode.tsx`
- Modify: `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx`
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`

**Context:** `NodePalette.tsx` has 7 flat items (lines 9-17). `DeviceNode.tsx` has `deviceIcons` map (lines 13-20) and `statusColors` (lines 22-26). `DevicePropertyPanel.tsx` has a type dropdown (lines 125-137). `TopologyEditorView.tsx` registers nodeTypes (lines 26-29).

**Changes:**

1. **`types/index.ts`** — Add TypeScript interfaces (after existing network types):

```typescript
export interface VPC {
  id: string; name: string; cloud_provider: 'aws'|'azure'|'gcp'|'oci';
  region: string; cidr_blocks: string[]; account_id: string; compliance_zone: string;
}

export interface VPNTunnel {
  id: string; name: string; tunnel_type: 'ipsec'|'gre'|'ssl';
  encryption: string; status: 'up'|'down'|'degraded';
}

export interface DirectConnectInfo {
  id: string; name: string; provider: 'aws_dx'|'azure_er'|'oci_fc';
  bandwidth_mbps: number; status: 'up'|'down'|'degraded';
}

export interface NACLVerdict {
  nacl_id: string; nacl_name: string; action: 'allow'|'deny';
  inbound: { action: string; rule_number: number; matched_rule_id: string };
  outbound: { action: string; rule_number: number; matched_rule_id: string };
}

export interface VPCCrossing {
  from_vpc: string; to_vpc: string;
}

export interface VPNSegment {
  device_id: string; name: string; tunnel_type: string; encryption: string;
}

export interface LBHop {
  device_id: string; device_name: string; device_type: string;
}
```

Add to `NetworkFindings`:
```typescript
nacl_verdicts?: NACLVerdict[];
vpc_boundary_crossings?: VPCCrossing[];
vpn_segments?: VPNSegment[];
load_balancers_in_path?: LBHop[];
```

2. **`NodePalette.tsx`** — Replace flat list with categorized sections:

```typescript
interface PaletteCategory {
  label: string;
  items: PaletteItem[];
}

const paletteCategories: PaletteCategory[] = [
  {
    label: 'Infrastructure',
    items: [
      { type: 'router', label: 'Router', icon: 'router' },
      { type: 'switch', label: 'Switch', icon: 'swap_horiz' },
      { type: 'firewall', label: 'Firewall', icon: 'local_fire_department' },
      { type: 'workload', label: 'Workload', icon: 'memory' },
    ],
  },
  {
    label: 'Cloud',
    items: [
      { type: 'vpc', label: 'VPC / VNet', icon: 'cloud_circle' },
      { type: 'transit_gateway', label: 'Transit Gateway', icon: 'hub' },
      { type: 'load_balancer', label: 'Load Balancer', icon: 'dns' },
      { type: 'cloud_gateway', label: 'Cloud Gateway', icon: 'cloud' },
    ],
  },
  {
    label: 'Connectivity',
    items: [
      { type: 'vpn_tunnel', label: 'VPN Tunnel', icon: 'vpn_lock' },
      { type: 'direct_connect', label: 'Direct Connect', icon: 'cable' },
      { type: 'mpls', label: 'MPLS Circuit', icon: 'conversion_path' },
    ],
  },
  {
    label: 'Security',
    items: [
      { type: 'nacl', label: 'NACL', icon: 'checklist' },
      { type: 'zone', label: 'Zone', icon: 'shield' },
      { type: 'subnet', label: 'Subnet', icon: 'lan' },
      { type: 'compliance_zone', label: 'Compliance Zone', icon: 'verified_user' },
    ],
  },
  {
    label: 'Data Center',
    items: [
      { type: 'vlan', label: 'VLAN', icon: 'label' },
    ],
  },
];
```

Render with category headers:
```tsx
{paletteCategories.map((cat) => (
  <div key={cat.label}>
    <div className="text-[9px] font-mono uppercase tracking-widest px-2 pt-3 pb-1"
         style={{ color: '#64748b' }}>
      {cat.label}
    </div>
    {cat.items.map((item) => (
      <div key={item.type} draggable onDragStart={(e) => onDragStart(e, item.type)}
           className="flex items-center gap-3 px-3 py-2 rounded-lg cursor-grab active:cursor-grabbing border transition-colors hover:border-[#07b6d5]/30"
           style={{ backgroundColor: '#162a2e', borderColor: '#224349', color: '#e2e8f0' }}>
        <span className="material-symbols-outlined text-lg"
              style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}>
          {item.icon}
        </span>
        <span className="text-xs font-mono">{item.label}</span>
      </div>
    ))}
  </div>
))}
```

3. **`DeviceNode.tsx`** — Add new entries to `deviceIcons` and add `deviceColors`:

```typescript
const deviceIcons: Record<string, string> = {
  router: 'router',
  switch: 'swap_horiz',
  firewall: 'local_fire_department',
  workload: 'memory',
  cloud_gateway: 'cloud',
  zone: 'shield',
  vpc: 'cloud_circle',
  transit_gateway: 'hub',
  load_balancer: 'dns',
  vpn_tunnel: 'vpn_lock',
  direct_connect: 'cable',
  nacl: 'checklist',
  vlan: 'label',
  mpls: 'conversion_path',
  compliance_zone: 'verified_user',
};

const deviceColors: Record<string, string> = {
  firewall: '#ef4444',
  vpc: '#3b82f6',
  transit_gateway: '#a855f7',
  load_balancer: '#22c55e',
  vpn_tunnel: '#f97316',
  direct_connect: '#eab308',
  nacl: '#ef4444',
  vlan: '#14b8a6',
  mpls: '#a855f7',
  compliance_zone: '#f59e0b',
};
```

Update icon color line to use `deviceColors`:
```typescript
const iconColor = deviceColors[data.deviceType] || (isFirewall ? '#ef4444' : '#f59e0b');
```

4. **`DevicePropertyPanel.tsx`** — Add new options to the type dropdown (lines 131-136):

```typescript
<option value="vpc">VPC / VNet</option>
<option value="transit_gateway">Transit Gateway</option>
<option value="load_balancer">Load Balancer</option>
<option value="vpn_tunnel">VPN Tunnel</option>
<option value="direct_connect">Direct Connect</option>
<option value="nacl">NACL</option>
<option value="vlan">VLAN</option>
<option value="mpls">MPLS Circuit</option>
<option value="compliance_zone">Compliance Zone</option>
```

Add type-specific fields that appear conditionally after the Zone field:

```tsx
{/* VPC-specific fields */}
{deviceType === 'vpc' && (
  <>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Cloud Provider</label>
      <select value={cloudProvider} onChange={(e) => setCloudProvider(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle}>
        <option value="aws">AWS</option>
        <option value="azure">Azure</option>
        <option value="gcp">GCP</option>
        <option value="oci">Oracle Cloud</option>
      </select>
    </div>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Region</label>
      <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1"
             className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle} />
    </div>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>CIDR Blocks</label>
      <input type="text" value={cidr} onChange={(e) => setCidr(e.target.value)} placeholder="10.0.0.0/16, 10.1.0.0/16"
             className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle} />
    </div>
  </>
)}

{/* VPN-specific fields */}
{deviceType === 'vpn_tunnel' && (
  <>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Tunnel Type</label>
      <select value={tunnelType} onChange={(e) => setTunnelType(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle}>
        <option value="ipsec">IPSec</option>
        <option value="gre">GRE</option>
        <option value="ssl">SSL VPN</option>
      </select>
    </div>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Encryption</label>
      <input type="text" value={encryption} onChange={(e) => setEncryption(e.target.value)} placeholder="AES-256-GCM"
             className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle} />
    </div>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Remote Gateway</label>
      <input type="text" value={remoteGateway} onChange={(e) => setRemoteGateway(e.target.value)} placeholder="203.0.113.1"
             className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle} />
    </div>
  </>
)}

{/* Load Balancer fields */}
{deviceType === 'load_balancer' && (
  <>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>LB Type</label>
      <select value={lbType} onChange={(e) => setLbType(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle}>
        <option value="alb">Application LB (ALB)</option>
        <option value="nlb">Network LB (NLB)</option>
        <option value="azure_lb">Azure LB</option>
        <option value="haproxy">HAProxy</option>
      </select>
    </div>
    <div className="flex flex-col gap-1">
      <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>Scheme</label>
      <select value={lbScheme} onChange={(e) => setLbScheme(e.target.value)}
              className="text-sm font-mono px-3 py-2 rounded border focus:outline-none focus:border-[#07b6d5]" style={inputStyle}>
        <option value="internal">Internal</option>
        <option value="internet_facing">Internet Facing</option>
      </select>
    </div>
  </>
)}
```

Add the necessary useState hooks for the new fields (cloudProvider, region, cidr, tunnelType, encryption, remoteGateway, lbType, lbScheme, etc.) and include them in handleApply.

5. **`TopologyEditorView.tsx`** — Add `vpc` and `compliance_zone` to the isSubnet check (line 116) so they render as container nodes:

```typescript
const isSubnet = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone';
```

**Verification:** `cd frontend && npx tsc --noEmit`

**Commit:** `git commit -m "feat(frontend): add enterprise node types to palette, DeviceNode, and property panel"`

---

## Task 7: VPC Container Node + Compliance Zone Node

**Files:**
- Create: `frontend/src/components/TopologyEditor/VPCNode.tsx`
- Create: `frontend/src/components/TopologyEditor/ComplianceZoneNode.tsx`
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`

**Context:** `SubnetGroupNode.tsx` is the existing container node pattern — dashed border, resizable, CIDR label. VPC and ComplianceZone nodes follow same pattern with different colors/labels.

**Changes:**

1. **`VPCNode.tsx`** — Based on SubnetGroupNode but with blue dashed border and cloud provider badge:

```tsx
import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface VPCNodeData {
  label: string;
  cidr?: string;
  cloudProvider?: string;
  region?: string;
  deviceType: string;
}

const providerLabels: Record<string, string> = {
  aws: 'AWS', azure: 'Azure', gcp: 'GCP', oci: 'OCI',
};

const VPCNode: React.FC<NodeProps<VPCNodeData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(59,130,246,0.05)', borderColor: selected ? '#3b82f6' : '#1e3a5f',
                  minWidth: 300, minHeight: 200 }}>
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={300} minHeight={200}
        style={{ background: 'transparent', border: 'none' }}>
        <div className="absolute bottom-0 right-0 w-3 h-3 cursor-se-resize"
             style={{ borderRight: '2px solid #3b82f6', borderBottom: '2px solid #3b82f6' }} />
      </NodeResizeControl>

      {/* Provider badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ backgroundColor: '#1e3a5f', color: '#3b82f6', border: '1px solid #2563eb' }}>
        {providerLabels[data.cloudProvider || ''] || 'Cloud'}
      </div>

      {/* CIDR label */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ backgroundColor: '#0f2023', color: '#3b82f6', border: '1px solid #1e3a5f' }}>
        {data.cidr || data.label}
      </div>

      {/* VPC name + region */}
      <div className="absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#64748b' }}>
        {data.label}{data.region ? ` (${data.region})` : ''}
      </div>
    </div>
  );
};

export default memo(VPCNode);
```

2. **`ComplianceZoneNode.tsx`** — Amber-bordered container with compliance standard badge:

```tsx
import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface ComplianceZoneData {
  label: string;
  complianceStandard?: string;
  deviceType: string;
}

const standardLabels: Record<string, string> = {
  pci_dss: 'PCI-DSS', soc2: 'SOC2', hipaa: 'HIPAA', custom: 'Custom',
};

const ComplianceZoneNode: React.FC<NodeProps<ComplianceZoneData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(245,158,11,0.05)', borderColor: selected ? '#f59e0b' : '#78350f',
                  minWidth: 250, minHeight: 180 }}>
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={250} minHeight={180}
        style={{ background: 'transparent', border: 'none' }}>
        <div className="absolute bottom-0 right-0 w-3 h-3 cursor-se-resize"
             style={{ borderRight: '2px solid #f59e0b', borderBottom: '2px solid #f59e0b' }} />
      </NodeResizeControl>

      {/* Standard badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        {standardLabels[data.complianceStandard || ''] || 'Compliance'}
      </div>

      {/* Zone name */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ backgroundColor: '#0f2023', color: '#f59e0b', border: '1px solid #78350f' }}>
        {data.label}
      </div>
    </div>
  );
};

export default memo(ComplianceZoneNode);
```

3. **`TopologyEditorView.tsx`** — Register new node types (line 26):

```typescript
import VPCNode from './VPCNode';
import ComplianceZoneNode from './ComplianceZoneNode';

const nodeTypes = {
  device: DeviceNode,
  subnet: SubnetGroupNode,
  vpc: VPCNode,
  compliance_zone: ComplianceZoneNode,
};
```

Update `onDrop` (line 116) for new container types:
```typescript
const isContainer = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone';
```

Set container sizes:
```typescript
...(isContainer
  ? { style: { width: type === 'vpc' ? 400 : 300, height: type === 'vpc' ? 300 : 200 } }
  : {}),
```

Set node type:
```typescript
type: isContainer ? (type === 'vpc' ? 'vpc' : type === 'compliance_zone' ? 'compliance_zone' : 'subnet') : 'device',
```

**Verification:** `cd frontend && npx tsc --noEmit`

**Commit:** `git commit -m "feat(frontend): add VPC and ComplianceZone container nodes"`

---

## Task 8: Network War Room — Enterprise Evidence Panels

**Files:**
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx`

**Context:** NetworkWarRoom currently shows path visualization, firewall verdicts, NAT translations, trace hops, and evidence panels. We add 4 new panels for enterprise constructs.

**Changes:**

Add new panels after existing firewall verdicts section. Each panel only renders when data exists:

1. **NACL Verdicts Panel** — Shows stateless rule evaluation per NACL:

```tsx
{findings?.nacl_verdicts && findings.nacl_verdicts.length > 0 && (
  <div className="rounded-lg border p-4" style={{ backgroundColor: '#0f2023', borderColor: '#224349' }}>
    <h3 className="text-xs font-mono font-semibold uppercase tracking-widest mb-3" style={{ color: '#ef4444' }}>
      NACL Evaluation
    </h3>
    <div className="flex flex-col gap-2">
      {findings.nacl_verdicts.map((v, i) => (
        <div key={i} className="flex items-center justify-between p-2 rounded border" style={{ borderColor: '#224349' }}>
          <span className="text-sm font-mono" style={{ color: '#e2e8f0' }}>{v.nacl_name}</span>
          <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded"
                style={{ backgroundColor: v.action === 'allow' ? '#052e16' : '#450a0a',
                         color: v.action === 'allow' ? '#22c55e' : '#ef4444' }}>
            {v.action.toUpperCase()}
          </span>
        </div>
      ))}
    </div>
  </div>
)}
```

2. **VPC Boundary Crossings Panel**
3. **Tunnel Segments Panel**
4. **LB in Path Panel**

(Same pattern — conditional render, styled cards with the appropriate accent colors.)

**Verification:** `cd frontend && npx tsc --noEmit`

**Commit:** `git commit -m "feat(frontend): add enterprise evidence panels to Network War Room"`

---

## Task 9: Existing Test Updates + Integration Test

**Files:**
- Modify: `backend/tests/test_network_pipeline.py` (add new state fields to initial state)
- Modify: `backend/tests/test_network_integration.py` (add new state fields)
- Create: `backend/tests/test_enterprise_integration.py`

**Context:** Existing network tests use `NetworkPipelineState` which now has new required-ish fields. They need default empty values added.

**Changes:**

1. Update any existing test `initial_state` dicts to include:
```python
"nacls_in_path": [],
"load_balancers_in_path": [],
"vpn_segments": [],
"nacl_verdicts": [],
"vpc_boundary_crossings": [],
```

2. Create integration test that builds a small topology with VPC + NACL + LB, runs the pipeline, and verifies:
- VPC crossings detected in final_path
- NACL verdict appears in state
- LB DNAT recorded in nat_translations
- Report includes VPN/VPC/NACL info

**Run:** `cd backend && python3 -m pytest --tb=short -q`

**Commit:** `git commit -m "test: update existing tests and add enterprise integration tests"`

---

## Task 10: Verification

**Run after all tasks:**

1. `cd backend && python3 -m pytest --tb=short -q` — all tests pass
2. `cd frontend && npx tsc --noEmit` — no TypeScript errors
3. Verify palette shows categorized items with new device types
4. Verify VPC container node renders with blue border and cloud provider badge
5. Verify ComplianceZone container renders with amber border
6. Verify DeviceNode shows correct icon/color for each new type
7. Verify property panel shows type-specific fields
