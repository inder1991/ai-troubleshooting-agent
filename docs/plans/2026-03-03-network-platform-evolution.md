# Network Platform Evolution — Full Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the network module from a basic topology viewer + single-direction diagnosis tool into a full Network Security & Operations Platform with enriched data models, real adapter wiring, bi-directional diagnosis, security grading, canvas-to-KG promotion, and confidence transparency.

**Architecture:** 8 priority layers (P0–P7) building bottom-up. P0 fixes foundational data models so all downstream features have correct data. P1 wires real firewall adapters so diagnosis produces truthful results. P2–P3 add diagnosis intelligence (writeback + security grading). P4 bridges the canvas-KG divergence. P5–P7 add advanced diagnosis modes, LLM explanation, and reachability matrix.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, NetworkX, LangGraph, SQLite, React 18, TypeScript, ReactFlow, Tailwind CSS

---

## Task 1: Enrich Device Model with Zone/VLAN/Description Fields (P0)

**Files:**
- Modify: `backend/src/network/models.py:127-134`
- Modify: `backend/src/network/topology_store.py:39-41` (devices table schema)
- Modify: `backend/src/network/topology_store.py:192-200` (add_device INSERT)
- Modify: `backend/src/network/topology_store.py:202-209` (get_device SELECT)
- Test: `backend/tests/test_network_models.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_network_models.py`:
```python
def test_device_has_zone_vlan_description():
    from src.network.models import Device, DeviceType
    d = Device(
        id="d1", name="fw-01", device_type=DeviceType.FIREWALL,
        management_ip="10.0.0.1", zone_id="pci", vlan_id=100,
        description="PCI firewall",
    )
    assert d.zone_id == "pci"
    assert d.vlan_id == 100
    assert d.description == "PCI firewall"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_network_models.py::test_device_has_zone_vlan_description -v`
Expected: FAIL — `Device.__init__() got unexpected keyword argument 'zone_id'`

**Step 3: Add fields to Device model**

In `backend/src/network/models.py`, change lines 127-134 from:
```python
class Device(BaseModel):
    id: str
    name: str
    vendor: str = ""
    device_type: DeviceType = DeviceType.HOST
    management_ip: str = ""
    model: str = ""
    location: str = ""
```
to:
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
```

**Step 4: Update topology_store devices table**

In `backend/src/network/topology_store.py`, update the `_init_tables` devices schema (line 39-41) to add the new columns. Since SQLite doesn't support ADD COLUMN IF NOT EXISTS in CREATE TABLE, and we use `CREATE TABLE IF NOT EXISTS`, we need to add an ALTER TABLE migration after the CREATE block. Add after line 187 (before `conn.commit()`):

```python
            -- Migration: add new Device columns if missing
            ALTER TABLE devices ADD COLUMN zone_id TEXT DEFAULT '';
            ALTER TABLE devices ADD COLUMN vlan_id INTEGER DEFAULT 0;
            ALTER TABLE devices ADD COLUMN description TEXT DEFAULT '';
```

But since ALTER TABLE fails if column already exists in SQLite, wrap each in try/except. Instead, update `_init_tables` to run migration safely after the main executescript. Add a new method `_migrate_tables` called after `_init_tables` in `__init__`:

In `__init__` (line 25-28), after `self._init_tables()`, add `self._migrate_tables()`.

Add method `_migrate_tables` after `_init_tables`:
```python
    def _migrate_tables(self):
        """Add columns that may be missing from older schemas."""
        conn = self._conn()
        migrations = [
            "ALTER TABLE devices ADD COLUMN zone_id TEXT DEFAULT ''",
            "ALTER TABLE devices ADD COLUMN vlan_id INTEGER DEFAULT 0",
            "ALTER TABLE devices ADD COLUMN description TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
            except Exception:
                pass  # Column already exists
        conn.commit()
        conn.close()
```

**Step 5: Update add_device INSERT**

In `topology_store.py`, update `add_device` (lines 192-200):
```python
    def add_device(self, device: Device) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO devices VALUES (?,?,?,?,?,?,?,?,?,?)",
            (device.id, device.name, device.vendor, device.device_type.value,
             device.management_ip, device.model, device.location,
             device.zone_id, device.vlan_id, device.description),
        )
        conn.commit()
        conn.close()
```

**Step 6: Update get_device SELECT**

In `topology_store.py`, update `get_device` (lines 202-209):
```python
    def get_device(self, device_id: str) -> Optional[Device]:
        conn = self._conn()
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return Device(
            id=row[0], name=row[1], vendor=row[2],
            device_type=DeviceType(row[3]) if row[3] else DeviceType.HOST,
            management_ip=row[4] or "", model=row[5] or "", location=row[6] or "",
            zone_id=row[7] or "" if len(row) > 7 else "",
            vlan_id=row[8] or 0 if len(row) > 8 else 0,
            description=row[9] or "" if len(row) > 9 else "",
        )
```

Also update `list_devices` similarly to construct Device with all fields.

**Step 7: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_network_models.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add backend/src/network/models.py backend/src/network/topology_store.py backend/tests/test_network_models.py
git commit -m "feat(network): add zone_id, vlan_id, description to Device model + DB schema"
```

---

## Task 2: Enrich IPAM CSV Ingestion to Populate All Device Fields (P0)

**Files:**
- Modify: `backend/src/network/ipam_ingestion.py:84-92`
- Test: `backend/tests/test_ipam_ingestion.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_ipam_ingestion.py`:
```python
def test_csv_populates_device_metadata(store):
    csv_content = """ip,subnet,device,zone,vlan,description,vendor,location,device_type
10.0.0.1,10.0.0.0/24,fw-core-01,pci,100,PCI firewall,Palo Alto,NYC-DC1,FIREWALL"""
    stats = parse_ipam_csv(csv_content, store)
    assert stats["devices_added"] == 1
    devices = store.list_devices()
    d = devices[0]
    assert d.management_ip == "10.0.0.1"
    assert d.zone_id == "pci"
    assert d.vlan_id == 100
    assert d.description == "PCI firewall"
    assert d.vendor == "Palo Alto"
    assert d.location == "NYC-DC1"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_ipam_ingestion.py::test_csv_populates_device_metadata -v`
Expected: FAIL — `d.management_ip == ""` (IP not set on Device) or `d.zone_id` not found

**Step 3: Update parse_ipam_csv to populate Device fields**

In `backend/src/network/ipam_ingestion.py`, update the device creation block (lines 84-92):

