# Knowledge Graph Architecture Overhaul — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the tightly-coupled, rebuild-on-every-request KnowledgeGraph with an enterprise-grade architecture: canonical data model with interface-level graph nodes, dual-store (Postgres + Neo4j), Kafka event bus, VRF-aware pathfinding with policy simulation, pluggable discovery adapters with BFS crawling, and frontend layout engine with WebSocket real-time updates.

**Architecture:** Layered migration — repository abstraction first, then Neo4j, then Kafka, then discovery, then visualization. Each layer is independently shippable and testable. Existing system never breaks during migration.

**Tech Stack:** Python (FastAPI), Postgres (Timescale for metrics), Neo4j (graph DB), Apache Kafka (event bus), NetworkX (in-memory cache), pytricia (CIDR LPM), React + ReactFlow + D3-force (frontend), WebSocket (real-time).

---

## Table of Contents

1. [Canonical Data Model](#1-canonical-data-model)
2. [Storage Architecture](#2-storage-architecture)
3. [Repository Layer & Ingestion Pipeline](#3-repository-layer--ingestion-pipeline)
4. [VRF-Aware Pathfinding & Policy Evaluation](#4-vrf-aware-pathfinding--policy-evaluation)
5. [Discovery Adapters & BFS Network Crawling](#5-discovery-adapters--bfs-network-crawling)
6. [Visualization](#6-visualization)

---

## 1. Canonical Data Model

### 42 Node Types

#### Core Topology (7)

| # | Node | Key Properties |
|---|------|---------------|
| 1 | `Device` | id, hostname, vendor, model, serial, device_type, site_id, managed_by, mode (routed/transparent), ha_mode, state_sync |
| 2 | `Interface` | id (`device_id:name`), mac, admin_state, oper_state, speed, mtu, duplex, port_channel_id, description, vrf_instance_id, vlan_membership[] |
| 3 | `IPAddress` | id, ip, assigned_to (entity_ref), assigned_from, lease_ts |
| 4 | `Subnet` | id, cidr, vpc_id, vrf_id, purpose, owner |
| 5 | `VLAN` | id, vlan_id (int), name, site_id |
| 6 | `LAG` | id, name, device_id, members[] |
| 7 | `Link` | id, speed, media_type (fiber/copper/virtual), latency, utilization |

#### Routing — VRF-Aware (4)

| # | Node | Key Properties |
|---|------|---------------|
| 8 | `VRF` | id, name, global_id |
| 9 | `VRF_Instance` | id, vrf_id, device_id, table_id |
| 10 | `Route` | id, destination_cidr, prefix_len, protocol, admin_distance, metric, next_hop_type, next_hop_refs[] (ordered, weighted — supports ECMP) |
| 11 | `RouteTable` | id, cloud_provider, vpc_id, name |

#### Security & Policy (6)

| # | Node | Key Properties |
|---|------|---------------|
| 12 | `Zone` | id, name, security_level, zone_type |
| 13 | `SecurityPolicy` | id, device_id, rule_order, name, src_zone, dst_zone, src_ip/mask, dst_ip/mask, src_port_range, dst_port_range, protocol, action, log, stateful, precedence |
| 14 | `SecurityGroup` | id, cloud_provider, name, rules[] (canonical match fields + precedence) |
| 15 | `TrafficClass` | id, src_vrf, dst_vrf, src_ips, dst_ips, ports, protocol, service_tag |
| 16 | `NATRule` | id, device_id, type (SNAT/DNAT/PAT/twice_nat), priority, original_src/dst, translated_src/dst, original_port, translated_port, direction |
| 17 | `CloudFirewall` | id, provider, name, vpc_id, subnet_ids[] |

#### Cloud Networking (12)

| # | Node | Key Properties |
|---|------|---------------|
| 18 | `VPC` | id, name, cloud_provider, region, cidr_blocks[] |
| 19 | `TransitGateway` | id, name, attached_vpc_ids[] |
| 20 | `CloudInterface` | id, instance_id, mac, subnet_id, security_group_ids[] *(AWS ENI, Azure NIC, GCP NetworkInterface, OCI VNIC)* |
| 21 | `CloudRegion` | id, provider, name |
| 22 | `CloudOnRamp` | id, type (DirectConnect/ExpressRoute/Interconnect/FastConnect), provider |
| 23 | `GatewayInterface` | id, gateway_id, attachment_type |
| 24 | `NATGateway` | id, provider, public_ip, subnet_id |
| 25 | `InternetGateway` | id, provider, vpc_id |
| 26 | `VPCPeeringConnection` | id, status, route_propagation, cross_account, requester_vpc_id, accepter_vpc_id |
| 27 | `TargetGroup` | id, lb_id, port, protocol, health_check, targets[] |
| 28 | `PrivateEndpoint` | id, provider, type (PrivateLink/PrivateEndpoint/PrivateServiceConnect), service_name |
| 29 | `DirectConnectGateway` | id, aws_account, region, asn |

#### WAN & Tunnels (7)

| # | Node | Key Properties |
|---|------|---------------|
| 30 | `Tunnel` | id, type (GRE/IPSec/VXLAN/MPLS/SD-WAN), status, local_ip, remote_ip, encapsulation, mtu, keepalive, routing_protocol, encryption |
| 31 | `IPSecSA` | id, spi, encryption_algo, hash_algo, lifetime, pfs, mode (transport/tunnel), direction (inbound/outbound), rekey_count |
| 32 | `VPNGateway` | id, provider, type (site_to_site/client_vpn/route_based/policy_based), public_ip, vpc_id, site_id, asn |
| 33 | `VirtualInterface` | id, type (private/public/transit), vlan, asn, bgp_state, amazon_address, customer_address |
| 34 | `MPLSCircuit` | id, label_stack[], lsp_name, endpoints[] |
| 35 | `DirectConnect` | id, connects_site, connects_region, bandwidth |
| 36 | `ExternalGateway` | id, name, type (internet/partner/cloud_onramp) |

#### Application & Observability (3)

| # | Node | Key Properties |
|---|------|---------------|
| 37 | `LoadBalancer` | id, type (ALB/NLB/GWLB/F5/Netscaler), vip, site_id |
| 38 | `Service` | id, name, owner |
| 39 | `Flow` | id, src_ip, dst_ip, src_port, dst_port, protocol, bytes, packets, timestamp *(aggregated 1min/5min buckets, raw to cold store)* |

#### Management & Topology (3)

| # | Node | Key Properties |
|---|------|---------------|
| 40 | `Site` | id, name, location, type (dc/branch/colo) |
| 41 | `Controller` | id, name, type (sdwan/wireless) |
| 42 | `VirtualRouter` | id, name, type |

### Complete Edge Types (~53)

#### Core Topology
- `HAS_INTERFACE`: Device → Interface
- `HAS_IP`: Interface → IPAddress
- `CONNECTED_TO`: Interface → Link → Interface (protocol, last_seen, confidence)
- `MEMBER_OF`: Interface → LAG
- `BELONGS_TO`: Interface → VLAN (tagged/untagged)
- `IN_SUBNET`: IPAddress → Subnet
- `IN_SITE`: Device → Site
- `IN_ZONE`: Device/Interface → Zone
- `HA_PEER`: Device → Device (ha_mode, priority, state_sync)
- `MANAGED_BY`: Device → Controller

#### Routing (VRF-Aware)
- `INSTANCE_OF`: VRF_Instance → VRF
- `ON_DEVICE`: VRF_Instance → Device
- `IN_VRF`: Route → VRF_Instance
- `ON_DEVICE`: Route → Device
- `NEXT_HOP`: Route → Interface or ExternalGateway (weight for ECMP)
- `IN_VRF`: Subnet → VRF
- `ASSOCIATED_WITH`: Subnet → RouteTable
- `HAS_ROUTE`: RouteTable → Route

#### Routing Adjacencies (BGP/OSPF/MPLS)
- `BGP_PEER`: Device → Device (asn_local, asn_remote, state, local_ip, remote_ip, md5, route_server)
- `OSPF_NEIGHBOR`: Device → Device (area_id, state, dr/bdr)
- `MPLS_LSP`: Device → Device (label_stack[], lsp_name)

#### Cloud Networking
- `IN_VPC`: Subnet → VPC
- `PEERS_VIA`: VPC → VPCPeeringConnection → VPC
- `ATTACHED_TO`: VPC → TransitGateway
- `ROUTES_TO`: TransitGateway → VPC
- `HAS_ENI`: Subnet → CloudInterface
- `ATTACHED_TO`: CloudInterface → Device
- `HAS`: VPC → InternetGateway
- `ROUTES_TO`: Subnet → NATGateway
- `CONNECTS_TO`: NATGateway → InternetGateway
- `CONNECTS`: CloudOnRamp → Site, CloudRegion

#### Direct Connect / Overlay-Underlay
- `HAS_VIF`: DirectConnect → VirtualInterface
- `CONNECTS_TO`: VirtualInterface → DirectConnectGateway
- `BGP_PEER`: VirtualInterface → Device
- `ATTACHED_TO`: DirectConnectGateway → TransitGateway/VPC
- `UNDERLAY`: Tunnel → DirectConnect/MPLSCircuit/Tunnel (overlay rides on underlay)
- `SERVES`: DirectConnect → Site (blast radius query)

#### Tunnel / VPN
- `TUNNEL_ENDPOINT`: Tunnel → Device (role: local/remote)
- `HAS_SA`: Tunnel → IPSecSA (direction: inbound/outbound)
- `CONNECTS`: Tunnel → Site (role: local/remote)
- `CARRIES`: Tunnel → Route (overlay routing)
- `BGP_SESSION_ON`: BGP_PEER → Tunnel
- `TERMINATES_AT`: Tunnel → VPNGateway → VPC
- `OBSERVED_ON`: Flow → Tunnel (latency, packet_loss, jitter, throughput)

#### Security & Policy
- `ENFORCES`: Device(FIREWALL) → SecurityPolicy/NATRule
- `APPLIED_TO`: SecurityPolicy → Zone/Interface/SG
- `APPLIED_TO`: SecurityGroup → CloudInterface
- `PERMITS/DENIES`: SecurityPolicy → TrafficClass (precedence)
- `PERMITS`: SecurityGroup → TrafficClass
- `APPLIES_TO`: NATRule → TrafficClass
- `TRANSFORMS`: NATRule → IPAddress (direction: snat/dnat)
- `ROUTES_TO`: Subnet → CloudFirewall
- `PERMITS/DENIES`: CloudFirewall → TrafficClass

#### Application & Observability
- `FORWARDS_TO`: LoadBalancer → TargetGroup
- `TARGETS`: TargetGroup → CloudInterface/IPAddress (port, weight)
- `DEPENDS_ON`: Service → IPAddress
- `OBSERVED_FLOW`: Interface → Flow
- `OBSERVED_ON`: Flow → CloudInterface (VPC Flow Logs)
- `ALLOWED_BY`: Flow → SecurityPolicy
- `DENIED_BY`: Flow → SecurityPolicy
- `TRANSLATED_BY`: Flow → NATRule
- `CONNECTS_TO`: CloudInterface → PrivateEndpoint → Service

#### WAN
- `TRAVERSES`: MPLSCircuit → Device (order, label_stack)

### Temporal Provenance (All Nodes & Edges)

```
sources[]        — ["snmp", "lldp", "aws_api", "ipam", "config_parser", "gnmi"]
first_seen       — ISO8601
last_seen        — ISO8601
confidence       — 0.0-1.0
stale            — boolean (last_seen > edge_ttl)
```

### Constraints & Indexes

- `Interface.id` = deterministic `device_id:name` — idempotent upserts
- `IPAddress` unique on `ip + assigned_to` time ranges — overlap detection
- `VRF_Instance → Device` existence enforced before route insertion
- Graph DB indexes: Device.id, Device.hostname, Device.serial, Interface.id, Interface.mac, IPAddress.ip (unique), Subnet.cidr, Route.destination, VRF_Instance.device_id, Flow.timestamp
- In-memory: one pytricia radix tree per VRF_Instance for CIDR LPM

### Explicit Scope Exclusions (v1)
- Multicast / PIM / mroute
- Segment Routing / SRv6 / TE
- QoS classes as entities

### Design Invariants
- All graph mutations are idempotent upserts with deterministic keys
- Stale edges are confidence-decayed, not hard-deleted (confirmation window before removal)
- Flow records stored as aggregated 1min/5min buckets; raw flows to cold store
- ECMP modeled as Route with multiple weighted NEXT_HOP edges
- Pathfinding is VRF-scoped by default; cross-VRF only through explicit NAT/route-reflection
- Firewall policy evaluation: top-down, first match wins, implicit deny

---

## 2. Storage Architecture

### Dual-Store Design

```
Collectors → Observation DB (Postgres: network_observations)
                ↓
           Normalization + Entity Resolution
                ↓
           Inventory DB (Postgres: network_inventory)
                ↓
           Kafka Event Bus (topology.*.changed topics)
                ↓
    ┌───────────┼───────────┬──────────────┐
    ▼           ▼           ▼              ▼
 Neo4j     In-Memory    WebSocket      Alert
(Graph)     Cache       Publisher     Evaluator
```

### Three Separate Databases

| Database | Purpose | Retention | Volume |
|----------|---------|-----------|--------|
| `network_observations` | Raw immutable observations from collectors | 90 days hot, archive | High |
| `network_inventory` | Canonical entities, policies, audit log, snapshots | Indefinite | Low |
| `network_metrics` (Timescale) | Time-series device/interface metrics, flow aggregates | 30d hot, 1yr downsampled | Very high |

### Kafka Topics

- `topology.device.changed`
- `topology.interface.changed`
- `topology.link.discovered`
- `topology.route.changed`
- `topology.policy.changed`
- `topology.stale.detected`
- `topology.snapshot.created`

Consumer groups: graph-mutator, cache-invalidator, alert-evaluator, websocket-publisher, audit-logger.

All events carry `schema_version` for evolution.

### Topology Snapshots

- Nightly scheduled (00:00 UTC)
- Before/after major changes
- Manual (operator-triggered)
- Pre-computed diffs stored in `topology_diffs` table

### Schema Evolution

- `schema_migrations` table with version + checksum
- Forward-only migrations (no rollback SQL)
- Additive changes in minor versions, breaking changes require major bump
- Kafka events carry schema_version — consumers ignore unknown versions

### Failure & Recovery

| Scenario | Recovery |
|----------|----------|
| Neo4j crashes | Rebuild from Postgres canonical tables. Kafka replays missed events. |
| Postgres (inventory) crashes | Restore from WAL/backup. Neo4j continues stale reads. |
| Kafka crashes | Events buffered in producer. On recovery, replay. |
| Cache corruption | Evict all, rebuild from Neo4j. |

---

## 3. Repository Layer & Ingestion Pipeline

### TopologyRepository Interface

```python
class TopologyRepository(ABC):
    # Reads
    get_device(id) → Device
    get_devices(site_id?, device_type?) → list[Device]
    get_interfaces(device_id) → list[Interface]
    get_ip_addresses(interface_id) → list[IPAddress]
    get_routes(device_id, vrf_instance_id?) → list[Route]
    get_neighbors(device_id) → list[NeighborLink]
    get_security_policies(device_id) → list[SecurityPolicy]
    find_device_by_ip(ip) → Device?
    find_device_by_serial(serial) → Device?
    find_device_by_hostname(hostname) → Device?

    # Writes (Postgres → Kafka → Neo4j)
    upsert_device(device) → Device
    upsert_interface(interface) → Interface
    upsert_neighbor_link(link) → NeighborLink
    upsert_route(route) → Route
    upsert_security_policy(policy) → SecurityPolicy
    mark_stale(entity_type, entity_id)
    delete_stale(entity_type, max_age) → int

    # Graph queries (Neo4j + cache)
    find_paths(src_ip, dst_ip, vrf, k) → list[Path]
    blast_radius(device_id) → BlastResult
    get_topology_export(site_id?) → TopologyExport
    get_device_graph(device_id, depth) → Subgraph

    # Snapshots
    create_snapshot(trigger, metadata) → Snapshot
    diff_snapshots(a, b) → TopologyDiff
```

### Write Path

1. Upsert canonical row in Postgres (network_inventory)
2. Write to topology_audit_log
3. Publish event to Kafka topic
4. Graph mutator (Kafka consumer) MERGEs into Neo4j (idempotent)
5. Cache invalidator evicts affected entries

### Entity Resolution Priority

1. Exact serial match
2. Cloud resource ARN/ID
3. Management IP match
4. Fuzzy hostname/MAC scoring (threshold: 0.85)
5. No match → create new canonical entity with low confidence

### Source Confidence Scoring

| Source | Confidence |
|--------|-----------|
| manual | 1.0 |
| lldp | 0.95 |
| gnmi | 0.95 |
| aws_api / azure_api / oci_api | 0.95 |
| snmp | 0.90 |
| cdp | 0.90 |
| config_parser | 0.85 |
| ipam | 0.80 |
| netflow | 0.70 |

### Staleness Policy

- Edge not observed for > edge_ttl → confidence *= 0.5, stale = true
- After 3x TTL → soft delete from Neo4j, keep in Postgres
- NEVER hard delete from Postgres

---

## 4. VRF-Aware Pathfinding & Policy Evaluation

### Path Simulation Steps

1. **Resolve endpoints**: src_ip → IPAddress → Interface → Device (within VRF context)
2. **Build weighted graph**: VRF-scoped, interface-level adjacency. Cross-VRF edges only at NAT/route-leak points.
3. **K-shortest paths**: Yen's algorithm. Cost = (1 - confidence) + topology_penalty + policy_penalty. Max depth 15, max enumeration 1000.
4. **Hop-by-hop simulation**: At each device, evaluate firewall policy, NAT, LB, tunnel overlay/underlay.
5. **Return results**: per-hop verdicts, NAT transformations, VRF crossings, ECMP branches, warnings.

### Topology Penalties

| Penalty | Value | Meaning |
|---------|-------|---------|
| vrf_boundary | 0.3 | Cross-VRF is expensive |
| cross_vpc | 0.25 | VPC peering adds cost |
| nat_crossing | 0.2 | NAT adds complexity |
| inter_site | 0.2 | Multi-site has latency |
| overlay_tunnel | 0.15 | GRE/overlay penalty |
| vpn_tunnel | 0.15 | Encrypted tunnel cost |
| transit_gateway | 0.1 | TGW adds hop |
| load_balancer | 0.1 | LB adds processing |
| low_bandwidth | 0.1 | Constrained links |
| direct_connect | 0.05 | DX is preferred |
| mpls_circuit | 0.05 | MPLS WAN is good |

### Firewall Policy Evaluation Order

```
Packet → Ingress Interface → Zone Lookup → Route Lookup (VRF-aware)
→ Policy Eval (top-down, first match, implicit deny)
→ NAT Transform (DNAT before routing, SNAT after)
→ Forward via egress interface
```

### Blast Radius Algorithm

1. Direct impact: neighbors, tunnels terminating at device, tunnels whose underlay traverses device
2. Sites served by failed DirectConnect/WAN
3. Cascade: devices that lose ALL paths to core
4. Returns: affected_devices, affected_tunnels, affected_sites, affected_vpcs, severed_paths

---

## 5. Discovery Adapters & BFS Network Crawling

### Adapter Interface

```python
class DiscoveryAdapter(ABC):
    async def discover(target) → AsyncIterator[DiscoveryObservation]
    def supports(target) → bool
```

### Protocol Adapters

| Adapter | Protocol | Discovers | Confidence |
|---------|----------|-----------|-----------|
| SNMPInventory | SNMP | Device inventory, interfaces, IPs | 0.90 |
| LLDPDiscovery | LLDP-MIB | L2 neighbors | 0.95 |
| CDPDiscovery | CISCO-CDP-MIB | L2 neighbors (Cisco) | 0.90 |
| BGPDiscovery | BGP4-MIB | BGP peers, ASNs, state | 0.95 |
| OSPFDiscovery | OSPF-MIB | OSPF neighbors, areas | 0.90 |
| ARPMACAdapter | IP-MIB, BRIDGE-MIB | IP→MAC, MAC→port | 0.70-0.75 |
| LACPAdapter | IEEE8023-LAG-MIB | LAG membership | 0.95 |

### Cloud Adapters

| Adapter | Provider | Resources |
|---------|----------|-----------|
| AWS | boto3 | VPCs, Subnets, Route Tables, IGWs, NAT GWs, TGWs, ENIs, SGs, DX + VIFs + DXGWs, ALB/NLB, VPN GWs, Network Firewall |
| Azure | azure-sdk | VNets, Subnets, Route Tables, NSGs, ExpressRoute, VPN GWs, Azure Firewall, LBs, NICs, VNet Peering, Private Endpoints, Virtual WAN |
| OCI | oci-sdk | VCNs, Subnets, Route Tables, Security Lists, NSGs, DRGs, FastConnect, LBs, VNICs |

### BFS Network Crawler

```
seed devices → BFS queue
  for each device:
    run all applicable protocol adapters
    discover neighbors → new devices
    add new devices to queue
  bounded by: max_depth (5), max_devices (1000), allowed_cidrs, rate_limit
```

### Discovery Scheduler

| Mode | Interval | Scope |
|------|----------|-------|
| incremental | 5 min | Known devices (SNMP + LLDP only) |
| cloud_sync | 15 min | Cloud accounts (full API discovery) |
| full_crawl | 1 hour | BFS from seeds (all protocol adapters) |
| event_triggered | On demand | Re-discover on topology change event |

---

## 6. Visualization

### Key Design Principle

**Backend exports semantic data (type, group, rank, relationships). Frontend decides visual layout (positions, sizes, colors).**

Backend does NOT export x/y pixel positions.

### Layout Engine (Frontend, Pluggable)

| Algorithm | When | Method |
|-----------|------|--------|
| force_directed | < 50 nodes | D3-force with group clustering |
| hierarchical | 50-500 nodes | Dagre with rank-based tiers |
| geographic | GPS data available | Mercator projection |
| radial | Single-site drill-down | Core at center, rings outward |

### Auto-Selection

```
< 50 nodes → force_directed
50-200 → hierarchical
200-500 → hierarchical + group collapsing
500+ → hierarchical + aggressive aggregation
Has GPS → geographic (override)
```

### Real-Time Updates

- WebSocket at `/api/v5/topology/stream`
- Kafka consumer → WebSocket publisher → connected frontends
- Delta events: node.status_changed, edge.added, edge.removed, metrics.updated
- No full reload — incremental merge into React state
- Per-client filtering by site/viewport

### Edge Styling

| Edge Type | Color | Width | Style |
|-----------|-------|-------|-------|
| physical | #22c55e | 3 | solid |
| logical | #22c55e | 2 | dashed |
| tunnel | #06b6d4 | 3 | dashed, animated |
| ha_peer | #f59e0b | 2 | dashed |
| mpls | #f59e0b | 4 | solid |
| route | #64748b | 1 | 30% opacity |
| load_balancer | #a855f7 | 2 | solid |
| stale | #64748b | 1 | dotted, 40% opacity |
| down | #ef4444 | 4 | dashed |

Utilization overlay: width scales 2-6px, color shifts green → amber (>75%) → red (>90%).

### Topology API (v5)

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v5/topology` | Full graph export (layout hints, no pixels) |
| `GET /api/v5/topology/site/:id` | Site subgraph |
| `GET /api/v5/topology/path` | VRF-aware pathfinding with policy simulation |
| `GET /api/v5/topology/blast-radius` | Failure impact analysis |
| `GET /api/v5/device/:id` | Device + neighbors + interfaces |
| `GET /api/v5/flows` | Flow queries |
| `GET /api/v5/topology/snapshot/:id` | Historical snapshot |
| `GET /api/v5/topology/diff` | Snapshot comparison |
| `WS /api/v5/topology/stream` | Real-time delta events |

---

## Implementation Phases

### Phase 1: Canonical Data Model + Repository Layer
- TopologyRepository interface (abstract)
- PostgresNeo4jRepository (concrete)
- Interface as graph nodes (device → interface → interface → device)
- neighbor_links table (persist L2 discovery)
- VRF + VRF_Instance modeling
- Entity resolution algorithm
- Topology validation (duplicate IP, subnet conflicts)

### Phase 2: Neo4j Integration
- Neo4j as graph store (behind repository interface)
- Cypher queries for path analysis, blast radius
- Property indexes on id, ip, cidr, hostname
- Idempotent MERGE upsert patterns
- Nightly reconciliation (rebuild from Postgres)

### Phase 3: Kafka Event Bus + Incremental Graph
- Kafka topics for topology changes
- Graph mutator consumer (Kafka → Neo4j)
- Cache invalidator consumer
- WebSocket publisher consumer
- Staleness detector service
- Schema evolution with versioned events

### Phase 4: Discovery Adapters + Normalization
- Protocol adapters (SNMP, LLDP, BGP, OSPF, ARP, LACP)
- Cloud adapters (AWS, Azure, OCI)
- BFS network crawler
- Discovery scheduler (incremental, cloud_sync, full_crawl)
- Normalization + entity resolution pipeline

### Phase 5: Visualization
- Frontend layout engine (force-directed, hierarchical, geographic)
- Backend exports hints, not coordinates
- WebSocket real-time topology updates
- Enhanced interactions (interface-level detail, VRF overlay, security overlay)
- Scale testing (500+ nodes)
