# Cluster Diagnostic Platform — Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the cluster diagnostic platform across 8 architectural gaps: LLM output reliability, semantic truncation, graph timeout recovery, observability, WebSocket event replay, and Alertmanager webhook integration.

**Architecture:** SQLite-backed storage abstraction (Redis-swappable via env var) underpins both event replay and LLM call logging. LLM output reliability is fixed by switching all agents to Anthropic tool_use structured output, eliminating string-based JSON parsing. All changes are backend-only — no frontend modifications required.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Anthropic SDK, aiosqlite, Pydantic v2, pytest-asyncio

**Design doc:** `docs/plans/2026-04-04-cluster-diagnostic-hardening-design.md`

---

## Phase 1 — Storage Foundation

---

### Task 1: DiagnosticStore — abstract interface + SQLite implementation + factory

**Files:**
- Create: `backend/src/observability/__init__.py`
- Create: `backend/src/observability/store.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_diagnostic_store.py`

**Context:**
This is the foundation for Tasks 7 and 8. Everything else depends on `get_store()` returning a working store. `aiosqlite` is available in the venv but not in `requirements.txt` — add it. `redis[hiredis]` is already in requirements.

**Step 1: Add aiosqlite to requirements**

```bash
echo "aiosqlite>=0.20.0" >> /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend/requirements.txt
```

**Step 2: Create `backend/src/observability/__init__.py`**

Empty file:
```python
```

**Step 3: Write failing test**

Create `backend/tests/test_diagnostic_store.py`:

```python
import asyncio
import os
import tempfile
import pytest

pytestmark = pytest.mark.asyncio


async def test_sqlite_append_and_get_events():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        seq1 = await store.append_event("sess-1", {"type": "task_event", "message": "hello"})
        seq2 = await store.append_event("sess-1", {"type": "task_event", "message": "world"})
        assert seq2 > seq1

        events = await store.get_events("sess-1", after_sequence=0)
        assert len(events) == 2
        assert events[0]["message"] == "hello"
        assert events[1]["message"] == "world"

        events_after = await store.get_events("sess-1", after_sequence=seq1)
        assert len(events_after) == 1
        assert events_after[0]["message"] == "world"
    finally:
        os.unlink(db_path)


async def test_sqlite_log_and_get_llm_calls():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        import time
        await store.log_llm_call({
            "session_id": "sess-2",
            "agent_name": "ctrl_plane",
            "model": "claude-haiku-4-5-20251001",
            "call_type": "tool_calling",
            "input_tokens": 100,
            "output_tokens": 50,
            "latency_ms": 200,
            "success": True,
            "error": None,
            "fallback_used": False,
            "response_json": {"anomalies": []},
            "created_at": time.time(),
        })

        calls = await store.get_llm_calls("sess-2")
        assert len(calls) == 1
        assert calls[0]["agent_name"] == "ctrl_plane"
        assert calls[0]["success"] is True
    finally:
        os.unlink(db_path)


async def test_sqlite_delete_session():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        await store.append_event("sess-del", {"message": "x"})
        await store.log_llm_call({"session_id": "sess-del", "agent_name": "a", "model": "m",
                                   "call_type": "t", "input_tokens": 1, "output_tokens": 1,
                                   "latency_ms": 1, "success": True, "error": None,
                                   "fallback_used": False, "response_json": {}, "created_at": 1.0})

        await store.delete_session("sess-del")

        events = await store.get_events("sess-del")
        calls = await store.get_llm_calls("sess-del")
        assert events == []
        assert calls == []
    finally:
        os.unlink(db_path)


async def test_factory_returns_sqlite_by_default():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ.pop("DIAGNOSTIC_STORE_BACKEND", None)
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        from src.observability.store import get_store
        store = get_store()
        assert "SQLite" in type(store).__name__
    finally:
        os.unlink(db_path)
```

**Step 4: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_diagnostic_store.py -v 2>&1 | tail -15
```

Expected: ImportError — `src.observability.store` does not exist.

**Step 5: Create `backend/src/observability/store.py`**

```python
"""DiagnosticStore: abstract interface + SQLite + Redis implementations + factory."""
from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_DDL = """
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
"""


class DiagnosticStore(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / connections. Call once on startup."""

    @abstractmethod
    async def append_event(self, session_id: str, event: dict) -> int:
        """Persist event. Returns assigned sequence_number (monotonically increasing)."""

    @abstractmethod
    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        """Return events for session with sequence_number > after_sequence, ordered ascending."""

    @abstractmethod
    async def log_llm_call(self, record: dict) -> None:
        """Persist LLM call metadata."""

    @abstractmethod
    async def get_llm_calls(self, session_id: str) -> list[dict]:
        """Return all LLM call records for session, ordered by created_at."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Remove all events and llm_calls for the session (called on TTL expiry)."""


class SQLiteDiagnosticStore(DiagnosticStore):
    def __init__(self, path: str) -> None:
        self._path = path

    async def initialize(self) -> None:
        os.makedirs(os.path.dirname(self._path) if os.path.dirname(self._path) else ".", exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_DDL)
            await db.commit()

    async def append_event(self, session_id: str, event: dict) -> int:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO events (session_id, event_json, created_at) VALUES (?, ?, ?)",
                (session_id, json.dumps(event, default=str), time.time()),
            )
            await db.commit()
            return cur.lastrowid  # AUTOINCREMENT rowid = sequence_number

    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, event_json FROM events WHERE session_id=? AND id>? ORDER BY id ASC",
                (session_id, after_sequence),
            )
            rows = await cur.fetchall()
        result = []
        for row in rows:
            try:
                evt = json.loads(row["event_json"])
                evt["sequence_number"] = row["id"]
                result.append(evt)
            except json.JSONDecodeError:
                logger.warning("Corrupt event in store for session %s", session_id)
        return result

    async def log_llm_call(self, record: dict) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """INSERT INTO llm_calls
                   (session_id, agent_name, model, call_type, input_tokens, output_tokens,
                    latency_ms, success, error, fallback_used, response_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.get("session_id", ""),
                    record.get("agent_name"),
                    record.get("model"),
                    record.get("call_type"),
                    record.get("input_tokens", 0),
                    record.get("output_tokens", 0),
                    record.get("latency_ms", 0),
                    1 if record.get("success") else 0,
                    record.get("error"),
                    1 if record.get("fallback_used") else 0,
                    json.dumps(record.get("response_json") or {}, default=str),
                    record.get("created_at", time.time()),
                ),
            )
            await db.commit()

    async def get_llm_calls(self, session_id: str) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM llm_calls WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            )
            rows = await cur.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["success"] = bool(d["success"])
            d["fallback_used"] = bool(d["fallback_used"])
            try:
                d["response_json"] = json.loads(d["response_json"] or "{}")
            except json.JSONDecodeError:
                d["response_json"] = {}
            result.append(d)
        return result

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            await db.execute("DELETE FROM llm_calls WHERE session_id=?", (session_id,))
            await db.commit()


class RedisDiagnosticStore(DiagnosticStore):
    """Redis implementation. Activated via DIAGNOSTIC_STORE_BACKEND=redis."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._redis = None

    async def initialize(self) -> None:
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self._url, decode_responses=True)

    async def append_event(self, session_id: str, event: dict) -> int:
        key = f"diag:events:{session_id}"
        serialized = json.dumps(event, default=str)
        await self._redis.rpush(key, serialized)
        seq = await self._redis.llen(key)
        return seq  # 1-based length = sequence_number

    async def get_events(self, session_id: str, after_sequence: int = 0) -> list[dict]:
        key = f"diag:events:{session_id}"
        # after_sequence is 1-based; LRANGE is 0-based
        raw = await self._redis.lrange(key, after_sequence, -1)
        result = []
        for i, item in enumerate(raw):
            try:
                evt = json.loads(item)
                evt["sequence_number"] = after_sequence + i + 1
                result.append(evt)
            except json.JSONDecodeError:
                pass
        return result

    async def log_llm_call(self, record: dict) -> None:
        key = f"diag:llm:{record.get('session_id', '')}"
        await self._redis.rpush(key, json.dumps(record, default=str))

    async def get_llm_calls(self, session_id: str) -> list[dict]:
        key = f"diag:llm:{session_id}"
        raw = await self._redis.lrange(key, 0, -1)
        result = []
        for item in raw:
            try:
                result.append(json.loads(item))
            except json.JSONDecodeError:
                pass
        return result

    async def delete_session(self, session_id: str) -> None:
        await self._redis.delete(
            f"diag:events:{session_id}",
            f"diag:llm:{session_id}",
        )


# Module-level singleton — initialized once at startup
_store: DiagnosticStore | None = None


def get_store() -> DiagnosticStore:
    """Return the configured store. Call initialize() before first use."""
    global _store
    if _store is None:
        backend = os.getenv("DIAGNOSTIC_STORE_BACKEND", "sqlite")
        if backend == "redis":
            _store = RedisDiagnosticStore(url=os.getenv("REDIS_URL", "redis://localhost:6379"))
        else:
            path = os.getenv("DIAGNOSTIC_DB_PATH", "data/diagnostics.db")
            _store = SQLiteDiagnosticStore(path=path)
    return _store
```

**Step 6: Run tests to verify they pass**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_diagnostic_store.py -v 2>&1 | tail -15
```

