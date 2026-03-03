# Enterprise Hybrid Network Topology — Design Document

**Date:** 2026-03-03
**Status:** Approved

## Goal

Extend the network troubleshooting system to support enterprise hybrid banking architectures — VPCs, VPN tunnels, Direct Connect, NACLs, load balancers, MPLS, VLANs, Transit Gateways, and compliance zone tagging. Full stack: models + topology UI + diagnosis pipeline.

## Architecture

Layered extension of existing codebase. No new modules or plugin system. All new constructs follow existing patterns (Pydantic models → SQLite store → NetworkX graph → LangGraph pipeline → React Flow UI).

## Constraints

- Zone tagging only for compliance (no validation rules)
- No DNS, DDoS/WAF, QoS, 802.1X, IPv6, or flow log ingestion
- All new node types reuse existing DeviceNode rendering where possible
- NACL evaluation is stateless and separate from stateful firewall evaluation

---

## Section 1: New Entity Models

### Category 1: Cloud Constructs

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **VPC** | id, name, cloud_provider (aws/azure/gcp/oci), region, cidr_blocks[], account_id, compliance_zone | First-class VPC/VNet container |
| **RouteTable** | id, vpc_id, name, is_main, routes[] | VPC route tables |
| **VPCPeering** | id, requester_vpc_id, accepter_vpc_id, status, cidr_routes[] | Cross-VPC peering |
| **TransitGateway** | id, name, cloud_provider, region, attached_vpc_ids[], route_table_id | Multi-VPC hub |

### Category 2: Hybrid Connectivity

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **VPNTunnel** | id, name, tunnel_type (ipsec/gre/ssl), local_gateway_id, remote_gateway_ip, local_cidrs[], remote_cidrs[], encryption, ike_version, status | IPSec/GRE tunnel |
| **DirectConnect** | id, name, provider (aws_dx/azure_er/oci_fc), bandwidth_mbps, location, vlan_id, bgp_asn, status | Dedicated circuit |

### Category 3: Security Layers

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **NACL** | id, name, vpc_id, subnet_ids[], is_default | Network ACL container |
| **NACLRule** | id, nacl_id, direction (inbound/outbound), rule_number, protocol, cidr, port_range_from, port_range_to, action | Stateless ordered rules |

### Category 4: Load Balancing

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **LoadBalancer** | id, name, lb_type (alb/nlb/azure_lb/haproxy), scheme (internet-facing/internal), vpc_id, listeners[], health_check_path | L4/L7 LB |
| **LBTargetGroup** | id, lb_id, name, protocol, port, target_ids[], health_status | Backend targets |

### Category 5: Advanced Networking

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **VLAN** | id, vlan_number, name, trunk_ports[], access_ports[], site | L2 segmentation |
| **MPLSCircuit** | id, name, label, provider, bandwidth_mbps, endpoints[], qos_class | WAN backbone |

### Category 6: Compliance Tagging

| Model | Key Fields | Purpose |
|-------|-----------|---------|
| **ComplianceZone** | id, name, standard (pci_dss/soc2/hipaa/custom), description, subnet_ids[], vpc_ids[] | Zone labels |

### New Enums

- `CloudProvider`: aws, azure, gcp, oci
- `TunnelType`: ipsec, gre, ssl
- `DirectConnectProvider`: aws_dx, azure_er, oci_fc
- `LBType`: alb, nlb, azure_lb, haproxy
- `LBScheme`: internet_facing, internal
- `ComplianceStandard`: pci_dss, soc2, hipaa, custom
- `NACLDirection`: inbound, outbound

### DeviceType Enum Additions

Add to existing enum: VPC, TRANSIT_GATEWAY, LOAD_BALANCER, VPN_TUNNEL, DIRECT_CONNECT, NACL, VLAN, MPLS, COMPLIANCE_ZONE

### NetworkDiagnosticState Additions

```python
nacls_in_path: list[dict] = []
load_balancers_in_path: list[dict] = []
vpn_segments: list[dict] = []
nacl_verdicts: list[dict] = []
vpc_boundary_crossings: list[dict] = []
```

---

## Section 2: Topology UI

### Node Palette — Categorized Sections

**Infrastructure:** Router, Switch, Firewall, Workload
**Cloud:** VPC/VNet, Transit Gateway, Load Balancer, Cloud Gateway
**Connectivity:** VPN Tunnel, Direct Connect, MPLS Circuit
**Security:** NACL, Zone, Subnet, Compliance Zone
**L2/Data Center:** VLAN

### New React Flow Node Components

