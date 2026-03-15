# Enterprise Network Mock Data & Observatory Gaps — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Populate the Knowledge Graph with a realistic enterprise hybrid network topology (35 devices, 120 interfaces, 30 links across on-prem + AWS + Azure + OCI) AND fix Observatory/monitoring gaps so the UI isn't a dead end.

**Architecture:** One large JSON fixture loaded into the KG on startup. Observatory gets honest empty states with adapter connection guidance instead of fake metrics. Path diagnosis, firewall simulation, and reachability matrix work against the fixture data.

**Tech Stack:** Python (backend fixtures + KG loading), React/TypeScript (frontend empty states)

**Scope rules:**
- Mock ONLY what backend can process (topology, policy, IPAM)
- Do NOT mock live monitoring data (SNMP metrics, BGP flaps, NetFlow) — those need real collectors
- Observatory shows clear "connect adapter" guidance instead of placeholder data

---

## Part 1: Enterprise Network Fixture Data (10 tasks)

### Task 1: Fixture File — On-Premises Devices

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/devices_onprem.json`

13 on-premises devices with full metadata:

```json
[
  {
    "id": "pa-core-fw-01",
    "name": "pa-core-fw-01",
    "vendor": "Palo Alto Networks",
    "model": "PA-5260",
    "role": "firewall",
    "site": "DC-East",
    "os_version": "PAN-OS 11.1.2",
    "serial": "PA5260-SN001",
    "ha_role": "active",
    "ha_peer": "pa-core-fw-02",
    "management_ip": "10.1.40.10",
    "interfaces": [
      {"name": "ethernet1/1", "ip": "10.0.0.1/30", "zone": "Untrust", "speed": "10G", "status": "up", "description": "To Checkpoint perimeter"},
      {"name": "ethernet1/2", "ip": "10.1.10.1/24", "zone": "Trust-Production", "speed": "10G", "status": "up", "description": "VLAN 10 SVI"},
      {"name": "ethernet1/3", "ip": "10.1.20.1/24", "zone": "Trust-Corporate", "speed": "10G", "status": "up", "description": "VLAN 20 SVI"},
      {"name": "ethernet1/4", "ip": "10.1.30.1/24", "zone": "DMZ", "speed": "10G", "status": "up", "description": "VLAN 30 DMZ"},
      {"name": "ethernet1/5", "ip": "10.0.0.9/30", "zone": "Cloud-Transit", "speed": "10G", "status": "up", "description": "To Core Router 01"},
      {"name": "ethernet1/6", "ip": "10.0.0.17/30", "zone": "Cloud-Transit", "speed": "10G", "status": "up", "description": "To Core Router 02"},
      {"name": "ethernet1/7", "ip": "10.1.40.10/24", "zone": "Management", "speed": "1G", "status": "up", "description": "Mgmt"},
      {"name": "ae1", "ip": "10.0.0.5/30", "zone": "HA", "speed": "10G", "status": "up", "description": "HA3 link to pa-core-fw-02"}
    ]
  },
  {
    "id": "pa-core-fw-02",
    "name": "pa-core-fw-02",
    "vendor": "Palo Alto Networks",
    "model": "PA-5260",
    "role": "firewall",
    "site": "DC-East",
    "os_version": "PAN-OS 11.1.2",
    "ha_role": "passive",
    "ha_peer": "pa-core-fw-01",
    "management_ip": "10.1.40.11"
  },
  {
    "id": "cp-perim-fw-01",
    "name": "cp-perim-fw-01",
    "vendor": "Checkpoint",
    "model": "6800",
    "role": "firewall",
    "site": "DC-East",
    "os_version": "R81.20",
    "ha_role": "active",
    "ha_peer": "cp-perim-fw-02",
    "management_ip": "10.1.40.20",
    "interfaces": [
      {"name": "eth1", "ip": "203.0.113.2/29", "zone": "External", "speed": "10G", "status": "up", "description": "ISP-1 uplink"},
      {"name": "eth2", "ip": "203.0.113.10/29", "zone": "External", "speed": "10G", "status": "up", "description": "ISP-2 uplink"},
      {"name": "eth3", "ip": "10.0.0.2/30", "zone": "Internal", "speed": "10G", "status": "up", "description": "To PA Core FW"},
      {"name": "eth4", "ip": "10.2.0.1/24", "zone": "Proxy", "speed": "1G", "status": "up", "description": "To Zscaler"}
    ]
  },
  {
    "id": "cp-perim-fw-02",
    "name": "cp-perim-fw-02",
    "vendor": "Checkpoint",
    "model": "6800",
    "role": "firewall",
    "site": "DC-East",
    "ha_role": "standby",
    "ha_peer": "cp-perim-fw-01"
  },
  {
    "id": "zs-proxy-01",
    "name": "zs-proxy-01",
    "vendor": "Zscaler",
    "model": "ZIA Virtual Appliance",
    "role": "proxy",
    "site": "DC-East",
    "management_ip": "10.1.40.30",
    "interfaces": [
      {"name": "eth0", "ip": "10.2.0.10/24", "zone": "Proxy", "speed": "10G", "status": "up"},
      {"name": "eth1", "ip": "10.0.0.25/30", "zone": "Internet-Breakout", "speed": "10G", "status": "up"}
    ]
  },
  {
    "id": "rtr-core-01",
    "name": "rtr-core-01",
    "vendor": "Cisco",
    "model": "C9500-48Y4C",
    "role": "router",
    "site": "DC-East",
    "os_version": "IOS-XE 17.9.4",
    "management_ip": "10.1.40.40",
    "interfaces": [
      {"name": "Loopback0", "ip": "10.255.0.1/32", "speed": "N/A", "status": "up", "description": "Router-ID"},
      {"name": "TenGigabitEthernet1/0/1", "ip": "10.0.0.10/30", "speed": "10G", "status": "up", "description": "To PA Core FW"},
      {"name": "TenGigabitEthernet1/0/2", "ip": "10.0.0.29/30", "speed": "10G", "status": "up", "description": "To rtr-core-02 (iBGP)"},
      {"name": "TenGigabitEthernet1/0/3", "ip": "10.0.0.33/30", "speed": "10G", "status": "up", "description": "To rtr-dc-edge-01"},
      {"name": "GigabitEthernet0/0/1", "ip": "10.1.10.2/24", "speed": "1G", "status": "up", "description": "VLAN 10 access", "vlan": 10},
      {"name": "GigabitEthernet0/0/2", "ip": "10.1.20.2/24", "speed": "1G", "status": "up", "description": "VLAN 20 access", "vlan": 20}
    ]
  },
  {
    "id": "rtr-core-02",
    "name": "rtr-core-02",
    "vendor": "Cisco",
    "model": "C9500-48Y4C",
    "role": "router",
    "site": "DC-East",
    "os_version": "IOS-XE 17.9.4",
    "management_ip": "10.1.40.41"
  },
  {
    "id": "rtr-dc-edge-01",
    "name": "rtr-dc-edge-01",
    "vendor": "Cisco",
    "model": "ASR 1001-X",
    "role": "router",
    "site": "DC-East",
    "os_version": "IOS-XE 17.6.5",
    "management_ip": "10.1.40.42",
    "interfaces": [
      {"name": "GigabitEthernet0/0/0", "ip": "10.0.0.34/30", "speed": "10G", "status": "up", "description": "To rtr-core-01"},
      {"name": "GigabitEthernet0/0/1", "ip": "169.254.100.1/30", "speed": "10G", "status": "up", "description": "AWS DX Primary VIF"},
      {"name": "GigabitEthernet0/0/2", "ip": "169.254.200.1/30", "speed": "10G", "status": "up", "description": "AWS DX Secondary VIF"},
      {"name": "GigabitEthernet0/0/3", "ip": "169.254.50.1/30", "speed": "5G", "status": "up", "description": "OCI FastConnect VIF"},
      {"name": "Tunnel100", "ip": "169.254.101.1/30", "speed": "N/A", "status": "up", "description": "GRE to csr-aws-01 over DX", "tunnel_type": "GRE", "tunnel_source": "GigabitEthernet0/0/1", "tunnel_destination": "169.254.100.2"},
      {"name": "Tunnel200", "ip": "169.254.102.1/30", "speed": "N/A", "status": "down", "description": "GRE to csr-aws-01 secondary (DOWN)", "tunnel_type": "GRE"}
    ]
  },
  {
    "id": "rtr-dc-edge-02",
    "name": "rtr-dc-edge-02",
    "vendor": "Cisco",
    "model": "ASR 1001-X",
    "role": "router",
    "site": "DC-East",
    "os_version": "IOS-XE 17.6.5",
    "management_ip": "10.1.40.43",
    "interfaces": [
      {"name": "GigabitEthernet0/0/0", "ip": "10.0.0.38/30", "speed": "10G", "status": "up", "description": "To rtr-core-02"},
      {"name": "GigabitEthernet0/0/1", "ip": "169.254.300.1/30", "speed": "5G", "status": "up", "description": "Azure ExpressRoute VIF"}
    ]
  },
  {
    "id": "f5-lb-01",
    "name": "f5-lb-01",
    "vendor": "F5 Networks",
    "model": "BIG-IP i5800",
    "role": "load_balancer",
    "site": "DC-East",
    "os_version": "BIG-IP 17.1.0",
    "ha_role": "active",
    "ha_peer": "f5-lb-02",
    "management_ip": "10.1.40.50",
    "interfaces": [
      {"name": "1.1", "ip": "10.1.30.100/24", "zone": "DMZ", "speed": "10G", "status": "up", "description": "VIP interface (external)"},
      {"name": "1.2", "ip": "10.1.10.100/24", "zone": "Trust-Production", "speed": "10G", "status": "up", "description": "Pool member interface (internal)"},
      {"name": "mgmt", "ip": "10.1.40.50/24", "speed": "1G", "status": "up"}
    ]
  },
  {
    "id": "f5-lb-02",
    "name": "f5-lb-02",
    "vendor": "F5 Networks",
    "model": "BIG-IP i5800",
    "role": "load_balancer",
    "site": "DC-East",
    "ha_role": "standby",
    "ha_peer": "f5-lb-01"
  },
  {
    "id": "sw-access-01",
    "name": "sw-access-01",
    "vendor": "Cisco",
    "model": "C9300-48T",
    "role": "switch",
    "site": "DC-East",
    "os_version": "IOS-XE 17.9.4",
    "management_ip": "10.1.40.60"
  },
  {
    "id": "sw-access-02",
    "name": "sw-access-02",
    "vendor": "Cisco",
    "model": "C9300-48T",
    "role": "switch",
    "site": "DC-East",
    "management_ip": "10.1.40.61"
  }
]
```

(This is the shape — actual file will have complete interface lists for all devices.)

**Commit:** `feat(fixtures): on-premises device inventory (13 devices)`

---

### Task 2: Fixture File — Cloud Devices (AWS + Azure + OCI)

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/devices_cloud.json`