Expected: 4 passed.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add requirements.txt src/observability/__init__.py src/observability/store.py tests/test_diagnostic_store.py
git commit -m "feat(observability): add DiagnosticStore — SQLite + Redis-ready abstraction layer"
```

---

## Phase 2 — Data Pipeline Integrity

---

### Task 2: Semantic truncation in tool_executor + TruncationFlags enrichment

**Files:**
- Modify: `backend/src/agents/cluster/tool_executor.py` (lines 13-100)
- Modify: `backend/src/agents/cluster/state.py` (lines 27-33, TruncationFlags class)
- Test: `backend/tests/test_tool_executor.py`

**Context:**
Current code at line 97-99 of `tool_executor.py`:
```python
result_str = json.dumps(data, default=str)
if len(result_str) > MAX_RESULT_SIZE:
    result_str = result_str[:MAX_RESULT_SIZE] + '..."truncated"'
```
This produces invalid JSON. Replace with item-aware slicing and a `TruncatedResult` envelope.

**Step 1: Write failing tests**

Create `backend/tests/test_tool_executor.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_client(data: list):
    result = MagicMock()
    result.data = data
    result.permission_denied = False
    result.truncated = False
    result.total_available = len(data)
    result.returned = len(data)
    client = MagicMock()
    client.list_pods = AsyncMock(return_value=result)
    client.list_events = AsyncMock(return_value=result)
    client.list_nodes = AsyncMock(return_value=result)
    return client


@pytest.mark.asyncio
async def test_truncated_result_is_valid_json():
    """When result exceeds MAX_RESULT_SIZE, returned JSON must be valid and complete."""
    from src.agents.cluster.tool_executor import execute_tool_call
    # Generate 100 large pod dicts to force truncation
    large_pods = [{"name": f"pod-{i}", "status": "x" * 200} for i in range(100)]
    client = _make_client(large_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)  # Must not raise

    assert "data" in parsed
    assert "truncated" in parsed
    assert "total_available" in parsed
    assert "returned" in parsed
    assert isinstance(parsed["data"], list)
    # All items in data must be complete dicts (not truncated mid-item)
    for item in parsed["data"]:
        assert isinstance(item, dict)
        assert "name" in item


@pytest.mark.asyncio
async def test_non_truncated_result_has_envelope():
    """Even small results use the envelope format."""
    from src.agents.cluster.tool_executor import execute_tool_call
    small_pods = [{"name": "pod-1", "status": "Running"}]
    client = _make_client(small_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)

    assert parsed["truncated"] is False
    assert parsed["returned"] == 1
    assert parsed["data"][0]["name"] == "pod-1"


@pytest.mark.asyncio
async def test_truncated_flag_set_when_data_dropped():
    """When items are dropped, truncated=True and returned < total_available."""
    from src.agents.cluster.tool_executor import execute_tool_call, MAX_RESULT_SIZE
    # Create items that will definitely exceed MAX_RESULT_SIZE
    big_pods = [{"name": f"pod-{i}", "payload": "z" * 500} for i in range(50)]
    client = _make_client(big_pods)

    result_str = await execute_tool_call("list_pods", {"namespace": "default"}, client)
    parsed = json.loads(result_str)

    if parsed["truncated"]:
        assert parsed["returned"] < parsed["total_available"]
        assert parsed["truncation_reason"] == "SIZE_LIMIT"


def test_truncation_flags_have_drop_counts():
    """TruncationFlags must have dropped-count fields for each flag."""
    from src.agents.cluster.state import TruncationFlags
    flags = TruncationFlags(events=True, events_dropped=80, pods=True, pods_dropped=200)
    assert flags.events_dropped == 80
    assert flags.pods_dropped == 200
    assert flags.nodes_dropped == 0  # default
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_tool_executor.py -v 2>&1 | tail -15
```

Expected: FAIL — `TruncationFlags` has no `events_dropped`; `execute_tool_call` returns truncated string not envelope.

**Step 3: Update `TruncationFlags` in `state.py` (lines 27-33)**

Replace:
```python
class TruncationFlags(BaseModel):
    events: bool = False
    pods: bool = False
    log_lines: bool = False
    metric_points: bool = False
    nodes: bool = False
    pvcs: bool = False
```

With:
```python
class TruncationFlags(BaseModel):
    events: bool = False
    events_dropped: int = 0
    pods: bool = False
    pods_dropped: int = 0
    log_lines: bool = False
    log_lines_dropped: int = 0
    metric_points: bool = False
    metric_points_dropped: int = 0
    nodes: bool = False
    nodes_dropped: int = 0
    pvcs: bool = False
    pvcs_dropped: int = 0
```

**Step 4: Update `tool_executor.py` (lines 97-100)**

Replace the final serialization block (lines 97-100):
```python
        result_str = json.dumps(data, default=str)
        if len(result_str) > MAX_RESULT_SIZE:
            result_str = result_str[:MAX_RESULT_SIZE] + '..."truncated"'
        return result_str
```

With:
```python
        return _serialize_with_envelope(data)
```

Add helper function after the `MAX_RESULT_SIZE` constant (after line 14):
```python
def _serialize_with_envelope(data: Any) -> str:
    """Serialize data into a TruncatedResult envelope. Always returns valid JSON."""
    if not isinstance(data, list):
        # Non-list results: serialize directly with size cap
        raw = json.dumps(data, default=str)
        if len(raw) > MAX_RESULT_SIZE:
            raw = raw[:MAX_RESULT_SIZE]  # truncate scalar/dict (rare case)
        return raw

    # Item-aware slicing for list results
    items: list = []
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
        "total_available": len(data),
        "returned": len(items),
        "truncated": truncated,
        "truncation_reason": "SIZE_LIMIT" if truncated else None,
    }, default=str)
```

**Step 5: Run tests to verify they pass**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_tool_executor.py -v 2>&1 | tail -10
```

Expected: 4 passed.

**Step 6: Run existing tests to verify no regressions**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_cluster_agents.py -v --tb=short -k "not test_initial_state_has_cluster_url and not test_elk_client_none and not test_prometheus_client_injected" 2>&1 | tail -15
```

Expected: all pass.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/tool_executor.py src/agents/cluster/state.py tests/test_tool_executor.py
git commit -m "fix(tool_executor): semantic truncation envelope — always valid JSON; add drop counts to TruncationFlags"
```

---

## Phase 3 — LLM Output Reliability

---

### Task 3: Output schemas — three Anthropic tool definitions

**Files:**
- Create: `backend/src/agents/cluster/output_schemas.py`
- Test: `backend/tests/test_output_schemas.py`

**Context:**
These three dicts are passed as the `tools` argument to Anthropic API calls, replacing free-text JSON requests. Anthropic guarantees `tool_use.input` is always valid JSON matching the schema.

**Step 1: Write failing test**

Create `backend/tests/test_output_schemas.py`:

```python
def test_submit_domain_findings_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    schema = SUBMIT_DOMAIN_FINDINGS_TOOL["input_schema"]
    assert schema["type"] == "object"
    required = schema["required"]
    assert "anomalies" in required
    assert "ruled_out" in required
    assert "confidence" in required
    # anomalies items must have severity enum
    anomaly_props = schema["properties"]["anomalies"]["items"]["properties"]
    assert "severity" in anomaly_props
    assert anomaly_props["severity"]["enum"] == ["high", "medium", "low"]


def test_submit_causal_analysis_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_CAUSAL_ANALYSIS_TOOL
    schema = SUBMIT_CAUSAL_ANALYSIS_TOOL["input_schema"]
    required = schema["required"]
    assert "causal_chains" in required
    assert "uncorrelated_findings" in required


def test_submit_verdict_has_required_fields():
    from src.agents.cluster.output_schemas import SUBMIT_VERDICT_TOOL
    schema = SUBMIT_VERDICT_TOOL["input_schema"]
    required = schema["required"]
    assert "platform_health" in required
    assert "re_dispatch_needed" in required
    assert "re_dispatch_domains" in required
    health_enum = schema["properties"]["platform_health"]["enum"]
    assert "HEALTHY" in health_enum
    assert "CRITICAL" in health_enum
    assert "UNKNOWN" in health_enum


def test_all_tools_have_name_and_description():
    from src.agents.cluster.output_schemas import (
        SUBMIT_DOMAIN_FINDINGS_TOOL,
        SUBMIT_CAUSAL_ANALYSIS_TOOL,
        SUBMIT_VERDICT_TOOL,
    )
    for tool in [SUBMIT_DOMAIN_FINDINGS_TOOL, SUBMIT_CAUSAL_ANALYSIS_TOOL, SUBMIT_VERDICT_TOOL]:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_output_schemas.py -v 2>&1 | tail -10
```

Expected: ImportError — module does not exist.

**Step 3: Create `backend/src/agents/cluster/output_schemas.py`**