| Component | Visual | Use |
|-----------|--------|-----|
| **VPCNode** | Large resizable container, blue dashed border, cloud provider badge, CIDR label | VPC/VNet grouping |
| **TunnelNode** | Pill/capsule, orange dashed border (VPN) or gold solid (DX) or purple (MPLS), shows encryption/bandwidth | Connectivity segments |
| **ComplianceZoneNode** | Large resizable container, amber dashed border, standard badge | Compliance grouping |

### DeviceNode Icon/Color Additions

```
transit_gateway  → hub,             #a855f7 (purple)
load_balancer    → dns,             #22c55e (green)
vpn_tunnel       → vpn_lock,        #f97316 (orange)
direct_connect   → cable,           #eab308 (gold)
nacl             → checklist,       #ef4444 (red)
vlan             → label,           #14b8a6 (teal)
mpls             → conversion_path, #a855f7 (purple)
```

### DevicePropertyPanel — Type-Specific Fields

- **VPC**: cloud_provider dropdown, region, account_id, CIDR blocks multi-input
- **VPN**: tunnel_type dropdown, encryption, IKE version, remote gateway IP, local/remote CIDRs
- **Direct Connect**: provider dropdown, bandwidth, BGP ASN, VLAN
- **Load Balancer**: lb_type dropdown, scheme dropdown, listeners
- **NACL**: inline rule list (rule_number, direction, action, CIDR, port range)
- **Compliance Zone**: standard dropdown, linked subnets

---

## Section 3: Diagnosis Pipeline

### Updated Pipeline Flow

```
START → input_resolver → graph_pathfinder → traceroute_probe → hop_attributor
  → [PARALLEL: firewall_evaluator, nacl_evaluator]
  → nat_resolver → path_synthesizer → report_generator → END
```

### Knowledge Graph Updates

**New node_types:** vpc, transit_gateway, load_balancer, vpn_tunnel, direct_connect, nacl, vlan, mpls, compliance_zone

**New edge_types:** vpc_contains, peered_to, attached_to, tunnel_to, load_balances, nacl_guards

**New topology penalties:**
- vpn_tunnel: 0.15
- direct_connect: 0.05
- mpls_circuit: 0.05
- cross_vpc: 0.25
- transit_gateway: 0.1
- load_balancer: 0.1

### Graph Pathfinder Updates

Identify NACLs, load balancers, and tunnel segments in addition to firewalls. Output new state fields: nacls_in_path, load_balancers_in_path, vpn_segments.

### New Node: nacl_evaluator.py

Stateless NACL rule evaluation:
1. Sort rules by rule_number ascending
2. Check INBOUND rules (dst perspective)
3. Check OUTBOUND rules (src perspective)
4. First matching rule wins
5. No match → implicit deny

### NAT Resolver Updates

Handle LB DNAT translations (VIP → backend IP) in addition to firewall NAT.

### Path Synthesizer Updates

Annotate VPN/DX/MPLS segments and LB hops in the final path.

### Report Generator Updates

Include NACL verdicts, tunnel info, VPC crossings, and LB translations in executive summary.

---

## Section 4: Frontend Types + War Room

### New TypeScript Interfaces

VPC, VPCPeering, TransitGateway, VPNTunnel, DirectConnect, MPLSCircuit, NACLRule, LoadBalancer, LBTargetGroup, VLAN, ComplianceZone

### NetworkFindings Extensions

nacl_verdicts[], vpc_boundary_crossings[], vpn_segments[], load_balancers_in_path[]

### New War Room Panels

1. **VPC Boundary Panel** — Shows VPC crossings via peering/TGW
2. **NACL Verdicts Panel** — Stateless rule evaluation results (inbound + outbound)
3. **Tunnel Segments Panel** — Encrypted/dedicated segments with encryption details
4. **LB Translation Row** — Added to existing NAT translations section

### Path Visualization Updates

- VPC containers around grouped hops
- Dashed lines for tunnel segments with lock icon
- Diamond shape for LB hops
- Shield icons for NACL checkpoints
- Compliance zone badges on devices

---

## Topology Store — New Tables

vpcs, route_tables, vpc_peerings, transit_gateways, vpn_tunnels, direct_connects, mpls_circuits, nacls, nacl_rules, load_balancers, lb_target_groups, vlans, compliance_zones

Each table gets standard CRUD methods (add, list, get, delete).

---

## Explicitly Out of Scope

- Compliance validation rules (just tagging)
- DNS resolution path tracing
- DDoS/WAF policy evaluation
- QoS/bandwidth simulation
- 802.1X/RADIUS authentication
- IPv6/NAT64
- Flow log ingestion from cloud providers
