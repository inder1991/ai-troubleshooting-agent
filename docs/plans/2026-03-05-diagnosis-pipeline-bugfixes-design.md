# Network Diagnosis Pipeline Bug Fixes — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 5 correctness, security, and UX bugs that silently break the network diagnosis pipeline.

**Architecture:** Surgical, independent fixes — each bug gets an isolated change + regression test. No refactors.

**Priority:** P0 (bugs 1-2 block all firewall/traceroute diagnosis), P1 (bugs 3-4 security + data integrity), P2 (bug 5 UX completeness).

---

## Bug 1: Enum Serialization — Firewalls Never Detected (P0)

### Problem

`graph_pathfinder.py:66` compares `node_data.get("device_type")` against `DeviceType.FIREWALL.value` (string `"firewall"`). But `knowledge_graph.py:61` stores devices via `d.model_dump()`, which by default keeps Python enum objects (not strings) in the dict. The comparison always fails, so `firewalls_in_path` stays empty and the firewall evaluator never runs.

### Root Cause

`model_dump()` without `mode="json"` preserves enum instances. NetworkX stores whatever Python objects you give it.

### Fix

Change every `model_dump()` call in `knowledge_graph.py` that feeds into `graph.add_node()` to `model_dump(mode="json")`. This serializes enums to their `.value` strings.

**Files:**
- `backend/src/network/knowledge_graph.py` — all `model_dump()` calls (14 sites)

### Regression Test

Create a FIREWALL device → load into KG → run `graph_pathfinder` → assert `firewalls_in_path` is non-empty.

---

## Bug 2: Semaphore Leak — Traceroute Dies After 3 Failures (P0)

### Problem

`traceroute_probe.py:37` acquires the semaphore. If `HAS_ICMPLIB` is False (line 44), the function returns immediately — but `_semaphore.release()` at line 100 is only reached via the `try/finally` block starting at line 53. After 3 such calls, all slots are exhausted and every subsequent diagnosis reports "Rate limit."

### Root Cause

Early returns between `acquire()` and the `try` block bypass the `finally` that releases.

### Fix

Restructure so `_semaphore.acquire()` happens just before the `try` block, and all post-acquire exit paths go through `finally`:

```python
def traceroute_probe(state: dict) -> dict:
    dst_ip = state.get("dst_ip", "")
    if not dst_ip:
        return {...}  # Before acquire — no leak

    if not _semaphore.acquire(blocking=False):
        return {...}  # Acquire failed — no leak

    try:
        if not HAS_ICMPLIB:
            return {...}  # Inside try — finally releases
        # ... actual traceroute ...
    except Exception as e:
        return {...}
    finally:
        _semaphore.release()
```

**Files:**
- `backend/src/agents/network/traceroute_probe.py`

### Regression Test

Patch `HAS_ICMPLIB = False`, call `traceroute_probe` 4 times, assert the 4th does NOT return "Rate limit" (proving slots are released).

---

## Bug 3: Stale IP→Device Cache (P1)

### Problem

`_device_index` (IP→device_id dict) is populated in `load_from_store()` but never cleared on reload. After deleting or reassigning interfaces, stale entries persist, causing pathfinding to follow non-existent nodes or resolve the wrong device.

Additionally, `promote_from_canvas()` adds interfaces (line 432-442) but never updates `_device_index` for those interface IPs.

### Fix

1. Add `self._device_index.clear()` at the top of `load_from_store()`, after `self.graph.clear()`.
2. In `promote_from_canvas()`, update `_device_index` when adding interfaces with IPs.

**Files:**
- `backend/src/network/knowledge_graph.py`

### Regression Test

Create device with IP → `find_device_by_ip` returns it → delete device → reload store → `find_device_by_ip` returns None.

---

## Bug 4: Adapter Credentials in Plaintext (P1)

### Problem

`topology_store.py:799` writes `instance.api_key` directly to SQLite. A compromise of `data/network.db` exposes every firewall token. The project already has `CredentialResolver` + `FernetSecretStore` but they're not used here.

### Fix

- `save_adapter_instance()`: encrypt `api_key` via `CredentialResolver.encrypt_and_store()` before writing.
- `get_adapter_instance()`, `list_adapter_instances()`, `list_adapter_instances_by_vendor()`: decrypt handle via `CredentialResolver.resolve()` before returning.
- Fresh start — no migration of existing plaintext rows. Users re-enter API keys.

**Files:**
- `backend/src/network/topology_store.py` — 4 methods

### Regression Test

Save an adapter instance, read raw SQLite row, assert `api_key` column does NOT contain the original plaintext.

---

## Bug 5: Reverse-Path Toggle Isolated in DiagnosisPanel (P2)

### Problem

The backend already supports bidirectional diagnosis (`network_endpoints.py:96-99` — swaps src/dst, runs return graph, stores `return_state`). But `NetworkWarRoom.tsx` always passes `findings` to all panels, and `NetworkCanvas` + `NetworkEvidenceStack` always read `findings.state`. Only `DiagnosisPanel` has a local forward/return toggle — it never propagates to the other panels.

### Fix

1. Lift `direction` state from `DiagnosisPanel` to `NetworkWarRoom`.
2. Add forward/return toggle to the War Room header (shown when `findings.return_state` exists).
3. Pass `direction` as prop to `DiagnosisPanel`, `NetworkCanvas`, `NetworkEvidenceStack`.
4. Each child selects: `state = direction === 'return' && findings.return_state ? findings.return_state : findings.state`.

**Files:**
- `frontend/src/components/NetworkTroubleshooting/NetworkWarRoom.tsx`
- `frontend/src/components/NetworkTroubleshooting/DiagnosisPanel.tsx`
- `frontend/src/components/NetworkTroubleshooting/NetworkCanvas.tsx`
- `frontend/src/components/NetworkTroubleshooting/NetworkEvidenceStack.tsx`

### Verification

Run a bidirectional diagnosis → toggle appears in header → switching to "Return" updates all 3 panels simultaneously.

---

## Execution Order

```
Phase 1 — Pipeline Correctness (sequential):
  Bug 2: Semaphore leak (unblocks traceroute)
  Bug 1: Enum serialization (unblocks firewall detection)

Phase 2 — Data Integrity + Security (parallel):
  Bug 3: Stale cache
  Bug 4: Credential encryption

Phase 3 — UX:
  Bug 5: Reverse-path toggle
```

## Verification

1. All existing tests pass
2. New regression tests pass for bugs 1-4
3. TypeScript compiles with 0 errors
4. Visual: bidirectional diagnosis shows toggle, switching updates all panels