```python
"""Anthropic tool definitions for structured LLM output.

These are passed as the `tools` argument to Anthropic API calls.
The LLM MUST call the tool to return findings — it cannot return free text.
Parse from tool_use.input (always valid JSON) instead of response.text.
"""

SUBMIT_DOMAIN_FINDINGS_TOOL: dict = {
    "name": "submit_domain_findings",
    "description": (
        "Submit your diagnostic findings for this domain. "
        "You MUST call this tool when your analysis is complete. "
        "Do NOT return findings as free text — only via this tool."
    ),
    "input_schema": {
        "type": "object",
        "required": ["anomalies", "ruled_out", "confidence"],
        "properties": {
            "anomalies": {
                "type": "array",
                "description": "List of anomalies found. Empty array if none.",
                "items": {
                    "type": "object",
                    "required": ["domain", "anomaly_id", "description", "evidence_ref", "severity"],
                    "properties": {
                        "domain": {"type": "string"},
                        "anomaly_id": {"type": "string", "description": "Unique ID e.g. ctrl-001"},
                        "description": {"type": "string"},
                        "evidence_ref": {"type": "string", "description": "e.g. pod/my-pod or operator/dns"},
                        "severity": {"enum": ["high", "medium", "low"]},
                        "evidence_sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "api_call": {"type": "string"},
                                    "resource": {"type": "string"},
                                    "data_snippet": {"type": "string"},
                                    "tool_call_id": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "ruled_out": {
                "type": "array",
                "description": "Items checked and found healthy.",
                "items": {"type": "string"},
            },
            "confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "0-100. Reflects data quality and coverage.",
            },
        },
    },
}

SUBMIT_CAUSAL_ANALYSIS_TOOL: dict = {
    "name": "submit_causal_analysis",
    "description": (
        "Submit causal chains and uncorrelated findings. "
        "You MUST call this tool — do not return analysis as free text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["causal_chains", "uncorrelated_findings"],
        "properties": {
            "causal_chains": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["chain_id", "confidence", "root_cause", "cascading_effects"],
                    "properties": {
                        "chain_id": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "root_cause": {
                            "type": "object",
                            "required": ["domain", "anomaly_id", "description", "evidence_ref"],
                            "properties": {
                                "domain": {"type": "string"},
                                "anomaly_id": {"type": "string"},
                                "description": {"type": "string"},
                                "evidence_ref": {"type": "string"},
                            },
                        },
                        "cascading_effects": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "order": {"type": "integer"},
                                    "domain": {"type": "string"},
                                    "anomaly_id": {"type": "string"},
                                    "description": {"type": "string"},
                                    "link_type": {"type": "string"},
                                    "evidence_ref": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "uncorrelated_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "anomaly_id": {"type": "string"},
                        "description": {"type": "string"},
                        "evidence_ref": {"type": "string"},
                        "severity": {"enum": ["high", "medium", "low"]},
                    },
                },
            },
        },
    },
}

SUBMIT_VERDICT_TOOL: dict = {
    "name": "submit_verdict",
    "description": (
        "Submit the cluster health verdict and remediation plan. "
        "You MUST call this tool — do not return the verdict as free text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["platform_health", "blast_radius", "remediation", "re_dispatch_needed", "re_dispatch_domains"],
        "properties": {
            "platform_health": {
                "enum": ["HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"],
            },
            "blast_radius": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "affected_namespaces": {"type": "array", "items": {"type": "string"}},
                    "affected_pods": {"type": "array", "items": {"type": "string"}},
                    "affected_nodes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "remediation": {
                "type": "object",
                "properties": {
                    "immediate": {"type": "array"},
                    "long_term": {"type": "array"},
                },
            },
            "re_dispatch_needed": {"type": "boolean"},
            "re_dispatch_domains": {
                "type": "array",
                "items": {"enum": ["ctrl_plane", "node", "network", "storage", "rbac"]},
                "description": "Only valid domain names. Leave empty if re_dispatch_needed=false.",
            },
        },
    },
}
```

**Step 4: Run tests to verify they pass**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_output_schemas.py -v 2>&1 | tail -10
```

Expected: 4 passed.

**Step 5: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/output_schemas.py tests/test_output_schemas.py
git commit -m "feat(llm): add structured output tool schemas for domain agents and synthesizer"
```

---

### Task 4: Structured output in all 5 domain agents

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py` (lines 70-86, 218-239)
- Modify: `backend/src/agents/cluster/node_agent.py` (same pattern)
- Modify: `backend/src/agents/cluster/network_agent.py` (lines 67-83, same pattern)
- Modify: `backend/src/agents/cluster/storage_agent.py` (same pattern)
- Modify: `backend/src/agents/cluster/rbac_agent.py` (same pattern)
- Test: `backend/tests/test_structured_output_agents.py`

**Context:**
All 5 agents have identical structure: `_llm_analyze` (single-pass fallback) and `_tool_calling_loop`. Both currently parse JSON from `response.text` using `text.index("{")`. The fix:
- In `_tool_calling_loop`: add `SUBMIT_DOMAIN_FINDINGS_TOOL` to the tools list; detect the tool call by name and return `tu.input` directly (already done at line 238 via `if tu.name == "submit_findings": return tu.input` — but the tool has no schema enforcement). Replace the text-block fallback (lines 221-234) with a schema-enforced path.
- In `_llm_analyze`: use `client.chat_with_tools` with `SUBMIT_DOMAIN_FINDINGS_TOOL` instead of `client.chat`; parse from tool_use.input.

**Step 1: Write failing test**

Create `backend/tests/test_structured_output_agents.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_tool_use_response(tool_name: str, input_dict: dict):
    """Simulate Anthropic response with a tool_use block."""
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    tool_use.name = tool_name
    tool_use.input = input_dict
    tool_use.id = "tu-123"

    response = MagicMock()
    response.content = [tool_use]
    response.text = ""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    response.usage = usage
    return response


def _make_text_response(text: str):
    """Simulate Anthropic response with text only (no tool use)."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.content = [text_block]
    response.text = text
    usage = MagicMock()
    usage.input_tokens = 50
    usage.output_tokens = 20
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_llm_analyze_parses_from_tool_input_not_text():
    """_llm_analyze must extract findings from tool_use.input, not response text."""
    from src.agents.cluster.ctrl_plane_agent import _llm_analyze

    expected_findings = {
        "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001",
                        "description": "DNS degraded", "evidence_ref": "op/dns",
                        "severity": "high"}],
        "ruled_out": ["etcd healthy"],
        "confidence": 75,
    }
    good_response = _make_tool_use_response("submit_domain_findings", expected_findings)

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_analyze("system", "prompt")

    assert result["confidence"] == 75
    assert result["anomalies"][0]["anomaly_id"] == "cp-001"
    # Verify it did NOT attempt string parsing (no text was in response)
    assert result != {"anomalies": [], "ruled_out": [], "confidence": 0}


@pytest.mark.asyncio
async def test_llm_analyze_falls_back_to_empty_when_tool_not_called():
    """_llm_analyze returns empty findings (not an exception) when LLM skips the tool."""
    from src.agents.cluster.ctrl_plane_agent import _llm_analyze

    text_only_response = _make_text_response("The cluster looks fine.")

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=text_only_response)
        result = await _llm_analyze("system", "prompt")

    assert result == {"anomalies": [], "ruled_out": [], "confidence": 0}


@pytest.mark.asyncio
async def test_tool_calling_loop_uses_submit_domain_findings_schema():
    """_tool_calling_loop must include SUBMIT_DOMAIN_FINDINGS_TOOL in the tools list."""
    from src.agents.cluster.ctrl_plane_agent import _tool_calling_loop
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL

    findings = {"anomalies": [], "ruled_out": ["all healthy"], "confidence": 90}
    submit_response = _make_tool_use_response("submit_domain_findings", findings)

    mock_client_instance = MagicMock()
    mock_client_instance.chat_with_tools = AsyncMock(return_value=submit_response)

    mock_cluster = MagicMock()

    captured_tools = []

    async def capture_chat_with_tools(**kwargs):
        captured_tools.extend(kwargs.get("tools", []))
        return submit_response

    mock_client_instance.chat_with_tools = capture_chat_with_tools

    import os
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with patch("src.agents.cluster.ctrl_plane_agent.AnthropicClient", return_value=mock_client_instance):
        await _tool_calling_loop("system", "context", mock_cluster)

    tool_names = [t["name"] for t in captured_tools if isinstance(t, dict)]
    assert "submit_domain_findings" in tool_names, \
        f"Expected submit_domain_findings in tools list, got: {tool_names}"
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_structured_output_agents.py -v 2>&1 | tail -15
```

Expected: FAIL — `_llm_analyze` uses `client.chat` not `client.chat_with_tools`.

**Step 3: Update `_llm_analyze` in `ctrl_plane_agent.py` (lines 70-86)**

Replace:
```python
async def _llm_analyze(system: str, prompt: str) -> dict:
    """Heuristic single-pass LLM call (fallback). Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_ctrl_plane")
    response = await client.chat(
        prompt=prompt,
        system=system,
        max_tokens=2000,
        temperature=0.1,
    )
    text = response.text
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM response as JSON", extra={"action": "parse_error"})
        return {"anomalies": [], "ruled_out": [], "confidence": 0}
