# Multi-Interface Appliance Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit interface roles, zone type classification, multi-interface canvas rendering, and three new validation rules (interface IP in subnet, no zone overlap, mgmt not in data plane).

**Architecture:** Extend existing `Interface` and `Zone` Pydantic models with new enums (`InterfaceRole`, `ZoneType`), add DB migrations, render interfaces as labeled rows with per-interface handles on canvas DeviceNode, add an interface editor to DevicePropertyPanel, extend `validateTopology()` with 3 new rules, and validate interfaces during promote.

**Tech Stack:** Python/Pydantic (backend models + validation), SQLite (topology store), React/TypeScript/ReactFlow (canvas), existing `networkValidation.ts` utility.

---

### Task 1: Add InterfaceRole and ZoneType enums + model fields

**Files:**
- Modify: `backend/src/network/models.py:155-233`

**Step 1: Add enums and model fields**

In `backend/src/network/models.py`, add the two new enums after `HARole` (line 159), add `role` and `subnet_id` fields to `Interface`, add IP validator to `Interface`, and add `zone_type` field to `Zone`.

After the `HARole` enum (line 159), add:

```python
class InterfaceRole(str, Enum):
    MANAGEMENT = "management"
    INSIDE = "inside"
    OUTSIDE = "outside"
    DMZ = "dmz"
    SYNC = "sync"
    LOOPBACK = "loopback"


class ZoneType(str, Enum):
    MANAGEMENT = "management"
    DATA = "data"
    DMZ = "dmz"
```

Update the `Interface` class (line 190) to add `role`, `subnet_id`, and an IP validator:

```python
class Interface(BaseModel):
    id: str
    device_id: str
    name: str = ""
    ip: str = ""
    mac: str = ""
    zone_id: str = ""
    vrf: str = ""
    speed: str = ""
    status: str = "up"
    role: str = ""       # InterfaceRole value or empty
    subnet_id: str = ""  # FK to subnet

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ip(v, "interface ip")
```

Update the `Zone` class (line 227) to add `zone_type`:

```python
class Zone(BaseModel):
    id: str
    name: str
    security_level: int = 0
    description: str = ""
    firewall_id: str = ""
    zone_type: str = ""  # ZoneType value or empty
```

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('backend/src/network/models.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/network/models.py
git commit -m "feat(models): add InterfaceRole, ZoneType enums and model fields"
```

---

### Task 2: DB migrations and store updates for new columns

**Files:**
- Modify: `backend/src/network/topology_store.py:38-50` (init_tables), `195-221` (migrate_tables), `299-330` (interface CRUD), `324-330` (zone CRUD)

**Step 1: Update `_init_tables` interfaces schema**

In the `_init_tables` method, update the `CREATE TABLE IF NOT EXISTS interfaces` statement to include the new columns:

```sql
CREATE TABLE IF NOT EXISTS interfaces (
    id TEXT PRIMARY KEY, device_id TEXT, name TEXT, ip TEXT,
    mac TEXT, zone_id TEXT, vrf TEXT, speed TEXT, status TEXT,
    role TEXT DEFAULT '', subnet_id TEXT DEFAULT '',
    FOREIGN KEY (device_id) REFERENCES devices(id)
);
```

Update the `CREATE TABLE IF NOT EXISTS zones` statement:

```sql
CREATE TABLE IF NOT EXISTS zones (
    id TEXT PRIMARY KEY, name TEXT, security_level INTEGER,
    description TEXT, firewall_id TEXT, zone_type TEXT DEFAULT ''
);
```

**Step 2: Add migrations in `_migrate_tables`**

Add these migrations to the `migrations` list:

```python
"ALTER TABLE interfaces ADD COLUMN role TEXT DEFAULT ''",
"ALTER TABLE interfaces ADD COLUMN subnet_id TEXT DEFAULT ''",
"ALTER TABLE zones ADD COLUMN zone_type TEXT DEFAULT ''",
```

**Step 3: Update `add_interface` to include new columns**

```python
def add_interface(self, iface: Interface) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO interfaces VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (iface.id, iface.device_id, iface.name, iface.ip,
         iface.mac, iface.zone_id, iface.vrf, iface.speed, iface.status,
         iface.role, iface.subnet_id),
    )
    conn.commit()
    conn.close()
