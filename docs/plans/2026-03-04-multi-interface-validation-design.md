# Multi-Interface Appliance Validation — Design

## Problem

The system models firewalls, routers, and load balancers as single-IP nodes. In reality, these devices have multiple interfaces (inside, outside, DMZ, sync, management), each belonging to different subnets/VLANs/zones. There is no validation that:

1. An interface IP belongs to the subnet it's attached to.
2. No interface overlaps between zones on the same device.
3. A management interface is NOT placed in a data plane zone.

## Goal

Extend the `Interface` model with explicit roles, add zone type classification, render interfaces visually on canvas device nodes, and enforce three new validation rules at canvas pre-save and backend promote.

## Data Model Changes

### Interface model additions

```python
class InterfaceRole(str, Enum):
    MANAGEMENT = "management"
    INSIDE = "inside"
    OUTSIDE = "outside"
    DMZ = "dmz"
    SYNC = "sync"       # HA heartbeat
    LOOPBACK = "loopback"

class Interface(BaseModel):
    # ... existing fields (id, device_id, name, ip, mac, zone_id, vrf, speed, status) ...
    role: InterfaceRole | str = ""   # explicit role selection
    subnet_id: str = ""              # which subnet this interface belongs to

    @field_validator("ip")
    def validate_ip(cls, v): ...     # reuse existing _validate_ip helper
```

### Zone model addition

```python
class ZoneType(str, Enum):
    MANAGEMENT = "management"
    DATA = "data"
    DMZ = "dmz"

class Zone(BaseModel):
    # ... existing fields (id, name, security_level, description, firewall_id) ...
    zone_type: ZoneType | str = ""   # defaults to empty (unclassified)
```

### DB migrations

- `interfaces` table: `ALTER TABLE interfaces ADD COLUMN role TEXT DEFAULT ''`
- `interfaces` table: `ALTER TABLE interfaces ADD COLUMN subnet_id TEXT DEFAULT ''`
- `zones` table: `ALTER TABLE zones ADD COLUMN zone_type TEXT DEFAULT ''`

## Validation Rules

| # | Rule | Severity | Where enforced |
|---|------|----------|----------------|
| 29 | Interface IP must be within the CIDR of its assigned subnet | error (blocks save) | Canvas pre-save + Backend promote + IPAM ingestion |
| 30 | No two interfaces on the same device may share a zone assignment (exception: sync role) | error (blocks save) | Canvas pre-save + Backend promote |
| 31 | Management-role interface must be in a management-type zone | warning (non-blocking) | Canvas pre-save + Backend promote |

### Rule 29 — Interface IP in subnet

- When an interface has both `ip` and `subnet_id`, resolve the subnet's CIDR and validate `isIPInCIDR(iface.ip, subnet.cidr)`.
- On canvas: infer subnet from containment (parentContainerId) if `subnet_id` not explicitly set.
- In IPAM ingestion: already partially exists, extend to set `subnet_id` on the Interface record.

### Rule 30 — No zone overlap per device

- Collect all interfaces for a device. If two non-sync interfaces share the same non-empty `zone_id`, flag as error.
- Exception: interfaces with `role=sync` are allowed to share a zone (HA heartbeat links may share a zone).

### Rule 31 — Management not in data plane

- If `interface.role == "management"` and the zone referenced by `interface.zone_id` has `zone_type` in `("data", "dmz")`, emit warning.
- This is a warning, not an error — some networks legitimately use in-band management.

## Canvas Rendering

Device nodes that have interfaces show them as labeled connection points:

```
┌──────────────────┐
│  FW-01  [FW]     │
│  10.0.1.1        │
├──────────────────┤
│ ● eth0  inside   │─── (handle)
│ ● eth1  outside  │─── (handle)
│ ● eth2  dmz      │─── (handle)
│ ○ mgmt  mgmt     │─── (handle)
└──────────────────┘
```

- Each interface gets a labeled row with a colored dot (green=inside, red=outside, amber=dmz, blue=mgmt, grey=sync)
- Each row has a ReactFlow `Handle` on the right for edge connections
- If device has 0 interfaces, show the simple node as today (backwards compatible)
- Interfaces are added/edited via the DevicePropertyPanel

### DevicePropertyPanel interface editor

Add an "Interfaces" collapsible section below existing fields:
- List of interface rows: `[name] [ip] [role dropdown] [zone dropdown] [- remove]`
- `[+ Add Interface]` button
- Inline validation per row (IP format, role selection)
- Changes stored on `node.data.interfaces[]` array

### DeviceNode data flow

1. User adds interfaces in PropertyPanel → stored on `node.data.interfaces[]`
2. On save → `validateTopology()` runs Rules 29, 30, 31 against node data
3. On promote → backend receives interfaces in node data, creates `Interface` records, validates server-side
4. ReactFlow export includes `interfaces` array in device node data

## Backend Integration

### promote_from_canvas() changes

When processing a device node with `data.interfaces`:
1. Create/update `Interface` records in the store
2. Run Rules 29, 30, 31 server-side
3. On errors, abort promote and return 422 with structured error list

### IPAM ingestion changes

- Support optional `interface_role` CSV column
- Support optional `interface_name` CSV column (instead of auto-generating `eth-{ip}`)
- Auto-set `subnet_id` on Interface from IPResolver after all subnets are loaded

### Knowledge Graph

- `export_react_flow_graph()`: include `interfaces` array in device node data dict
- Graph edges from `load_from_store()`: use interface role as edge label metadata

## Files Changed

| File | Action |
|------|--------|
| `backend/src/network/models.py` | Modify — add `InterfaceRole`, `ZoneType` enums; add `role`, `subnet_id` to Interface; add `zone_type` to Zone; add IP validator to Interface |
| `backend/src/network/topology_store.py` | Modify — migrations for `role`, `subnet_id`, `zone_type` columns; update `add_interface`/`list_interfaces` |
| `backend/src/network/knowledge_graph.py` | Modify — include interfaces in ReactFlow export; validate interfaces on promote |
| `backend/src/network/ipam_ingestion.py` | Modify — support `interface_role`, `interface_name` columns; set `subnet_id` |
| `frontend/src/utils/networkValidation.ts` | Modify — add Rules 29, 30, 31 to `validateTopology()` |
| `frontend/src/components/TopologyEditor/DeviceNode.tsx` | Modify — render interface rows + per-interface handles |
| `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx` | Modify — add interface editor section |
| `frontend/src/components/TopologyEditor/TopologyEditorView.tsx` | Modify — pass interfaces through to promote payload |
| `backend/tests/test_interface_validation.py` | Create — tests for Rules 29, 30, 31 |