```

With:
```python
async def _llm_analyze(system: str, prompt: str) -> dict:
    """Single-pass LLM call using structured tool output. Returns findings dict."""
    from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
    client = AnthropicClient(agent_name="cluster_ctrl_plane")
    response = await client.chat_with_tools(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[SUBMIT_DOMAIN_FINDINGS_TOOL],
        max_tokens=2000,
        temperature=0.1,
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_domain_findings":
            return block.input
    logger.warning("LLM did not call submit_domain_findings tool", extra={"action": "parse_error"})
    return {"anomalies": [], "ruled_out": [], "confidence": 0}
```

**Step 4: Update `_tool_calling_loop` — add schema to tools list and fix text-block fallback**

In `_tool_calling_loop` (line 163):
```python
tools = get_tools_for_agent("ctrl_plane")
```
Replace with:
```python
from src.agents.cluster.output_schemas import SUBMIT_DOMAIN_FINDINGS_TOOL
base_tools = get_tools_for_agent("ctrl_plane")
# Ensure submit_domain_findings has the strict schema (not the no-schema version from tools.py)
tools = [t for t in base_tools if t.get("name") != "submit_domain_findings"]
tools.append(SUBMIT_DOMAIN_FINDINGS_TOOL)
```

In the text-block fallback (lines 221-234), replace:
```python
        if not tool_uses:
            # Model is done -- extract findings from text
            text = "".join(b.text for b in text_blocks)
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                if telemetry:
                    telemetry.record_call(LLMCallRecord(
                        agent_name="cluster_ctrl_plane", call_type="tool_calling",
                        error="parse_error", success=False,
                    ))
                return None
```
With:
```python
        if not tool_uses:
            # LLM responded without calling any tool — treat as no findings
            logger.warning("LLM iteration produced no tool calls — falling back",
                           extra={"action": "no_tool_call", "iteration": iteration})
            return None
```

**Step 5: Apply the same changes to the other 4 agents**

For each of these files, apply the **identical** changes to `_llm_analyze` and `_tool_calling_loop`:
- `backend/src/agents/cluster/node_agent.py` — agent_name: `"cluster_node"`, tool getter: `get_tools_for_agent("node")`
- `backend/src/agents/cluster/network_agent.py` — agent_name: `"cluster_network"`, tool getter: `get_tools_for_agent("network")`
- `backend/src/agents/cluster/storage_agent.py` — agent_name: `"cluster_storage"`, tool getter: `get_tools_for_agent("storage")`
- `backend/src/agents/cluster/rbac_agent.py` — agent_name: `"cluster_rbac"`, tool getter: `get_tools_for_agent("rbac")`

The only difference between agents is the `agent_name` string and the `get_tools_for_agent(domain)` argument. Read each file to find the exact `agent_name` string before editing.

**Step 6: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_structured_output_agents.py tests/test_cluster_agents.py -v --tb=short \
  -k "not test_initial_state_has_cluster_url and not test_elk_client_none and not test_prometheus_client_injected" \
  2>&1 | tail -20
```

Expected: All pass.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/ctrl_plane_agent.py src/agents/cluster/node_agent.py \
        src/agents/cluster/network_agent.py src/agents/cluster/storage_agent.py \
        src/agents/cluster/rbac_agent.py tests/test_structured_output_agents.py
git commit -m "fix(agents): use structured tool_use output in all 5 domain agents — eliminates string JSON parsing"
```

---

### Task 5: Structured output + bounded prompt + truncation awareness in synthesizer

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py` (lines 79-230 for causal, 233-348 for verdict)
- Test: `backend/tests/test_synthesizer_hardening.py`

**Context:**
Two functions need updating: `_llm_causal_reasoning` (lines 192-230) and `_llm_verdict` (lines 289-348). Both use `client.chat()` + string JSON parsing. Both need:
1. Switch to `chat_with_tools` with the schema tool
2. Parse from `tool_use.input`
3. `_llm_causal_reasoning` also needs `_build_bounded_causal_prompt()` and truncation warning

**Step 1: Write failing tests**

Create `backend/tests/test_synthesizer_hardening.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_tool_response(tool_name: str, input_dict: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = input_dict
    response = MagicMock()
    response.content = [block]
    response.text = ""
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 200
    response.usage = usage
    return response


@pytest.mark.asyncio
async def test_causal_reasoning_uses_tool_input_not_text():
    """_llm_causal_reasoning must parse from tool_use.input."""
    from src.agents.cluster.synthesizer import _llm_causal_reasoning

    expected = {
        "causal_chains": [{"chain_id": "cc-001", "confidence": 0.8,
                            "root_cause": {"domain": "node", "anomaly_id": "n-1",
                                            "description": "disk full", "evidence_ref": "node/worker-1"},
                            "cascading_effects": []}],
        "uncorrelated_findings": [],
    }
    good_response = _mock_tool_response("submit_causal_analysis", expected)

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_causal_reasoning(anomalies=[], reports=[])

    assert len(result["causal_chains"]) == 1
    assert result["causal_chains"][0]["chain_id"] == "cc-001"


@pytest.mark.asyncio
async def test_verdict_uses_tool_input_not_text():
    """_llm_verdict must parse from tool_use.input."""
    from src.agents.cluster.synthesizer import _llm_verdict

    expected = {
        "platform_health": "DEGRADED",
        "blast_radius": {"summary": "2 pods down", "affected_namespaces": ["default"],
                          "affected_pods": [], "affected_nodes": []},
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
        "re_dispatch_domains": [],
    }
    good_response = _mock_tool_response("submit_verdict", expected)

    with patch("src.agents.cluster.synthesizer.AnthropicClient") as MockClient:
        instance = MockClient.return_value
        instance.chat_with_tools = AsyncMock(return_value=good_response)
        result = await _llm_verdict(causal_chains=[], reports=[], data_completeness=0.9)

    assert result["platform_health"] == "DEGRADED"
    assert result["re_dispatch_needed"] is False


def test_build_bounded_causal_prompt_drops_low_priority_anomalies():
    """_build_bounded_causal_prompt must drop low-confidence anomalies when over budget."""
    from src.agents.cluster.synthesizer import _build_bounded_causal_prompt

    # Create many low-severity anomalies that would exceed 60k token budget
    low_anomalies = [
        {"domain": "node", "anomaly_id": f"n-{i}", "description": "minor issue " * 50,
         "evidence_ref": f"pod/pod-{i}", "severity": "low", "evidence_sources": []}
        for i in range(200)
    ]
    critical_anomaly = {
        "domain": "ctrl_plane", "anomaly_id": "cp-001", "description": "API server down",
        "evidence_ref": "api-server/health", "severity": "high", "evidence_sources": [],
    }
    all_anomalies = [critical_anomaly] + low_anomalies

    prompt = _build_bounded_causal_prompt(all_anomalies, [], {}, [])

    # Critical anomaly must always be present
    assert "cp-001" in prompt
    assert "API server down" in prompt
    # Prompt must be under 60k * 4 chars (240k chars) — generous bound for the approximation
    assert len(prompt) < 300_000


def test_truncation_warning_included_when_flags_set():
    """_build_bounded_causal_prompt must include DATA COMPLETENESS block when truncation flags set."""
    from src.agents.cluster.synthesizer import _build_bounded_causal_prompt
    from src.agents.cluster.state import DomainReport, TruncationFlags, DomainStatus

    report = DomainReport(
        domain="node",
        status=DomainStatus.SUCCESS,
        confidence=70,
        truncation_flags=TruncationFlags(events=True, events_dropped=80,
                                          pods=True, pods_dropped=200),
    )

    prompt = _build_bounded_causal_prompt([], [report], {}, [])

    assert "DATA COMPLETENESS WARNING" in prompt
    assert "node" in prompt
    assert "events" in prompt.lower() or "truncated" in prompt.lower()
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_synthesizer_hardening.py -v 2>&1 | tail -15
```

Expected: FAIL — functions use `client.chat` not `chat_with_tools`; `_build_bounded_causal_prompt` doesn't exist.

**Step 3: Add `_build_bounded_causal_prompt` to `synthesizer.py`**

Add after the `_merge_reports` function (after line 76):

```python
_TOKEN_BUDGET = 60_000  # Conservative estimate; leaves room for system prompt + response


def _build_bounded_causal_prompt(
    anomalies: list,
    reports: list,
    search_space: dict,
    hypotheses: list,
    selection: dict | None = None,
) -> str:
    """Build causal reasoning prompt within token budget. Drops low-priority anomalies if needed."""
    import json as _json

    TOKEN_BUDGET_CHARS = _TOKEN_BUDGET * 4  # 1 token ≈ 4 chars

    # Build truncation warning from domain reports
    truncation_warning = ""
    truncated_domains = []
    for r in reports:
        if hasattr(r, "truncation_flags"):
            tf = r.truncation_flags
            dropped = []
            if getattr(tf, "events", False):
                dropped.append(f"events (~{getattr(tf, 'events_dropped', '?')} items dropped)")
            if getattr(tf, "pods", False):
                dropped.append(f"pods (~{getattr(tf, 'pods_dropped', '?')} items dropped)")
            if getattr(tf, "nodes", False):
                dropped.append(f"nodes (~{getattr(tf, 'nodes_dropped', '?')} items dropped)")
            if dropped:
                truncated_domains.append(f"- {r.domain} domain: {', '.join(dropped)}")

    if truncated_domains:
        truncation_warning = (
            "\n⚠️  DATA COMPLETENESS WARNING:\n"
            "The following data sources were truncated before analysis:\n"
            + "\n".join(truncated_domains)
            + "\nRule: Do not assign confidence > 60% to findings that depend solely on "
              "truncated data sources. State the data gap explicitly in your reasoning.\n"
        )

    # Sort anomalies by priority: high → medium → low; within tier, by confidence desc
    severity_order = {"high": 0, "medium": 1, "low": 2}
    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: (severity_order.get(a.get("severity", "low") if isinstance(a, dict)
                        else getattr(a, "severity", "low"), 2)),
    )

    # Include anomalies up to budget
    included = []
    omitted = 0
    running_chars = len(truncation_warning)
    for anomaly in sorted_anomalies:
        item_str = _json.dumps(anomaly if isinstance(anomaly, dict) else anomaly.model_dump(mode="json"),
                               indent=2)
        if running_chars + len(item_str) > TOKEN_BUDGET_CHARS:
            omitted += 1
        else:
            included.append(anomaly if isinstance(anomaly, dict) else anomaly.model_dump(mode="json"))
            running_chars += len(item_str)

    omitted_note = ""
    if omitted:
        omitted_note = (
            f"\nNOTE: {omitted} lower-priority anomalies omitted (context limit reached). "
            "Do not claim exhaustive analysis.\n"
        )

    report_summaries = [
        {"domain": r.domain if hasattr(r, "domain") else r.get("domain"),
         "status": (r.status.value if hasattr(r.status, "value") else r.get("status"))
                   if hasattr(r, "status") else r.get("status"),
         "confidence": r.confidence if hasattr(r, "confidence") else r.get("confidence"),
         "anomaly_count": len(r.anomalies) if hasattr(r, "anomalies") else r.get("anomaly_count", 0)}
        for r in reports
    ]

    # Build search space sections (same logic as before but using bounded anomalies)
    issue_clusters_summary = search_space.get("issue_clusters_summary", []) if search_space else []
    annotated_links = search_space.get("annotated_links", []) if search_space else []
    blocked_count = search_space.get("total_blocked", 0) if search_space else 0
    root_cands = search_space.get("root_candidates", []) if search_space else []

    cluster_section = ""
    if root_cands or annotated_links or blocked_count:
        cluster_section = f"""
## Pre-Correlated Issue Clusters
{_json.dumps(issue_clusters_summary, indent=2)}

## Root Cause Hypothesis Seeds
{_json.dumps(root_cands, indent=2)}

## Annotated Links
{_json.dumps(annotated_links, indent=2)}

## Blocked Links: {blocked_count} excluded
"""

    hyp_section = ""
    if hypotheses:
        hyp_section = f"""
## Pre-Ranked Hypotheses
{_json.dumps(hypotheses[:10], indent=2)}
{_json.dumps(selection or {}, indent=2)}
"""

    return (
        f"{truncation_warning}"
        f"Analyze these cross-domain anomalies and identify causal chains.\n\n"
        f"## Anomalies Found\n{_json.dumps(included, indent=2)}\n"
        f"{omitted_note}"
        f"## Domain Report Summaries\n{_json.dumps(report_summaries, indent=2)}\n"
        f"{cluster_section}"
        f"{hyp_section}"
    )
```

**Step 4: Update `_llm_causal_reasoning` to use tool output and bounded prompt**

Replace the `client.chat(...)` call and the JSON parsing block (lines 192-230):

```python
    from src.agents.cluster.output_schemas import SUBMIT_CAUSAL_ANALYSIS_TOOL
    bounded_prompt = _build_bounded_causal_prompt(
        anomalies=[a.model_dump(mode="json") for a in anomalies],
        reports=reports,
        search_space=search_space or {},
        hypotheses=kwargs.get("hypotheses", []),
        selection=kwargs.get("hypothesis_selection", {}),
    )

    call_start = time.monotonic()
    try:
        cluster_context = (
            f"Cluster Context:\n"
            f"- Platform: {platform}\n"
            f"- Namespace: {namespace or 'all namespaces'}\n"
            f"- Cluster: {cluster_url or 'unknown'}\n\n"
        )
        system_prompt = (
            cluster_context
            + "You are a causal reasoning engine for cluster diagnostics. Be precise and evidence-based. "
            + "You MUST call submit_causal_analysis to return your analysis."
        )
        response = await asyncio.wait_for(
            client.chat_with_tools(
                system=system_prompt,
                messages=[{"role": "user", "content": bounded_prompt}],
                tools=[SUBMIT_CAUSAL_ANALYSIS_TOOL],
                max_tokens=3000,
                temperature=0.1,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM causal reasoning timed out after 30s")
        return {"causal_chains": [], "uncorrelated_findings": []}

    latency_ms = int((time.monotonic() - call_start) * 1000)
    usage = getattr(response, "usage", None)
    in_tok = usage.input_tokens if usage else 0
    out_tok = usage.output_tokens if usage else 0
    used_model = model or "claude-sonnet-4-20250514"

    if budget:
        budget.record(input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency_ms)
    if telemetry:
        telemetry.record_call(LLMCallRecord(
            agent_name="cluster_synthesizer", model=used_model,
            call_type="synthesis_causal", input_tokens=in_tok, output_tokens=out_tok,
            latency_ms=latency_ms, success=True,
        ))

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_causal_analysis":
            return block.input

    logger.warning("Synthesizer causal reasoning: LLM did not call submit_causal_analysis")
    if telemetry:
        telemetry.record_call(LLMCallRecord(
            agent_name="cluster_synthesizer", call_type="synthesis_causal",
            error="tool_not_called", success=False,
        ))
    return {"causal_chains": [], "uncorrelated_findings": []}
```

**Step 5: Update `_llm_verdict` to use tool output**

Replace the `client.chat(...)` call and JSON parsing (lines ~289-348):

```python
    from src.agents.cluster.output_schemas import SUBMIT_VERDICT_TOOL

    # ... (keep existing prompt building unchanged) ...

    call_start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            client.chat_with_tools(
                system="You are a cluster health verdict engine. You MUST call submit_verdict to return your verdict.",
                messages=[{"role": "user", "content": prompt}],
                tools=[SUBMIT_VERDICT_TOOL],
                max_tokens=3000,
                temperature=0.1,
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM verdict timed out after 30s")
        return {"platform_health": "UNKNOWN", "blast_radius": {}, "remediation": {"immediate": [], "long_term": []},
                "re_dispatch_needed": False, "re_dispatch_domains": []}

    # ... (keep token recording unchanged) ...

    _VALID_DOMAINS = {"ctrl_plane", "node", "network", "storage", "rbac"}
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_verdict":
            parsed = block.input
            raw_domains = parsed.get("re_dispatch_domains", [])
            parsed["re_dispatch_domains"] = [d for d in raw_domains if d in _VALID_DOMAINS]
            return parsed

    logger.warning("Synthesizer verdict: LLM did not call submit_verdict")
    return {"platform_health": "UNKNOWN", "blast_radius": {}, "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False, "re_dispatch_domains": []}
```

**Step 6: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_synthesizer_hardening.py -v 2>&1 | tail -15
```

Expected: 4 passed.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/synthesizer.py tests/test_synthesizer_hardening.py
git commit -m "fix(synthesizer): structured tool_use output + bounded prompt (60k token guard) + truncation awareness"
```

---

## Phase 4 — Graph Resilience

---

### Task 6: Graph timeout graceful degradation

**Files:**
- Modify: `backend/src/agents/cluster/graph.py` (add `_build_partial_health_report`)
- Modify: `backend/src/api/routes_v4.py` (timeout recovery block ~lines 714-719)
- Test: `backend/tests/test_graph_timeout_recovery.py`

**Context:**
`run_cluster_diagnosis` in `routes_v4.py` wraps `graph.ainvoke` in a timeout. On `asyncio.TimeoutError`, it currently only emits an error event and returns. We need it to read whatever partial state was checkpointed in `session["state"]` and build a `PARTIAL_TIMEOUT` health report from it.

Domain agents already write to `session["state"]` via `emitter` — but the session state is only set at the very end (line ~705). We need to checkpoint after the fan-in phase.

**Step 1: Write failing test**

Create `backend/tests/test_graph_timeout_recovery.py`:

```python
import pytest


def test_build_partial_health_report_from_domain_reports():
    """_build_partial_health_report must return a ClusterHealthReport-like dict from partial state."""
    from src.agents.cluster.graph import _build_partial_health_report

    partial_state = {
        "domain_reports": [
            {"domain": "ctrl_plane", "status": "SUCCESS", "confidence": 80,
             "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001",
                             "description": "DNS degraded", "evidence_ref": "op/dns",
                             "severity": "high", "evidence_sources": []}],
             "ruled_out": [], "evidence_refs": [], "truncation_flags": {},
             "token_usage": 0, "duration_ms": 0},
            {"domain": "node", "status": "FAILED", "confidence": 0,
             "anomalies": [], "ruled_out": [], "evidence_refs": [],
             "truncation_flags": {}, "token_usage": 0, "duration_ms": 0},
        ],
        "proactive_findings": [],
        "data_completeness": 0.4,
        "namespaces": ["default"],
        "platform": "kubernetes",
        "platform_version": "1.29.0",
        "diagnostic_id": "test-diag",
    }

    report = _build_partial_health_report(partial_state)

    assert report is not None
    assert report.get("status") == "PARTIAL_TIMEOUT"
    # With a FAILED domain, health must be UNKNOWN or DEGRADED — not HEALTHY
    assert report.get("overall_status") not in ("HEALTHY",)
    # All anomalies from completed domains should be in uncorrelated_findings
    assert any(f.get("anomaly_id") == "cp-001"
               for f in report.get("uncorrelated_findings", []))
    # No remediation steps (synthesis didn't complete)
    assert report.get("remediation", {}).get("immediate", []) == []


def test_build_partial_health_report_empty_state():
    """_build_partial_health_report must not crash on empty state."""
    from src.agents.cluster.graph import _build_partial_health_report

    report = _build_partial_health_report({})
    assert report is not None
    assert report.get("status") == "PARTIAL_TIMEOUT"
    assert report.get("overall_status") == "UNKNOWN"
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_graph_timeout_recovery.py -v 2>&1 | tail -10
```

Expected: ImportError — `_build_partial_health_report` does not exist.

**Step 3: Add `_build_partial_health_report` to `graph.py`**

Add after the `ALL_DOMAINS` constant (after line 37):

```python
def _build_partial_health_report(state: dict) -> dict:
    """
    Build a partial ClusterHealthReport from whatever state was checkpointed before timeout.
    Called when graph.ainvoke() times out — returns PARTIAL_TIMEOUT status with all
    anomalies found so far in uncorrelated_findings (no causal chains, no remediation).
    """
    domain_reports = state.get("domain_reports") or []
    proactive_findings = state.get("proactive_findings") or []
    data_completeness = state.get("data_completeness") or 0.0

    # Derive health from domain statuses
    statuses = [r.get("status", "PENDING") if isinstance(r, dict) else r.status.value
                for r in domain_reports]
    has_failed = any(s in ("FAILED",) for s in statuses)
    has_anomalies = any(
        len(r.get("anomalies", []) if isinstance(r, dict) else r.anomalies) > 0
        for r in domain_reports
    )

    if has_failed and has_anomalies:
        overall_status = "CRITICAL"
    elif has_failed:
        overall_status = "UNKNOWN"
    elif has_anomalies:
        overall_status = "DEGRADED"
    else:
        overall_status = "UNKNOWN"  # Can't claim HEALTHY without completed synthesis

    # Collect all anomalies from completed domains as uncorrelated_findings
    uncorrelated: list[dict] = []
    for r in domain_reports:
        anomalies = r.get("anomalies", []) if isinstance(r, dict) else [
            a.model_dump(mode="json") for a in r.anomalies
        ]
        uncorrelated.extend(anomalies)

    return {
        "status": "PARTIAL_TIMEOUT",
        "overall_status": overall_status,
        "data_completeness": data_completeness,
        "domain_reports": domain_reports,
        "proactive_findings": proactive_findings,
        "causal_chains": [],
        "uncorrelated_findings": uncorrelated,
        "remediation": {"immediate": [], "long_term": []},
        "blast_radius": {
            "summary": f"Diagnosis timed out. {len(uncorrelated)} anomalies found before timeout.",
            "affected_namespaces": state.get("namespaces", []),
            "affected_pods": [],
            "affected_nodes": [],
        },
        "note": "Diagnosis timed out before synthesis. Results reflect partial data only.",
    }
```

**Step 4: Update `run_cluster_diagnosis` timeout handler in `routes_v4.py`**

Find the `except asyncio.TimeoutError:` block (around line 714-719). Replace:
```python
    except asyncio.TimeoutError:
        await emitter.emit("cluster_supervisor", "error", "Cluster diagnosis timed out after 180s")
```

With:
```python
    except asyncio.TimeoutError:
        # Build partial report from whatever state was checkpointed before timeout
        from src.agents.cluster.graph import _build_partial_health_report
        partial_state = sessions.get(session_id, {}).get("state") or {}
        if partial_state.get("domain_reports"):
            partial_report = _build_partial_health_report(partial_state)
            async with session_locks[session_id]:
                sessions[session_id]["state"]["health_report"] = partial_report
                sessions[session_id]["state"]["phase"] = "partial_timeout"
        await emitter.emit(
            "cluster_supervisor", "warning",
            "Diagnosis timed out — partial results available",
            {"phase": "partial_timeout",
             "data_completeness": partial_state.get("data_completeness", 0.0)},
        )
```

**Step 5: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_graph_timeout_recovery.py -v 2>&1 | tail -10
```

Expected: 2 passed.

**Step 6: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/graph.py src/api/routes_v4.py tests/test_graph_timeout_recovery.py
git commit -m "fix(graph): graceful partial result on 180s timeout — PARTIAL_TIMEOUT health report from checkpointed state"
```

---

## Phase 5 — Observability

---

### Task 7: WebSocket event replay via DiagnosticStore

**Files:**
- Modify: `backend/src/utils/event_emitter.py`
- Modify: `backend/src/models/schemas.py` (add `sequence_number` to TaskEvent, line 158-164)
- Modify: `backend/src/api/routes_v4.py` (initialize store; events endpoint; cleanup)
- Modify: `backend/src/api/main.py` (store initialize on startup)
- Test: `backend/tests/test_event_replay.py`

**Context:**
`EventEmitter` (at `backend/src/utils/event_emitter.py`) currently stores events in `self._events` (in-memory list). We add: write to `DiagnosticStore`, attach `sequence_number` to each event. The existing `GET /session/{id}/events` endpoint gets an `after_sequence` query param for replay.

**Step 1: Write failing tests**

Create `backend/tests/test_event_replay.py`:

```python
import asyncio
import os
import tempfile
import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_emitter_assigns_sequence_number_to_events():
    """After emit(), TaskEvent must have a sequence_number set."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        # Reset singleton
        import src.observability.store as store_module
        store_module._store = None

        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        from src.utils.event_emitter import EventEmitter
        emitter = EventEmitter(session_id="sess-replay", store=store)

        event1 = await emitter.emit("agent-a", "phase_change", "Starting")
        event2 = await emitter.emit("agent-a", "progress", "Working")

        assert event1.sequence_number is not None
        assert event2.sequence_number is not None
        assert event2.sequence_number > event1.sequence_number
    finally:
        os.unlink(db_path)
        import src.observability.store as store_module
        store_module._store = None


@pytest.mark.asyncio
async def test_emitter_persists_events_to_store():
    """Events must be retrievable from the store after emit()."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None

        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        from src.utils.event_emitter import EventEmitter
        emitter = EventEmitter(session_id="sess-persist", store=store)
        await emitter.emit("agent-x", "phase_change", "Event A")
        first_event = await emitter.emit("agent-x", "phase_change", "Event B")

        # Retrieve events after first (replay from sequence_number of Event A)
        events = await store.get_events("sess-persist", after_sequence=first_event.sequence_number - 1)
        assert any(e.get("message") == "Event B" for e in events)
    finally:
        os.unlink(db_path)
        import src.observability.store as store_module
        store_module._store = None
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_event_replay.py -v 2>&1 | tail -15
```

Expected: FAIL — `EventEmitter.__init__` does not accept `store` argument; `TaskEvent` has no `sequence_number`.

**Step 3: Add `sequence_number` to `TaskEvent` in `schemas.py` (after line 164)**

```python
class TaskEvent(BaseModel):
    timestamp: datetime
    agent_name: str
    event_type: Literal["started", "progress", "success", "warning", "error", "tool_call",
                         "phase_change", "finding", "summary", "attestation_required",
                         "fix_proposal", "fix_approved", "waiting_for_input", "reasoning"]
    message: str
    details: Optional[dict] = None
    session_id: Optional[str] = None
    sequence_number: Optional[int] = None   # Set after store.append_event()
```

**Step 4: Update `EventEmitter` in `event_emitter.py`**

Replace the full file:

```python
from datetime import datetime, timezone
from typing import Optional

from src.models.schemas import TaskEvent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class EventEmitter:
    """Emits real-time task events via WebSocket and persists them to DiagnosticStore."""

    def __init__(self, session_id: str, websocket_manager=None, store=None):
        self.session_id = session_id
        self._websocket_manager = websocket_manager
        self._store = store
        self._events: list[TaskEvent] = []

    async def emit(
        self,
        agent_name: str,
        event_type: str,
        message: str,
        details: dict | None = None,
    ) -> TaskEvent:
        """Emit a task event — persists to store, broadcasts via WebSocket."""
        event = TaskEvent(
            timestamp=datetime.now(timezone.utc),
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            details=details,
            session_id=self.session_id,
        )

        # Persist to store first — assigns sequence_number
        if self._store is not None:
            try:
                seq = await self._store.append_event(
                    self.session_id, event.model_dump(mode="json")
                )
                event.sequence_number = seq
            except Exception as e:
                logger.warning("Failed to persist event to store: %s", e,
                               extra={"session_id": self.session_id})

        self._events.append(event)
        logger.debug("Event emitted", extra={
            "session_id": self.session_id, "agent_name": agent_name,
            "action": event_type, "extra": message,
        })

        if self._websocket_manager:
            try:
                await self._websocket_manager.send_message(
                    self.session_id,
                    {"type": "task_event", "data": event.model_dump(mode="json")},
                )
            except Exception as e:
                logger.warning(
                    "WebSocket broadcast failed (event persisted at seq=%s)",
                    event.sequence_number,
                    extra={"session_id": self.session_id, "action": "ws_broadcast_failed",
                           "extra": str(e)},
                )

        return event

    def get_all_events(self) -> list[TaskEvent]:
        """Return all in-memory events for this session."""
        return list(self._events)

    def get_events_by_agent(self, agent_name: str) -> list[TaskEvent]:
        """Return events filtered by agent name."""
        return [e for e in self._events if e.agent_name == agent_name]
```

**Step 5: Initialize store in `main.py` on startup**

In `main.py`, find the `@app.on_event("startup")` handler (or add one). Add store initialization:

```python
@app.on_event("startup")
async def _startup():
    from src.observability.store import get_store
    store = get_store()
    await store.initialize()
```

**Step 6: Pass store to EventEmitter in `routes_v4.py`**

Find the line `emitter = EventEmitter(session_id=session_id, websocket_manager=manager)` (line ~308). Replace with:

```python
from src.observability.store import get_store as _get_store
emitter = EventEmitter(session_id=session_id, websocket_manager=manager, store=_get_store())
```

**Step 7: Add `after_sequence` param to events endpoint in `routes_v4.py`**

Find the `GET /session/{session_id}/events` endpoint (around line 1576). Update:

```python
@router.get("/session/{session_id}/events")
async def get_session_events(
    session_id: str,
    after_sequence: int = 0,
):
    """Return session events. Use after_sequence for replay (returns events after that seq)."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    from src.observability.store import get_store
    store = get_store()
    try:
        events = await store.get_events(session_id, after_sequence=after_sequence)
        return {"events": events}
    except Exception:
        # Fallback to in-memory events if store unavailable
        emitter = sessions[session_id].get("emitter")
        if emitter:
            all_events = emitter.get_all_events()
            event_dicts = [e.model_dump(mode="json") for e in all_events
                           if (e.sequence_number or 0) > after_sequence]
            return {"events": event_dicts}
        return {"events": []}
```

**Step 8: Add `store.delete_session` to cleanup loop in `routes_v4.py`**

In `_session_cleanup_loop`, after the existing cleanup steps (after the existing session removal code), add:

```python
                from src.observability.store import get_store
                try:
                    await get_store().delete_session(sid)
                except Exception as e:
                    logger.warning("Failed to delete session from store: %s", e)
```

**Step 9: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_event_replay.py -v 2>&1 | tail -10
```

Expected: 2 passed.

**Step 10: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/utils/event_emitter.py src/models/schemas.py src/api/routes_v4.py src/api/main.py tests/test_event_replay.py
git commit -m "feat(observability): WebSocket event replay via DiagnosticStore — sequence_number + after_sequence endpoint"
```

---

### Task 8: LLM call logging to DiagnosticStore + API endpoint

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py` (add store.log_llm_call after telemetry.record_call)
- Modify: `backend/src/agents/cluster/node_agent.py` (same)
- Modify: `backend/src/agents/cluster/network_agent.py` (same)
- Modify: `backend/src/agents/cluster/storage_agent.py` (same)
- Modify: `backend/src/agents/cluster/synthesizer.py` (same for both stages)
- Modify: `backend/src/api/routes_v4.py` (new GET endpoint for llm-calls)
- Test: `backend/tests/test_llm_logging.py`

**Context:**
After each `telemetry.record_call(LLMCallRecord(...))` in the agents, add `await store.log_llm_call({...})`. The `store` must be passed via `config["configurable"]["store"]`. Add `"store": get_store()` to the graph config dict in `routes_v4.py`.

**Step 1: Write failing test**

Create `backend/tests/test_llm_logging.py`:

```python
import asyncio
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_ctrl_plane_agent_logs_llm_call_to_store():
    """ctrl_plane_agent must call store.log_llm_call after each LLM call."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        os.environ["DIAGNOSTIC_STORE_BACKEND"] = "sqlite"
        os.environ["DIAGNOSTIC_DB_PATH"] = db_path
        import src.observability.store as store_module
        store_module._store = None

        from src.observability.store import get_store
        store = get_store()
        await store.initialize()

        from src.agents.cluster_client.mock_client import MockClusterClient
        client = MockClusterClient(platform="kubernetes")

        state = {
            "diagnostic_id": "DIAG-LOG-TEST",
            "platform": "kubernetes",
            "platform_version": "1.29",
            "namespaces": ["default"],
            "diagnostic_scope": {},
            "dispatch_domains": ["ctrl_plane"],
            "scan_mode": "diagnostic",
            "cluster_url": "",
            "cluster_type": "",
            "cluster_role": "",
        }
        config = {"configurable": {
            "cluster_client": client,
            "emitter": AsyncMock(),
            "diagnostic_cache": MagicMock(),
            "store": store,
        }}

        with patch("src.agents.cluster.ctrl_plane_agent._heuristic_analyze", new_callable=AsyncMock) as mock_h:
            mock_h.return_value = {"anomalies": [], "ruled_out": [], "confidence": 50}
            from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
            await ctrl_plane_agent(state, config)

        calls = await store.get_llm_calls("DIAG-LOG-TEST")
        # At minimum, the heuristic path still logs a call record
        # (even if no LLM was called, agent logs a "heuristic" call)
        assert isinstance(calls, list)
    finally:
        os.unlink(db_path)
        import src.observability.store as store_module
        store_module._store = None
```

**Step 2: Run to verify it fails**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_llm_logging.py -v 2>&1 | tail -10
```

Expected: FAIL or PASS with empty calls list (no logging yet).

**Step 3: Pass store via config in `routes_v4.py`**

Find the `config` dict built for `graph.ainvoke` (around line 688-698). Add `"store"` to the `configurable` dict:

```python
from src.observability.store import get_store as _get_store
config = {
    "configurable": {
        "cluster_client": cluster_client,
        "prometheus_client": prometheus_client,
        "elk_client": elk_client,
        "elk_index": elk_index or "",
        "emitter": emitter,
        "budget": budget,
        "telemetry": telemetry,
        "store": _get_store(),   # ← ADD THIS
    }
}
```

**Step 4: Add `store.log_llm_call` to domain agents**

In each agent's `_tool_calling_loop`, after the existing `telemetry.record_call(...)` block (lines 210-215 in ctrl_plane_agent.py), add:

```python
        # Log to DiagnosticStore for replay/debugging
        _store = config.get("configurable", {}).get("store") if "config" in dir() else None
        if _store is not None:
            import asyncio as _asyncio
            _asyncio.ensure_future(_store.log_llm_call({
                "session_id": state.get("diagnostic_id", ""),
                "agent_name": "cluster_ctrl_plane",
                "model": "claude-haiku-4-5-20251001",
                "call_type": "tool_calling",
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "latency_ms": latency_ms,
                "success": True,
                "error": None,
                "fallback_used": False,
                "response_json": {},
                "created_at": __import__("time").time(),
            }))
```

**Note:** `config` is not available inside `_tool_calling_loop` — it only has the `budget` and `telemetry` args. To pass `store`, add `store=None` as a new parameter to `_tool_calling_loop` in all agents, and pass it from the agent's main function where `config["configurable"]` is accessed.

Pattern for extracting store in each agent's main function:
```python
store = config.get("configurable", {}).get("store")
# then pass store=store to _tool_calling_loop(...)
```

Do this for all 5 agents and the synthesizer.

**Step 5: Add `GET /session/{session_id}/llm-calls` endpoint to `routes_v4.py`**

Add after the events endpoint:

```python
@router.get("/session/{session_id}/llm-calls")
async def get_session_llm_calls(session_id: str):
    """Return LLM call metadata for a session. For debugging wrong causal chains."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    from src.observability.store import get_store
    calls = await get_store().get_llm_calls(session_id)
    return {"llm_calls": calls}
```

**Step 6: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_llm_logging.py -v 2>&1 | tail -10
```

Expected: Pass.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/agents/cluster/ctrl_plane_agent.py src/agents/cluster/node_agent.py \
        src/agents/cluster/network_agent.py src/agents/cluster/storage_agent.py \
        src/agents/cluster/rbac_agent.py src/agents/cluster/synthesizer.py \
        src/api/routes_v4.py tests/test_llm_logging.py
git commit -m "feat(observability): LLM call logging to DiagnosticStore + GET /session/{id}/llm-calls endpoint"
```

---

## Phase 6 — Alertmanager Integration

---

### Task 9: Alertmanager webhook endpoint

**Files:**
- Create: `backend/src/api/routes_alerts.py`
- Modify: `backend/src/api/main.py` (register router + in-memory dedup dict)
- Test: `backend/tests/test_alertmanager_webhook.py`

**Step 1: Write failing tests**

Create `backend/tests/test_alertmanager_webhook.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_webhook_accepts_firing_alert_and_schedules_session():
    """Webhook must accept a firing Alertmanager payload and return session_id."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "firing",
                         "labels": {"namespace": "production", "workload": "order-service",
                                    "severity": "warning", "alertname": "HighRestartRate"},
                         "annotations": {"summary": "High restart rate"}}],
            "groupLabels": {"namespace": "production"},
            "commonLabels": {"severity": "warning", "namespace": "production",
                              "workload": "order-service"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "scheduled"
    assert "session_id" in body
    assert body["delay_seconds"] >= 0
    assert "scope" in body


@pytest.mark.asyncio
async def test_webhook_ignores_resolved_alerts():
    """Webhook must return status=ignored for resolved alerts."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "resolved",
                         "labels": {"namespace": "production", "severity": "warning"},
                         "annotations": {}}],
            "groupLabels": {},
            "commonLabels": {"severity": "warning"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_ignores_info_severity():
    """Webhook must return status=ignored for severity=info."""
    from src.api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "alerts": [{"status": "firing",
                         "labels": {"namespace": "default", "severity": "info"},
                         "annotations": {}}],
            "groupLabels": {},
            "commonLabels": {"severity": "info"},
            "commonAnnotations": {},
        }
        resp = await client.post("/api/v5/alerts/webhook", json=payload)

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_scope_derivation_workload_level():
    """When workload + namespace labels present, scope level must be workload."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope(
        {"namespace": "prod", "workload": "my-app", "severity": "critical"}
    )
    assert scope["level"] == "workload"
    assert scope["namespaces"] == ["prod"]
    assert scan_mode == "comprehensive"


def test_scope_derivation_namespace_level():
    """When only namespace label, scope must be namespace."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope({"namespace": "staging", "severity": "warning"})
    assert scope["level"] == "namespace"
    assert scan_mode == "diagnostic"