```

**Step 4: Update `add_zone` to include `zone_type`**

```python
def add_zone(self, zone: Zone) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO zones VALUES (?,?,?,?,?,?)",
        (zone.id, zone.name, zone.security_level, zone.description,
         zone.firewall_id, zone.zone_type),
    )
    conn.commit()
    conn.close()
```

**Step 5: Verify**

Run: `python3 -c "from src.network.topology_store import TopologyStore; s = TopologyStore(':memory:'); print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add backend/src/network/topology_store.py
git commit -m "feat(store): add role, subnet_id, zone_type columns with migrations"
```

---

### Task 3: Backend interface validation rules

**Files:**
- Create: `backend/src/network/interface_validation.py`
- Create: `backend/tests/test_interface_validation.py`

**Step 1: Write the tests**

Create `backend/tests/test_interface_validation.py`:

```python
"""Tests for multi-interface validation rules 29, 30, 31."""
import pytest
from src.network.interface_validation import validate_device_interfaces
from src.network.models import Interface, Subnet, Zone


@pytest.fixture
def subnet_10():
    return Subnet(id="s1", cidr="10.0.1.0/24")


@pytest.fixture
def subnet_192():
    return Subnet(id="s2", cidr="192.168.1.0/24")


@pytest.fixture
def mgmt_zone():
    return Zone(id="z-mgmt", name="management", zone_type="management")


@pytest.fixture
def data_zone():
    return Zone(id="z-data", name="production", zone_type="data")


@pytest.fixture
def dmz_zone():
    return Zone(id="z-dmz", name="dmz", zone_type="dmz")


