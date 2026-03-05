# Diagnosis Pipeline Bug Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 bugs that silently break firewall detection, leak semaphore slots, serve stale cache, expose credentials, and hide reverse-path diagnostics.

**Architecture:** Surgical, independent fixes. Each bug gets an isolated change + regression test. No refactors.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, NetworkX, React 18, TypeScript

---

### Task 1: Fix Semaphore Leak in Traceroute Probe

**Files:**
- Modify: `backend/src/agents/network/traceroute_probe.py:20-50`
- Test: `backend/tests/test_traceroute_semaphore.py`

**Step 1: Write the failing test**

Create `backend/tests/test_traceroute_semaphore.py`:

```python
"""Regression test: semaphore must be released even when icmplib is unavailable."""
import unittest.mock as mock

import pytest


def test_semaphore_released_when_icmplib_missing():
    """Call traceroute_probe 4+ times with HAS_ICMPLIB=False.
    If semaphore leaks, the 4th call returns 'Rate limit'.
    If fixed, ALL calls return 'icmplib not available' (never rate-limited).
    """
    import src.agents.network.traceroute_probe as tp

    # Reset semaphore to a fresh state
    tp._semaphore = __import__("threading").Semaphore(tp._MAX_CONCURRENT)

    with mock.patch.object(tp, "HAS_ICMPLIB", False):
        results = []
        for _ in range(tp._MAX_CONCURRENT + 2):  # 5 calls with max=3
            r = tp.traceroute_probe({"dst_ip": "10.0.0.1"})
            results.append(r)

    # NONE of the results should say "Rate limit"
    for i, r in enumerate(results):
        details = [e["detail"] for e in r.get("evidence", [])]
        assert not any("Rate limit" in d for d in details), (
            f"Call {i} was rate-limited — semaphore leaked"
        )
        # All should report icmplib not available
        assert any("icmplib" in d for d in details), (
            f"Call {i} didn't report icmplib unavailable"
        )


def test_semaphore_released_when_no_dst_ip():
    """Early return for missing dst_ip must not leak semaphore."""
    import src.agents.network.traceroute_probe as tp

    tp._semaphore = __import__("threading").Semaphore(tp._MAX_CONCURRENT)

    for _ in range(tp._MAX_CONCURRENT + 2):
        r = tp.traceroute_probe({"dst_ip": ""})
        details = [e["detail"] for e in r.get("evidence", [])]
        assert any("No destination" in d for d in details)

    # One more call with a real IP should NOT be rate-limited
    with mock.patch.object(tp, "HAS_ICMPLIB", False):
        r = tp.traceroute_probe({"dst_ip": "10.0.0.1"})
        details = [e["detail"] for e in r.get("evidence", [])]
        assert not any("Rate limit" in d for d in details)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_traceroute_semaphore.py -v`
Expected: FAIL — `test_semaphore_released_when_icmplib_missing` will fail with "Call 3 was rate-limited — semaphore leaked"

**Step 3: Fix the semaphore leak**

Replace the function body in `backend/src/agents/network/traceroute_probe.py` (lines 20-101). The key change: move the `HAS_ICMPLIB` check INSIDE the try/finally that wraps `_semaphore.release()`, and move `dst_ip` check BEFORE semaphore acquisition:

```python
def traceroute_probe(state: dict) -> dict:
    """Run traceroute from current host to destination.

    Features:
    - Rate limiting (max 3 concurrent)
    - Loop detection (repeated IPs)
    - Graceful fallback when icmplib unavailable
    """
    dst_ip = state.get("dst_ip", "")

    # Early return BEFORE acquiring semaphore — no leak possible
    if not dst_ip:
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "evidence": [{"type": "traceroute", "detail": "No destination IP"}],
        }

    if not _semaphore.acquire(blocking=False):
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "evidence": [{"type": "traceroute", "detail": "Rate limit: too many concurrent traceroutes"}],
        }

    # Everything from here is inside try/finally to guarantee release
    try:
        if not HAS_ICMPLIB:
            return {
                "trace_method": "unavailable",
                "trace_hops": [],
                "evidence": [{"type": "traceroute", "detail": "icmplib not available"}],
            }

        trace_id = str(uuid.uuid4())[:8]

        result = icmp_traceroute(dst_ip, max_hops=30, timeout=2)

        hops = []
        seen_ips = set()
        loop_detected = False

        for i, hop in enumerate(result):
            hop_ip = hop.address if hop.address != "*" else ""
            rtt = hop.avg_rtt if hasattr(hop, 'avg_rtt') else 0.0
            status = "responded" if hop_ip else "timeout"

            # Loop detection
            if hop_ip and hop_ip in seen_ips:
                loop_detected = True
            if hop_ip:
                seen_ips.add(hop_ip)

            hops.append({
                "id": f"hop-{trace_id}-{i+1}",
                "trace_id": trace_id,
                "hop_number": i + 1,
                "ip": hop_ip,
                "rtt_ms": rtt,
                "status": status,
            })

        return {
            "trace_id": trace_id,
            "trace_method": "icmp",
            "trace_hops": hops,
            "routing_loop_detected": loop_detected,
            "traced_path": {
                "hops": [h["ip"] for h in hops if h["ip"]],
                "method": "icmp",
                "hop_count": len(hops),
            },
            "evidence": [{"type": "traceroute", "detail": f"ICMP traceroute: {len(hops)} hops, loop={'yes' if loop_detected else 'no'}"}],
        }
    except Exception as e:
        return {
            "trace_method": "unavailable",
            "trace_hops": [],
            "error": str(e),
            "evidence": [{"type": "traceroute", "detail": f"Traceroute failed: {e}"}],
        }
    finally:
        _semaphore.release()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_traceroute_semaphore.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/network/traceroute_probe.py backend/tests/test_traceroute_semaphore.py
git commit -m "fix: prevent semaphore leak in traceroute_probe on early returns"
```

---

### Task 2: Fix Enum Serialization — Firewalls Never Detected

**Files:**
- Modify: `backend/src/network/knowledge_graph.py:51-182`
- Test: `backend/tests/test_firewall_detection.py`

**Step 1: Write the failing test**

Create `backend/tests/test_firewall_detection.py`:

```python
"""Regression test: firewalls must appear in firewalls_in_path."""
from unittest.mock import MagicMock
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet, Interface
from src.network.topology_store import TopologyStore
from src.agents.network.graph_pathfinder import graph_pathfinder


def _make_store_with_firewall():
    """Create a TopologyStore with a path: host-A -> firewall-1 -> host-B."""
    store = TopologyStore(db_path=":memory:")
    # Devices
    host_a = Device(id="host-a", name="Host A", device_type=DeviceType.HOST, management_ip="10.0.1.10")
    fw = Device(id="fw-1", name="Firewall 1", device_type=DeviceType.FIREWALL, management_ip="10.0.1.1")
    host_b = Device(id="host-b", name="Host B", device_type=DeviceType.HOST, management_ip="10.0.2.10")
    store.add_device(host_a)
    store.add_device(fw)
    store.add_device(host_b)
    # Subnet
    subnet_a = Subnet(id="subnet-a", cidr="10.0.1.0/24")
    subnet_b = Subnet(id="subnet-b", cidr="10.0.2.0/24")
    store.add_subnet(subnet_a)
    store.add_subnet(subnet_b)
    # Interfaces
    store.add_interface(Interface(id="iface-a", device_id="host-a", name="eth0", ip="10.0.1.10"))
    store.add_interface(Interface(id="iface-fw-in", device_id="fw-1", name="eth0", ip="10.0.1.1"))
    store.add_interface(Interface(id="iface-fw-out", device_id="fw-1", name="eth1", ip="10.0.2.1"))
    store.add_interface(Interface(id="iface-b", device_id="host-b", name="eth0", ip="10.0.2.10"))
    return store


def test_firewalls_detected_in_path():
    """After model_dump(mode='json'), DeviceType.FIREWALL should match string comparison."""
    store = _make_store_with_firewall()
    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()

    # Verify the firewall node has device_type as string "firewall" (not enum)
    fw_data = kg.graph.nodes.get("fw-1", {})
    assert fw_data.get("device_type") == "firewall", (
        f"Expected string 'firewall', got {fw_data.get('device_type')!r}"
    )

    # Build manual edges for the path: host-a -> fw-1 -> host-b
    kg.graph.add_edge("host-a", "fw-1", edge_type="connected_to", confidence=0.9)
    kg.graph.add_edge("fw-1", "host-b", edge_type="connected_to", confidence=0.9)

    # Run pathfinder
    state = {"src_ip": "10.0.1.10", "dst_ip": "10.0.2.10"}
    result = graph_pathfinder(state, kg=kg)

    assert len(result["firewalls_in_path"]) > 0, (
        f"Expected at least 1 firewall, got {result['firewalls_in_path']}"
    )
    assert result["firewalls_in_path"][0]["device_id"] == "fw-1"


def test_enum_serialization_consistency():
    """All node types should store device_type as a string, not an Enum."""
    store = TopologyStore(db_path=":memory:")
    store.add_device(Device(id="d1", name="Router", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
    store.add_device(Device(id="d2", name="Switch", device_type=DeviceType.SWITCH, management_ip="10.0.0.2"))
    store.add_device(Device(id="d3", name="FW", device_type=DeviceType.FIREWALL, management_ip="10.0.0.3"))

    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()

    for node_id in ["d1", "d2", "d3"]:
        dt = kg.graph.nodes[node_id].get("device_type")
        assert isinstance(dt, str), f"Node {node_id} device_type is {type(dt).__name__}, expected str"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_firewall_detection.py -v`