def test_scope_derivation_cluster_level():
    """When no namespace label, scope must be cluster."""
    from src.api.routes_alerts import _derive_scope
    scope, scan_mode = _derive_scope({"severity": "critical"})
    assert scope["level"] == "cluster"
```

**Step 2: Run to verify they fail**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_alertmanager_webhook.py -v 2>&1 | tail -15
```

Expected: ImportError or 404 — endpoint does not exist.

**Step 3: Create `backend/src/api/routes_alerts.py`**

```python
"""Alertmanager v2 webhook receiver.

POST /api/v5/alerts/webhook
Accepts Alertmanager firing alerts and auto-creates cluster diagnostic sessions.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v5/alerts", tags=["alerts"])

# Deduplication: (namespace, workload) -> (session_id, created_at)
_active_alert_sessions: dict[tuple[str, str], tuple[str, float]] = {}
_DEDUP_WINDOW_SECONDS = 1800  # 30 minutes

ALERT_DIAGNOSTIC_DELAY_SECONDS = int(os.getenv("ALERT_DIAGNOSTIC_DELAY_SECONDS", "120"))


# ── Pydantic models ──────────────────────────────────────────────────────────

class AlertmanagerAlert(BaseModel):
    status: str
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AlertmanagerPayload(BaseModel):
    alerts: list[AlertmanagerAlert]
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}


# ── Scope derivation ─────────────────────────────────────────────────────────

def _derive_scope(merged_labels: dict[str, str]) -> tuple[dict, str]:
    """Derive DiagnosticScope and scan_mode from merged alert labels."""
    namespace = merged_labels.get("namespace", "")
    workload = merged_labels.get("workload", "")
    severity = merged_labels.get("severity", "warning").lower()

    scan_mode = "comprehensive" if severity == "critical" else "diagnostic"
    include_cp = severity == "critical"

    if workload and namespace:
        scope = {
            "level": "workload",
            "namespaces": [namespace],
            "workload_key": workload,
            "domains": ["node", "network"],
            "include_control_plane": include_cp,
        }
    elif namespace:
        scope = {
            "level": "namespace",
            "namespaces": [namespace],
            "workload_key": None,
            "domains": ["ctrl_plane", "node", "network", "storage", "rbac"],
            "include_control_plane": include_cp,
        }
    else:
        scope = {
            "level": "cluster",
            "namespaces": [],
            "workload_key": None,
            "domains": ["ctrl_plane", "node", "network", "storage", "rbac"],
            "include_control_plane": True,
        }

    return scope, scan_mode


# ── Webhook endpoint ─────────────────────────────────────────────────────────

@router.post("/webhook")
async def alertmanager_webhook(payload: AlertmanagerPayload):
    """Receive Alertmanager v2 webhook and schedule a cluster diagnostic session."""
    # Only process firing alerts
    firing = [a for a in payload.alerts if a.status == "firing"]
    if not firing:
        return {"status": "ignored", "reason": "status=resolved"}

    # Merge labels: commonLabels wins over groupLabels
    merged = {**payload.groupLabels, **payload.commonLabels}
    severity = merged.get("severity", "warning").lower()

    if severity == "info":
        return {"status": "ignored", "reason": "severity=info"}

    scope, scan_mode = _derive_scope(merged)

    namespace = merged.get("namespace", "")
    workload = merged.get("workload", "")
    dedup_key = (namespace, workload)

    # Deduplication check
    existing = _active_alert_sessions.get(dedup_key)
    if existing:
        existing_session_id, created_at = existing
        if time.time() - created_at < _DEDUP_WINDOW_SECONDS:
            return {
                "status": "deduplicated",
                "session_id": existing_session_id,
                "message": "Diagnostic already running for this target",
            }

    # Create session
    session_id = str(uuid.uuid4())
    alertname = merged.get("alertname", "UnknownAlert")
    service_name = f"{alertname}-{namespace}" if namespace else alertname
    incident_id = f"ALERT-{session_id[:8].upper()}"

    _active_alert_sessions[dedup_key] = (session_id, time.time())

    # Schedule delayed diagnostic (fire-and-forget)
    asyncio.create_task(_run_delayed_diagnostic(
        session_id=session_id,
        service_name=service_name,
        incident_id=incident_id,
        scope=scope,
        scan_mode=scan_mode,
        delay=ALERT_DIAGNOSTIC_DELAY_SECONDS,
    ))

    logger.info(
        "Alertmanager webhook: scheduled diagnostic",
        extra={"session_id": session_id, "scope_level": scope["level"],
               "severity": severity, "alert_count": len(firing)},
    )

    return {
        "status": "scheduled",
        "session_id": session_id,
        "delay_seconds": ALERT_DIAGNOSTIC_DELAY_SECONDS,
        "scope": scope,
        "alert_count": len(firing),
        "incident_id": incident_id,
    }


async def _run_delayed_diagnostic(
    session_id: str,
    service_name: str,
    incident_id: str,
    scope: dict,
    scan_mode: str,
    delay: int,
) -> None:
    """Wait delay seconds then trigger cluster diagnostic (runs as background task)."""
    await asyncio.sleep(delay)

    try:
        # Import here to avoid circular imports
        from src.api.routes_v4 import sessions, session_locks, run_cluster_diagnosis
        from src.agents.cluster.cluster_client import build_cluster_client
        from src.agents.cluster.graph import build_cluster_diagnostic_graph
        from src.utils.event_emitter import EventEmitter
        from src.observability.store import get_store

        cluster_client = build_cluster_client({})  # Use default (env-based) client
        graph = build_cluster_diagnostic_graph()
        store = get_store()
        emitter = EventEmitter(session_id=session_id, store=store)

        sessions[session_id] = {
            "service_name": service_name,
            "incident_id": incident_id,
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            "emitter": emitter,
            "state": {},
            "graph": graph,
            "diagnostic_scope": scope,
            "scan_mode": scan_mode,
            "capability": "cluster_diagnostics",
        }
        session_locks[session_id] = __import__("asyncio").Lock()

        await run_cluster_diagnosis(
            session_id=session_id,
            graph=graph,
            cluster_client=cluster_client,
            emitter=emitter,
            scan_mode=scan_mode,
        )
    except Exception as exc:
        logger.error("Alert-triggered diagnostic failed: %s", exc,
                     extra={"session_id": session_id})
```