~22 cloud resources:

**AWS (15):**
- tgw-hub-01 (Transit Gateway)
- vpc-production, vpc-staging, vpc-shared-services, vpc-inspection (4 VPCs)
- pa-aws-fw-01, pa-aws-fw-02 (Palo Alto VM-Series in inspection VPC)
- csr-aws-01 (Cisco CSR1000v, cloud router)
- f5-aws-01 (F5 BIG-IP VE)
- gwlb-inspection-01 (Gateway Load Balancer)
- dx-connection-01, dx-connection-02 (Direct Connect)
- natgw-prod-01 (NAT Gateway)
- igw-prod-01 (Internet Gateway)

**Azure (5):**
- vwan-hub-01 (Virtual WAN Hub)
- vnet-production, vnet-shared (VNets)
- er-circuit-01 (ExpressRoute)
- er-gateway-01 (ExpressRoute Gateway)

**OCI (3):**
- vcn-production (VCN)
- drg-01 (Dynamic Routing Gateway)
- fc-circuit-01 (FastConnect)

Each with correct interface IPs, subnet associations, route tables.

**Commit:** `feat(fixtures): cloud device inventory (AWS/Azure/OCI, 22 resources)`

---

### Task 3: Fixture File — VLANs, Subnets, IP Ranges

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/vlans_subnets.json`

On-prem VLANs (8):
| VLAN | Name | Subnet | Gateway | Zone |
|------|------|--------|---------|------|
| 10 | Production | 10.1.10.0/24 | 10.1.10.1 | Trust-Production |
| 20 | Corporate | 10.1.20.0/24 | 10.1.20.1 | Trust-Corporate |
| 30 | DMZ | 10.1.30.0/24 | 10.1.30.1 | DMZ |
| 40 | Management | 10.1.40.0/24 | 10.1.40.1 | Management |
| 50 | Voice | 10.1.50.0/24 | 10.1.50.1 | Trust-Voice |
| 100 | Storage | 10.1.100.0/24 | — | Isolated |
| 200 | WAN-Transit | 10.0.0.0/24 | — | Transit |
| 999 | Internet-Edge | 203.0.113.0/29 | 203.0.113.1 | Untrust |

Cloud subnets (12):
- AWS: 10.10.0.0/16 (prod), 10.11.0.0/16 (staging), 10.12.0.0/16 (shared), 10.13.0.0/16 (inspection) — each split into /24 app/db/mgmt subnets
- Azure: 10.20.0.0/16 (prod), 10.21.0.0/16 (shared)
- OCI: 10.30.0.0/16 (prod)

IPAM address blocks with realistic utilization (production 78% used, staging 23%, etc.).

**Commit:** `feat(fixtures): VLANs, subnets, and IPAM address blocks`

---

### Task 4: Fixture File — Links and WAN Circuits

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/links.json`