Expected: FAIL — `device_type` will be an Enum instance, not a string

**Step 3: Fix all model_dump() calls in knowledge_graph.py**

In `backend/src/network/knowledge_graph.py`, change every `model_dump()` that feeds into `graph.add_node()` to `model_dump(mode="json")`. There are 14 call sites:

Replace ALL occurrences of `.model_dump()` with `.model_dump(mode="json")` in the file (lines 57, 61, 67, 71, 93, 118, 127, 136, 140, 147, 156, 160, 170, 182, 188).

**Important:** Line 57 (`self.ip_resolver.load_subnets([s.model_dump() for s in subnets])`) should also use `mode="json"` for consistency, though it may not strictly need it.

**Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_firewall_detection.py -v`
Expected: 2 PASSED

**Step 5: Run existing tests to ensure no regression**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -x -q --timeout=60`
Expected: All existing tests pass

**Step 6: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/tests/test_firewall_detection.py
git commit -m "fix: use model_dump(mode='json') so firewall detection works"
```

---

### Task 3: Fix Stale IP→Device Cache

**Files:**
- Modify: `backend/src/network/knowledge_graph.py:51-53,430-442`
- Test: `backend/tests/test_device_index_cache.py`

**Step 1: Write the failing test**

Create `backend/tests/test_device_index_cache.py`:

```python
"""Regression test: _device_index must be cleared on reload."""
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Interface
from src.network.topology_store import TopologyStore


def test_cache_cleared_on_reload():
    """After deleting a device and reloading, find_device_by_ip should return None."""
    store = TopologyStore(db_path=":memory:")
    store.add_device(Device(id="d1", name="Host1", device_type=DeviceType.HOST, management_ip="10.0.0.1"))
    store.add_interface(Interface(id="i1", device_id="d1", name="eth0", ip="10.0.0.1"))

    kg = NetworkKnowledgeGraph(store)
    kg.load_from_store()
    assert kg.find_device_by_ip("10.0.0.1") == "d1"

    # Delete device from store
    store.delete_device("d1")
    kg.load_from_store()

    # After reload, the old IP should NOT resolve
    assert kg.find_device_by_ip("10.0.0.1") is None, (
        "Stale cache: IP still resolves to deleted device"
    )


def test_promote_updates_interface_cache():
    """Interfaces added via promote_from_canvas should update _device_index."""
    store = TopologyStore(db_path=":memory:")
    kg = NetworkKnowledgeGraph(store)

    nodes = [{
        "id": "dev-x",
        "type": "device",
        "data": {
            "label": "DevX",
            "deviceType": "HOST",
            "ip": "10.0.0.5",
            "interfaces": [
                {"id": "iface-x1", "name": "eth0", "ip": "192.168.1.10", "role": "inside"},
            ],
        },
    }]
    kg.promote_from_canvas(nodes, [])

    # Management IP should resolve
    assert kg.find_device_by_ip("10.0.0.5") == "dev-x"
    # Interface IP should also resolve (this is the bug — currently it doesn't)
    assert kg.find_device_by_ip("192.168.1.10") == "dev-x", (
        "Interface IP not cached after promote"
    )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_device_index_cache.py -v`
Expected: FAIL — `test_cache_cleared_on_reload` fails (stale IP resolves), `test_promote_updates_interface_cache` fails (interface IP not found)

**Step 3: Fix the cache**

In `backend/src/network/knowledge_graph.py`:

**Fix 1:** Clear cache on reload. After line 53 (`self.graph.clear()`), add:

```python
self._device_index.clear()
```

**Fix 2:** Update cache when promoting interfaces. In `promote_from_canvas()`, after the `self.store.add_interface(iface)` call (around line 442), add:

```python
if iface.ip:
    self._device_index[iface.ip] = node_id