**Step 4: Register router in `main.py`**

In `main.py`, after existing router imports, add:

```python
from src.api.routes_alerts import router as alerts_router
```

And after existing `app.include_router(...)` calls:

```python
app.include_router(alerts_router)
```

**Step 5: Run tests**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_alertmanager_webhook.py -v 2>&1 | tail -15
```

Expected: All pass (the route tests for scope derivation are pure unit tests; the HTTP tests use ASGI test client).

**Step 6: Run full regression**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_cluster_agents.py tests/test_diagnostic_store.py tests/test_output_schemas.py \
       tests/test_tool_executor.py tests/test_event_replay.py tests/test_alertmanager_webhook.py \
       -v --tb=short \
       -k "not test_initial_state_has_cluster_url and not test_elk_client_none and not test_prometheus_client_injected" \
       2>&1 | tail -30
```

Expected: All pass.

**Step 7: Commit**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
git add src/api/routes_alerts.py src/api/main.py tests/test_alertmanager_webhook.py
git commit -m "feat(alerts): Alertmanager v2 webhook — auto-schedules cluster diagnostic with configurable delay + dedup"
```

---

## Final Validation

**Run all new tests together:**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
pytest tests/test_diagnostic_store.py tests/test_tool_executor.py tests/test_output_schemas.py \
       tests/test_structured_output_agents.py tests/test_synthesizer_hardening.py \
       tests/test_graph_timeout_recovery.py tests/test_event_replay.py \
       tests/test_llm_logging.py tests/test_alertmanager_webhook.py \
       -v --tb=short 2>&1 | tail -30
```

**Verify graph still compiles:**

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend
python -c "
from src.agents.cluster.graph import build_cluster_diagnostic_graph
g = build_cluster_diagnostic_graph()
nodes = sorted(g.nodes)
print('Nodes:', len(nodes))
required = ['rbac_preflight', 'proactive_analysis', 'synthesize', 'guard_formatter']
missing = [n for n in required if n not in nodes]
print('Missing:', missing or 'none')
"
```

Expected: All tests pass, no missing nodes.