30 links covering all connection types:

| # | Type | From | To | Bandwidth | Status |
|---|------|------|----|-----------|--------|
| 1 | Ethernet | pa-core-fw-01 eth1/1 | cp-perim-fw-01 eth3 | 10G | up |
| 2 | Ethernet | pa-core-fw-01 eth1/5 | rtr-core-01 Te1/0/1 | 10G | up |
| 3 | Ethernet | pa-core-fw-01 ae1 | pa-core-fw-02 ae1 | 10G | up (HA) |
| 4 | Ethernet | rtr-core-01 Te1/0/2 | rtr-core-02 Te1/0/2 | 10G | up (iBGP) |
| 5 | Ethernet | rtr-core-01 Te1/0/3 | rtr-dc-edge-01 Gi0/0/0 | 10G | up |
| 6 | Ethernet | f5-lb-01 1.1 | pa-core-fw-01 eth1/4 | 10G | up (DMZ) |
| 7 | Ethernet | f5-lb-01 1.2 | sw-access-01 Gi1/0/48 | 10G | up |
| 8 | Direct Connect | rtr-dc-edge-01 Gi0/0/1 | AWS dx-connection-01 | 10G | up |
| 9 | Direct Connect | rtr-dc-edge-01 Gi0/0/2 | AWS dx-connection-02 | 10G | standby |
| 10 | GRE Tunnel | rtr-dc-edge-01 Tu100 | csr-aws-01 Tu100 | over DX | up |
| 11 | GRE Tunnel | rtr-dc-edge-01 Tu200 | csr-aws-01 Tu200 | over DX | down |
| 12 | ExpressRoute | rtr-dc-edge-02 Gi0/0/1 | Azure er-circuit-01 | 5G | up |
| 13 | FastConnect | rtr-dc-edge-01 Gi0/0/3 | OCI fc-circuit-01 | 5G | up |
| 14 | ISP | cp-perim-fw-01 eth1 | ISP-Primary | 1G | up |
| 15 | ISP | cp-perim-fw-02 eth2 | ISP-Secondary | 1G | standby |
| 16 | MPLS | rtr-core-01 | Branch-NY | 100M | up |
| 17 | MPLS | rtr-core-01 | Branch-London | 50M | up |
| 18 | TGW Attachment | tgw-hub-01 | vpc-production | N/A | active |
| 19 | TGW Attachment | tgw-hub-01 | vpc-staging | N/A | active |
| 20 | TGW Attachment | tgw-hub-01 | vpc-inspection | N/A | active |
| 21 | GWLB Endpoint | gwlb-inspection-01 | pa-aws-fw-01 | N/A | healthy |
| 22 | GWLB Endpoint | gwlb-inspection-01 | pa-aws-fw-02 | N/A | healthy |
| 23-30 | Inter-VPC, VNet peering, DRG attachments | ... | ... | ... | ... |