```

**Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_device_index_cache.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add backend/src/network/knowledge_graph.py backend/tests/test_device_index_cache.py
git commit -m "fix: clear _device_index on reload, update on promote"
```

---

### Task 4: Encrypt Adapter Credentials at Rest

**Files:**
- Modify: `backend/src/network/topology_store.py:786-846`
- Test: `backend/tests/test_adapter_credential_encryption.py`

**Step 1: Write the failing test**

Create `backend/tests/test_adapter_credential_encryption.py`:

```python
"""Regression test: adapter api_key must be encrypted in SQLite."""
import sqlite3

from src.network.topology_store import TopologyStore
from src.network.models import AdapterInstance, AdapterVendor


def test_api_key_not_stored_in_plaintext():
    """Save an adapter, read raw SQLite — api_key column must NOT be plaintext."""
    store = TopologyStore(db_path=":memory:")
    plaintext_key = "sk-super-secret-paloalto-token-12345"

    instance = AdapterInstance(
        instance_id="test-inst-1",
        label="Test PAN",
        vendor=AdapterVendor.PALO_ALTO,
        api_endpoint="https://pan.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    # Read raw SQLite row
    conn = store._conn()
    try:
        row = conn.execute(
            "SELECT api_key FROM adapter_instances WHERE instance_id=?",
            ("test-inst-1",),
        ).fetchone()
        raw_stored = row["api_key"]
    finally:
        conn.close()

    assert raw_stored != plaintext_key, (
        f"api_key stored in plaintext! raw={raw_stored}"
    )


def test_api_key_roundtrip():
    """Save and retrieve an adapter — api_key should be decrypted back to original."""
    store = TopologyStore(db_path=":memory:")
    plaintext_key = "sk-another-secret-key-67890"

    instance = AdapterInstance(
        instance_id="test-inst-2",
        label="Test AWS",
        vendor=AdapterVendor.AWS_SG,
        api_endpoint="https://aws.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    loaded = store.get_adapter_instance("test-inst-2")
    assert loaded is not None
    assert loaded.api_key == plaintext_key, (
        f"Decrypted key doesn't match: {loaded.api_key}"
    )


def test_list_adapter_instances_decrypts():
    """list_adapter_instances should also decrypt api_keys."""
    store = TopologyStore(db_path=":memory:")
    plaintext_key = "sk-list-test-key"

    instance = AdapterInstance(
        instance_id="test-inst-3",
        label="Test ZS",
        vendor=AdapterVendor.ZSCALER,
        api_endpoint="https://zs.example.com",
        api_key=plaintext_key,
    )
    store.save_adapter_instance(instance)

    instances = store.list_adapter_instances()
    assert len(instances) == 1
    assert instances[0].api_key == plaintext_key
```

**Step 2: Run test to verify it fails**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_adapter_credential_encryption.py -v`
Expected: FAIL — `test_api_key_not_stored_in_plaintext` fails (raw value == plaintext)

**Step 3: Add encryption to topology_store.py**

In `backend/src/network/topology_store.py`:

Add import at top (near other imports):
```python
from src.integrations.credential_resolver import get_credential_resolver
```

Modify `save_adapter_instance()` — encrypt api_key before storing:

Replace the line that writes `instance.api_key` (line ~799) with:
```python
# Encrypt api_key before storing
encrypted_key = instance.api_key
if instance.api_key:
    resolver = get_credential_resolver()
    encrypted_key = resolver.encrypt_and_store(
        instance.instance_id, "adapter_api_key", instance.api_key
    )
```

Then use `encrypted_key` in the INSERT statement instead of `instance.api_key`.

Modify `get_adapter_instance()` — decrypt api_key after reading:

After creating the `AdapterInstance` object, decrypt:
```python
result = AdapterInstance(**d)
if result.api_key:
    try:
        resolver = get_credential_resolver()
        result.api_key = resolver.resolve(
            result.instance_id, "adapter_api_key", result.api_key
        )
    except Exception:
        result.api_key = ""  # Handle corrupted/old entries