```python
            # Create/update device
            if device_name and device_name not in seen_devices:
                device_id = f"device-{device_name.lower().replace(' ', '-')}"
                vendor = row.get("vendor", "").strip()
                location = row.get("location", "").strip() or row.get("site", "").strip()
                store.add_device(Device(
                    id=device_id, name=device_name,
                    device_type=_infer_device_type(device_name, row),
                    management_ip=ip,
                    vendor=vendor,
                    location=location,
                    zone_id=zone,
                    vlan_id=int(vlan or 0),
                    description=description,
                ))
                seen_devices.add(device_name)
                stats["devices_added"] += 1
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_ipam_ingestion.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/network/ipam_ingestion.py backend/tests/test_ipam_ingestion.py
git commit -m "feat(network): populate all Device fields from IPAM CSV upload"
```

---

## Task 3: Wire Real Adapter Factory (P1)

**Files:**
- Create: `backend/src/network/adapters/factory.py`
- Modify: `backend/src/api/network_endpoints.py:269-320`
- Test: `backend/tests/test_adapter_factory.py`

**Step 1: Write the failing test**

Create `backend/tests/test_adapter_factory.py`:
```python
"""Tests for adapter factory."""
import pytest
from src.network.adapters.factory import create_adapter
from src.network.adapters.mock_adapter import MockFirewallAdapter
from src.network.models import FirewallVendor


def test_factory_creates_mock_for_unknown():
    adapter = create_adapter(FirewallVendor.PALO_ALTO, api_endpoint="", api_key="")
    # Without pan-os-python installed, falls back to mock
    assert adapter is not None


def test_factory_returns_mock_when_sdk_missing():
    adapter = create_adapter(
        FirewallVendor.PALO_ALTO,
        api_endpoint="https://panorama.example.com",
        api_key="fake-key",
    )
    assert adapter is not None


def test_factory_aws_without_boto3():
    adapter = create_adapter(
        FirewallVendor.AWS_SG,
        api_endpoint="",
        api_key="",
        extra_config={"region": "us-east-1", "security_group_id": "sg-123"},
    )
    assert adapter is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_adapter_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.network.adapters.factory'`

**Step 3: Create adapter factory**

Create `backend/src/network/adapters/factory.py`:
```python
"""Adapter factory — creates the right adapter based on vendor and SDK availability."""
from __future__ import annotations

import logging
from typing import Optional

from ..models import FirewallVendor
from .base import FirewallAdapter
from .mock_adapter import MockFirewallAdapter

logger = logging.getLogger(__name__)


def create_adapter(
    vendor: FirewallVendor,
    api_endpoint: str = "",
    api_key: str = "",
    extra_config: Optional[dict] = None,
) -> FirewallAdapter:
    """Create the appropriate adapter for the given vendor.

    Falls back to MockFirewallAdapter if the vendor SDK is not installed.
    """
    extra = extra_config or {}

    if vendor == FirewallVendor.PALO_ALTO:
        try:
            from .panorama_adapter import PanoramaAdapter, HAS_PANOS
            if HAS_PANOS and api_endpoint:
                device_group = extra.get("device_group", "")
                return PanoramaAdapter(
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                    device_group=device_group,
                )
        except Exception as e:
            logger.warning("Failed to create PanoramaAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.AWS_SG:
        try:
            from .aws_sg_adapter import AWSSGAdapter, BOTO3_AVAILABLE
            if BOTO3_AVAILABLE and extra.get("security_group_id"):
                return AWSSGAdapter(
                    region=extra.get("region", "us-east-1"),
                    security_group_id=extra["security_group_id"],
                    aws_access_key=extra.get("aws_access_key"),
                    aws_secret_key=extra.get("aws_secret_key"),
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create AWSSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.AZURE_NSG:
        try:
            from .azure_nsg_adapter import AzureNSGAdapter, AZURE_AVAILABLE
            if AZURE_AVAILABLE and extra.get("nsg_name"):
                return AzureNSGAdapter(
                    subscription_id=extra.get("subscription_id", ""),
                    resource_group=extra.get("resource_group", ""),
                    nsg_name=extra["nsg_name"],
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create AzureNSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.ORACLE_NSG:
        try:
            from .oracle_nsg_adapter import OracleNSGAdapter
            if extra.get("nsg_id"):
                return OracleNSGAdapter(
                    compartment_id=extra.get("compartment_id", ""),
                    nsg_id=extra["nsg_id"],
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                )
        except Exception as e:
            logger.warning("Failed to create OracleNSGAdapter: %s, falling back to mock", e)

    elif vendor == FirewallVendor.ZSCALER:
        try:
            from .zscaler_adapter import ZscalerAdapter
            if api_endpoint:
                return ZscalerAdapter(
                    api_endpoint=api_endpoint,
                    api_key=api_key,
                    extra_config=extra,
                )
        except Exception as e:
            logger.warning("Failed to create ZscalerAdapter: %s, falling back to mock", e)

    # Fallback: mock adapter
    logger.info("Using MockFirewallAdapter for vendor=%s (SDK not available or not configured)", vendor.value)
    return MockFirewallAdapter(
        vendor=vendor,
        api_endpoint=api_endpoint,
        api_key=api_key,
        extra_config=extra,
    )
```

**Step 4: Update network_endpoints.py to use factory**

In `backend/src/api/network_endpoints.py`, replace lines 269-320 (both `adapter_test` and `adapter_configure` endpoints):

For `adapter_test` (lines 269-290), replace:
```python
    from src.network.adapters.mock_adapter import MockFirewallAdapter
    ...
    adapter = MockFirewallAdapter(...)
```
with:
```python
    from src.network.adapters.factory import create_adapter
    ...
    adapter = create_adapter(
        fw_vendor,
        api_endpoint=req.api_endpoint,
        api_key=req.api_key,
        extra_config=req.extra_config,
    )
```

