# Cluster Diagnostic Platform — Hardening Design

**Date:** 2026-04-04
**Status:** Approved
**Priority mix:** P0 (LLM reliability) · P1 (Alertmanager webhook) · P2 (semantic truncation) + observability + resilience

---

## Goals

Fix 8 architectural gaps identified in the Head of Architecture review:

1. Replace string-parsed LLM JSON with structured tool_use output
2. Replace hard string-truncation of tool results with semantic truncation + envelope
3. Build Alertmanager inbound webhook endpoint
4. Add LLM call metadata logging (SQLite → Redis-ready)
5. Add WebSocket event replay for reconnecting clients
6. Graceful partial result on graph-level timeout
7. Surface truncation flags in synthesizer prompts
8. Guard synthesizer prompt against token overflow on large clusters

---

## Architecture Overview

Six self-contained changes. Four share a common storage abstraction layer (SQLite now, Redis via env var later). No new external services required for initial deployment.

```
┌─────────────────────────────────────────────────────────┐
│                  DiagnosticStore (abstract)             │
│   SQLiteDiagnosticStore  ←→  RedisDiagnosticStore       │
│   (default, file-based)       (via DIAGNOSTIC_STORE_    │
│                                BACKEND=redis)           │
└───────────────┬─────────────────────────┬───────────────┘
                │                         │
         Event Replay               LLM Call Logging
         (Section 5)                (Section 5)
```

---

## Section 1: LLM Output Reliability (P0)

### 1a. Shared output schemas

**New file:** `backend/src/agents/cluster/output_schemas.py`

Three Anthropic tool definitions with strict JSON schemas — one per output contract:

**`submit_domain_findings`** (used by all 5 domain agents):
```json
{
  "name": "submit_domain_findings",
  "input_schema": {
    "type": "object",
    "required": ["anomalies", "ruled_out", "confidence"],
    "properties": {
      "anomalies": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["domain", "anomaly_id", "description", "evidence_ref", "severity"],
          "properties": {
            "domain": {"type": "string"},
            "anomaly_id": {"type": "string"},
            "description": {"type": "string"},
            "evidence_ref": {"type": "string"},
            "severity": {"enum": ["high", "medium", "low"]},
            "evidence_sources": {"type": "array"}
          }
        }
      },
      "ruled_out": {"type": "array", "items": {"type": "string"}},
      "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
    }
  }
}
```

**`submit_causal_analysis`** (used by `_llm_causal_reasoning`):
```json
{
  "name": "submit_causal_analysis",
  "input_schema": {
    "type": "object",
    "required": ["causal_chains", "uncorrelated_findings"],
    "properties": {
      "causal_chains": {"type": "array"},
      "uncorrelated_findings": {"type": "array"}
    }
  }
}
```

**`submit_verdict`** (used by `_llm_verdict`):
```json
{
  "name": "submit_verdict",
  "input_schema": {
    "type": "object",
    "required": ["platform_health", "blast_radius", "remediation", "re_dispatch_needed", "re_dispatch_domains"],
    "properties": {
      "platform_health": {"enum": ["HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"]},
      "blast_radius": {"type": "object"},
      "remediation": {"type": "object"},
      "re_dispatch_needed": {"type": "boolean"},
      "re_dispatch_domains": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

### 1b. Parse from tool_input, not response.text

Every agent's `_tool_calling_loop` and `_llm_analyze` is updated:

1. Pass the appropriate schema as the `tools` argument in the Anthropic API call
2. After the API returns, scan `response.content` for a `tool_use` block matching the submit tool name
3. Extract `tool_use.input` — Anthropic guarantees this is always valid JSON matching the schema
4. Validate with corresponding Pydantic model
5. Fall back to heuristic only if the tool was **never called** (not if JSON was malformed)

The `text.index("{") / text.rindex("}")` pattern is removed from all 7 files:
- `ctrl_plane_agent.py` (lines 70–86, 224–227)
- `node_agent.py`
- `network_agent.py` (lines 77–80)
- `storage_agent.py`
- `rbac_agent.py`
- `synthesizer.py` (lines 219–230, 326–348)

### 1c. Synthesizer prompt overflow guard

New function `_build_bounded_causal_prompt()` in `synthesizer.py`:

**Token budget:** 60,000 tokens (leaves room for system prompt + response within claude-sonnet context)
**Token estimation:** `len(text) / 4` (cheap approximation, conservative)

**Priority ordering:**
1. Critical + high severity anomalies → always included
2. Pattern matches → always included
3. Medium severity anomalies → included until budget consumed
4. Low confidence anomalies (< 40%) → dropped if over budget

When items are dropped, append to prompt:
```
NOTE: {N} low-priority anomalies omitted (context limit reached).
Do not claim exhaustive analysis. Findings below reflect highest-signal data only.
```

### 1d. Truncation awareness in synthesis

After collecting `domain_reports`, scan all `truncation_flags`. If any flag is set:

1. Prepend a DATA COMPLETENESS block to both `_llm_causal_reasoning` and `_llm_verdict` prompts:
```
DATA COMPLETENESS WARNING:
The following data sources were truncated before analysis:
- ctrl_plane domain: events truncated (approx. 80 items dropped)
- node domain: pods truncated (approx. 200 items dropped)