**Commit:** `feat(fixtures): WAN links, tunnels, and cloud circuits (30 links)`

---

### Task 5: Fixture File — Routing Tables (BGP + Static)

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/routing.json`

~20 BGP peers + route entries:

```json
{
  "bgp_peers": [
    {"device": "rtr-core-01", "local_as": 65000, "remote_as": 65000, "neighbor": "10.255.0.2", "peer_device": "rtr-core-02", "type": "iBGP", "state": "Established", "prefixes_received": 45},
    {"device": "rtr-dc-edge-01", "local_as": 65000, "remote_as": 64512, "neighbor": "169.254.100.2", "peer_device": "AWS TGW", "type": "eBGP", "state": "Established", "prefixes_received": 12},
    {"device": "rtr-dc-edge-02", "local_as": 65000, "remote_as": 12076, "neighbor": "169.254.300.2", "peer_device": "Azure MSEE", "type": "eBGP", "state": "Established", "prefixes_received": 8},
    {"device": "rtr-dc-edge-01", "local_as": 65000, "remote_as": 31898, "neighbor": "169.254.50.2", "peer_device": "OCI DRG", "type": "eBGP", "state": "Established", "prefixes_received": 4},
    {"device": "csr-aws-01", "local_as": 64512, "remote_as": 65000, "neighbor": "169.254.101.1", "peer_device": "rtr-dc-edge-01", "type": "eBGP", "state": "Established", "prefixes_received": 30}
  ],
  "route_table": [
    {"device": "rtr-core-01", "prefix": "10.10.0.0/16", "next_hop": "169.254.100.2", "protocol": "BGP", "metric": 100, "via": "AWS DX"},
    {"device": "rtr-core-01", "prefix": "10.20.0.0/16", "next_hop": "169.254.300.2", "protocol": "BGP", "metric": 100, "via": "Azure ER"},
    {"device": "rtr-core-01", "prefix": "10.30.0.0/16", "next_hop": "169.254.50.2", "protocol": "BGP", "metric": 100, "via": "OCI FC"},
    {"device": "rtr-core-01", "prefix": "0.0.0.0/0", "next_hop": "10.0.0.9", "protocol": "static", "via": "PA Core FW"}
  ]
}
```

**Commit:** `feat(fixtures): BGP peering and route tables`

---

### Task 6: Fixture File — Firewall Rules and Zones

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/firewall_policies.json`