For `adapter_configure` (lines 293-320), same replacement — use `create_adapter` instead of `MockFirewallAdapter`.

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_adapter_factory.py tests/test_adapter_endpoints.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/network/adapters/factory.py backend/src/api/network_endpoints.py backend/tests/test_adapter_factory.py
git commit -m "feat(network): wire real adapter factory with SDK-aware fallback"
```

---

## Task 4: Diagnosis Writeback — Connect Dead Code (P2)

**Files:**
- Modify: `backend/src/agents/network/graph.py:95-175`
- Modify: `backend/src/api/network_endpoints.py:66-92`
- Test: `backend/tests/test_diagnosis_writeback.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_diagnosis_writeback.py`:
```python
"""Tests for diagnosis writeback integration."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, Subnet, Interface, DeviceType


@pytest.fixture
def kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    kg = NetworkKnowledgeGraph(store)
    return kg


def test_writeback_adds_discovered_device(kg):
    hops = [
        {"ip": "10.0.0.1", "device_name": "discovered-router", "rtt_ms": 5, "status": "responded"},
        {"ip": "10.0.0.2", "device_name": "discovered-switch", "rtt_ms": 8, "status": "responded"},
    ]
    added = kg.writeback_discovered_hops(hops)
    assert added == 2
    assert kg.node_count == 2
    assert kg.edge_count == 1  # edge between hop 1 and hop 2
```

**Step 2: Run test to verify it passes (writeback_discovered_hops already exists)**

Run: `cd backend && python -m pytest tests/test_diagnosis_writeback.py -v`
Expected: PASS (the function exists, just isn't called from the pipeline)

**Step 3: Wire writeback into the pipeline**

The key integration point is in `_run_network_diagnosis` in `network_endpoints.py`. After the pipeline completes, call writeback with the trace hops and boost confidence on verified edges.

In `backend/src/api/network_endpoints.py`, update `_run_network_diagnosis` (lines 66-92):

After line 73 (`_network_sessions[session_id]["state"] = result`), add:
```python
        # Writeback discovered hops to KG
        kg = _get_knowledge_graph()
        trace_hops = result.get("trace_hops", []) if isinstance(result, dict) else []
        if trace_hops:
            kg.writeback_discovered_hops(trace_hops)
        # Boost confidence on verified edges
        final_path = result.get("final_path", {}) if isinstance(result, dict) else {}
        hops = final_path.get("hops", [])
        for i in range(len(hops) - 1):
            kg.boost_edge_confidence(hops[i], hops[i + 1])
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_diagnosis_writeback.py tests/test_network_endpoints.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/api/network_endpoints.py backend/tests/test_diagnosis_writeback.py
git commit -m "feat(network): wire diagnosis writeback to enrich KG after each run"
```

---

## Task 5: Security Grading on Firewall Verdicts (P3)

**Files:**
- Modify: `backend/src/network/models.py:392-398` (PolicyVerdict)
- Modify: `backend/src/agents/network/firewall_evaluator.py:49-57`
- Modify: `backend/src/agents/network/report_generator.py`
- Modify: `frontend/src/components/NetworkTroubleshooting/FirewallVerdictCard.tsx`
- Modify: `frontend/src/types/index.ts` (FirewallVerdict type)
- Test: `backend/tests/test_security_grading.py`

**Step 1: Write the failing test**

Create `backend/tests/test_security_grading.py`:
```python
"""Tests for security grading heuristic."""
from src.agents.network.report_generator import _compute_security_grade


def test_any_any_is_critical():
    verdict = {
        "action": "allow",
        "matched_source": "0.0.0.0/0",
        "matched_destination": "0.0.0.0/0",
        "matched_ports": "any",
    }
    assert _compute_security_grade(verdict) == "CRITICAL"


def test_internet_to_specific_is_high():
    verdict = {
        "action": "allow",
        "matched_source": "0.0.0.0/0",
        "matched_destination": "10.0.1.0/24",
        "matched_ports": "443",
    }
    assert _compute_security_grade(verdict) == "HIGH"


def test_tight_rule_is_low():
    verdict = {
        "action": "allow",
        "matched_source": "10.0.1.0/24",
        "matched_destination": "10.0.2.50/32",
        "matched_ports": "443",
    }
    assert _compute_security_grade(verdict) == "LOW"


def test_deny_has_no_grade():
    verdict = {"action": "deny"}
    assert _compute_security_grade(verdict) is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_security_grading.py -v`
Expected: FAIL — `cannot import name '_compute_security_grade'`

**Step 3: Add matched_source/matched_destination to PolicyVerdict**

In `backend/src/network/models.py`, update PolicyVerdict (lines 392-398):
```python
class PolicyVerdict(BaseModel):
    action: PolicyAction
    rule_id: str = ""
    rule_name: str = ""
    match_type: VerdictMatchType = VerdictMatchType.EXACT
    confidence: float = 0.0
    details: str = ""
    matched_source: str = ""
    matched_destination: str = ""
    matched_ports: str = ""
```

**Step 4: Pass matched rule details from firewall_evaluator**

In `backend/src/agents/network/firewall_evaluator.py`, update the verdict dict (around line 49-57) to include matched rule scope. Add after `"details"`:
```python
                    "matched_source": ",".join(verdict_obj.matched_source) if hasattr(verdict_obj, 'matched_source') else "",
                    "matched_destination": ",".join(verdict_obj.matched_destination) if hasattr(verdict_obj, 'matched_destination') else "",
                    "matched_ports": verdict_obj.matched_ports if hasattr(verdict_obj, 'matched_ports') else "",
```

Wait — the `verdict` returned by `adapter.simulate_flow()` is a `PolicyVerdict`. We need to also pass the matched rule's actual scope. Update the mock adapter's `simulate_flow` to populate these fields, and update the firewall_evaluator to forward them:

In `mock_adapter.py` `simulate_flow`, when a rule matches (line 38-45):
```python
                return PolicyVerdict(
                    action=rule.action,
                    rule_id=rule.id,
                    rule_name=rule.rule_name,
                    match_type=VerdictMatchType.EXACT,
                    confidence=0.95,
                    details=f"Matched rule {rule.rule_name} (order {rule.order})",
                    matched_source=",".join(rule.src_ips) if rule.src_ips else "",
                    matched_destination=",".join(rule.dst_ips) if rule.dst_ips else "",
                    matched_ports=",".join(rule.ports) if rule.ports else "",
                )
```

In `firewall_evaluator.py`, update the verdict dict construction to include:
```python
                    "matched_source": verdict.matched_source,
                    "matched_destination": verdict.matched_destination,
                    "matched_ports": verdict.matched_ports,
```

**Step 5: Add security grading function to report_generator**

In `backend/src/agents/network/report_generator.py`, add before `report_generator`:
```python
import ipaddress


def _compute_security_grade(verdict: dict) -> str | None:
    """Compute a security risk grade for an ALLOW verdict.

    Returns None for deny/drop verdicts (no security concern on blocking).
    """
    action = verdict.get("action", "").lower()
    if action in ("deny", "drop"):
        return None

    src = verdict.get("matched_source", "")
    dst = verdict.get("matched_destination", "")
    ports = verdict.get("matched_ports", "")

    src_is_any = src in ("0.0.0.0/0", "any", "*", "")
    dst_is_any = dst in ("0.0.0.0/0", "any", "*", "")
    port_is_any = ports in ("any", "*", "", "0-65535")

    # Broad source CIDR detection
    src_is_broad = src_is_any
    if not src_is_any and src:
        try:
            for cidr in src.split(","):
                net = ipaddress.ip_network(cidr.strip(), strict=False)
                if net.prefixlen <= 16:
                    src_is_broad = True
                    break
        except ValueError:
            pass

    if src_is_any and port_is_any:
        return "CRITICAL"
    if src_is_any and not port_is_any:
        return "HIGH"
    if src_is_broad and port_is_any:
        return "MEDIUM"
    return "LOW"
```

Update `report_generator` function to add security grades to the executive summary:

After the existing firewall verdicts processing, add:
```python
    # Security grading
    security_warnings = []
    for v in firewall_verdicts:
        grade = _compute_security_grade(v)
        if grade and grade in ("CRITICAL", "HIGH"):
            security_warnings.append(
                f"SEC-WARN ({grade}): {v.get('device_name', 'unknown')} allows traffic via "
                f"overly permissive rule '{v.get('rule_name', 'unknown')}'"
            )
    if security_warnings:
        summary += " " + " | ".join(security_warnings)
        next_steps.extend([
            "Review overly permissive firewall rules flagged with SEC-WARN",
            "Consider tightening source/destination CIDR scope",
        ])
```

**Step 6: Update frontend FirewallVerdictCard**

In `frontend/src/components/NetworkTroubleshooting/FirewallVerdictCard.tsx`, add security grade badge. Update the interface (lines 3-12):
```typescript
interface FirewallVerdict {
  device_id: string;
  device_name: string;
  action: string;
  rule_id?: string;
  rule_name?: string;
  confidence: number;
  match_type: string;
  details?: string;
  matched_source?: string;
  matched_destination?: string;
  matched_ports?: string;
  security_grade?: string;
}
```

Add security grade badge rendering after the action badge (after line 51):
```tsx
        {/* Security Grade */}
        {verdict.action?.toUpperCase() === 'ALLOW' && verdict.matched_source && (
          (() => {
            const srcAny = ['0.0.0.0/0', 'any', '*', ''].includes(verdict.matched_source || '');
            const portAny = ['any', '*', '', '0-65535'].includes(verdict.matched_ports || '');
            const grade = srcAny && portAny ? 'CRITICAL' : srcAny ? 'HIGH' : 'LOW';
            if (grade === 'LOW') return null;
            const gradeColors = { CRITICAL: '#ef4444', HIGH: '#f59e0b' };
            return (
              <span
                className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider animate-pulse"
                style={{
                  color: gradeColors[grade as keyof typeof gradeColors],
                  backgroundColor: `${gradeColors[grade as keyof typeof gradeColors]}20`,
                }}
              >
                SEC-WARN
              </span>
            );
          })()
        )}
```

**Step 7: Update types/index.ts**

In `frontend/src/types/index.ts`, update the firewall_verdicts array type in NetworkFindings to include the new fields.

**Step 8: Run backend tests**

Run: `cd backend && python -m pytest tests/test_security_grading.py -v`
Expected: ALL PASS

**Step 9: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 10: Commit**

```bash
git add backend/src/network/models.py backend/src/agents/network/firewall_evaluator.py \
  backend/src/agents/network/report_generator.py backend/src/network/adapters/mock_adapter.py \
  backend/tests/test_security_grading.py \
  frontend/src/components/NetworkTroubleshooting/FirewallVerdictCard.tsx \
  frontend/src/types/index.ts
git commit -m "feat(network): add security grading on firewall verdicts with SEC-WARN badges"
```

---

## Task 6: Canvas-to-KG Promotion (P4)

**Files:**
- Modify: `backend/src/api/network_endpoints.py` (add POST /topology/promote)
- Modify: `backend/src/api/network_models.py` (add PromoteRequest)
- Modify: `backend/src/network/knowledge_graph.py` (add promote_from_canvas method)
- Modify: `frontend/src/components/TopologyEditor/TopologyToolbar.tsx` (add Promote button)
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx` (add promote handler)
- Modify: `frontend/src/services/api.ts` (add promoteTopology function)
- Test: `backend/tests/test_topology_promote.py`

**Step 1: Write the failing test**

Create `backend/tests/test_topology_promote.py`:
```python
"""Tests for canvas-to-KG promotion."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph


@pytest.fixture
def kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    return NetworkKnowledgeGraph(store)


def test_promote_adds_devices_to_kg(kg):
    canvas_nodes = [
        {
            "id": "device-fw-01",
            "type": "device",
            "data": {
                "label": "fw-01",
                "deviceType": "firewall",
                "ip": "10.0.0.1",
                "vendor": "Palo Alto",
                "zone": "dmz",
                "vlan": 100,
            },
        },
    ]
    canvas_edges = [
        {"source": "device-fw-01", "target": "device-rtr-01"},
    ]
    result = kg.promote_from_canvas(canvas_nodes, canvas_edges)
    assert result["devices_promoted"] >= 1
    assert kg.node_count >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_topology_promote.py -v`
Expected: FAIL — `AttributeError: 'NetworkKnowledgeGraph' has no attribute 'promote_from_canvas'`

**Step 3: Add promote_from_canvas to KnowledgeGraph**

In `backend/src/network/knowledge_graph.py`, add method before `export_react_flow_graph`:
```python
    def promote_from_canvas(self, nodes: list[dict], edges: list[dict]) -> dict:
        """Promote canvas nodes/edges into the authoritative KG.

        Validates against Pydantic models, upserts into SQLite + NetworkX.
        Returns summary: {devices_promoted, edges_promoted, errors}.
        """
        stats = {"devices_promoted": 0, "edges_promoted": 0, "errors": []}

        for node in nodes:
            try:
                node_type = node.get("type", "device")
                data = node.get("data", {})
                node_id = node.get("id", "")

                if node_type == "device":
                    dt_str = (data.get("deviceType") or "HOST").upper()
                    try:
                        dt = DeviceType[dt_str]
                    except KeyError:
                        dt = DeviceType.HOST

                    device = Device(
                        id=node_id,
                        name=data.get("label", node_id),
                        device_type=dt,
                        management_ip=data.get("ip", ""),
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

        for edge in edges:
            try:
                src = edge.get("source", "")
                tgt = edge.get("target", "")
                if src and tgt:
                    self.add_edge(
                        src, tgt,
                        EdgeMetadata(
                            confidence=0.8,
                            source=EdgeSource.MANUAL,
                            edge_type=edge.get("label", "connected_to"),
                        ),
                    )
                    stats["edges_promoted"] += 1
            except Exception as e:
                stats["errors"].append(f"Edge {src}->{tgt}: {str(e)}")

        return stats
```

**Step 4: Add API endpoint**

In `backend/src/api/network_models.py`, add:
```python
class TopologyPromoteRequest(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []
```

In `backend/src/api/network_endpoints.py`, add after the topology_current endpoint:
```python
@network_router.post("/topology/promote")
async def topology_promote(req: TopologyPromoteRequest):
    """Promote canvas nodes/edges to the authoritative Knowledge Graph."""
    kg = _get_knowledge_graph()
    result = kg.promote_from_canvas(req.nodes, req.edges)
    return {"status": "promoted", **result}
```

Import `TopologyPromoteRequest` at the top of network_endpoints.py.

**Step 5: Add frontend API function**

In `frontend/src/services/api.ts`, add:
```typescript
export const promoteTopology = async (nodes: unknown[], edges: unknown[]): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/topology/promote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges }),
  });
  if (!response.ok) throw new Error(`Failed to promote topology: ${response.statusText}`);
  return response.json();
};
```

**Step 6: Add Promote button to TopologyToolbar**

In `frontend/src/components/TopologyEditor/TopologyToolbar.tsx`, add `onPromote` prop and button:

Update props interface:
```typescript
interface TopologyToolbarProps {
  onSave: () => void;
  onLoad: () => void;
  onImportIPAM: () => void;
  onAdapterStatus: () => void;
  onRefreshFromKG: () => void;
  onPromote?: () => void;
  saving?: boolean;
  loading?: boolean;
  refreshing?: boolean;
  promoting?: boolean;
}
```

Add Promote button after the Adapter Status button:
```tsx
{onPromote && (
  <button onClick={onPromote} disabled={promoting}
    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-colors"
    style={{ backgroundColor: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)' }}
  >
    <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
      {promoting ? 'sync' : 'published_with_changes'}
    </span>
    {promoting ? 'Promoting...' : 'Promote to Infrastructure'}
  </button>
)}
```

**Step 7: Wire promote handler in TopologyEditorView**

In `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`, add:
```typescript
const [promoting, setPromoting] = useState(false);

const handlePromote = useCallback(async () => {
  if (!reactFlowInstance) return;
  setPromoting(true);
  try {
    const flow = reactFlowInstance.toObject();
    await promoteTopology(flow.nodes, flow.edges);
    // Success feedback could be a toast
  } catch (err) {
    console.error('Promote failed:', err);
  } finally {
    setPromoting(false);
  }
}, [reactFlowInstance]);
```

Pass `onPromote={handlePromote}` and `promoting={promoting}` to `<TopologyToolbar />`.

**Step 8: Run tests**

Run: `cd backend && python -m pytest tests/test_topology_promote.py -v`
Expected: PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 9: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/src/api/network_endpoints.py \
  backend/src/api/network_models.py backend/tests/test_topology_promote.py \
  frontend/src/components/TopologyEditor/TopologyToolbar.tsx \
  frontend/src/components/TopologyEditor/TopologyEditorView.tsx \
  frontend/src/services/api.ts
git commit -m "feat(network): add Promote to Infrastructure — canvas-to-KG pipeline"
```

---

## Task 7: Bi-Directional Diagnosis (P5)

**Files:**
- Modify: `backend/src/api/network_endpoints.py` (run forward + return diagnosis)
- Modify: `backend/src/api/network_models.py` (add bidirectional flag)
- Modify: `backend/src/agents/network/state.py` (add direction field)
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx` (split path view)
- Modify: `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx` (forward/return tabs)
- Modify: `frontend/src/types/index.ts` (add return_path to NetworkFindings)
- Test: `backend/tests/test_bidirectional.py`

**Step 1: Write the failing test**

Create `backend/tests/test_bidirectional.py`:
```python
"""Tests for bi-directional diagnosis."""
import pytest
from src.api.network_models import DiagnoseRequest


def test_diagnose_request_has_bidirectional_flag():
    req = DiagnoseRequest(
        src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443,
        bidirectional=True,
    )
    assert req.bidirectional is True


def test_diagnose_request_defaults_unidirectional():
    req = DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443)
    assert req.bidirectional is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_bidirectional.py -v`
Expected: FAIL — `DiagnoseRequest.__init__() got unexpected keyword argument 'bidirectional'`

**Step 3: Add bidirectional flag to DiagnoseRequest**

In `backend/src/api/network_models.py`, update DiagnoseRequest:
```python
class DiagnoseRequest(BaseModel):
    src_ip: str
    dst_ip: str
    port: int = 80
    protocol: str = "tcp"
    session_id: Optional[str] = None
    bidirectional: bool = False