Rule: Do not assign confidence > 60% to any finding that depends solely on
a truncated data source. State the data gap explicitly in your reasoning.
```

2. Post-processing confidence damping: any causal chain where **all** `evidence_refs` map back to anomalies from a truncated domain → cap `chain.confidence = min(chain.confidence, 60)`

---

## Section 2: Semantic Truncation (P2)

### Files changed
- `backend/src/agents/cluster/tool_executor.py`
- `backend/src/agents/cluster/state.py` (TruncationFlags)

### 2a. TruncatedResult envelope

`execute_tool_call()` returns a valid JSON object instead of a potentially malformed truncated string:

```json
{
  "data": [ ...first N complete objects... ],
  "total_available": 150,
  "returned": 50,
  "truncated": true,
  "truncation_reason": "SIZE_LIMIT"
}
```

`truncation_reason` values: `"SIZE_LIMIT"` | `"API_LIMIT"` | `"BUDGET"`

### 2b. Item-aware slicing

Replace `result_str[:MAX_RESULT_SIZE] + '..."truncated"'` with:

```python
items = []
total_size = 0
for item in data:
    item_str = json.dumps(item, default=str)
    if total_size + len(item_str) > MAX_RESULT_SIZE:
        break
    items.append(item)
    total_size += len(item_str)

truncated = len(items) < len(data)
return json.dumps({
    "data": items,
    "total_available": len(data),  # or result.total_available
    "returned": len(items),
    "truncated": truncated,
    "truncation_reason": "SIZE_LIMIT" if truncated else None,
})
```

### 2c. TruncationFlags enrichment

When a tool returns `truncated: true`, the agent sets the corresponding `DomainReport.truncation_flags` field. Add `dropped_count: int` to each flag so the synthesis warning (Section 1d) can report approximate drop counts.

Updated `TruncationFlags`:
```python
class TruncationFlags(BaseModel):
    events: bool = False
    events_dropped: int = 0
    pods: bool = False
    pods_dropped: int = 0
    log_lines: bool = False
    log_lines_dropped: int = 0
    metric_points: bool = False
    nodes: bool = False
    nodes_dropped: int = 0
    pvcs: bool = False
    pvcs_dropped: int = 0
```

### 2d. LLM tool result message annotation

Agent prompt instructions updated to include:
```
When a tool result contains "truncated": true, you MUST:
1. Note the data gap in your reasoning
2. Not assign high confidence to findings that depend on the dropped items
3. Include "based on partial data" in the affected anomaly description
```

---

## Section 3: Graph Timeout Graceful Degradation (HIGH)

### Files changed
- `backend/src/api/routes_v4.py`
- `backend/src/agents/cluster/graph.py`

### 3a. Progressive state checkpointing

Each major phase completion writes its state slice into `session["state"]` via the emitter callback. No new mechanism — the session dict already exists and is safe to read under the session lock.

Checkpoint points:
| Phase | Fields written |
|-------|---------------|
| Domain fan-in complete | `domain_reports`, `proactive_findings`, `data_completeness` |
| Pattern matching complete | `pattern_matches`, `normalized_signals` |
| Synthesis Stage 1 complete | deduplicated anomaly list (stored in `_checkpoint_anomalies`) |
| Synthesis Stage 2 complete | `causal_chains`, `uncorrelated_findings` |

Each checkpoint is written by calling a lightweight `_checkpoint_state(session_id, partial_state)` function that merges into `session["state"]` under the session lock.

### 3b. Timeout recovery

```python
except asyncio.TimeoutError:
    partial_state = sessions.get(session_id, {}).get("state") or {}
    if partial_state.get("domain_reports"):
        partial_report = _build_partial_health_report(partial_state)
        sessions[session_id]["state"]["health_report"] = partial_report
        sessions[session_id]["state"]["phase"] = "partial_timeout"
    await emitter.emit(
        "cluster_supervisor", "warning",
        "Diagnosis timed out — partial results available",
        {"phase": "partial_timeout",
         "data_completeness": partial_state.get("data_completeness", 0.0)}
    )
