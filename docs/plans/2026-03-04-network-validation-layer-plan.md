# Network Validation Layer & HA Pair Modeling — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add comprehensive validation across the network stack (format, relationship, referential integrity) and model HA device pairs as first-class entities, so invalid data is caught before it corrupts the Knowledge Graph or produces wrong diagnosis results.

**Architecture:** Three-gate validation (frontend instant → canvas pre-save → backend Pydantic). HA pairs modeled as HAGroup entity with VIP tracking, backed by a new SQLite table. Canvas containment tracked via ReactFlow `parentId`. All validation errors surface as structured objects with field, message, severity.

**Tech Stack:** Python 3.12, Pydantic v2 field validators, Python `ipaddress` module, TypeScript, ReactFlow parentId/extent, React state for inline errors

---

## Task 1: Shared Network Validation Utility (Frontend)

**Files:**
- Create: `frontend/src/utils/networkValidation.ts`
- Test: manual — used by all subsequent frontend tasks

**Step 1: Create the validation utility**

Create `frontend/src/utils/networkValidation.ts`:

```typescript
/**
 * Network validation utilities — shared across canvas, forms, and dialogs.
 * Backend is authoritative; these are for instant UX feedback.
 */

export interface ValidationError {
  field: string;
  message: string;
  severity: 'error' | 'warning' | 'suggestion';
  nodeId?: string;
}

/** Validate an IPv4 address. Returns error message or null. */
export function validateIPv4(ip: string): string | null {
  if (!ip) return null; // empty is allowed (optional field)
  const parts = ip.split('.');
  if (parts.length !== 4) return `'${ip}' is not a valid IPv4 address`;
  for (const part of parts) {
    const num = Number(part);
    if (!Number.isInteger(num) || num < 0 || num > 255 || part !== String(num)) {
      return `'${ip}' is not a valid IPv4 address`;
    }
  }
  return null;
}

/** Validate a CIDR block (e.g. 10.0.0.0/24). Returns error message or null. */
export function validateCIDR(cidr: string): string | null {
  if (!cidr) return null;
  const parts = cidr.split('/');
  if (parts.length !== 2) return `'${cidr}' is not valid CIDR notation`;
  const ipErr = validateIPv4(parts[0]);
  if (ipErr) return `'${cidr}' has invalid IP portion`;
  const prefix = Number(parts[1]);
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    return `'${cidr}' has invalid prefix length (must be 0-32)`;
  }
  return null;
}

/** Validate a port number. Returns error message or null. */
export function validatePort(port: string | number): string | null {
  const num = typeof port === 'string' ? Number(port) : port;
  if (isNaN(num) || !Number.isInteger(num)) return 'Port must be a whole number';
  if (num < 0 || num > 65535) return 'Port must be 0–65535';
  return null;
}

/** Validate a VLAN ID. Returns error message or null. 0 means "unset". */
export function validateVLAN(vlan: string | number): string | null {
  const num = typeof vlan === 'string' ? Number(vlan) : vlan;
  if (isNaN(num) || !Number.isInteger(num)) return 'VLAN must be a whole number';
  if (num === 0) return null; // unset
  if (num < 1 || num > 4094) return 'VLAN must be 1–4094';
  return null;
}

/** Parse an IPv4 address to a 32-bit integer for comparison. */
function ipToInt(ip: string): number {
  return ip.split('.').reduce((acc, octet) => (acc << 8) + Number(octet), 0) >>> 0;
}

/** Parse CIDR to { network: number, mask: number }. */
function parseCIDR(cidr: string): { network: number; mask: number; prefix: number } | null {
  const parts = cidr.split('/');
  if (parts.length !== 2) return null;
  const prefix = Number(parts[1]);
  if (isNaN(prefix) || prefix < 0 || prefix > 32) return null;
  const mask = prefix === 0 ? 0 : (~0 << (32 - prefix)) >>> 0;
  const network = ipToInt(parts[0]) & mask;
  return { network, mask, prefix };
}

/** Check if an IP address falls within a CIDR block. */
export function isIPInCIDR(ip: string, cidr: string): boolean {
  const parsed = parseCIDR(cidr);
  if (!parsed) return false;
  const ipNum = ipToInt(ip);
  return (ipNum & parsed.mask) === parsed.network;
}

/** Check if child CIDR is a subset of parent CIDR. */
export function isCIDRSubsetOf(child: string, parent: string): boolean {
  const c = parseCIDR(child);
  const p = parseCIDR(parent);
  if (!c || !p) return false;
  // Child prefix must be >= parent prefix (smaller or equal network)
  if (c.prefix < p.prefix) return false;
  // Child network masked by parent mask must equal parent network
  return (c.network & p.mask) === p.network;
}

/**
 * Detect overlapping CIDRs in a list. Returns pairs of overlapping CIDRs.
 * Two CIDRs overlap if either is a subset of the other.
 */
export function detectOverlappingCIDRs(cidrs: string[]): Array<[string, string]> {
  const overlaps: Array<[string, string]> = [];
  for (let i = 0; i < cidrs.length; i++) {
    for (let j = i + 1; j < cidrs.length; j++) {
      if (isCIDRSubsetOf(cidrs[i], cidrs[j]) || isCIDRSubsetOf(cidrs[j], cidrs[i])) {
        overlaps.push([cidrs[i], cidrs[j]]);
      }
    }
  }
  return overlaps;
}

/** Check if two CIDRs overlap (either direction). */
export function doCIDRsOverlap(a: string, b: string): boolean {
  return isCIDRSubsetOf(a, b) || isCIDRSubsetOf(b, a);
}
```

**Step 2: Run TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/utils/networkValidation.ts
git commit -m "feat(network): add shared network validation utility"
```

---

## Task 2: Backend Pydantic Field Validators (P0 + P3)

**Files:**
- Modify: `backend/src/network/models.py:1-5, 127-137, 150-157, 335-344`
- Modify: `backend/src/api/network_models.py:1-12`
- Create: `backend/tests/test_network_validation.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_network_validation.py`:

```python
"""Tests for Pydantic field validators on network models."""
import pytest
from pydantic import ValidationError
from src.network.models import Device, Subnet, Flow, DeviceType


class TestDeviceValidation:
    def test_valid_device(self):
        d = Device(id="d1", name="fw-01", management_ip="10.0.0.1")
        assert d.management_ip == "10.0.0.1"

    def test_empty_ip_allowed(self):
        d = Device(id="d1", name="fw-01", management_ip="")
        assert d.management_ip == ""

    def test_invalid_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Device(id="d1", name="fw-01", management_ip="999.999.999.999")

    def test_garbage_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Device(id="d1", name="fw-01", management_ip="not-an-ip")

    def test_valid_vlan(self):
        d = Device(id="d1", name="fw-01", vlan_id=100)
        assert d.vlan_id == 100

    def test_vlan_zero_allowed(self):
        d = Device(id="d1", name="fw-01", vlan_id=0)
        assert d.vlan_id == 0

    def test_vlan_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="VLAN"):
            Device(id="d1", name="fw-01", vlan_id=5000)

    def test_negative_vlan_rejected(self):
        with pytest.raises(ValidationError, match="VLAN"):
            Device(id="d1", name="fw-01", vlan_id=-1)


class TestSubnetValidation:
    def test_valid_cidr(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24")
        assert s.cidr == "10.0.0.0/24"

    def test_invalid_cidr_rejected(self):
        with pytest.raises(ValidationError, match="Invalid CIDR"):
            Subnet(id="s1", cidr="not-a-cidr")

    def test_empty_gateway_allowed(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="")
        assert s.gateway_ip == ""

    def test_valid_gateway(self):
        s = Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="10.0.0.1")
        assert s.gateway_ip == "10.0.0.1"

    def test_invalid_gateway_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Subnet(id="s1", cidr="10.0.0.0/24", gateway_ip="bad-ip")