Zone definitions (8 zones) + rules for each firewall:

**Palo Alto Core (pa-core-fw-01):**
- Trust-Production → DMZ: Allow HTTPS (443), HTTP (80)
- Trust-Corporate → Internet: Allow via Zscaler proxy
- Trust → Cloud-Transit: Allow 10.1.0.0/16 → 10.10-30.0.0/16
- DMZ → Trust-Production: Allow app-specific (8080, 5432)
- Any → Management: Deny (except VLAN 40)

**Checkpoint Perimeter (cp-perim-fw-01):**
- External → DMZ: Allow HTTPS to VIPs (DNAT)
- Internal → External: Allow outbound (SNAT to 203.0.113.4)
- Any → Any: Implicit deny + log

**Palo Alto AWS (pa-aws-fw-01):**
- vpc-production → vpc-staging: Allow specific ports
- Any → Internet: Deny (force through NAT GW)

**NAT rules:**
- cp-perim-fw-01: DNAT 203.0.113.5:443 → f5-lb-01:443 (VIP)
- cp-perim-fw-01: SNAT 10.0.0.0/8 → 203.0.113.4 (outbound)
- f5-lb-01: SNAT pool 10.1.10.100 (client → pool member)

**Commit:** `feat(fixtures): firewall policies, zones, and NAT rules`