return result
```

Apply the same decryption pattern to `list_adapter_instances()` and `list_adapter_instances_by_vendor()`.

**Step 4: Run test to verify it passes**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_adapter_credential_encryption.py -v`
Expected: 3 PASSED

**Step 5: Run existing adapter tests to check regression**

Run: `cd backend && ../.venv/bin/python -m pytest tests/test_adapter_endpoints.py tests/test_adapter_registry.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/src/network/topology_store.py backend/tests/test_adapter_credential_encryption.py
git commit -m "fix(security): encrypt adapter api_key via CredentialResolver"
```

---

### Task 5: Lift Reverse-Path Toggle to War Room Header

**Files:**
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx`
- Modify: `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx`
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkCanvas.tsx`
- Modify: `frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx`

**Step 1: Update NetworkWarRoom.tsx — add direction state and toggle**

In `NetworkWarRoom.tsx`:

Add state after line 17:
```typescript
const [direction, setDirection] = useState<'forward' | 'return'>('forward');
```

Add toggle buttons in the header (inside the `<div className="flex items-center gap-3">` after the phase badge, before the Back button):
```typescript
{findings?.return_state && (
  <div className="flex gap-0.5 rounded-lg p-0.5" style={{ backgroundColor: '#0a1a1e' }}>
    <button
      onClick={() => setDirection('forward')}
      className="px-3 py-1 rounded-md text-xs font-mono font-medium transition-colors"
      style={direction === 'forward'
        ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
        : { color: '#64748b' }}
    >
      A&#8594;B
    </button>
    <button
      onClick={() => setDirection('return')}
      className="px-3 py-1 rounded-md text-xs font-mono font-medium transition-colors"
      style={direction === 'return'
        ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
        : { color: '#64748b' }}
    >
      B&#8594;A
    </button>
  </div>
)}
```

Pass `direction` to all children:
```typescript
<DiagnosisPanel findings={findings} direction={direction} />
<NetworkCanvas findings={findings} direction={direction} />
<NetworkEvidenceStack findings={findings} adapters={adapters} direction={direction} />
```

**Step 2: Update DiagnosisPanel.tsx — accept direction as prop**

Change interface:
```typescript
interface DiagnosisPanelProps {
  findings: NetworkFindings;
  direction: 'forward' | 'return';
}
```

Change component signature:
```typescript
const DiagnosisPanel: React.FC<DiagnosisPanelProps> = ({ findings, direction }) => {
```

Remove internal direction state (delete the old `useState` line).
Keep the state selection logic:
```typescript
const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;
```

Remove the toggle buttons from this component (lines 27-38) — the toggle now lives in the header.

**Step 3: Update NetworkCanvas.tsx — accept direction as prop**

Change interface:
```typescript
interface NetworkCanvasProps {
  findings: NetworkFindings;
  direction: 'forward' | 'return';
}
```

Change component signature and state selection:
```typescript
const NetworkCanvas: React.FC<NetworkCanvasProps> = ({ findings, direction }) => {
  const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;
```

The rest of the component already reads from `state`, so no further changes needed.

**Step 4: Update NetworkEvidenceStack.tsx — accept direction as prop**

Change interface:
```typescript
interface NetworkEvidenceStackProps {
  findings: NetworkFindings;
  adapters?: Array<{ vendor: string; status: string }>;
  direction: 'forward' | 'return';
}
```

Change component signature and state selection:
```typescript
const NetworkEvidenceStack: React.FC<NetworkEvidenceStackProps> = ({
  findings,
  adapters,
  direction,
}) => {
  const state = direction === 'return' && findings.return_state ? findings.return_state : findings.state;
```

**Step 5: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 6: Commit**

```bash
git add frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx \
        frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx \
        frontend/src/components/NetworkTroubleshooting/NetworkCanvas.tsx \
        frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx
git commit -m "fix: lift reverse-path toggle to War Room header, wire into all panels"
```

---

### Task 6: Full Verification

**Step 1: Run all Python tests**

Run: `cd backend && ../.venv/bin/python -m pytest tests/ -q --timeout=120`
Expected: All tests pass (including new tests from tasks 1-4)

**Step 2: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Verify Python compilation**

Run: `cd backend && ../.venv/bin/python -c "from src.agents.network.traceroute_probe import traceroute_probe; from src.network.knowledge_graph import NetworkKnowledgeGraph; from src.network.topology_store import TopologyStore; print('All imports OK')"`
Expected: "All imports OK"