```

**Step 4: Update _run_network_diagnosis for bidirectional mode**

In `backend/src/api/network_endpoints.py`, update `_run_network_diagnosis` to accept a `bidirectional` param. When True, run two pipeline invocations (forward + return) and store both results:

```python
async def _run_network_diagnosis(
    session_id: str, flow_id: str, graph, initial_state: dict,
    bidirectional: bool = False, return_graph=None, return_state: dict | None = None,
):
    store = _get_topology_store()
    try:
        _network_sessions[session_id]["phase"] = "running"
        # Forward path
        result = await graph.ainvoke(initial_state)
        _network_sessions[session_id]["state"] = result

        # Return path (bidirectional)
        if bidirectional and return_graph and return_state:
            _network_sessions[session_id]["phase"] = "running_return"
            return_result = await return_graph.ainvoke(return_state)
            _network_sessions[session_id]["return_state"] = return_result

        _network_sessions[session_id]["phase"] = "complete"
        confidence = result.get("confidence", 0.0) if isinstance(result, dict) else 0.0
        store.update_flow_status(flow_id, "complete", confidence)

        # Writeback
        kg = _get_knowledge_graph()
        trace_hops = result.get("trace_hops", []) if isinstance(result, dict) else []
        if trace_hops:
            kg.writeback_discovered_hops(trace_hops)
        final_path = result.get("final_path", {}) if isinstance(result, dict) else {}
        hops = final_path.get("hops", [])
        for i in range(len(hops) - 1):
            kg.boost_edge_confidence(hops[i], hops[i + 1])
    except Exception as e:
        logger.error("Network diagnosis failed", extra={"session_id": session_id, "error": str(e)})
        _network_sessions[session_id]["error"] = str(e)
        _network_sessions[session_id]["phase"] = "error"
        store.update_flow_status(flow_id, "error", 0.0)
    finally:
        if len(_network_sessions) > _MAX_SESSIONS:
            to_remove = []
            for sid, sess in _network_sessions.items():
                if sess.get("phase") in ("complete", "error") and sid != session_id:
                    to_remove.append(sid)
            for sid in to_remove[:len(_network_sessions) - _MAX_SESSIONS]:
                _network_sessions.pop(sid, None)
```

In the `diagnose` endpoint, when `req.bidirectional` is True, build a second graph with swapped src/dst:
```python
    if req.bidirectional:
        return_state = {
            "flow_id": flow_id,
            "src_ip": req.dst_ip,  # swapped
            "dst_ip": req.src_ip,  # swapped
            "port": req.port,
            "protocol": req.protocol,
            "session_id": session_id,
        }
        return_graph = build_network_diagnostic_graph(kg, adapters)
        background_tasks.add_task(
            _run_network_diagnosis, session_id, flow_id, compiled_graph, initial_state,
            bidirectional=True, return_graph=return_graph, return_state=return_state,
        )
    else:
        background_tasks.add_task(_run_network_diagnosis, session_id, flow_id, compiled_graph, initial_state)
