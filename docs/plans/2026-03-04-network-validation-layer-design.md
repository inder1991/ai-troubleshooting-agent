# Network Validation Layer & HA Pair Modeling — Design

## Problem

The network module accepts invalid data at every layer. A user can place a firewall inside a VPC on the canvas, assign an IP outside the VPC's CIDR, and save without error. There is no validation on IP formats in forms, no relationship checks between devices and their parent containers, no duplicate IP detection across the topology, and no concept of HA (High Availability) device pairs — meaning shared Virtual IPs are flagged as duplicates and failover paths are invisible to diagnosis.

## Goal

Add a comprehensive validation layer across frontend, canvas, and backend that catches data integrity issues **before** they corrupt the Knowledge Graph or produce wrong diagnosis results. Additionally, model HA device pairs as first-class entities so active-passive/active-active topologies are correctly represented, validated, and diagnosed.

## Architecture

Validation runs at three gates, each progressively stricter:

| Gate | When | What it catches |
|------|------|-----------------|
| **Frontend (instant)** | On keystroke / on blur | Malformed IPs, ports, CIDRs — red border + inline error |
| **Pre-save (canvas)** | User clicks Save or Promote | Relationship violations: IP-outside-CIDR, overlapping subnets, orphaned refs |
| **Backend (API)** | Request hits endpoint | Pydantic validators as final safety net. Rejects 422 + structured errors |

Backend is authoritative. Frontend validation is for UX speed — never the only gate.

**Error format (consistent everywhere):**
```json
{ "field": "management_ip", "message": "10.99.0.5 is outside VPC CIDR 10.0.0.0/16", "severity": "error" }
```

## Validation Rules

### P0 — Format Validation (blocks save)

| # | Rule | Where enforced |
|---|------|----------------|
| 1 | IP addresses must be valid IPv4/IPv6 (`management_ip`, `gateway_ip`, `src_ip`, `dst_ip`, interface IPs) | Frontend + Pydantic |
| 2 | CIDRs must be valid notation (`subnet.cidr`, `vpc.cidr_blocks`) | Frontend + Pydantic |
| 3 | Port must be 0–65535 | Frontend + Pydantic |
| 4 | Protocol must be one of: `tcp`, `udp`, `icmp`, `any` | Frontend + Pydantic |
| 5 | VLAN ID must be 0 (unset) or 1–4094 | Frontend + Pydantic |

### P1 — Relationship Validation (blocks save/promote)

| # | Rule | Where enforced |
|---|------|----------------|
| 6 | Device IP must be within parent VPC/subnet CIDR (if device is contained within a VPC/subnet on canvas) | Canvas pre-save + Backend promote |
| 7 | Subnet CIDR must be a subset of parent VPC CIDR | Canvas pre-save + Backend promote |
| 8 | Gateway IP must be within its subnet's CIDR | Canvas pre-save + Backend promote |
| 9 | No overlapping subnet CIDRs within the same VPC | Canvas pre-save + Backend promote |
| 10 | No duplicate management IPs across all devices in topology (exception: VIPs in HA groups) | Canvas pre-save + IPAM ingestion |
| 11 | Interface IP must fall within its declared subnet CIDR | IPAM ingestion + Backend promote |

### P2 — Referential Integrity (blocks promote)

| # | Rule | Where enforced |
|---|------|----------------|
| 12 | `zone_id` on a device must reference an existing zone (or be empty) | Backend promote |
| 13 | NACL `subnet_ids` must reference existing subnets | Backend promote |
| 14 | LB `target_ids` must reference existing devices | Backend promote |
| 15 | Route `next_hop` must resolve to a known device IP or interface | Backend promote |

### P3 — Diagnosis Request Validation

| # | Rule | Where enforced |
|---|------|----------------|
| 16 | `DiagnoseRequest.src_ip` / `dst_ip` must be valid IPs | Frontend form + Pydantic |
| 17 | `DiagnoseRequest.port` must be 0–65535 | Frontend form + Pydantic |
| 18 | `DiagnoseRequest.protocol` must be in allowed set | Frontend form + Pydantic |
| 19 | Confidence values must be 0.0–1.0 | Pydantic |