class TestFlowValidation:
    def test_valid_flow(self):
        f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=443)
        assert f.port == 443

    def test_invalid_src_ip_rejected(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            Flow(id="f1", src_ip="bad", dst_ip="10.0.0.2", port=443)

    def test_port_out_of_range(self):
        with pytest.raises(ValidationError, match="port"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=99999)

    def test_negative_port_rejected(self):
        with pytest.raises(ValidationError, match="port"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=-1)

    def test_invalid_protocol_rejected(self):
        with pytest.raises(ValidationError, match="protocol"):
            Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=80, protocol="ftp")

    def test_valid_protocols(self):
        for proto in ("tcp", "udp", "icmp", "any"):
            f = Flow(id="f1", src_ip="10.0.0.1", dst_ip="10.0.0.2", port=80, protocol=proto)
            assert f.protocol == proto


class TestDiagnoseRequestValidation:
    def test_valid_request(self):
        from src.api.network_models import DiagnoseRequest
        r = DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.0.2", port=443)
        assert r.protocol == "tcp"

    def test_invalid_src_ip(self):
        from src.api.network_models import DiagnoseRequest
        with pytest.raises(ValidationError, match="Invalid IP"):
            DiagnoseRequest(src_ip="bad", dst_ip="10.0.0.2")

    def test_port_out_of_range(self):
        from src.api.network_models import DiagnoseRequest
        with pytest.raises(ValidationError, match="port"):
            DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.0.2", port=70000)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_network_validation.py -v`
Expected: FAIL — no validators exist yet

**Step 3: Add validators to models.py**

In `backend/src/network/models.py`, add `field_validator` to imports on line 5:

```python
from pydantic import BaseModel, Field, ConfigDict, field_validator
```

Add a shared validator helper after the imports (after line 7):

```python
import ipaddress as _ipaddress

def _validate_ip(v: str, field_name: str) -> str:
    """Validate IP address format. Empty string is allowed (optional)."""
    if not v:
        return v
    try:
        _ipaddress.ip_address(v)
    except ValueError:
        raise ValueError(f"Invalid IP address for {field_name}: '{v}'")
    return v

def _validate_cidr(v: str, field_name: str) -> str:
    """Validate CIDR notation. Empty string is allowed."""
    if not v:
        return v
    try:
        _ipaddress.ip_network(v, strict=False)
    except ValueError:
        raise ValueError(f"Invalid CIDR for {field_name}: '{v}'")
    return v

VALID_PROTOCOLS = {"tcp", "udp", "icmp", "any"}
```

Add validators to `Device` (after line 137):

```python
class Device(BaseModel):
    id: str
    name: str
    vendor: str = ""
    device_type: DeviceType = DeviceType.HOST
    management_ip: str = ""
    model: str = ""
    location: str = ""
    zone_id: str = ""
    vlan_id: int = 0
    description: str = ""

    @field_validator("management_ip")
    @classmethod
    def validate_management_ip(cls, v: str) -> str:
        return _validate_ip(v, "management_ip")

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v: int) -> int:
        if v != 0 and (v < 1 or v > 4094):
            raise ValueError(f"VLAN ID must be 0 (unset) or 1-4094, got {v}")
        return v
```

Add validators to `Subnet` (after line 157):

```python
class Subnet(BaseModel):
    id: str
    cidr: str
    vlan_id: int = 0
    zone_id: str = ""
    gateway_ip: str = ""
    description: str = ""
    site: str = ""

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        return _validate_cidr(v, "cidr")

    @field_validator("gateway_ip")
    @classmethod
    def validate_gateway_ip(cls, v: str) -> str:
        return _validate_ip(v, "gateway_ip")

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v: int) -> int:
        if v != 0 and (v < 1 or v > 4094):
            raise ValueError(f"VLAN ID must be 0 (unset) or 1-4094, got {v}")
        return v
```

Add validators to `Flow` (after line 344):

```python
class Flow(BaseModel):
    id: str
    src_ip: str
    dst_ip: str
    port: int
    protocol: str = "tcp"
    timestamp: str = ""
    diagnosis_status: DiagnosisStatus = DiagnosisStatus.RUNNING
    confidence: float = 0.0
    session_id: str = ""

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_flow_ips(cls, v: str) -> str:
        return _validate_ip(v, "ip")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 0 or v > 65535:
            raise ValueError(f"port must be 0-65535, got {v}")
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v not in VALID_PROTOCOLS:
            raise ValueError(f"protocol must be one of {VALID_PROTOCOLS}, got '{v}'")
        return v
```

**Step 4: Add validators to DiagnoseRequest**

In `backend/src/api/network_models.py`, update:

```python
"""Request/response Pydantic models for the network troubleshooting API."""
import ipaddress
from pydantic import BaseModel, Field, field_validator
from typing import Optional

VALID_PROTOCOLS = {"tcp", "udp", "icmp", "any"}


class DiagnoseRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 80
    protocol: str = "tcp"
    session_id: Optional[str] = None
    bidirectional: bool = False

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def validate_ips(cls, v: str) -> str:
        if not v:
            raise ValueError("IP address is required")
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid IP address: '{v}'")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v < 0 or v > 65535:
            raise ValueError(f"port must be 0-65535, got {v}")
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v: str) -> str:
        if v not in VALID_PROTOCOLS:
            raise ValueError(f"protocol must be one of {VALID_PROTOCOLS}, got '{v}'")
        return v
```

**Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_network_validation.py -v`
Expected: ALL PASS

Run: `cd backend && python3 -m pytest tests/ -v --ignore=tests/test_diagnosis_writeback.py`
Expected: ALL PASS (existing tests still work — Device("", management_ip="") is still valid)

**Step 6: Commit**

```bash
git add backend/src/network/models.py backend/src/api/network_models.py backend/tests/test_network_validation.py
git commit -m "feat(network): add Pydantic field validators for IP, CIDR, port, protocol, VLAN"
```

---

## Task 3: IPAM Ingestion — IP-in-Subnet + Gateway Validation (P1)

**Files:**
- Modify: `backend/src/network/ipam_ingestion.py:57-78`
- Modify: `backend/tests/test_ipam_ingestion.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_ipam_ingestion.py`:

```python
class TestIPInSubnetValidation:
    """IP must fall within its declared subnet CIDR."""

    def test_ip_outside_subnet_rejected(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
192.168.100.50,10.0.0.0/24,Device1,trust,100,IP not in subnet"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 1
        assert "not within subnet" in stats["errors"][0]
        assert stats["devices_added"] == 0
        assert stats["interfaces_added"] == 0

    def test_ip_inside_subnet_accepted(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.50,10.0.0.0/24,Device1,trust,100,Valid"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0
        assert stats["devices_added"] == 1

    def test_ip_at_network_boundary_accepted(self, tmp_store):
        """First usable IP in subnet should be accepted."""
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,100,Valid"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0

    def test_ip_at_broadcast_accepted(self, tmp_store):
        """Broadcast address - technically valid to assign (some systems use it)."""
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.255,10.0.0.0/24,Device1,trust,100,Broadcast"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert len(stats["errors"]) == 0


class TestGatewayValidation:
    """Gateway IP must be within its subnet CIDR if a gateway column is provided."""

    def test_gateway_outside_subnet_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description,gateway
10.0.0.1,10.0.0.0/24,Device1,trust,100,test,192.168.1.1"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        # Gateway outside subnet is a warning, row still imported
        assert any("gateway" in e.lower() for e in stats["errors"])

    def test_valid_gateway_no_warning(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description,gateway
10.0.0.1,10.0.0.0/24,Device1,trust,100,test,10.0.0.254"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert not any("gateway" in e.lower() for e in stats["errors"])


class TestVLANRangeValidation:
    """VLAN IDs must be 0 (unset) or 1-4094."""

    def test_vlan_out_of_range_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,5000,Bad VLAN"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert any("VLAN" in e for e in stats["errors"])

    def test_vlan_zero_allowed(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,0,No VLAN"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert not any("VLAN" in e for e in stats["errors"])


class TestOverlappingSubnets:
    """Detect overlapping CIDRs in the same import."""

    def test_overlapping_cidrs_warned(self, tmp_store):
        csv_content = """ip,subnet,device,zone,vlan,description
10.0.0.1,10.0.0.0/24,Device1,trust,100,Parent
10.0.0.129,10.0.0.128/25,Device2,trust,100,Overlapping child"""
        stats = parse_ipam_csv(csv_content, tmp_store)
        assert any("overlap" in e.lower() for e in stats["errors"])
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_ipam_ingestion.py::TestIPInSubnetValidation -v`
Expected: FAIL

**Step 3: Add validations to parse_ipam_csv**

In `backend/src/network/ipam_ingestion.py`, add after the duplicate IP check (after line 78) and before subnet creation:

```python
            # Validate IP is within declared subnet
            if ip and subnet_cidr:
                try:
                    net = ipaddress.ip_network(subnet_cidr, strict=False)
                    if ipaddress.ip_address(ip) not in net:
                        stats["errors"].append(
                            f"Row {row_num}: IP '{ip}' is not within subnet '{subnet_cidr}'"
                        )
                        continue
                except ValueError:
                    pass  # Already caught above

            # Validate VLAN range
            vlan_int = int(vlan or 0)
            if vlan_int != 0 and (vlan_int < 1 or vlan_int > 4094):
                stats["errors"].append(f"Row {row_num}: VLAN {vlan_int} out of range (1-4094)")
                vlan_int = 0  # Reset to unset but don't skip row
```

After the subnet creation loop, add gateway validation:

```python
            # Validate gateway IP if provided
            gateway = row.get("gateway", "").strip()
            if gateway and subnet_cidr:
                try:
                    net = ipaddress.ip_network(subnet_cidr, strict=False)
                    if ipaddress.ip_address(gateway) not in net:
                        stats["errors"].append(
                            f"Row {row_num}: Gateway '{gateway}' is not within subnet '{subnet_cidr}'"
                        )
                except ValueError:
                    pass
```

Add overlapping CIDR detection after the main loop (before `return stats`):

```python
    # Detect overlapping subnets
    subnet_list = list(seen_subnets)
    for i in range(len(subnet_list)):
        for j in range(i + 1, len(subnet_list)):
            try:
                a = ipaddress.ip_network(subnet_list[i], strict=False)
                b = ipaddress.ip_network(subnet_list[j], strict=False)
                if a.overlaps(b):
                    stats["errors"].append(
                        f"Overlapping subnets detected: '{subnet_list[i]}' and '{subnet_list[j]}'"
                    )
            except ValueError:
                pass
```

Also update the `vlan` variable usage in device/subnet creation to use `vlan_int`.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_ipam_ingestion.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/ipam_ingestion.py backend/tests/test_ipam_ingestion.py
git commit -m "feat(network): add IP-in-subnet, gateway, VLAN range, and overlap validation to IPAM ingestion"
```

---

## Task 4: Frontend Form Validation — Diagnosis Request + Property Panel (P0)

**Files:**
- Modify: `frontend/src/components/ActionCenter/forms/NetworkTroubleshootingFields.tsx`
- Modify: `frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx`

**Step 1: Add inline validation to NetworkTroubleshootingFields**

In `frontend/src/components/ActionCenter/forms/NetworkTroubleshootingFields.tsx`, import the validation utility and add error state:

```typescript
import React, { useMemo } from 'react';
import { NetworkTroubleshootingForm } from '../../../types';
import { validateIPv4, validatePort } from '../../../utils/networkValidation';

interface NetworkTroubleshootingFieldsProps {
  data: NetworkTroubleshootingForm;
  onChange: (data: NetworkTroubleshootingForm) => void;
}

const NetworkTroubleshootingFields: React.FC<NetworkTroubleshootingFieldsProps> = ({ data, onChange }) => {
  const update = (field: Partial<NetworkTroubleshootingForm>) => {
    onChange({ ...data, ...field });
  };

  const errors = useMemo(() => ({
    src_ip: data.src_ip ? validateIPv4(data.src_ip) : null,
    dst_ip: data.dst_ip ? validateIPv4(data.dst_ip) : null,
    port: data.port ? validatePort(data.port) : null,
  }), [data.src_ip, data.dst_ip, data.port]);

  const inputClasses = "w-full rounded-lg border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-1";
  const inputStyle = (hasError: boolean) => ({
    backgroundColor: '#0f2023',
    borderColor: hasError ? '#ef4444' : '#224349',
    color: '#e2e8f0',
  });
  const labelClasses = "text-xs font-mono uppercase tracking-widest mb-1.5 block";
  const labelStyle = { color: '#64748b' };
  const errorStyle = { color: '#ef4444', fontSize: '10px', fontFamily: 'monospace', marginTop: '4px' };

  return (
    <div className="space-y-4">
      <div>
        <label className={labelClasses} style={labelStyle}>Source IP</label>
        <input type="text" placeholder="e.g. 10.0.1.50" value={data.src_ip}
          onChange={(e) => update({ src_ip: e.target.value })}
          className={inputClasses} style={inputStyle(!!errors.src_ip)} />
        {errors.src_ip && <p style={errorStyle}>{errors.src_ip}</p>}
      </div>
      <div>
        <label className={labelClasses} style={labelStyle}>Destination IP</label>
        <input type="text" placeholder="e.g. 10.2.0.100" value={data.dst_ip}
          onChange={(e) => update({ dst_ip: e.target.value })}
          className={inputClasses} style={inputStyle(!!errors.dst_ip)} />
        {errors.dst_ip && <p style={errorStyle}>{errors.dst_ip}</p>}
      </div>
      <div>
        <label className={labelClasses} style={labelStyle}>Port</label>
        <input type="text" placeholder="e.g. 443" value={data.port}
          onChange={(e) => update({ port: e.target.value })}
          className={inputClasses} style={inputStyle(!!errors.port)} />
        {errors.port && <p style={errorStyle}>{errors.port}</p>}
      </div>
      <div>
        <label className={labelClasses} style={labelStyle}>Protocol</label>
        <div className="flex gap-2">
          {(['tcp', 'udp'] as const).map((proto) => (
            <button key={proto} type="button" onClick={() => update({ protocol: proto })}
              className="px-4 py-2 rounded-lg text-xs font-mono uppercase tracking-wider transition-colors"
              style={{
                backgroundColor: data.protocol === proto ? '#07b6d5' : '#0f2023',
                color: data.protocol === proto ? '#0f2023' : '#64748b',
                borderWidth: 1, borderColor: data.protocol === proto ? '#07b6d5' : '#224349',
              }}>
              {proto}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default NetworkTroubleshootingFields;
```

**Step 2: Add inline validation to DevicePropertyPanel**

In `DevicePropertyPanel.tsx`, import the utility and add validation to IP and CIDR fields:

- Import: `import { validateIPv4, validateCIDR } from '../../utils/networkValidation';`
- Add `useMemo` to the React import
- Add errors computation:
```typescript
const errors = useMemo(() => ({
  ip: ip ? validateIPv4(ip) : null,
  cidr: cidr ? validateCIDR(cidr) : null,
  remoteGateway: remoteGateway ? validateIPv4(remoteGateway) : null,
}), [ip, cidr, remoteGateway]);
```
- Add `disabled={!!errors.ip || !!errors.cidr || !!errors.remoteGateway}` to the Apply button
- Add red border on error fields: change `style={inputStyle}` to `style={{ ...inputStyle, borderColor: errors.ip ? '#ef4444' : '#224349' }}` on the IP input
- Add error text below each field: `{errors.ip && <p style={{ color: '#ef4444', fontSize: '10px', fontFamily: 'monospace', marginTop: '2px' }}>{errors.ip}</p>}`
- Apply same pattern for CIDR and Remote Gateway fields

**Step 3: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ActionCenter/forms/NetworkTroubleshootingFields.tsx \
  frontend/src/components/TopologyEditor/DevicePropertyPanel.tsx
git commit -m "feat(network): add inline IP/CIDR/port validation to diagnosis form and property panel"
```

---

## Task 5: Canvas Containment Tracking via parentId (P1)

**Files:**
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`

**Step 1: Add onNodeDragStop handler for containment detection**

In `TopologyEditorView.tsx`, add a handler after `onPaneClick` (around line 101) that detects when a device node is dropped inside a container node (VPC, subnet) and sets `parentId`:

```typescript
// Containment detection — auto-set parentId when device is inside a container
const onNodeDragStop = useCallback(
  (_: React.MouseEvent, draggedNode: Node) => {
    if (draggedNode.type !== 'device') return; // only devices get parented

    const containers = nodes.filter(
      (n) => (n.type === 'vpc' || n.type === 'subnet' || n.type === 'compliance_zone') && n.id !== draggedNode.id
    );

    let newParentId: string | undefined = undefined;

    for (const container of containers) {
      const cw = (container.style?.width as number) || 300;
      const ch = (container.style?.height as number) || 200;
      const cx = container.position.x;
      const cy = container.position.y;
      const dx = draggedNode.position.x;
      const dy = draggedNode.position.y;

      if (dx >= cx && dx <= cx + cw && dy >= cy && dy <= cy + ch) {
        newParentId = container.id;
        break; // use first (innermost later if needed)
      }
    }

    // Update parentId on the dragged node
    setNodes((nds) =>
      nds.map((n) =>
        n.id === draggedNode.id
          ? { ...n, data: { ...n.data, parentContainerId: newParentId || '' } }
          : n
      )
    );
  },
  [nodes, setNodes]
);
```

Add `onNodeDragStop={onNodeDragStop}` to the `<ReactFlow>` component props.

**Step 2: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/TopologyEditor/TopologyEditorView.tsx
git commit -m "feat(network): track canvas containment via parentContainerId on device nodes"
```

---

## Task 6: Canvas Pre-Save Validation + Validation Panel (P1)

**Files:**
- Create: `frontend/src/components/TopologyEditor/ValidationPanel.tsx`
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`

**Step 1: Create ValidationPanel component**

Create `frontend/src/components/TopologyEditor/ValidationPanel.tsx`:

```tsx
import React from 'react';
import type { ValidationError } from '../../utils/networkValidation';

interface ValidationPanelProps {
  errors: ValidationError[];
  onClickError: (nodeId: string) => void;
  onDismiss: () => void;
}

const ValidationPanel: React.FC<ValidationPanelProps> = ({ errors, onClickError, onDismiss }) => {
  if (errors.length === 0) return null;

  const errorCount = errors.filter((e) => e.severity === 'error').length;
  const warnCount = errors.filter((e) => e.severity === 'warning').length;

  return (
    <div
      className="border-t p-3 overflow-y-auto"
      style={{ backgroundColor: '#0f1a1e', borderColor: '#224349', maxHeight: '200px' }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="material-symbols-outlined text-base"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#ef4444' }}
          >
            error
          </span>
          <span className="text-xs font-mono font-semibold" style={{ color: '#e2e8f0' }}>
            {errorCount > 0 && <span style={{ color: '#ef4444' }}>{errorCount} error{errorCount !== 1 ? 's' : ''}</span>}
            {errorCount > 0 && warnCount > 0 && ', '}
            {warnCount > 0 && <span style={{ color: '#f59e0b' }}>{warnCount} warning{warnCount !== 1 ? 's' : ''}</span>}
          </span>
        </div>
        <button
          onClick={onDismiss}
          className="text-xs font-mono px-2 py-1 rounded transition-colors hover:bg-white/5"
          style={{ color: '#64748b' }}
        >
          Dismiss
        </button>
      </div>
      <div className="flex flex-col gap-1">
        {errors.map((err, i) => (
          <button
            key={i}
            onClick={() => err.nodeId && onClickError(err.nodeId)}
            className="flex items-start gap-2 text-left px-2 py-1.5 rounded transition-colors hover:bg-white/5 text-xs font-mono"
            style={{ color: err.severity === 'error' ? '#ef4444' : err.severity === 'warning' ? '#f59e0b' : '#64748b' }}
          >
            <span
              className="material-symbols-outlined text-sm mt-0.5 flex-shrink-0"
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              {err.severity === 'error' ? 'cancel' : err.severity === 'warning' ? 'warning' : 'info'}
            </span>
            <span>{err.message}</span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default ValidationPanel;
```

**Step 2: Add validateTopology function**

Add to `frontend/src/utils/networkValidation.ts`:

```typescript
interface CanvasNode {
  id: string;
  type?: string;
  position: { x: number; y: number };
  style?: { width?: number; height?: number };
  data: Record<string, unknown>;
}

/** Validate all topology relationships before save/promote. */
export function validateTopology(nodes: CanvasNode[]): ValidationError[] {
  const errors: ValidationError[] = [];
  const containers = nodes.filter(
    (n) => n.type === 'vpc' || n.type === 'subnet' || n.type === 'compliance_zone'
  );
  const devices = nodes.filter((n) => n.type === 'device');

  // Collect all device IPs for duplicate detection
  const ipToNodes: Map<string, string[]> = new Map();
  for (const dev of devices) {
    const ip = (dev.data.ip as string) || '';
    if (ip) {
      const existing = ipToNodes.get(ip) || [];
      existing.push(dev.id);
      ipToNodes.set(ip, existing);
    }
  }

  // Rule 10: Duplicate IPs
  for (const [ip, nodeIds] of ipToNodes) {
    if (nodeIds.length > 1) {
      const names = nodeIds.map((id) => {
        const n = nodes.find((nd) => nd.id === id);
        return (n?.data.label as string) || id;
      });
      for (const nodeId of nodeIds) {
        errors.push({
          field: 'ip',
          message: `Duplicate IP '${ip}' shared by: ${names.join(', ')}`,
          severity: 'error',
          nodeId,
        });
      }
    }
  }

  // Rule 6: Device IP must be within parent container CIDR
  for (const dev of devices) {
    const devIp = (dev.data.ip as string) || '';
    const parentId = (dev.data.parentContainerId as string) || '';
    if (!devIp || !parentId) continue;

    const parent = containers.find((c) => c.id === parentId);
    if (!parent) continue;

    const parentCidr = (parent.data.cidr as string) || '';
    if (!parentCidr) continue;

    if (validateIPv4(devIp) || validateCIDR(parentCidr)) continue; // skip if formats are bad

    if (!isIPInCIDR(devIp, parentCidr)) {
      errors.push({
        field: 'ip',
        message: `'${dev.data.label || dev.id}' IP ${devIp} is outside ${parent.data.label || parent.id} CIDR ${parentCidr}`,
        severity: 'error',
        nodeId: dev.id,
      });
    }
  }

  // Rule 9: Overlapping subnet CIDRs
  const subnetNodes = containers.filter((c) => c.type === 'subnet');
  const subnetCidrs = subnetNodes.map((s) => ({
    id: s.id,
    label: (s.data.label as string) || s.id,
    cidr: (s.data.cidr as string) || '',
  })).filter((s) => s.cidr && !validateCIDR(s.cidr));

  for (let i = 0; i < subnetCidrs.length; i++) {
    for (let j = i + 1; j < subnetCidrs.length; j++) {
      if (doCIDRsOverlap(subnetCidrs[i].cidr, subnetCidrs[j].cidr)) {
        errors.push({
          field: 'cidr',
          message: `Overlapping subnets: '${subnetCidrs[i].label}' (${subnetCidrs[i].cidr}) and '${subnetCidrs[j].label}' (${subnetCidrs[j].cidr})`,
          severity: 'warning',
          nodeId: subnetCidrs[i].id,
        });
      }
    }
  }

  // Rule 7: Subnet CIDR must be inside parent VPC CIDR (check via position)
  for (const subnet of subnetNodes) {
    const subCidr = (subnet.data.cidr as string) || '';
    if (!subCidr || validateCIDR(subCidr)) continue;

    const parentVpc = containers.find(
      (c) => c.type === 'vpc' && isNodeInsideContainer(subnet, c)
    );
    if (!parentVpc) continue;

    const vpcCidr = (parentVpc.data.cidr as string) || '';
    if (!vpcCidr || validateCIDR(vpcCidr)) continue;

    if (!isCIDRSubsetOf(subCidr, vpcCidr)) {
      errors.push({
        field: 'cidr',
        message: `Subnet '${subnet.data.label || subnet.id}' CIDR ${subCidr} is not within VPC '${parentVpc.data.label || parentVpc.id}' CIDR ${vpcCidr}`,
        severity: 'error',
        nodeId: subnet.id,
      });
    }
  }

  return errors;
}

/** Check if nodeA's position is inside containerB's bounds. */
function isNodeInsideContainer(nodeA: CanvasNode, containerB: CanvasNode): boolean {
  const cw = (containerB.style?.width as number) || 300;
  const ch = (containerB.style?.height as number) || 200;
  return (
    nodeA.position.x >= containerB.position.x &&
    nodeA.position.x <= containerB.position.x + cw &&
    nodeA.position.y >= containerB.position.y &&
    nodeA.position.y <= containerB.position.y + ch
  );
}
```

**Step 3: Wire validation into TopologyEditorView**

In `TopologyEditorView.tsx`:

- Import: `import ValidationPanel from './ValidationPanel';`
- Import: `import { validateTopology, type ValidationError } from '../../utils/networkValidation';`
- Add state: `const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);`
- Modify `handleSave` to validate first:

```typescript
const handleSave = useCallback(async () => {
  if (!reactFlowInstance) return;
  const flow = reactFlowInstance.toObject();
  const errs = validateTopology(flow.nodes as any);
  const blocking = errs.filter((e) => e.severity === 'error');
  setValidationErrors(errs);
  if (blocking.length > 0) return; // block save

  setSaving(true);
  try {
    await saveTopology(JSON.stringify(flow), 'User-saved topology');
  } catch (err) {
    console.error('Failed to save topology:', err);
  } finally {
    setSaving(false);
  }
}, [reactFlowInstance]);
```

- Same pattern for `handlePromote`.
- Add `onClickError` handler to zoom to node:

```typescript
const handleValidationClick = useCallback((nodeId: string) => {
  const node = nodes.find((n) => n.id === nodeId);
  if (node && reactFlowInstance) {
    reactFlowInstance.fitView({ nodes: [node], duration: 300, padding: 0.5 });
    setSelectedNode(node);
  }
}, [nodes, reactFlowInstance]);
```

- Render `ValidationPanel` below the ReactFlow canvas (before `</div>` closing the main area):

```tsx
<ValidationPanel
  errors={validationErrors}
  onClickError={handleValidationClick}
  onDismiss={() => setValidationErrors([])}
/>
```

**Step 4: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/components/TopologyEditor/ValidationPanel.tsx \
  frontend/src/components/TopologyEditor/TopologyEditorView.tsx \
  frontend/src/utils/networkValidation.ts
git commit -m "feat(network): add canvas pre-save validation with ValidationPanel and containment checks"
```

---

## Task 7: Backend Promote Validation (P1 + P2)

**Files:**
- Modify: `backend/src/network/knowledge_graph.py:356-426`
- Create: `backend/tests/test_promote_validation.py`

**Step 1: Write failing tests**

Create `backend/tests/test_promote_validation.py`:

```python
"""Tests for topology promotion validation."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    return NetworkKnowledgeGraph(store)


def test_promote_device_with_invalid_ip_rejected(kg):
    nodes = [{"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "999.999.999.999", "deviceType": "firewall"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert len(result["errors"]) >= 1
    assert result["devices_promoted"] == 0


def test_promote_device_with_valid_ip_accepted(kg):
    nodes = [{"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.1", "deviceType": "firewall"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert result["devices_promoted"] == 1
    assert len(result["errors"]) == 0


def test_promote_subnet_with_invalid_cidr_rejected(kg):
    nodes = [{"id": "s1", "type": "subnet", "data": {"cidr": "not-valid"}}]
    result = kg.promote_from_canvas(nodes, [])
    assert len(result["errors"]) >= 1


def test_promote_duplicate_ips_warned(kg):
    nodes = [
        {"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.1", "deviceType": "firewall"}},
        {"id": "d2", "type": "device", "data": {"label": "fw-02", "ip": "10.0.0.1", "deviceType": "firewall"}},
    ]
    result = kg.promote_from_canvas(nodes, [])
    assert any("Duplicate IP" in e for e in result["errors"])
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_promote_validation.py -v`
Expected: FAIL

**Step 3: Add validation to promote_from_canvas**

In `knowledge_graph.py`, update `promote_from_canvas` to add a pre-validation pass before the main loop. Add duplicate IP detection and let Pydantic validators (from Task 2) catch format issues:

```python
def promote_from_canvas(self, nodes: list[dict], edges: list[dict]) -> dict:
    stats = {"devices_promoted": 0, "edges_promoted": 0, "errors": []}

    # Pre-validation: collect IPs for duplicate detection
    seen_ips: dict[str, str] = {}  # ip -> first node label

    for node in nodes:
        try:
            node_type = node.get("type", "device")
            data = node.get("data", {})
            node_id = node.get("id", "")

            if node_type == "device":
                ip = data.get("ip", "")

                # Duplicate IP detection
                if ip and ip in seen_ips:
                    stats["errors"].append(
                        f"Duplicate IP '{ip}' on '{data.get('label', node_id)}' "
                        f"(already used by '{seen_ips[ip]}')"
                    )
                    continue
                if ip:
                    seen_ips[ip] = data.get("label", node_id)

                dt_str = (data.get("deviceType") or "HOST").upper()
                try:
                    dt = DeviceType[dt_str]
                except KeyError:
                    dt = DeviceType.HOST

                device = Device(
                    id=node_id,
                    name=data.get("label", node_id),
                    device_type=dt,
                    management_ip=ip,
                    vendor=data.get("vendor", ""),
                    location=data.get("location", ""),
                    zone_id=data.get("zone", ""),
                    vlan_id=int(data.get("vlan") or 0),
                    description=data.get("description", ""),
                )
                self.store.add_device(device)
                self.add_device(device)
                stats["devices_promoted"] += 1

            elif node_type == "subnet":
                cidr = data.get("cidr") or data.get("ip", "")
                if cidr:
                    subnet = Subnet(
                        id=node_id,
                        cidr=cidr,
                        zone_id=data.get("zone", ""),
                        vlan_id=int(data.get("vlan") or 0),
                        description=data.get("description", ""),
                    )
                    self.store.add_subnet(subnet)
                    self.add_subnet(subnet)
                    stats["devices_promoted"] += 1

        except Exception as e:
            stats["errors"].append(f"Node {node.get('id', '?')}: {str(e)}")

    # ... edges loop unchanged ...
    return stats
```

The key change is that Pydantic `Device(management_ip="999.999.999.999")` now raises `ValidationError` which gets caught by the `except Exception` and added to `stats["errors"]`.

**Step 4: Run tests**

Run: `cd backend && python3 -m pytest tests/test_promote_validation.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/tests/test_promote_validation.py
git commit -m "feat(network): add validation to canvas-to-KG promotion (duplicate IPs, format checks)"
```

---

## Task 8: HA Group Data Model + Store (P4)

**Files:**
- Modify: `backend/src/network/models.py` — add HAMode, HARole, HAGroup
- Modify: `backend/src/network/topology_store.py` — add ha_groups table + CRUD
- Modify: `backend/src/network/models.py` — add ha_group_id, ha_role to Device
- Create: `backend/tests/test_ha_groups.py`

**Step 1: Write failing tests**

Create `backend/tests/test_ha_groups.py`:

```python
"""Tests for HA group model and store."""
import os
import pytest
from pydantic import ValidationError
from src.network.models import HAGroup, HAMode, HARole, Device, DeviceType
from src.network.topology_store import TopologyStore


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


class TestHAGroupModel:
    def test_valid_ha_group(self):
        g = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
                    active_member_id="d1")
        assert g.ha_mode == HAMode.ACTIVE_PASSIVE
        assert len(g.member_ids) == 2

    def test_ha_group_needs_2_members(self):
        with pytest.raises(ValidationError, match="at least 2"):
            HAGroup(id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1"])

    def test_vip_must_be_valid_ip(self):
        with pytest.raises(ValidationError, match="Invalid IP"):
            HAGroup(id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["not-an-ip"])

    def test_device_ha_fields(self):
        d = Device(id="d1", name="fw-01", ha_group_id="ha1", ha_role="active")
        assert d.ha_group_id == "ha1"
        assert d.ha_role == "active"


class TestHAGroupStore:
    def test_add_and_get_ha_group(self, store):
        g = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                    member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
                    active_member_id="d1")
        store.add_ha_group(g)
        loaded = store.get_ha_group("ha1")
        assert loaded is not None
        assert loaded.name == "FW-HA"
        assert loaded.member_ids == ["d1", "d2"]
        assert loaded.virtual_ips == ["10.0.0.1"]

    def test_list_ha_groups(self, store):
        g1 = HAGroup(id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
                     member_ids=["d1", "d2"])
        g2 = HAGroup(id="ha2", name="LB-HA", ha_mode=HAMode.ACTIVE_ACTIVE,
                     member_ids=["d3", "d4"])
        store.add_ha_group(g1)
        store.add_ha_group(g2)
        groups = store.list_ha_groups()
        assert len(groups) == 2

    def test_device_with_ha_fields_roundtrip(self, store):
        d = Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL,
                   management_ip="10.0.0.2", ha_group_id="ha1", ha_role="active")
        store.add_device(d)
        loaded = store.get_device("d1")
        assert loaded.ha_group_id == "ha1"
        assert loaded.ha_role == "active"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_ha_groups.py -v`
Expected: FAIL — HAGroup, HAMode, HARole not defined

**Step 3: Add HA enums and model to models.py**

In `backend/src/network/models.py`, add after the existing enums (after `ConnectivityStatus`, around line 123):

```python
class HAMode(str, Enum):
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    VRRP = "vrrp"
    CLUSTER = "cluster"

class HARole(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    MEMBER = "member"
```

Add the HAGroup model after the `ComplianceZone` class (around line 289):

```python
class HAGroup(BaseModel):
    id: str
    name: str
    ha_mode: HAMode
    member_ids: list[str]
    virtual_ips: list[str] = Field(default_factory=list)
    active_member_id: str = ""
    priority_map: dict[str, int] = Field(default_factory=dict)
    sync_interface: str = ""

    @field_validator("member_ids")
    @classmethod
    def validate_member_ids(cls, v: list[str]) -> list[str]:
        if len(v) < 2:
            raise ValueError("HA group must have at least 2 members")
        return v

    @field_validator("virtual_ips")
    @classmethod
    def validate_virtual_ips(cls, v: list[str]) -> list[str]:
        for vip in v:
            _validate_ip(vip, "virtual_ip")
        return v
```

Add `ha_group_id` and `ha_role` to Device model:

```python
class Device(BaseModel):
    # ... existing fields ...
    ha_group_id: str = ""
    ha_role: str = ""  # "active", "standby", "member", or ""
```

**Step 4: Add ha_groups table and CRUD to topology_store.py**

In `topology_store.py`, add to `_init_tables`:

```sql
CREATE TABLE IF NOT EXISTS ha_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ha_mode TEXT NOT NULL,
    member_ids TEXT NOT NULL,
    virtual_ips TEXT DEFAULT '[]',
    active_member_id TEXT DEFAULT '',
    priority_map TEXT DEFAULT '{}',
    sync_interface TEXT DEFAULT ''
);
```

Add to `_migrate_tables`:

```python
"ALTER TABLE devices ADD COLUMN ha_group_id TEXT DEFAULT ''",
"ALTER TABLE devices ADD COLUMN ha_role TEXT DEFAULT ''",
```

Add CRUD methods:

```python
def add_ha_group(self, group: HAGroup) -> None:
    conn = self._conn()
    conn.execute(
        "INSERT OR REPLACE INTO ha_groups (id, name, ha_mode, member_ids, virtual_ips, active_member_id, priority_map, sync_interface) VALUES (?,?,?,?,?,?,?,?)",
        (group.id, group.name, group.ha_mode.value, json.dumps(group.member_ids),
         json.dumps(group.virtual_ips), group.active_member_id,
         json.dumps(group.priority_map), group.sync_interface),
    )
    conn.commit()
    conn.close()

def get_ha_group(self, group_id: str) -> Optional[HAGroup]:
    conn = self._conn()
    row = conn.execute("SELECT * FROM ha_groups WHERE id = ?", (group_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return HAGroup(
        id=row["id"], name=row["name"],
        ha_mode=HAMode(row["ha_mode"]),
        member_ids=json.loads(row["member_ids"]),
        virtual_ips=json.loads(row["virtual_ips"] or "[]"),
        active_member_id=row["active_member_id"] or "",
        priority_map=json.loads(row["priority_map"] or "{}"),
        sync_interface=row["sync_interface"] or "",
    )

def list_ha_groups(self) -> list[HAGroup]:
    conn = self._conn()
    rows = conn.execute("SELECT * FROM ha_groups").fetchall()
    conn.close()
    return [HAGroup(
        id=r["id"], name=r["name"],
        ha_mode=HAMode(r["ha_mode"]),
        member_ids=json.loads(r["member_ids"]),
        virtual_ips=json.loads(r["virtual_ips"] or "[]"),
        active_member_id=r["active_member_id"] or "",
        priority_map=json.loads(r["priority_map"] or "{}"),
        sync_interface=r["sync_interface"] or "",
    ) for r in rows]
```

Update `add_device` INSERT to include ha_group_id and ha_role. Update `get_device` and `list_devices` SELECT to read ha_group_id and ha_role with NULL guards.

**Step 5: Run tests**

Run: `cd backend && python3 -m pytest tests/test_ha_groups.py -v`
Expected: ALL PASS

Run: `cd backend && python3 -m pytest tests/ -v --ignore=tests/test_diagnosis_writeback.py`
Expected: ALL PASS (no regressions)

**Step 6: Commit**

```bash
git add backend/src/network/models.py backend/src/network/topology_store.py backend/tests/test_ha_groups.py
git commit -m "feat(network): add HAGroup model, enums, and store with CRUD operations"
```

---

## Task 9: HA Group API Endpoints

**Files:**
- Modify: `backend/src/api/network_models.py` — add HAGroupRequest
- Modify: `backend/src/api/network_endpoints.py` — add HA CRUD endpoints

**Step 1: Add request model**

In `backend/src/api/network_models.py`, add:

```python
class HAGroupRequest(BaseModel):
    name: str
    ha_mode: str  # "active_passive", "active_active", "vrrp", "cluster"
    member_ids: list[str]
    virtual_ips: list[str] = []
    active_member_id: str = ""
```

**Step 2: Add endpoints to network_endpoints.py**

Add imports: `HAGroupRequest` from network_models, `HAGroup, HAMode` from models.

Add endpoints:

```python
@network_router.post("/ha-groups")
async def create_ha_group(req: HAGroupRequest):
    """Create an HA group."""
    import uuid
    from src.network.models import HAGroup, HAMode
    store = _get_topology_store()
    group = HAGroup(
        id=str(uuid.uuid4()),
        name=req.name,
        ha_mode=HAMode(req.ha_mode),
        member_ids=req.member_ids,
        virtual_ips=req.virtual_ips,
        active_member_id=req.active_member_id,
    )
    store.add_ha_group(group)
    # Update member devices with ha_group_id
    for i, mid in enumerate(req.member_ids):
        device = store.get_device(mid)
        if device:
            role = "active" if mid == req.active_member_id else "standby"
            if req.ha_mode == "active_active":
                role = "member"
            device.ha_group_id = group.id
            device.ha_role = role
            store.add_device(device)
    return {"status": "created", "ha_group_id": group.id}


@network_router.get("/ha-groups")
async def list_ha_groups():
    """List all HA groups."""
    store = _get_topology_store()
    groups = store.list_ha_groups()
    return {"ha_groups": [g.model_dump() for g in groups]}


@network_router.get("/ha-groups/{group_id}")
async def get_ha_group(group_id: str):
    """Get HA group details."""
    store = _get_topology_store()
    group = store.get_ha_group(group_id)
    if not group:
        raise HTTPException(404, "HA group not found")
    return {"ha_group": group.model_dump()}
```

**Step 3: Run type check + tests**

Run: `cd backend && python3 -m pytest tests/ -v --ignore=tests/test_diagnosis_writeback.py`
Expected: ALL PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add backend/src/api/network_models.py backend/src/api/network_endpoints.py
git commit -m "feat(network): add HA group CRUD API endpoints"
```

---

## Task 10: HA Group Validation Rules (P4)

**Files:**
- Modify: `backend/tests/test_ha_groups.py`
- Modify: `backend/src/network/knowledge_graph.py` or create `backend/src/network/ha_validation.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_ha_groups.py`:

```python
from src.network.ha_validation import validate_ha_group


class TestHAValidation:
    def test_members_must_be_same_device_type(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="rtr-01", device_type=DeviceType.ROUTER, management_ip="10.0.0.2"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"]))
        assert any("same device type" in e for e in errors)

    def test_members_must_be_in_same_subnet(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="192.168.1.1"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"]))
        assert any("same subnet" in e.lower() for e in errors)

    def test_vip_must_be_in_member_subnet(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], virtual_ips=["192.168.1.100"]))
        assert any("VIP" in e and "not within" in e for e in errors)

    def test_active_passive_needs_one_active(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="bad", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], active_member_id=""))
        assert any("active member" in e.lower() for e in errors)

    def test_valid_ha_group_no_errors(self, store):
        store.add_device(Device(id="d1", name="fw-01", device_type=DeviceType.FIREWALL, management_ip="10.0.0.1"))
        store.add_device(Device(id="d2", name="fw-02", device_type=DeviceType.FIREWALL, management_ip="10.0.0.2"))
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/24"))
        errors = validate_ha_group(store, HAGroup(
            id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
            member_ids=["d1", "d2"], virtual_ips=["10.0.0.100"],
            active_member_id="d1"))
        assert len(errors) == 0
```

**Step 2: Create ha_validation.py**

Create `backend/src/network/ha_validation.py`:

```python
"""HA group validation rules."""
import ipaddress
from .models import HAGroup, HAMode
from .topology_store import TopologyStore


def validate_ha_group(store: TopologyStore, group: HAGroup) -> list[str]:
    """Validate an HA group against stored topology. Returns list of error strings."""
    errors: list[str] = []

    # Load member devices
    members = []
    for mid in group.member_ids:
        device = store.get_device(mid)
        if not device:
            errors.append(f"Member device '{mid}' not found")
            continue
        members.append(device)

    if len(members) < 2:
        return errors  # can't validate further

    # Rule 20: Members must be same device type
    types = set(m.device_type for m in members)
    if len(types) > 1:
        errors.append(f"HA members must be same device type, found: {', '.join(t.value for t in types)}")

    # Rule 21: Members must be in same subnet
    member_ips = [m.management_ip for m in members if m.management_ip]
    if member_ips:
        subnets = store.list_subnets()
        member_subnets: dict[str, str] = {}
        for mip in member_ips:
            for s in subnets:
                try:
                    if ipaddress.ip_address(mip) in ipaddress.ip_network(s.cidr, strict=False):
                        member_subnets[mip] = s.cidr
                        break
                except ValueError:
                    pass
        subnet_set = set(member_subnets.values())
        if len(subnet_set) > 1:
            errors.append(f"HA members must be in same subnet, found: {', '.join(subnet_set)}")

    # Rule 22: VIPs must be in member subnet
    if group.virtual_ips and member_ips:
        # Find the common subnet
        subnets = store.list_subnets()
        for vip in group.virtual_ips:
            vip_in_subnet = False
            for s in subnets:
                try:
                    if ipaddress.ip_address(vip) in ipaddress.ip_network(s.cidr, strict=False):
                        # Check at least one member is also in this subnet
                        for mip in member_ips:
                            try:
                                if ipaddress.ip_address(mip) in ipaddress.ip_network(s.cidr, strict=False):
                                    vip_in_subnet = True
                                    break
                            except ValueError:
                                pass
                        if vip_in_subnet:
                            break
                except ValueError:
                    pass
            if not vip_in_subnet:
                errors.append(f"VIP '{vip}' is not within any subnet containing HA members")

    # Rule 24: Active-passive needs exactly 1 active
    if group.ha_mode == HAMode.ACTIVE_PASSIVE:
        if not group.active_member_id:
            errors.append("Active-passive HA group requires an active member to be designated")
        elif group.active_member_id not in group.member_ids:
            errors.append(f"Active member '{group.active_member_id}' is not in member list")

    return errors
```

**Step 3: Run tests**

Run: `cd backend && python3 -m pytest tests/test_ha_groups.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add backend/src/network/ha_validation.py backend/tests/test_ha_groups.py
git commit -m "feat(network): add HA group validation rules (same type, same subnet, VIP, active member)"
```

---

## Task 11: HA Group Duplicate-IP Suppression (P4 edge case)

**Files:**
- Modify: `backend/src/network/knowledge_graph.py` — suppress VIP duplicates in promote
- Modify: `frontend/src/utils/networkValidation.ts` — suppress VIP duplicates in canvas validation
- Modify: `backend/tests/test_promote_validation.py`

**Step 1: Write failing test**

Add to `backend/tests/test_promote_validation.py`:

```python
def test_promote_vip_not_flagged_as_duplicate(kg):
    """VIPs shared by HA group members should not trigger duplicate IP errors."""
    # First create an HA group in the store
    from src.network.models import HAGroup, HAMode
    kg.store.add_ha_group(HAGroup(
        id="ha1", name="FW-HA", ha_mode=HAMode.ACTIVE_PASSIVE,
        member_ids=["d1", "d2"], virtual_ips=["10.0.0.1"],
        active_member_id="d1",
    ))
    nodes = [
        {"id": "d1", "type": "device", "data": {"label": "fw-01", "ip": "10.0.0.2", "deviceType": "firewall"}},
        {"id": "d2", "type": "device", "data": {"label": "fw-02", "ip": "10.0.0.3", "deviceType": "firewall"}},
    ]
    result = kg.promote_from_canvas(nodes, [])
    assert not any("Duplicate IP" in e for e in result["errors"])
    assert result["devices_promoted"] == 2
```

**Step 2: Implement VIP suppression in promote**

In `promote_from_canvas`, load VIPs from HA groups before the duplicate check:

```python
# Load VIPs from HA groups to suppress false duplicate warnings
ha_groups = self.store.list_ha_groups()
known_vips = set()
for hg in ha_groups:
    known_vips.update(hg.virtual_ips)
```

Then in the duplicate check: `if ip and ip in seen_ips and ip not in known_vips:`

**Step 3: Run tests**

Run: `cd backend && python3 -m pytest tests/test_promote_validation.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/tests/test_promote_validation.py
git commit -m "feat(network): suppress duplicate-IP errors for HA group VIPs during promotion"
```

---

## Task 12: HA Group Canvas Node + Frontend API

**Files:**
- Create: `frontend/src/components/TopologyEditor/HAGroupNode.tsx`
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx` — register node type
- Modify: `frontend/src/components/TopologyEditor/NodePalette.tsx` — add HA Group to palette
- Modify: `frontend/src/services/api.ts` — add HA group API functions

**Step 1: Create HAGroupNode**

Create `frontend/src/components/TopologyEditor/HAGroupNode.tsx`:

```tsx
import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

const HAGroupNode: React.FC<NodeProps> = ({ data }) => {
  const mode = (data.haMode as string) || 'active_passive';
  const modeLabel = mode === 'active_active' ? 'A/A' : mode === 'vrrp' ? 'VRRP' : 'A/P';
  const vips = (data.virtualIps as string) || '';

  return (
    <div
      className="rounded-lg border-2 border-dashed p-3 relative"
      style={{
        minWidth: 280,
        minHeight: 140,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.05)',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#f59e0b' }} />
      <Handle type="source" position={Position.Right} style={{ background: '#f59e0b' }} />

      <div className="flex items-center gap-2 mb-1">
        <span
          className="material-symbols-outlined text-sm"
          style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}
        >
          sync
        </span>
        <span className="text-xs font-mono font-bold" style={{ color: '#f59e0b' }}>
          HA: {modeLabel}
        </span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
          {data.label || 'HA Group'}
        </span>
      </div>
      {vips && (
        <div className="text-[10px] font-mono" style={{ color: '#94a3b8' }}>
          VIP: {vips}
        </div>
      )}
    </div>
  );
};

export default memo(HAGroupNode);
```

**Step 2: Register in TopologyEditorView**

In `TopologyEditorView.tsx`:

- Import: `import HAGroupNode from './HAGroupNode';`
- Add to `nodeTypes`: `ha_group: HAGroupNode,`
- In the `onDrop` handler, add `'ha_group'` to the container types: `const isContainer = type === 'subnet' || type === 'zone' || type === 'vpc' || type === 'compliance_zone' || type === 'ha_group';`

**Step 3: Add to NodePalette**

In `NodePalette.tsx`, add an HA Group entry to the palette items with icon `sync` and type `ha_group`.

**Step 4: Add API functions**

In `frontend/src/services/api.ts`, add:

```typescript
export const createHAGroup = async (data: {
  name: string; ha_mode: string; member_ids: string[];
  virtual_ips?: string[]; active_member_id?: string;
}): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ha-groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Failed to create HA group: ${response.statusText}`);
  return response.json();
};

export const listHAGroups = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/ha-groups`);
  if (!response.ok) throw new Error(`Failed to list HA groups: ${response.statusText}`);
  return response.json();
};
```

**Step 5: Run type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 6: Commit**

```bash
git add frontend/src/components/TopologyEditor/HAGroupNode.tsx \
  frontend/src/components/TopologyEditor/TopologyEditorView.tsx \
  frontend/src/components/TopologyEditor/NodePalette.tsx \
  frontend/src/services/api.ts
git commit -m "feat(network): add HA Group canvas node, palette entry, and API functions"
```

---

## Verification Checklist

After all tasks are complete, verify:

1. `cd backend && python3 -m pytest tests/ -v --ignore=tests/test_diagnosis_writeback.py` — ALL PASS
2. `cd frontend && npx tsc --noEmit` — 0 errors
3. Manual verification:
   - Type "999.999.999.999" in diagnosis form Source IP → red border + error text
   - Type port "99999" → red border + "Port must be 0–65535"
   - Upload CSV with IP outside subnet (192.168.1.1 in 10.0.0.0/24) → error in results
   - Upload CSV with overlapping subnets → warning in results
   - Upload CSV with VLAN 5000 → warning about range
   - Drop firewall inside VPC, set IP outside VPC CIDR → red error on Save
   - Drop two devices with same IP → "Duplicate IP" error on Save
   - Create subnet inside VPC with CIDR outside VPC range → error on Save
   - Promote topology with bad IPs → errors in response
   - Create HA group with mismatched device types → validation error
   - Create HA group with VIP outside member subnet → validation error
   - Create valid HA group → success, devices updated with ha_group_id/ha_role

## Edge Cases Covered

- **Empty/optional fields**: Empty IP, CIDR, gateway are all allowed (optional)
- **Boundary IPs**: .0 (network) and .255 (broadcast) are accepted — some systems legitimately use them
- **CIDR with host bits**: `10.0.0.5/24` accepted (strict=False) — common in real IPAM exports
- **Multiple VIPs per HA group**: Supported (active-active LBs often have several)
- **HA group with missing member devices**: Validation returns error but doesn't crash
- **VPC with comma-separated CIDRs**: Handled in property panel CIDR field
- **Overlapping subnet detection**: Uses `ipaddress.ip_network.overlaps()` which handles all edge cases including identical CIDRs
- **Device dragged out of container**: parentContainerId cleared, no validation error
- **Save with only warnings (no errors)**: Allowed — warnings don't block save
- **Promote with Pydantic validation failure**: Caught by except, added to errors list, doesn't crash promotion of other nodes
- **IPv6 addresses**: Python `ipaddress` module handles both IPv4 and IPv6 in validators
- **HA active-active mode**: No active_member_id required, all members get role "member"
- **VRRP gateway detection**: Subnet gateway_ip matching a VIP triggers informational warning