```

**Step 5: Update get_findings to include return_state**

In the `get_findings` endpoint, include return_state if present:
```python
    return {
        "session_id": session_id,
        "flow_id": session.get("flow_id"),
        "phase": session.get("phase"),
        "error": session.get("error"),
        "state": session.get("state", {}),
        "return_state": session.get("return_state"),
    }
```

**Step 6: Update frontend types**

In `frontend/src/types/index.ts`, add `return_state` to `NetworkFindings`:
```typescript
export interface NetworkFindings {
  session_id: string;
  flow_id: string;
  phase: string;
  error?: string;
  state: { /* existing fields */ };
  return_state?: { /* same shape as state */ };
}
```

**Step 7: Update DiagnosisPanel with Forward/Return tabs**

In `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx`, add a tab toggle when `return_state` exists:

Add state: `const [direction, setDirection] = useState<'forward' | 'return'>('forward');`
Add tab buttons before the content:
```tsx
{findings.return_state && (
  <div className="flex gap-1 mb-3 rounded-lg p-0.5" style={{ backgroundColor: '#0a1a1e' }}>
    <button onClick={() => setDirection('forward')}
      className="flex-1 px-3 py-1 rounded-md text-xs font-mono font-medium"
      style={direction === 'forward' ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' } : { color: '#64748b' }}
    >Forward (A→B)</button>
    <button onClick={() => setDirection('return')}
      className="flex-1 px-3 py-1 rounded-md text-xs font-mono font-medium"
      style={direction === 'return' ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' } : { color: '#64748b' }}
    >Return (B→A)</button>
  </div>
)}
```

Use `const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;` for all data rendering.

**Step 8: Run tests**

Run: `cd backend && python -m pytest tests/test_bidirectional.py -v`
Expected: PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 9: Commit**

```bash
git add backend/src/api/network_endpoints.py backend/src/api/network_models.py \
  backend/src/agents/network/state.py backend/tests/test_bidirectional.py \
  frontend/src/types/index.ts \
  frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx \
  frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx
git commit -m "feat(network): add bi-directional diagnosis with forward/return path view"
```

---

## Task 8: Confidence Decomposition (P3 supplement)

**Files:**
- Modify: `backend/src/agents/network/path_synthesizer.py`
- Modify: `backend/src/agents/network/state.py`
- Modify: `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx`
- Modify: `frontend/src/types/index.ts`

**Step 1: Add confidence_breakdown to pipeline state**

In `backend/src/agents/network/state.py`, add to `NetworkPipelineState`:
```python
    confidence_breakdown: Optional[dict]  # { path, firewall, contradiction_bonus, penalties }
```

**Step 2: Update path_synthesizer to emit breakdown**

In `backend/src/agents/network/path_synthesizer.py`, after computing overall confidence (around line 74), add:
```python
    penalties = []
    if routing_loop:
        penalties.append({"type": "routing_loop", "impact": -0.7})
    if any_deny:
        penalties.append({"type": "firewall_deny_cap", "impact": -(overall - 0.5) if overall > 0.5 else 0})

    confidence_breakdown = {
        "path_confidence": round(path_confidence / 3.0 * 0.6, 3),
        "path_source": path_source,
        "firewall_confidence": round(fw_confidence * 0.3, 3),
        "contradiction_bonus": 0.1 if not contradictions else 0.0,
        "penalties": penalties,
        "overall": round(overall, 3),
    }
```

Add `"confidence_breakdown": confidence_breakdown` to the return dict.

**Step 3: Update frontend DiagnosisPanel**

Replace the simple confidence bar with a stacked breakdown showing:
- Path: X% (source: traced/graph)
- Firewall: X%
- Contradiction bonus: +X%
- Penalties: -X%

```tsx
{state.confidence_breakdown && (
  <div className="space-y-1.5">
    {Object.entries(state.confidence_breakdown)
      .filter(([k]) => !['overall', 'penalties', 'path_source'].includes(k))
      .map(([key, val]) => (
        <div key={key} className="flex justify-between text-[11px] font-mono">
          <span style={{ color: '#64748b' }}>{key.replace(/_/g, ' ')}</span>
          <span style={{ color: '#94a3b8' }}>{(Number(val) * 100).toFixed(0)}%</span>
        </div>
      ))}
  </div>
)}
```

**Step 4: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add backend/src/agents/network/path_synthesizer.py backend/src/agents/network/state.py \
  frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx frontend/src/types/index.ts
git commit -m "feat(network): add confidence decomposition breakdown to diagnosis"
```

---

## Task 9: Empty KG / No Adapters Warning Banners (P3 supplement)

**Files:**
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx`
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx`

**Step 1: Add "No topology data" warning**

In `NetworkWarRoom.tsx`, after the findings check, add a warning banner when `diagnosis_status === 'no_path_known'`:

```tsx
{findings && findings.state?.diagnosis_status === 'no_path_known' && (
  <div className="mx-4 mt-2 rounded-lg p-3 flex items-center gap-3 font-mono text-xs"
    style={{ backgroundColor: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)' }}>
    <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}>warning</span>
    <div>
      <p className="font-semibold" style={{ color: '#f59e0b' }}>No Topology Data</p>
      <p style={{ color: '#94a3b8' }}>
        Import IPAM data or build a topology canvas to enable path analysis.
        Without topology data, the diagnosis engine cannot find network paths.
      </p>
    </div>
  </div>
)}
```

**Step 2: Add "No adapters configured" warning**

In `NetworkEvidenceStack.tsx`, in the Adapter Health section, add a warning when all adapters have status `not_configured` or when the adapters array is empty:

```tsx
{(!adapters || adapters.length === 0) && (
  <div className="rounded-lg p-3 font-mono text-xs"
    style={{ backgroundColor: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
    <p className="font-semibold mb-1" style={{ color: '#f59e0b' }}>No Firewall Adapters</p>
    <p style={{ color: '#94a3b8' }}>
      Firewall rules cannot be verified. Configure adapters in the Topology Editor
      to get accurate firewall verdicts.
    </p>
  </div>
)}
```

**Step 3: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx \
  frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx
git commit -m "feat(network): add warning banners for missing topology data and adapters"
```

---

## Task 10: Reachability Matrix Mode (P7)

**Files:**
- Create: `backend/src/agents/network/reachability_matrix.py`
- Modify: `backend/src/api/network_endpoints.py` (add POST /matrix)
- Modify: `backend/src/api/network_models.py` (add MatrixRequest)
- Create: `frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx`
- Modify: `frontend/src/App.tsx` (add matrix view)
- Modify: `frontend/src/components/Layout/SidebarNav.tsx` (add Matrix nav item)
- Modify: `frontend/src/services/api.ts` (add runMatrix function)
- Test: `backend/tests/test_reachability_matrix.py`

**Step 1: Write the failing test**

Create `backend/tests/test_reachability_matrix.py`:
```python
"""Tests for reachability matrix."""
import os
import pytest
from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, Subnet, Interface, DeviceType, Zone
from src.agents.network.reachability_matrix import compute_reachability_matrix


@pytest.fixture
def populated_kg(tmp_path):
    db_path = os.path.join(str(tmp_path), "test.db")
    store = TopologyStore(db_path=db_path)
    kg = NetworkKnowledgeGraph(store)
    # Add zones
    store.add_zone(Zone(id="zone-pci", name="PCI", security_level=5))
    store.add_zone(Zone(id="zone-dev", name="DEV", security_level=1))
    # Add devices
    store.add_device(Device(id="d1", name="pci-server", zone_id="zone-pci",
                           management_ip="10.0.1.1", device_type=DeviceType.HOST))
    store.add_device(Device(id="d2", name="dev-server", zone_id="zone-dev",
                           management_ip="10.0.2.1", device_type=DeviceType.HOST))
    kg.load_from_store()
    return kg


def test_matrix_returns_grid(populated_kg):
    result = compute_reachability_matrix(populated_kg, ["zone-pci", "zone-dev"])
    assert "matrix" in result
    assert len(result["matrix"]) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_reachability_matrix.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create reachability matrix module**

Create `backend/src/agents/network/reachability_matrix.py`:
```python
"""Reachability matrix — zone-to-zone connectivity analysis."""
from __future__ import annotations
from src.network.knowledge_graph import NetworkKnowledgeGraph


def compute_reachability_matrix(
    kg: NetworkKnowledgeGraph,
    zone_ids: list[str],
) -> dict:
    """Compute zone-to-zone reachability using graph pathfinding only.

    No traceroute — purely topological analysis.
    Returns: {matrix: [{src_zone, dst_zone, reachable, path_count, confidence}]}
    """
    # Find representative devices per zone
    zone_devices: dict[str, list[str]] = {}
    for node_id, data in kg.graph.nodes(data=True):
        z = data.get("zone_id", "")
        if z in zone_ids:
            zone_devices.setdefault(z, []).append(node_id)

    matrix = []
    for src_zone in zone_ids:
        for dst_zone in zone_ids:
            if src_zone == dst_zone:
                continue
            src_devs = zone_devices.get(src_zone, [])
            dst_devs = zone_devices.get(dst_zone, [])
            if not src_devs or not dst_devs:
                matrix.append({
                    "src_zone": src_zone,
                    "dst_zone": dst_zone,
                    "reachable": "unknown",
                    "path_count": 0,
                    "confidence": 0.0,
                })
                continue
            # Test with first representative device from each zone
            paths = kg.find_k_shortest_paths(src_devs[0], dst_devs[0], k=1)
            matrix.append({
                "src_zone": src_zone,
                "dst_zone": dst_zone,
                "reachable": "yes" if paths else "no",
                "path_count": len(paths),
                "confidence": 0.8 if paths else 0.0,
            })

    return {"matrix": matrix, "zone_count": len(zone_ids)}
```

**Step 4: Add API endpoint**

In `backend/src/api/network_models.py`, add:
```python
class MatrixRequest(BaseModel):
    zone_ids: list[str]
```

In `backend/src/api/network_endpoints.py`, add:
```python
@network_router.post("/matrix")
async def reachability_matrix(req: MatrixRequest):
    """Compute zone-to-zone reachability matrix."""
    from src.agents.network.reachability_matrix import compute_reachability_matrix
    kg = _get_knowledge_graph()
    result = compute_reachability_matrix(kg, req.zone_ids)
    return result
```

**Step 5: Add frontend API function**

In `frontend/src/services/api.ts`:
```typescript
export const runReachabilityMatrix = async (zoneIds: string[]): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/network/matrix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zone_ids: zoneIds }),
  });
  if (!response.ok) throw new Error(`Failed to run matrix: ${response.statusText}`);
  return response.json();
};
```

**Step 6: Create ReachabilityMatrix component**

Create `frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx`:

A grid component that:
- Fetches zones from the backend on mount
- Lets user select source/destination zones
- Runs the matrix computation
- Displays a color-coded grid (green = reachable, red = blocked, gray = unknown)

```tsx
import React, { useState, useEffect } from 'react';
import { runReachabilityMatrix } from '../../services/api';

interface MatrixCell {
  src_zone: string;
  dst_zone: string;
  reachable: string;
  path_count: number;
  confidence: number;
}

const ReachabilityMatrix: React.FC = () => {
  const [zones, setZones] = useState<string[]>([]);
  const [matrix, setMatrix] = useState<MatrixCell[]>([]);
  const [loading, setLoading] = useState(false);

  // Simple zone fetch placeholder - would come from API
  const handleRun = async () => {
    if (zones.length < 2) return;
    setLoading(true);
    try {
      const result = await runReachabilityMatrix(zones);
      setMatrix(result.matrix || []);
    } finally {
      setLoading(false);
    }
  };

  const cellColor = (reachable: string) => {
    if (reachable === 'yes') return '#22c55e';
    if (reachable === 'no') return '#ef4444';
    return '#64748b';
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6" style={{ backgroundColor: '#0f2023' }}>
      <h1 className="text-xl font-bold text-white mb-4">Reachability Matrix</h1>
      {/* Zone input */}
      <div className="flex gap-3 mb-4">
        <input
          type="text"
          placeholder="Enter zone IDs comma-separated..."
          onChange={(e) => setZones(e.target.value.split(',').map(z => z.trim()).filter(Boolean))}
          className="flex-1 px-3 py-2 rounded-lg border text-sm font-mono outline-none"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        />
        <button onClick={handleRun} disabled={loading || zones.length < 2}
          className="px-4 py-2 rounded-lg font-semibold text-sm"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023' }}>
          {loading ? 'Computing...' : 'Run Matrix'}
        </button>
      </div>
      {/* Matrix grid */}
      {matrix.length > 0 && (
        <div className="overflow-auto">
          <table className="border-collapse font-mono text-xs">
            <thead>
              <tr>
                <th className="p-2 text-left" style={{ color: '#64748b' }}>From \\ To</th>
                {zones.map(z => <th key={z} className="p-2" style={{ color: '#94a3b8' }}>{z}</th>)}
              </tr>
            </thead>
            <tbody>
              {zones.map(src => (
                <tr key={src}>
                  <td className="p-2 font-semibold" style={{ color: '#94a3b8' }}>{src}</td>
                  {zones.map(dst => {
                    if (src === dst) return <td key={dst} className="p-2 text-center" style={{ color: '#64748b' }}>—</td>;
                    const cell = matrix.find(m => m.src_zone === src && m.dst_zone === dst);
                    return (
                      <td key={dst} className="p-2 text-center">
                        <span className="px-2 py-1 rounded font-bold"
                          style={{ color: cellColor(cell?.reachable || 'unknown'),
                            backgroundColor: `${cellColor(cell?.reachable || 'unknown')}15` }}>
                          {cell?.reachable?.toUpperCase() || '?'}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ReachabilityMatrix;
```

**Step 7: Add to App.tsx routing and SidebarNav**

In `SidebarNav.tsx`, add `'matrix'` to NavView type and add it as a child of the Network group:
```typescript
export type NavView = 'home' | 'sessions' | 'integrations' | 'settings' | 'agents' | 'network-topology' | 'ipam' | 'matrix';
```

Add to Network group children:
```typescript
{ id: 'matrix', label: 'Matrix', icon: 'grid_view' },
```

In `App.tsx`, add `'matrix'` to ViewState and render ReachabilityMatrix.

**Step 8: Run tests**

Run: `cd backend && python -m pytest tests/test_reachability_matrix.py -v`
Expected: PASS

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 9: Commit**

```bash
git add backend/src/agents/network/reachability_matrix.py backend/src/api/network_endpoints.py \
  backend/src/api/network_models.py backend/tests/test_reachability_matrix.py \
  frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx \
  frontend/src/components/Layout/SidebarNav.tsx frontend/src/App.tsx frontend/src/services/api.ts
git commit -m "feat(network): add reachability matrix for zone-to-zone compliance analysis"
```

---

## Task 11: Device Type Case-Insensitive Fix (P0 supplement)

**Files:**
- Modify: `backend/src/network/ipam_ingestion.py:13-15`
- Test: `backend/tests/test_ipam_ingestion.py`

**Step 1: Write the failing test**

```python
def test_device_type_case_insensitive(store):
    csv_content = """ip,subnet,device,zone,vlan,description,device_type
10.0.0.1,10.0.0.0/24,fw-01,trust,100,test,Firewall"""
    stats = parse_ipam_csv(csv_content, store)
    devices = store.list_devices()
    assert devices[0].device_type == DeviceType.FIREWALL
```

**Step 2: Fix _infer_device_type**

In `backend/src/network/ipam_ingestion.py`, update lines 13-15:
```python
    explicit = row.get("device_type", "").strip().upper()
    if explicit:
        # Try exact match first, then common aliases
        if hasattr(DeviceType, explicit):
            return DeviceType[explicit]
        aliases = {"FW": "FIREWALL", "RTR": "ROUTER", "SW": "SWITCH", "LB": "LOAD_BALANCER"}
        if explicit in aliases and hasattr(DeviceType, aliases[explicit]):
            return DeviceType[aliases[explicit]]
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_ipam_ingestion.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add backend/src/network/ipam_ingestion.py backend/tests/test_ipam_ingestion.py
git commit -m "fix(network): make device_type column case-insensitive with alias support"
```

---

## Task 12: IPAM Upload Dialog — Show Results Before Closing (P3 supplement)

**Files:**
- Modify: `frontend/src/components/TopologyEditor/IPAMUploadDialog.tsx`

**Step 1: Update dialog to keep open after upload success**

Currently the dialog auto-closes on success. Change it to show results and let the user manually close:

- After successful upload, show a success card with:
  - Devices imported: X
  - Subnets imported: X
  - Warnings: [list]
  - A "Close & View" button that closes dialog and triggers onImported

**Step 2: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/TopologyEditor/IPAMUploadDialog.tsx
git commit -m "fix(network): keep IPAM upload dialog open to show results before closing"
```

---

## Verification Checklist

After all tasks are complete, verify:

1. `cd backend && python -m pytest tests/ -v --tb=short` — ALL PASS
2. `cd frontend && npx tsc --noEmit` — 0 errors
3. Manual verification:
   - Upload CSV with zone/vlan/description/vendor/location columns
   - Verify IPAM Inventory shows all fields populated
   - Canvas DeviceNode shows zone badge and device type
   - Configure Palo Alto adapter (if SDK installed) — real adapter created
   - Run diagnosis — writeback enriches KG
   - Firewall verdict shows SEC-WARN badge for overly permissive rules
   - "Promote to Infrastructure" button pushes canvas edits to KG
   - Bi-directional diagnosis shows Forward/Return tabs
   - Confidence breakdown shows component scores
   - Warning banners appear for empty KG / no adapters
   - Reachability matrix computes zone-to-zone grid
   - IPAM upload dialog stays open to show results

## Files Changed (Summary)

| File | Action |
|------|--------|
| `backend/src/network/models.py` | Modify — add Device fields, extend PolicyVerdict |
| `backend/src/network/topology_store.py` | Modify — DB migration, updated CRUD |
| `backend/src/network/ipam_ingestion.py` | Modify — populate all Device fields, case-insensitive types |
| `backend/src/network/knowledge_graph.py` | Modify — add promote_from_canvas |
| `backend/src/network/adapters/factory.py` | **Create** — adapter factory |
| `backend/src/network/adapters/mock_adapter.py` | Modify — pass matched rule scope |
| `backend/src/api/network_endpoints.py` | Modify — factory, writeback, bidirectional, matrix, promote |
| `backend/src/api/network_models.py` | Modify — add request models |
| `backend/src/agents/network/state.py` | Modify — add confidence_breakdown |
| `backend/src/agents/network/path_synthesizer.py` | Modify — emit confidence breakdown |
| `backend/src/agents/network/report_generator.py` | Modify — security grading |
| `backend/src/agents/network/firewall_evaluator.py` | Modify — pass matched rule details |
| `backend/src/agents/network/reachability_matrix.py` | **Create** — matrix computation |
| `frontend/src/types/index.ts` | Modify — add new fields |
| `frontend/src/services/api.ts` | Modify — add promote, matrix APIs |
| `frontend/src/components/TopologyEditor/TopologyToolbar.tsx` | Modify — promote button |
| `frontend/src/components/TopologyEditor/TopologyEditorView.tsx` | Modify — promote handler |
| `frontend/src/components/TopologyEditor/IPAMUploadDialog.tsx` | Modify — show results |
| `frontend/src/components/NetworkTroubleshooting/FirewallVerdictCard.tsx` | Modify — SEC-WARN badge |
| `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx` | Modify — breakdown, bidir tabs |
| `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx` | Modify — warning banners |
| `frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx` | Modify — adapter warning |
| `frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx` | **Create** — matrix UI |
| `frontend/src/components/Layout/SidebarNav.tsx` | Modify — add Matrix nav |
| `frontend/src/App.tsx` | Modify — add matrix routing |
| `backend/tests/test_adapter_factory.py` | **Create** |
| `backend/tests/test_security_grading.py` | **Create** |
| `backend/tests/test_topology_promote.py` | **Create** |
| `backend/tests/test_bidirectional.py` | **Create** |
| `backend/tests/test_reachability_matrix.py` | **Create** |