### P4 — HA Pair Validation

| # | Rule | Where enforced |
|---|------|----------------|
| 20 | HA members must be same device type | Backend + Canvas pre-save |
| 21 | HA members must be in the same subnet (all management IPs in same CIDR) | Backend + Canvas pre-save |
| 22 | VIP must be within members' subnet CIDR | Backend + Canvas pre-save |
| 23 | VIP is NOT a duplicate-IP violation (suppress for HA group VIPs) | Duplicate-IP checker |
| 24 | Active-passive must have exactly 1 active member | Backend + Canvas pre-save |
| 25 | HA members should be in same security zone | Warning (non-blocking) |
| 26 | HA peers should have consistent firewall rules (flag rule drift if adapters connected) | Warning (non-blocking) |
| 27 | If subnet gateway_ip matches an HA group VIP, validate the HA group is healthy | Warning (non-blocking) |
| 28 | Standalone device sharing an IP with another device — suggest HA group creation | Suggestion (non-blocking) |

## HA Pair Data Model

### New model: `HAGroup`

```python
class HAMode(str, Enum):
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    VRRP = "vrrp"
    CLUSTER = "cluster"

class HARole(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    MEMBER = "member"  # for active-active, all are "member"

class HAGroup(BaseModel):
    id: str
    name: str
    ha_mode: HAMode
    member_ids: list[str]       # device IDs
    virtual_ips: list[str] = [] # VIPs shared by the group
    active_member_id: str = ""  # which device is active (active-passive only)
    priority_map: dict[str, int] = {}  # device_id -> priority for failover ordering
    sync_interface: str = ""    # heartbeat/sync link interface name
```

### Device model additions:

```python
class Device(BaseModel):
    # ... existing fields ...
    ha_group_id: str = ""     # which HA group this device belongs to
    ha_role: HARole | str = ""  # active / standby / member / "" (standalone)
```

### Database: new `ha_groups` table

```sql
CREATE TABLE IF NOT EXISTS ha_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ha_mode TEXT NOT NULL,
    member_ids TEXT NOT NULL,       -- JSON array of device IDs
    virtual_ips TEXT DEFAULT '[]',  -- JSON array of VIP strings
    active_member_id TEXT DEFAULT '',
    priority_map TEXT DEFAULT '{}', -- JSON dict
    sync_interface TEXT DEFAULT ''
);
```

Devices table adds: `ha_group_id TEXT DEFAULT ''`, `ha_role TEXT DEFAULT ''`.

### Knowledge Graph integration

- HA group rendered as a special "cluster node" in the KG
- Edges between HA members: `edge_source=HA_SYNC`, bidirectional
- VIPs stored as node attributes on the HA group node
- Path resolution through an HA group resolves to the active member (or both for active-active)

### Canvas representation

HA pairs render as a grouped visual with an HA badge:

```
┌─────────────────────────┐
│  HA: Active-Passive     │
│  VIP: 10.0.1.1          │
│  ┌─────┐    ┌─────┐     │
│  │FW-01│◄──►│FW-02│     │
│  │ ACT │    │ SBY │     │
│  └─────┘    └─────┘     │
└─────────────────────────┘
```

New node type: `ha-group` — a container node (like VPC) with:
- HA mode badge (A/P or A/A)
- VIP display
- Active/standby indicators on member devices
- Heartbeat link shown as dashed edge between members

## Canvas Containment Tracking

Currently, device-in-VPC is purely visual (pixel position). To enable validation, we need data-level containment.

**Approach:** Use ReactFlow's `parentId` field.

- When a device node is dropped inside a VPC/subnet bounds, auto-set `node.parentId = vpc_node_id`
- On drag out, clear `parentId`
- On save, parentId is available for validation: "device X has parentId VPC-Y, so device X's IP must be in VPC-Y's CIDR"
- `onNodeDragStop` handler checks if node is within any container's bounds and updates parentId