---

### Task 7: Fixture File — F5 Load Balancer Configuration

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/f5_config.json`

On-prem F5 VIPs (3):
```json
[
  {
    "vip": "web-app-vip",
    "address": "10.1.30.100:443",
    "pool": "web-app-pool",
    "members": [
      {"address": "10.1.10.50:8080", "status": "up", "ratio": 1},
      {"address": "10.1.10.51:8080", "status": "up", "ratio": 1},
      {"address": "10.1.10.52:8080", "status": "down", "ratio": 1}
    ],
    "ssl_profile_client": "ssl-offload-profile",
    "ssl_cert_expiry": "2026-03-27T00:00:00Z",
    "persistence": "cookie",
    "snat": "automap"
  },
  {
    "vip": "api-gateway-vip",
    "address": "10.1.30.101:443",
    "pool": "api-pool",
    "members": [
      {"address": "10.1.10.60:9090", "status": "up"},
      {"address": "10.1.10.61:9090", "status": "up"}
    ],
    "snat": "snat-pool-01"
  },
  {
    "vip": "internal-api-vip",
    "address": "10.1.10.200:8443",
    "pool": "internal-api-pool",
    "members": [
      {"address": "10.1.10.70:8080", "status": "up"},
      {"address": "10.1.10.71:8080", "status": "up"}
    ]
  }
]
```

AWS F5 VIPs (2):
```json
[
  {
    "vip": "aws-web-vip",
    "address": "10.10.1.100:443",
    "pool": "aws-web-pool",
    "members": [
      {"address": "10.10.1.50:8080", "status": "up"},
      {"address": "10.10.1.51:8080", "status": "up"}
    ],
    "ssl_profile_client": "aws-ssl-profile",
    "snat": "automap"
  }
]
```

**Commit:** `feat(fixtures): F5 load balancer VIPs and pool members`

---

### Task 8: Fixture File — HA Groups

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/ha_groups.json`

```json
[
  {"id": "ha-pa-core", "name": "PA Core Firewall HA", "type": "active-passive", "members": ["pa-core-fw-01", "pa-core-fw-02"], "active": "pa-core-fw-01", "sync_state": "synchronized"},
  {"id": "ha-cp-perim", "name": "Checkpoint Perimeter HA", "type": "active-standby", "members": ["cp-perim-fw-01", "cp-perim-fw-02"], "active": "cp-perim-fw-01", "sync_state": "synchronized"},
  {"id": "ha-f5-onprem", "name": "F5 On-Prem HA", "type": "active-standby", "members": ["f5-lb-01", "f5-lb-02"], "active": "f5-lb-01", "sync_state": "in-sync"},
  {"id": "ha-pa-aws", "name": "PA AWS Inspection HA", "type": "active-passive", "members": ["pa-aws-fw-01", "pa-aws-fw-02"], "active": "pa-aws-fw-01", "sync_state": "synchronized"},
  {"id": "ha-rtr-core", "name": "Core Router HSRP", "type": "VRRP", "members": ["rtr-core-01", "rtr-core-02"], "active": "rtr-core-01", "vip": "10.0.0.254"}
]
```

**Commit:** `feat(fixtures): HA group definitions (5 groups)`

---

### Task 9: Knowledge Graph Loader

**Files:**
- Create: `backend/src/network/fixture_loader.py`
- Modify: `backend/src/api/main.py` (call loader on startup)

A function that reads all fixture JSON files and populates the Knowledge Graph:

```python
async def load_enterprise_fixtures(kg: KnowledgeGraph):
    """Load enterprise network fixtures into KG on startup."""
    fixture_dir = Path(__file__).parent.parent / "agents/fixtures/enterprise_network"

    if not fixture_dir.exists():
        return

    # Load devices → create KG nodes
    # Load interfaces → add to device nodes
    # Load links → create KG edges
    # Load VLANs/subnets → populate IPAM
    # Load routes → inject into KG routing tables
    # Load firewall rules → store for adapter simulation
    # Load F5 config → store for LB queries
    # Load HA groups → create HA entities
```