```

### 3c. `_build_partial_health_report()`

New function in `graph.py`:

1. Reads `domain_reports`, `pattern_matches`, `proactive_findings` from state
2. Derives `platform_health`:
   - Any domain FAILED or PARTIAL + critical anomaly present → `"CRITICAL"`
   - Any domain FAILED + no anomalies → `"UNKNOWN"`
   - All domains SUCCESS → `"DEGRADED"` (synthesis didn't complete, can't claim HEALTHY)
3. Sets `data_completeness` from fraction of dispatched domains that completed
4. Sets `status = "PARTIAL_TIMEOUT"` on the report
5. All anomalies found so far go into `uncorrelated_findings` (no causal chains — synthesis incomplete)
6. `remediation` is empty — no commands without causal analysis

---

## Section 4: Storage Abstraction Layer

### New files
- `backend/src/observability/__init__.py`
- `backend/src/observability/store.py`

### Abstract interface

```python
class DiagnosticStore(ABC):
    async def append_event(self, session_id: str, event: dict) -> int: ...
    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]: ...
    async def log_llm_call(self, record: dict) -> None: ...
    async def get_llm_calls(self, session_id: str) -> list[dict]: ...
    async def delete_session(self, session_id: str) -> None: ...
```

### SQLite implementation (`SQLiteDiagnosticStore`)

Database: `data/diagnostics.db` (created on first use)

```sql
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    event_json  TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);

CREATE TABLE IF NOT EXISTS llm_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    agent_name    TEXT,
    model         TEXT,
    call_type     TEXT,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    latency_ms    INTEGER,
    success       INTEGER,
    error         TEXT,
    fallback_used INTEGER,
    response_json TEXT,
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_session ON llm_calls(session_id);
```

Uses `aiosqlite` for non-blocking async I/O. Single shared connection pool per process.

### Redis implementation (`RedisDiagnosticStore`)

- Events → `RPUSH diag:events:{session_id}` + `LRANGE` with offset for replay
- LLM calls → `RPUSH diag:llm:{session_id}` with `EXPIREAT` matching session TTL
- Sequence number = Redis LLEN before push

### Factory

```python
def get_store() -> DiagnosticStore:
    backend = os.getenv("DIAGNOSTIC_STORE_BACKEND", "sqlite")
    if backend == "redis":
        return RedisDiagnosticStore(url=os.getenv("REDIS_URL", "redis://localhost:6379"))
    return SQLiteDiagnosticStore(
        path=os.getenv("DIAGNOSTIC_DB_PATH", "data/diagnostics.db")
    )
```

One env var to switch. No caller changes needed.

### Session cleanup integration

Existing `_session_cleanup_loop()` calls `await store.delete_session(session_id)` after existing cleanup steps — removes all events and LLM logs for expired sessions.

---

## Section 5: Observability — LLM Logging + WebSocket Event Replay

### Files changed
- `backend/src/observability/store.py` (new — Section 4)
- `backend/src/api/event_emitter.py`
- `backend/src/api/routes_v4.py`
- All agent files + synthesizer (one `await store.log_llm_call(...)` per LLM call)

### 5a. LLM call logging

After every Anthropic API call (where telemetry is already recorded), add:

```python
await store.log_llm_call({
    "session_id": session_id,
    "agent_name": agent_name,
    "model": model,
    "call_type": call_type,          # "tool_calling" | "single_pass" | "causal_reasoning" | "verdict"
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "latency_ms": latency_ms,
    "success": success,
    "error": error_str,              # None if success
    "fallback_used": fallback_used,
    "response_json": response_dict,  # Structured output dict only (no raw prompt text)
    "created_at": time.time(),
})
```

New API endpoint:
```
GET /api/v5/session/{session_id}/llm-calls
→ list of call records ordered by created_at ascending
```

### 5b. WebSocket event replay

`EventEmitter.emit()` updated:

```python
async def emit(self, agent_name, event_type, message, details=None):
    event = TaskEvent(...)
    sequence_number = await store.append_event(self.session_id, event.model_dump(mode="json"))
    event.sequence_number = sequence_number          # attached before broadcast
    self._events.append(event)

    if self._websocket_manager:
        try:
            await self._websocket_manager.send_message(self.session_id, {
                "type": "task_event",
                "data": event.model_dump(mode="json"),
            })
        except Exception as e:
            logger.warning("WebSocket broadcast failed (event persisted at seq=%d)", sequence_number)
    return event
```

`TaskEvent` gains `sequence_number: Optional[int] = None` field.

### 5c. Replay endpoint

Existing `GET /session/{session_id}/events` extended with optional query param:

```
GET /api/v5/session/{session_id}/events?after_sequence=15
→ Events with sequence_number > 15, ordered ascending
```

Frontend reconnect flow:
1. Frontend tracks `last_sequence_number` from received events
2. On WebSocket reconnect: fetch `?after_sequence={last_sequence_number}`
3. Replay missed events in sequence order

---

## Section 6: Alertmanager Webhook (P1)

### New file
- `backend/src/api/routes_alerts.py`

### Registered at
- `POST /api/v5/alerts/webhook`

### 6a. Pydantic models

```python
class AlertmanagerAlert(BaseModel):
    status: str                        # "firing" | "resolved"
    labels: dict[str, str]
    annotations: dict[str, str] = {}