## Frontend Validation Utility

New file: `frontend/src/utils/networkValidation.ts`

```typescript
// Format validators (return error message or null)
validateIPv4(ip: string): string | null
validateCIDR(cidr: string): string | null
validatePort(port: number | string): string | null
validateVLAN(vlan: number | string): string | null

// Relationship validators
isIPInCIDR(ip: string, cidr: string): boolean
isCIDRSubsetOf(child: string, parent: string): boolean
detectOverlappingCIDRs(cidrs: string[]): Array<[string, string]>

// Topology-level validation (pre-save)
validateTopology(nodes: Node[], edges: Edge[]): ValidationResult[]
```

`validateTopology()` runs all P0+P1 rules and returns a list of `ValidationResult` objects. Used by the Save and Promote buttons.

## Backend Pydantic Validators

Add `@field_validator` decorators to existing models:

- `Device`: validate `management_ip` (valid IP or empty), `vlan_id` (0 or 1–4094)
- `Subnet`: validate `cidr` (valid CIDR), `gateway_ip` (valid IP or empty)
- `Flow` / `DiagnoseRequest`: validate `src_ip`, `dst_ip` (valid IP), `port` (0–65535), `protocol` (allowed set)
- `HAGroup`: validate `virtual_ips` (all valid IPs), `member_ids` (non-empty list, min 2)

Backend `promote_from_canvas()` gets a `_validate_topology()` pre-check that runs P1+P2 rules before any writes.

## Validation Error UX

**Canvas:**
- Nodes with errors get a red border glow (CSS `box-shadow: 0 0 8px rgba(239,68,68,0.6)`)
- A collapsible **Validation Panel** slides up from the bottom of the canvas
- Each issue is clickable — selects and zooms to the offending node
- Save/Promote buttons show error count badge and are disabled until all errors resolved

**Forms (diagnosis, adapter config):**
- Standard inline validation: red border + error text below the field
- Submit button disabled until all fields valid

**IPAM upload:**
- Existing warning display enhanced with format pre-validation before upload

## Impact on Diagnosis

- HA-aware path resolution: diagnosis through an HA pair resolves to active member
- If active member denies traffic, note HA peer as potential failover path
- Reachability matrix treats HA pairs as single logical hop
- Security grading evaluates active member's rules; flags rule drift between HA peers as warning

## Files Changed

| File | Action |
|------|--------|
| `backend/src/network/models.py` | Modify — add HAGroup, HAMode, HARole; add field validators to Device, Subnet, Flow |
| `backend/src/network/topology_store.py` | Modify — add ha_groups table, CRUD, migration |
| `backend/src/network/knowledge_graph.py` | Modify — HA group nodes, validate topology on promote |
| `backend/src/network/ipam_ingestion.py` | Modify — add IP-in-CIDR check, VLAN range check |
| `backend/src/api/network_models.py` | Modify — add validators to DiagnoseRequest, MatrixRequest |
| `backend/src/api/network_endpoints.py` | Modify — add HA group CRUD endpoints, validation on promote |
| `frontend/src/utils/networkValidation.ts` | **Create** — shared validation utility |
| `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx` | Modify — inline validation on fields |
| `frontend/src/components/TopologyEditor/TopologyEditorView.tsx` | Modify — parentId tracking, pre-save validation, validation panel |
| `frontend/src/components/TopologyEditor/HAGroupNode.tsx` | **Create** — HA group container node |
| `frontend/src/components/TopologyEditor/ValidationPanel.tsx` | **Create** — error list panel |
| `frontend/src/components/ActionCenter/forms/NetworkTroubleshootingFields.tsx` | Modify — inline IP/port validation |
| `backend/tests/test_network_validation.py` | **Create** — validation rule tests |
| `backend/tests/test_ha_groups.py` | **Create** — HA group model + store tests |