Wire into `main.py` startup:
```python
@app.on_event("startup")
async def startup():
    await load_enterprise_fixtures(knowledge_graph)
```

**Commit:** `feat(network): fixture loader populates KG on startup`

---

### Task 10: Traffic Flow Definitions (for Path Diagnosis)

**Files:**
- Create: `backend/src/agents/fixtures/enterprise_network/traffic_flows.json`

7 pre-defined flows that path diagnosis can trace:

```json
[
  {
    "name": "Internet to On-Prem Web App",
    "src_ip": "198.51.100.50",
    "dst_ip": "10.1.30.100",
    "dst_port": 443,
    "protocol": "TCP",
    "expected_path": ["cp-perim-fw-01", "pa-core-fw-01", "f5-lb-01", "10.1.10.50"],
    "nat_translations": [
      {"device": "cp-perim-fw-01", "type": "DNAT", "from": "203.0.113.5:443", "to": "10.1.30.100:443"},
      {"device": "f5-lb-01", "type": "SNAT", "from": "client-ip", "to": "10.1.10.100"}
    ]
  },
  {
    "name": "On-Prem User to AWS App",
    "src_ip": "10.1.20.50",
    "dst_ip": "10.10.1.50",
    "dst_port": 443,
    "protocol": "TCP",
    "expected_path": ["rtr-core-01", "pa-core-fw-01", "rtr-dc-edge-01", "GRE-Tu100", "csr-aws-01", "tgw-hub-01", "gwlb-inspection-01", "pa-aws-fw-01", "vpc-production"]
  },
  {
    "name": "AWS to Azure via On-Prem Hairpin",
    "src_ip": "10.10.1.50",
    "dst_ip": "10.20.1.50",
    "dst_port": 443,
    "expected_path": ["tgw-hub-01", "csr-aws-01", "GRE-Tu100", "rtr-dc-edge-01", "rtr-core-01", "rtr-dc-edge-02", "er-circuit-01", "vwan-hub-01", "vnet-production"]
  },
  {
    "name": "On-Prem to Internet via Zscaler",
    "src_ip": "10.1.20.50",
    "dst_ip": "8.8.8.8",
    "dst_port": 443,
    "expected_path": ["rtr-core-01", "zs-proxy-01", "cp-perim-fw-01", "ISP-Primary"]
  },
  {
    "name": "AWS East-West via Inspection VPC",
    "src_ip": "10.10.1.50",
    "dst_ip": "10.11.1.50",
    "dst_port": 5432,
    "expected_path": ["tgw-hub-01", "gwlb-inspection-01", "pa-aws-fw-01", "gwlb-inspection-01", "tgw-hub-01", "vpc-staging"]
  },
  {
    "name": "Branch Office to DC",
    "src_ip": "172.16.1.50",
    "dst_ip": "10.1.10.50",
    "dst_port": 443,
    "expected_path": ["MPLS-PE", "rtr-core-01", "pa-core-fw-01", "sw-access-01"]
  },
  {
    "name": "On-Prem to OCI Database",
    "src_ip": "10.1.10.50",
    "dst_ip": "10.30.1.50",
    "dst_port": 1521,
    "expected_path": ["rtr-core-01", "rtr-dc-edge-01", "fc-circuit-01", "drg-01", "vcn-production"]
  }
]
```

These flows are usable for path diagnosis — `POST /diagnose` with these src/dst pairs will trace through the fixture-populated KG.

**Commit:** `feat(fixtures): 7 enterprise traffic flow definitions`

---

## Part 2: Observatory Empty States & Guidance (4 tasks)

### Task 11: Observatory Device Health — Honest Empty State

**Files:**
- Modify: `frontend/src/components/Observatory/` (device health tab)

Currently shows placeholder metrics. Replace with:

```
┌─────────────────────────────────────────────────────────┐
│ Device Health Monitoring                                 │
│                                                         │
│ 📡  Connect SNMP or API adapters to enable live         │
│     device monitoring.                                  │
│                                                         │
│ Supported:                                              │
│ • Cisco IOS-XE (SNMP v2c/v3)                           │
│ • Palo Alto PAN-OS (REST API via Panorama)              │
│ • F5 BIG-IP (iControl REST)                             │
│ • Checkpoint (HTTPS API)                                │
│ • Zscaler (Cloud API)                                   │
│                                                         │
│ [Configure Adapters →]                                  │
│                                                         │
│ ─── Available from Topology ───                         │
│                                                         │
│ 35 devices discovered in topology                       │
│ 5 HA groups configured                                  │
│ 120 interfaces mapped                                   │
│                                                         │
│ [View Topology →]  [Run Path Diagnosis →]               │
└─────────────────────────────────────────────────────────┘
```

Shows what IS available (topology data) and guides toward what's needed (adapters) for live metrics.

**Commit:** `feat(observatory): honest empty state with adapter guidance`

---

### Task 12: Observatory Traffic Flows — Honest Empty State

**Files:**
- Modify: `frontend/src/components/Observatory/` (traffic flows tab)

```
┌─────────────────────────────────────────────────────────┐
│ Traffic Flow Analysis                                    │
│                                                         │
│ 📊  Configure NetFlow/IPFIX export on your routers      │
│     to enable live traffic analysis.                    │
│                                                         │
│ Required: NetFlow v5/v9 or IPFIX → UDP port 2055       │
│                                                         │
│ [View NetFlow Setup Guide →]                            │
│                                                         │
│ ─── Path Diagnosis Available ───                        │
│                                                         │
│ You can still trace paths between any two IPs           │
│ using the topology and firewall policy data.            │
│                                                         │
│ [Start Path Diagnosis →]                                │
└─────────────────────────────────────────────────────────┘
```

**Commit:** `feat(observatory): traffic flows empty state with setup guide`

---

### Task 13: Observatory Alerts — Honest Empty State

**Files:**
- Modify: `frontend/src/components/Observatory/` (alerts tab)

```
┌─────────────────────────────────────────────────────────┐
│ Alerts & Events                                          │
│                                                         │
│ 🔔  Connect syslog or SNMP trap receivers to enable     │
│     real-time alerting.                                 │
│                                                         │
│ Supported sources:                                      │
│ • Syslog (UDP 514) — Cisco, Palo Alto, F5              │
│ • SNMP Traps (UDP 162) — any SNMP v2c/v3 device        │
│ • Webhook (HTTP POST) — cloud provider alerts           │
│                                                         │
│ [Configure Alert Sources →]                             │
└─────────────────────────────────────────────────────────┘
```

**Commit:** `feat(observatory): alerts empty state with source guidance`

---

### Task 14: Observatory DNS — Honest Empty State

**Files:**
- Modify: `frontend/src/components/Observatory/` (DNS tab)

```
┌─────────────────────────────────────────────────────────┐
│ DNS Monitoring                                           │
│                                                         │
│ 🌐  Configure DNS probe targets to monitor resolution   │
│     latency and availability.                           │
│                                                         │
│ [Configure DNS Probes →]                                │
│                                                         │
│ ─── Split-Horizon DNS Detected ───                      │
│                                                         │
│ Topology shows DNS infrastructure:                      │
│ • On-Prem AD DNS: 10.1.40.100                          │
│ • AWS Route 53: vpc-shared-services                     │
│                                                         │
│ Path diagnosis can trace DNS traffic between zones.     │
└─────────────────────────────────────────────────────────┘
```

**Commit:** `feat(observatory): DNS monitoring empty state`

---

## Implementation Order

**Part 1 (fixtures) — sequential, each task builds on previous:**
- Tasks 1-8: Create all 8 JSON fixture files (can be parallelized)
- Task 9: KG loader (depends on fixture format from 1-8)
- Task 10: Traffic flow definitions (depends on device IPs from 1-2)

**Part 2 (observatory) — independent, parallel:**
- Tasks 11-14: All independent empty state updates

**Total: 14 tasks.**