class AlertmanagerPayload(BaseModel):
    alerts: list[AlertmanagerAlert]
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
```

### 6b. Scope derivation

Merged labels = `{**groupLabels, **commonLabels}` (commonLabels wins):

| Labels | Scope level | Control plane |
|--------|-------------|---------------|
| `workload` + `namespace` | `workload` | False |
| `namespace` only | `namespace` | False |
| `severity=critical` (any scope) | — | True |
| neither | `cluster` | True |

Severity filter:
- `critical` → `scan_mode = "comprehensive"`
- `warning` → `scan_mode = "diagnostic"`
- `info` / missing → **drop silently**, return `{"status": "ignored", "reason": "severity=info"}`
- `resolved` alerts → **drop silently**, return `{"status": "ignored", "reason": "status=resolved"}`

### 6c. Deduplication

In-memory dict `_active_alert_sessions: dict[tuple[str,str], str]` keyed by `(namespace, workload)`.

Before scheduling:
1. If key exists and session age < 30 minutes → return existing session_id, status `"deduplicated"`
2. Else → create new session, register key

Cleanup: key removed when session expires in `_session_cleanup_loop`.

### 6d. Scheduling

```python
session_id = _create_cluster_session(scope, scan_mode, service_name, incident_id)

async def _delayed_diagnosis():
    await asyncio.sleep(ALERT_DIAGNOSTIC_DELAY_SECONDS)
    await run_cluster_diagnosis(session_id, ...)

asyncio.create_task(_delayed_diagnosis())
```

`ALERT_DIAGNOSTIC_DELAY_SECONDS` env var, default `120`.

### 6e. Response

```json
{
  "status": "scheduled",
  "session_id": "uuid",
  "delay_seconds": 120,
  "scope": {"level": "namespace", "namespaces": ["production"]},
  "alert_count": 3,
  "incident_id": "ALERT-a1b2c3d4"
}
```

### 6f. Optional HMAC auth

`ALERT_WEBHOOK_SECRET` env var. If set, verify `X-Alertmanager-Signature` header (SHA256 HMAC). If not set, endpoint is unauthenticated (suitable for internal-network-only Alertmanager).

---

## File Change Summary

| File | Change |
|------|--------|
| `backend/src/agents/cluster/output_schemas.py` | **NEW** — 3 Anthropic tool definitions |
| `backend/src/observability/__init__.py` | **NEW** — package init |
| `backend/src/observability/store.py` | **NEW** — abstract store + SQLite + Redis + factory |
| `backend/src/api/routes_alerts.py` | **NEW** — Alertmanager webhook endpoint |
| `backend/src/agents/cluster/ctrl_plane_agent.py` | Remove string JSON parsing; use submit_domain_findings schema; add store.log_llm_call |
| `backend/src/agents/cluster/node_agent.py` | Same as ctrl_plane_agent |
| `backend/src/agents/cluster/network_agent.py` | Same as ctrl_plane_agent |
| `backend/src/agents/cluster/storage_agent.py` | Same as ctrl_plane_agent |
| `backend/src/agents/cluster/rbac_agent.py` | Same as ctrl_plane_agent |
| `backend/src/agents/cluster/synthesizer.py` | Use submit_causal_analysis + submit_verdict schemas; add _build_bounded_causal_prompt; add truncation warning block; add store.log_llm_call |
| `backend/src/agents/cluster/tool_executor.py` | Replace hard truncation with TruncatedResult envelope; item-aware slicing |
| `backend/src/agents/cluster/state.py` | Add dropped_count fields to TruncationFlags; add sequence_number to TaskEvent |
| `backend/src/agents/cluster/graph.py` | Add _build_partial_health_report; add _checkpoint_state; add proactive_findings truncation flag propagation |
| `backend/src/api/routes_v4.py` | Timeout recovery logic; store.delete_session in cleanup; GET /llm-calls endpoint; after_sequence param on events endpoint; store injection into config |
| `backend/src/api/event_emitter.py` | Write events to store; attach sequence_number; keep existing WebSocket broadcast |
| `backend/src/api/main.py` | Register routes_alerts router; initialize store singleton on startup |

---

## Non-Goals

- Frontend changes (Alertmanager sessions appear in existing session list; event sequence_number is additive)
- Redis deployment (SQLite is the default; Redis is activated by env var only)
- Changing GRAPH_TIMEOUT value (180s stays)
- Modifying the re-dispatch loop depth
- Any change to the 5 domain agent data collection logic (only output parsing changes)