class TestRule29_IPInSubnet:
    def test_ip_within_subnet_passes(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.5", subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        assert not any(e["rule"] == 29 for e in errors)

    def test_ip_outside_subnet_fails(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.2.5", subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        rule29 = [e for e in errors if e["rule"] == 29]
        assert len(rule29) == 1
        assert "10.0.2.5" in rule29[0]["message"]

    def test_no_subnet_id_skips_check(self):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.5", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 29 for e in errors)

    def test_empty_ip_skips_check(self, subnet_10):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            subnet_id="s1", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [subnet_10], [])
        assert not any(e["rule"] == 29 for e in errors)


class TestRule30_NoZoneOverlap:
    def test_different_zones_passes(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.2.1", zone_id="z-outside", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)

    def test_same_zone_fails(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.1.2", zone_id="z-inside", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        rule30 = [e for e in errors if e["rule"] == 30]
        assert len(rule30) == 1

    def test_sync_role_exempt_from_zone_overlap(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="z-inside", role="inside"),
            Interface(id="i2", device_id="d1", name="sync0",
                      ip="10.0.1.2", zone_id="z-inside", role="sync"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)

    def test_empty_zone_skipped(self):
        ifaces = [
            Interface(id="i1", device_id="d1", name="eth0",
                      ip="10.0.1.1", zone_id="", role="inside"),
            Interface(id="i2", device_id="d1", name="eth1",
                      ip="10.0.2.1", zone_id="", role="outside"),
        ]
        errors = validate_device_interfaces("d1", ifaces, [], [])
        assert not any(e["rule"] == 30 for e in errors)


class TestRule31_MgmtNotInDataPlane:
    def test_mgmt_in_mgmt_zone_passes(self, mgmt_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-mgmt", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [mgmt_zone])
        assert not any(e["rule"] == 31 for e in errors)

    def test_mgmt_in_data_zone_warns(self, data_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-data", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [data_zone])
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1
        assert rule31[0]["severity"] == "warning"

    def test_mgmt_in_dmz_zone_warns(self, dmz_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-dmz", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [dmz_zone])
        rule31 = [e for e in errors if e["rule"] == 31]
        assert len(rule31) == 1

    def test_non_mgmt_role_in_data_zone_ok(self, data_zone):
        ifaces = [Interface(id="i1", device_id="d1", name="eth0",
                            ip="10.0.1.1", zone_id="z-data", role="inside")]
        errors = validate_device_interfaces("d1", ifaces, [], [data_zone])
        assert not any(e["rule"] == 31 for e in errors)

    def test_mgmt_in_unclassified_zone_ok(self):
        unclassified = Zone(id="z-x", name="legacy", zone_type="")
        ifaces = [Interface(id="i1", device_id="d1", name="mgmt0",
                            ip="10.0.1.1", zone_id="z-x", role="management")]
        errors = validate_device_interfaces("d1", ifaces, [], [unclassified])
        assert not any(e["rule"] == 31 for e in errors)
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest backend/tests/test_interface_validation.py -v`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

Create `backend/src/network/interface_validation.py`:

```python
"""Multi-interface validation rules for network appliances."""
import ipaddress
from .models import Interface, Subnet, Zone


def validate_device_interfaces(
    device_id: str,
    interfaces: list[Interface],
    subnets: list[Subnet],
    zones: list[Zone],
) -> list[dict]:
    """Validate interfaces for a single device.

    Returns list of dicts: {rule, field, message, severity, interface_id}.
    """
    errors: list[dict] = []
    subnet_map = {s.id: s for s in subnets}
    zone_map = {z.id: z for z in zones}

    # Rule 29: Interface IP must be within its assigned subnet CIDR
    for iface in interfaces:
        if not iface.ip or not iface.subnet_id:
            continue
        subnet = subnet_map.get(iface.subnet_id)
        if not subnet:
            continue
        try:
            net = ipaddress.ip_network(subnet.cidr, strict=False)
            if ipaddress.ip_address(iface.ip) not in net:
                errors.append({
                    "rule": 29,
                    "field": "ip",
                    "message": (
                        f"Interface '{iface.name}' IP {iface.ip} is outside "
                        f"subnet '{subnet.id}' CIDR {subnet.cidr}"
                    ),
                    "severity": "error",
                    "interface_id": iface.id,
                })
        except ValueError:
            pass  # Bad IP/CIDR caught by model validators

    # Rule 30: No two non-sync interfaces may share a zone on the same device
    zone_ifaces: dict[str, list[Interface]] = {}
    for iface in interfaces:
        if not iface.zone_id or iface.role == "sync":
            continue
        zone_ifaces.setdefault(iface.zone_id, []).append(iface)

    for zone_id, iface_list in zone_ifaces.items():
        if len(iface_list) > 1:
            names = ", ".join(f"'{i.name}'" for i in iface_list)
            errors.append({
                "rule": 30,
                "field": "zone_id",
                "message": (
                    f"Interfaces {names} on device '{device_id}' share "
                    f"zone '{zone_id}' — each interface should be in a unique zone"
                ),
                "severity": "error",
                "interface_id": iface_list[0].id,
            })

    # Rule 31: Management interface should not be in a data/dmz zone
    for iface in interfaces:
        if iface.role != "management" or not iface.zone_id:
            continue
        zone = zone_map.get(iface.zone_id)
        if not zone or not zone.zone_type:
            continue  # Unclassified zone — no warning
        if zone.zone_type in ("data", "dmz"):
            errors.append({
                "rule": 31,
                "field": "role",
                "message": (
                    f"Management interface '{iface.name}' is in "
                    f"{zone.zone_type} zone '{zone.name}' — "
                    f"management interfaces should be in a management zone"
                ),
                "severity": "warning",
                "interface_id": iface.id,
            })

    return errors
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest backend/tests/test_interface_validation.py -v`
Expected: All 13 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/interface_validation.py backend/tests/test_interface_validation.py
git commit -m "feat(validation): add interface validation rules 29, 30, 31 with tests"
```

---

### Task 4: Frontend validation rules 29, 30, 31

**Files:**
- Modify: `frontend/src/utils/networkValidation.ts:114-240`

**Step 1: Add interface validation types and rules**

Add an `InterfaceData` interface before `CanvasNode` (line 114) and update `CanvasNode.data` to optionally include interfaces:

```typescript
export interface InterfaceData {
  id: string;
  name: string;
  ip: string;
  role: string;    // management | inside | outside | dmz | sync | loopback
  zone: string;    // zone ID
  subnetId?: string;
}
```

Inside `validateTopology()`, after the existing Rule 7 block (line 237), add the three new rules:

```typescript
  // Rule 29: Interface IP must be within assigned subnet CIDR
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    for (const iface of ifaces) {
      if (!iface.ip || !iface.subnetId) continue;
      const ipErr = validateIPv4(iface.ip);
      if (ipErr) continue; // skip bad IPs (caught by form validation)
      const subnetNode = containers.find((c) => c.id === iface.subnetId);
      if (!subnetNode) continue;
      const subCidr = (subnetNode.data.cidr as string) || '';
      if (!subCidr || validateCIDR(subCidr)) continue;
      if (!isIPInCIDR(iface.ip, subCidr)) {
        errors.push({
          field: 'interface.ip',
          message: `Interface '${iface.name}' IP ${iface.ip} is outside subnet CIDR ${subCidr}`,
          severity: 'error',
          nodeId: dev.id,
        });
      }
    }
  }

  // Rule 30: No two non-sync interfaces on same device may share a zone
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    const zoneMap = new Map<string, string[]>();
    for (const iface of ifaces) {
      if (!iface.zone || iface.role === 'sync') continue;
      const existing = zoneMap.get(iface.zone) || [];
      existing.push(iface.name || iface.id);
      zoneMap.set(iface.zone, existing);
    }
    for (const [zone, names] of zoneMap) {
      if (names.length > 1) {
        errors.push({
          field: 'interface.zone',
          message: `Interfaces ${names.join(', ')} on '${dev.data.label || dev.id}' share zone '${zone}'`,
          severity: 'error',
          nodeId: dev.id,
        });
      }
    }
  }

  // Rule 31: Management interface should not be in data/dmz zone
  for (const dev of devices) {
    const ifaces = (dev.data.interfaces as InterfaceData[]) || [];
    for (const iface of ifaces) {
      if (iface.role !== 'management' || !iface.zone) continue;
      // Check if the zone node on canvas has a zone_type that is data or dmz
      const zoneNode = nodes.find(
        (n) => (n.data.entityId === iface.zone || n.id === iface.zone)
              && (n.data.zoneType === 'data' || n.data.zoneType === 'dmz')
      );
      if (zoneNode) {
        errors.push({
          field: 'interface.role',
          message: `Management interface '${iface.name}' is in ${zoneNode.data.zoneType} zone '${zoneNode.data.label || iface.zone}'`,
          severity: 'warning',
          nodeId: dev.id,
        });
      }
    }
  }
```

**Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/utils/networkValidation.ts
git commit -m "feat(validation): add interface rules 29, 30, 31 to frontend validateTopology"
```

---

### Task 5: Render interfaces on DeviceNode

**Files:**
- Modify: `frontend/src/components/TopologyEditor/DeviceNode.tsx`

**Step 1: Update DeviceNodeData and rendering**

Add `interfaces` to `DeviceNodeData`:

```typescript
interface DeviceNodeData {
  label: string;
  deviceType: string;
  ip?: string;
  vendor?: string;
  zone?: string;
  vlan?: number;
  description?: string;
  location?: string;
  status?: 'healthy' | 'degraded' | 'down';
  interfaces?: Array<{
    id: string;
    name: string;
    ip: string;
    role: string;
    zone: string;
  }>;
}
```

Add role color map after `typeAbbreviations`:

```typescript
const roleColors: Record<string, string> = {
  inside: '#22c55e',
  outside: '#ef4444',
  dmz: '#f59e0b',
  management: '#3b82f6',
  sync: '#64748b',
  loopback: '#a855f7',
};
```

After the zone label block (line 158), before the closing `</div>`, add the interfaces section:

```tsx
{/* Interfaces */}
{data.interfaces && data.interfaces.length > 0 && (
  <>
    <div className="w-full border-t mt-1 pt-1" style={{ borderColor: '#224349' }} />
    {data.interfaces.map((iface, idx) => (
      <div key={iface.id || idx} className="flex items-center gap-1.5 w-full px-1">
        <div
          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: roleColors[iface.role] || '#64748b' }}
        />
        <span className="text-[8px] font-mono truncate" style={{ color: '#94a3b8' }}>
          {iface.name}
        </span>
        <span className="text-[7px] font-mono ml-auto" style={{ color: '#475569' }}>
          {iface.role ? iface.role.slice(0, 3).toUpperCase() : ''}
        </span>
        <Handle
          type="source"
          position={Position.Right}
          id={`iface-${iface.id || idx}`}
          className="!w-2 !h-2 !bg-[#07b6d5] !border !border-[#0a0f13] !right-[-8px]"
          style={{ top: 'auto', position: 'relative' }}
        />
      </div>
    ))}
  </>
)}
```

**Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/TopologyEditor/DeviceNode.tsx
git commit -m "feat(canvas): render interface rows with role-colored dots on DeviceNode"
```

---

### Task 6: Interface editor in DevicePropertyPanel

**Files:**
- Modify: `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx`

**Step 1: Add interface editing state and UI**

Add interface state after the existing state declarations (after line 28):

```typescript
const [interfaces, setInterfaces] = useState<Array<{
  id: string; name: string; ip: string; role: string; zone: string;
}>>([]);
```

In the `useEffect` that loads `selectedNode` data (line 30-47), add:

```typescript
const ifaces = (d.interfaces as typeof interfaces) || [];
setInterfaces(ifaces);
```

Add interface errors to the `errors` useMemo:

```typescript
const errors = useMemo(() => {
  const ifaceErrors: Record<number, string | null> = {};
  interfaces.forEach((iface, idx) => {
    ifaceErrors[idx] = iface.ip ? validateIPv4(iface.ip) : null;
  });
  return {
    ip: ip ? validateIPv4(ip) : null,
    cidr: cidr ? validateCIDR(cidr) : null,
    remoteGateway: remoteGateway ? validateIPv4(remoteGateway) : null,
    interfaces: ifaceErrors,
  };
}, [ip, cidr, remoteGateway, interfaces]);
```

In `handleApply`, add `interfaces` to the data sent:

```typescript
const handleApply = () => {
  onNodeUpdate(selectedNode.id, {
    label: name, ip, vendor, deviceType, zone,
    cloudProvider, region, cidr, tunnelType, encryption,
    remoteGateway, lbType, lbScheme,
    interfaces,
  });
};
```

Update the Apply button disabled condition:

```typescript
disabled={!!errors.ip || !!errors.cidr || !!errors.remoteGateway || Object.values(errors.interfaces).some(Boolean)}
```

Add the Interfaces section before the Apply button (before line 274). Show it for multi-interface device types (firewall, router, switch, load_balancer):

```tsx
{/* Interfaces */}
{['firewall', 'router', 'switch', 'load_balancer'].includes(deviceType) && (
  <div className="flex flex-col gap-2 mt-2 pt-2 border-t" style={{ borderColor: '#224349' }}>
    <label className="text-[10px] font-mono uppercase tracking-wider" style={{ color: '#64748b' }}>
      Interfaces
    </label>
    {interfaces.map((iface, idx) => (
      <div key={idx} className="flex flex-col gap-1 p-2 rounded" style={{ backgroundColor: '#0a0f13' }}>
        <div className="flex gap-1">
          <input
            type="text" value={iface.name} placeholder="eth0"
            onChange={(e) => {
              const next = [...interfaces];
              next[idx] = { ...next[idx], name: e.target.value };
              setInterfaces(next);
            }}
            className="text-xs font-mono px-2 py-1 rounded border w-16 focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
          <input
            type="text" value={iface.ip} placeholder="10.0.1.1"
            onChange={(e) => {
              const next = [...interfaces];
              next[idx] = { ...next[idx], ip: e.target.value };
              setInterfaces(next);
            }}
            className="text-xs font-mono px-2 py-1 rounded border flex-1 focus:outline-none focus:border-[#07b6d5]"
            style={{ ...inputStyle, borderColor: errors.interfaces[idx] ? '#ef4444' : '#224349' }}
          />
        </div>
        {errors.interfaces[idx] && (
          <p style={{ color: '#ef4444', fontSize: '9px', fontFamily: 'monospace' }}>{errors.interfaces[idx]}</p>
        )}
        <div className="flex gap-1">
          <select
            value={iface.role}
            onChange={(e) => {
              const next = [...interfaces];
              next[idx] = { ...next[idx], role: e.target.value };
              setInterfaces(next);
            }}
            className="text-xs font-mono px-1 py-1 rounded border flex-1 focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          >
            <option value="">Role...</option>
            <option value="management">Management</option>
            <option value="inside">Inside</option>
            <option value="outside">Outside</option>
            <option value="dmz">DMZ</option>
            <option value="sync">Sync</option>
            <option value="loopback">Loopback</option>
          </select>
          <input
            type="text" value={iface.zone} placeholder="Zone"
            onChange={(e) => {
              const next = [...interfaces];
              next[idx] = { ...next[idx], zone: e.target.value };
              setInterfaces(next);
            }}
            className="text-xs font-mono px-2 py-1 rounded border w-16 focus:outline-none focus:border-[#07b6d5]"
            style={inputStyle}
          />
          <button
            onClick={() => setInterfaces(interfaces.filter((_, i) => i !== idx))}
            className="text-xs px-1 rounded hover:bg-red-900/30"
            style={{ color: '#ef4444' }}
          >
            ×
          </button>
        </div>
      </div>
    ))}
    <button
      onClick={() => setInterfaces([...interfaces, { id: `iface-${Date.now()}`, name: '', ip: '', role: '', zone: '' }])}
      className="text-xs font-mono px-3 py-1 rounded border transition-colors hover:border-[#07b6d5]"
      style={{ borderColor: '#224349', color: '#07b6d5', backgroundColor: 'transparent' }}
    >
      + Add Interface
    </button>
  </div>
)}
```

**Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx
git commit -m "feat(panel): add interface editor with role/zone dropdowns and inline validation"
```

---

### Task 7: Include interfaces in ReactFlow export + promote

**Files:**
- Modify: `backend/src/network/knowledge_graph.py:64-79` (load_from_store), `449-493` (export), `356-447` (promote)

**Step 1: Include interfaces in export_react_flow_graph**

In `export_react_flow_graph()`, after building the `data` dict for each node (line 470-481), add interface data for device nodes:

```python
# Include interfaces for device nodes
if ntype == "device":
    device_ifaces = self.store.list_interfaces(device_id=node_id)
    data_dict["interfaces"] = [
        {
            "id": iface.id,
            "name": iface.name,
            "ip": iface.ip,
            "role": iface.role,
            "zone": iface.zone_id,
            "subnetId": iface.subnet_id,
        }
        for iface in device_ifaces
    ]
```

Where `data_dict` is the `"data"` key in the node dict being built. Refactor the code so the data dict is built into a variable first:

```python
data_dict = {
    "label": data.get("name", node_id),
    "entityId": node_id,
    "deviceType": data.get("device_type", "HOST"),
    "ip": data.get("management_ip") or data.get("cidr", ""),
    "vendor": data.get("vendor", ""),
    "zone": data.get("zone_id", ""),
    "vlan": data.get("vlan_id", 0),
    "description": data.get("description", ""),
    "location": data.get("location", "") or data.get("site", ""),
    "status": "healthy",
}

# Include interfaces for device nodes
if ntype == "device":
    device_ifaces = self.store.list_interfaces(device_id=node_id)
    data_dict["interfaces"] = [
        {
            "id": iface.id,
            "name": iface.name,
            "ip": iface.ip,
            "role": iface.role,
            "zone": iface.zone_id,
            "subnetId": iface.subnet_id,
        }
        for iface in device_ifaces
    ]

rf_nodes.append({
    "id": node_id,
    "type": rf_type,
    "position": {"x": (i % 6) * ROW_WIDTH, "y": (i // 6) * COL_HEIGHT},
    "data": data_dict,
})
```

**Step 2: Handle interfaces in promote_from_canvas**

In `promote_from_canvas()`, after `self.store.add_device(device)` (line 409), add interface processing:

```python
# Process interfaces from canvas data
iface_list = data.get("interfaces", [])
for iface_data in iface_list:
    iface = Interface(
        id=iface_data.get("id", f"iface-{node_id}-{iface_data.get('name', '')}"),
        device_id=node_id,
        name=iface_data.get("name", ""),
        ip=iface_data.get("ip", ""),
        role=iface_data.get("role", ""),
        zone_id=iface_data.get("zone", ""),
        subnet_id=iface_data.get("subnetId", ""),
    )
    self.store.add_interface(iface)
```

Add import for `Interface` at the top of the file if not already present (it should be in the existing imports from `.models`).

Also add import for `validate_device_interfaces`:

```python
from .interface_validation import validate_device_interfaces
```

After all nodes are processed, before returning `stats`, add interface validation:

```python
# Validate interfaces for all promoted devices
all_subnets = self.store.list_subnets()
all_zones = self.store.list_zones()
for node in nodes:
    if node.get("type", "device") == "device":
        device_id = node.get("id", "")
        device_ifaces = self.store.list_interfaces(device_id=device_id)
        if device_ifaces:
            iface_errors = validate_device_interfaces(
                device_id, device_ifaces, all_subnets, all_zones,
            )
            for ie in iface_errors:
                stats["errors"].append(ie["message"])
```

**Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('backend/src/network/knowledge_graph.py').read()); print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/network/knowledge_graph.py
git commit -m "feat(kg): include interfaces in ReactFlow export and validate on promote"
```

---

### Task 8: IPAM ingestion — support interface_role and interface_name columns

**Files:**
- Modify: `backend/src/network/ipam_ingestion.py:138-146`

**Step 1: Update interface creation in parse_ipam_csv**

In the interface creation block (lines 138-146), read optional `interface_role` and `interface_name` columns:

```python
# Create interface
if ip and device_name:
    device_id = f"device-{device_name.lower().replace(' ', '-')}"
    iface_name = row.get("interface_name", "").strip() or f"eth-{ip}"
    iface_role = row.get("interface_role", "").strip()
    iface_id = f"iface-{device_id}-{ip.replace('.', '-')}"

    # Resolve subnet_id from IP
    iface_subnet_id = ""
    if subnet_cidr:
        iface_subnet_id = f"subnet-{subnet_cidr.replace('/', '-')}"

    store.add_interface(Interface(
        id=iface_id, device_id=device_id, name=iface_name,
        ip=ip, zone_id=zone, role=iface_role,
        subnet_id=iface_subnet_id,
    ))
    stats["interfaces_added"] += 1
```

**Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('backend/src/network/ipam_ingestion.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Run existing IPAM tests**

Run: `python3 -m pytest backend/tests/test_ipam_ingestion.py -v`
Expected: All existing tests PASS (new columns are optional, backward compatible)

**Step 4: Commit**

```bash
git add backend/src/network/ipam_ingestion.py
git commit -m "feat(ipam): support interface_role, interface_name columns and auto-set subnet_id"
```

---

### Task 9: Final integration test and full suite verification

**Files:**
- No new files

**Step 1: Run all backend tests**

Run: `python3 -m pytest backend/tests/ -x -q`
Expected: All tests pass, 0 failures

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit any remaining fixes**

If any tests fail, fix and commit. Otherwise, this step produces no commit.

---

## Files Summary

| File | Action |
|------|--------|
| `backend/src/network/models.py` | Modify — InterfaceRole, ZoneType enums, Interface.role/subnet_id/validate_ip, Zone.zone_type |
| `backend/src/network/topology_store.py` | Modify — schema + migrations for role, subnet_id, zone_type; update add_interface, add_zone |
| `backend/src/network/interface_validation.py` | Create — validate_device_interfaces() with rules 29, 30, 31 |
| `backend/tests/test_interface_validation.py` | Create — 13 tests for rules 29, 30, 31 |
| `frontend/src/utils/networkValidation.ts` | Modify — InterfaceData type, rules 29, 30, 31 in validateTopology() |
| `frontend/src/components/TopologyEditor/DeviceNode.tsx` | Modify — interface rows with role-colored dots and per-interface handles |
| `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx` | Modify — interface editor section with add/remove/validate |
| `backend/src/network/knowledge_graph.py` | Modify — include interfaces in ReactFlow export, create interfaces on promote, validate |
| `backend/src/network/ipam_ingestion.py` | Modify — support interface_role, interface_name columns, set subnet_id |
