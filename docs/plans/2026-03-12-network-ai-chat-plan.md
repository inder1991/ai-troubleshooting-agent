# Network AI Chat — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add LLM-powered contextual chat to all network views (Observatory, Topology Editor, IPAM, Device Monitoring, etc.) via a three-layer Gateway/Orchestrator/ToolGuard architecture.

**Architecture:** Thin NetworkChatGateway (HTTP + WS) delegates to NetworkAgentOrchestrator (prompt selection, tool routing, LLM calls), which passes tool calls through ToolGuard (safety validation) before executing against existing backend services. Frontend gets a reusable NetworkChatDrawer mounted in each network view.

**Tech Stack:** Python/FastAPI (backend), SQLite (storage), Anthropic SDK (LLM), React/TypeScript (frontend), WebSocket (streaming)

**Design Doc:** `docs/plans/2026-03-12-network-ai-chat-design.md`

---

## Task 1: Thread & Message Storage

**Files:**
- Create: `backend/src/database/network_chat_store.py`
- Test: `backend/tests/test_network_chat_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_chat_store.py
import os
import pytest
from src.database.network_chat_store import NetworkChatStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    return NetworkChatStore(db_path=db_path)


class TestThreadCRUD:
    def test_create_thread(self, store):
        thread = store.create_thread(user_id="user-1", view="observatory")
        assert thread["thread_id"]
        assert thread["user_id"] == "user-1"
        assert thread["view"] == "observatory"
        assert thread["investigation_session_id"] is None

    def test_get_thread(self, store):
        created = store.create_thread(user_id="user-1", view="ipam")
        fetched = store.get_thread(created["thread_id"])
        assert fetched is not None
        assert fetched["thread_id"] == created["thread_id"]

    def test_get_thread_not_found(self, store):
        assert store.get_thread("nonexistent") is None

    def test_get_active_thread_for_view(self, store):
        store.create_thread(user_id="user-1", view="observatory")
        active = store.get_active_thread(user_id="user-1", view="observatory")
        assert active is not None
        assert active["view"] == "observatory"

    def test_escalate_thread(self, store):
        thread = store.create_thread(user_id="user-1", view="observatory")
        store.escalate_thread(thread["thread_id"], investigation_session_id="inv-123")
        updated = store.get_thread(thread["thread_id"])
        assert updated["investigation_session_id"] == "inv-123"


class TestMessageCRUD:
    def test_add_and_list_messages(self, store):
        thread = store.create_thread(user_id="user-1", view="observatory")
        tid = thread["thread_id"]

        store.add_message(thread_id=tid, role="user", content="What's causing the spike?")
        store.add_message(thread_id=tid, role="assistant", content="Let me check flows.")
        store.add_message(
            thread_id=tid,
            role="tool",
            content='{"top_talkers": [...]}',
            tool_name="get_top_talkers",
            tool_args='{}',
            tool_result='{"top_talkers": [...]}',
        )

        messages = store.list_messages(tid)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "tool"
        assert messages[2]["tool_name"] == "get_top_talkers"

    def test_list_messages_with_limit(self, store):
        thread = store.create_thread(user_id="user-1", view="observatory")
        tid = thread["thread_id"]
        for i in range(25):
            store.add_message(thread_id=tid, role="user", content=f"msg-{i}")
        messages = store.list_messages(tid, limit=20)
        assert len(messages) == 20
        # Should return the LAST 20 messages (most recent)
        assert messages[0]["content"] == "msg-5"

    def test_add_message_updates_thread_last_message_at(self, store):
        thread = store.create_thread(user_id="user-1", view="observatory")
        tid = thread["thread_id"]
        original = store.get_thread(tid)["last_message_at"]
        store.add_message(thread_id=tid, role="user", content="hello")
        updated = store.get_thread(tid)["last_message_at"]
        assert updated >= original
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_network_chat_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.database.network_chat_store'`

**Step 3: Implement NetworkChatStore**

```python
# backend/src/database/network_chat_store.py
"""Persistent storage for network chat threads and messages."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


class NetworkChatStore:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._db_path = db_path
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS network_chat_threads (
                    thread_id                TEXT PRIMARY KEY,
                    user_id                  TEXT NOT NULL,
                    view                     TEXT NOT NULL,
                    created_at               TEXT NOT NULL,
                    last_message_at          TEXT NOT NULL,
                    investigation_session_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS network_chat_messages (
                    message_id  TEXT PRIMARY KEY,
                    thread_id   TEXT NOT NULL REFERENCES network_chat_threads(thread_id),
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    tool_name   TEXT,
                    tool_args   TEXT,
                    tool_result TEXT,
                    timestamp   TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ncm_thread
                ON network_chat_messages(thread_id, timestamp)
            """)

    # ── Thread operations ──

    def create_thread(self, user_id: str, view: str) -> dict:
        thread_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO network_chat_threads (thread_id, user_id, view, created_at, last_message_at) VALUES (?,?,?,?,?)",
                (thread_id, user_id, view, now, now),
            )
        return self.get_thread(thread_id)  # type: ignore[return-value]

    def get_thread(self, thread_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM network_chat_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_active_thread(self, user_id: str, view: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM network_chat_threads WHERE user_id = ? AND view = ? AND investigation_session_id IS NULL ORDER BY last_message_at DESC LIMIT 1",
                (user_id, view),
            ).fetchone()
        return dict(row) if row else None

    def escalate_thread(self, thread_id: str, investigation_session_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE network_chat_threads SET investigation_session_id = ? WHERE thread_id = ?",
                (investigation_session_id, thread_id),
            )

    # ── Message operations ──

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_args: str | None = None,
        tool_result: str | None = None,
    ) -> dict:
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO network_chat_messages (message_id, thread_id, role, content, tool_name, tool_args, tool_result, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                (message_id, thread_id, role, content, tool_name, tool_args, tool_result, now),
            )
            conn.execute(
                "UPDATE network_chat_threads SET last_message_at = ? WHERE thread_id = ?",
                (now, thread_id),
            )
        return {"message_id": message_id, "thread_id": thread_id, "role": role, "content": content, "timestamp": now}

    def list_messages(self, thread_id: str, limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM network_chat_messages WHERE thread_id = ? ORDER BY timestamp DESC LIMIT ?",
                (thread_id, limit),
            ).fetchall()
        messages = [dict(r) for r in reversed(rows)]
        return messages
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_network_chat_store.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/database/network_chat_store.py backend/tests/test_network_chat_store.py
git commit -m "feat(network-chat): add thread and message storage"
```

---

## Task 2: ToolGuard Safety Layer

**Files:**
- Create: `backend/src/agents/network/tool_guard.py`
- Test: `backend/tests/test_tool_guard.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_tool_guard.py
import json
import pytest
from src.agents.network.tool_guard import ToolGuard, ToolGuardError


@pytest.fixture
def guard():
    return ToolGuard()


class TestToolGuard:
    def test_allows_valid_read_tool(self, guard):
        # Should pass without raising
        guard.validate(
            tool_name="get_top_talkers",
            tool_args={"window": "5m", "limit": 20},
            view="observatory",
        )

    def test_rejects_over_max_rows(self, guard):
        with pytest.raises(ToolGuardError, match="max_rows"):
            guard.validate(
                tool_name="get_top_talkers",
                tool_args={"limit": 1000},
                view="observatory",
            )

    def test_rejects_simulate_in_non_investigation(self, guard):
        with pytest.raises(ToolGuardError, match="not allowed"):
            guard.validate(
                tool_name="simulate_rule_change",
                tool_args={"rule_id": "r1"},
                view="observatory",
                is_investigation=False,
            )

    def test_allows_simulate_in_investigation(self, guard):
        guard.validate(
            tool_name="simulate_rule_change",
            tool_args={"rule_id": "r1"},
            view="observatory",
            is_investigation=True,
        )

    def test_rate_limit(self, guard):
        thread_id = "thread-1"
        for _ in range(20):
            guard.check_rate_limit(thread_id)
        with pytest.raises(ToolGuardError, match="rate limit"):
            guard.check_rate_limit(thread_id)

    def test_truncates_large_result(self, guard):
        large_result = json.dumps({"data": "x" * 10000})
        truncated = guard.truncate_result(large_result, max_bytes=8192)
        assert len(truncated) <= 8192
        parsed = json.loads(truncated)
        assert "truncated" in parsed
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_guard.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement ToolGuard**

```python
# backend/src/agents/network/tool_guard.py
"""Safety layer between LLM tool calls and actual tool execution."""
import json
import time
from collections import defaultdict


class ToolGuardError(Exception):
    """Raised when a tool call is rejected by the guard."""
    pass


# Tools that require investigation mode
_SIMULATE_TOOLS = frozenset({
    "simulate_rule_change",
    "simulate_connectivity",
})

# Default limits
MAX_ROWS_DEFAULT = 500
MAX_TOOL_CALLS_PER_MINUTE = 20
MAX_RESULT_BYTES = 8192


class ToolGuard:
    def __init__(self):
        self._call_timestamps: dict[str, list[float]] = defaultdict(list)

    def validate(
        self,
        tool_name: str,
        tool_args: dict,
        view: str,
        is_investigation: bool = False,
    ) -> None:
        # Check row limits
        limit_val = tool_args.get("limit")
        if limit_val is not None and int(limit_val) > MAX_ROWS_DEFAULT:
            raise ToolGuardError(
                f"Requested limit {limit_val} exceeds max_rows ({MAX_ROWS_DEFAULT}). "
                f"Reduce the limit parameter."
            )

        # Block simulate tools outside investigation mode
        if tool_name in _SIMULATE_TOOLS and not is_investigation:
            raise ToolGuardError(
                f"Tool '{tool_name}' is not allowed outside investigation mode. "
                f"Start a Network Investigation session first."
            )

    def check_rate_limit(self, thread_id: str) -> None:
        now = time.monotonic()
        window = 60.0  # 1 minute
        timestamps = self._call_timestamps[thread_id]
        # Prune old entries
        self._call_timestamps[thread_id] = [t for t in timestamps if now - t < window]
        if len(self._call_timestamps[thread_id]) >= MAX_TOOL_CALLS_PER_MINUTE:
            raise ToolGuardError(
                f"Tool call rate limit exceeded ({MAX_TOOL_CALLS_PER_MINUTE}/min). "
                f"Wait before making more queries."
            )
        self._call_timestamps[thread_id].append(now)

    def truncate_result(self, result_json: str, max_bytes: int = MAX_RESULT_BYTES) -> str:
        if len(result_json.encode("utf-8")) <= max_bytes:
            return result_json
        # Parse, add truncation marker, re-serialize within budget
        try:
            data = json.loads(result_json)
        except json.JSONDecodeError:
            return result_json[:max_bytes]
        # If dict, add truncation flag and trim
        if isinstance(data, dict):
            data["truncated"] = True
            data["truncated_note"] = "Result exceeded size limit and was truncated."
            # Remove largest value fields until under budget
            while len(json.dumps(data).encode("utf-8")) > max_bytes and data:
                largest_key = max(
                    (k for k in data if k not in ("truncated", "truncated_note")),
                    key=lambda k: len(json.dumps(data[k])),
                    default=None,
                )
                if largest_key is None:
                    break
                data[largest_key] = f"[truncated — {len(json.dumps(data[largest_key]))} bytes]"
            return json.dumps(data)
        elif isinstance(data, list):
            return json.dumps({"items": data[:50], "total": len(data), "truncated": True})
        return result_json[:max_bytes]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_guard.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/network/tool_guard.py backend/tests/test_tool_guard.py
git commit -m "feat(network-chat): add ToolGuard safety layer"
```

---

## Task 3: Network Tool Registry

**Files:**
- Create: `backend/src/agents/network/tool_registry.py`
- Test: `backend/tests/test_network_tool_registry.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_tool_registry.py
import pytest
from src.agents.network.tool_registry import NetworkToolRegistry


class TestToolRegistry:
    def test_get_tools_for_observatory(self):
        tools = NetworkToolRegistry.get_tools_for_view("observatory")
        tool_names = {t["name"] for t in tools}
        # Observatory should have flow, alert, device, diagnostic, and shared tools
        assert "get_top_talkers" in tool_names
        assert "get_active_alerts" in tool_names
        assert "get_device_health" in tool_names
        assert "diagnose_path" in tool_names
        assert "summarize_context" in tool_names  # shared

    def test_get_tools_for_topology(self):
        tools = NetworkToolRegistry.get_tools_for_view("network-topology")
        tool_names = {t["name"] for t in tools}
        assert "get_topology_graph" in tool_names
        assert "evaluate_rule" in tool_names
        assert "diagnose_path" in tool_names

    def test_get_tools_for_ipam(self):
        tools = NetworkToolRegistry.get_tools_for_view("ipam")
        tool_names = {t["name"] for t in tools}
        assert "search_ip" in tool_names
        assert "get_subnet_utilization" in tool_names

    def test_get_all_tools_for_investigation(self):
        tools = NetworkToolRegistry.get_all_tools()
        tool_names = {t["name"] for t in tools}
        # Should include tools from all groups
        assert "get_top_talkers" in tool_names
        assert "get_topology_graph" in tool_names
        assert "search_ip" in tool_names
        assert "get_bgp_neighbors" in tool_names

    def test_tool_has_valid_schema(self):
        tools = NetworkToolRegistry.get_tools_for_view("observatory")
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_unknown_view_returns_shared_only(self):
        tools = NetworkToolRegistry.get_tools_for_view("unknown-view")
        tool_names = {t["name"] for t in tools}
        assert "summarize_context" in tool_names
        assert len(tool_names) == 2  # shared tools only
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_network_tool_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the tool registry**

```python
# backend/src/agents/network/tool_registry.py
"""Network tool definitions and view-based tool group routing."""


# ── Tool Group: Topology ──
_TOPOLOGY_TOOLS: list[dict] = [
    {
        "name": "get_topology_graph",
        "description": "Get the full network topology graph including devices, subnets, zones, and connections. Returns nodes and edges with metadata.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_path",
        "description": "Find the network path between two IP addresses. Returns ordered hops with devices, interfaces, and zones traversed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src_ip": {"type": "string", "description": "Source IP address"},
                "dst_ip": {"type": "string", "description": "Destination IP address"},
            },
            "required": ["src_ip", "dst_ip"],
        },
    },
    {
        "name": "list_devices_in_zone",
        "description": "List all devices in a specific security zone.",
        "input_schema": {
            "type": "object",
            "properties": {"zone_id": {"type": "string", "description": "Zone ID"}},
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_device_details",
        "description": "Get full details for a specific device including interfaces, routes, and zone membership.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID or name"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_interfaces",
        "description": "List interfaces for a device with IP, MAC, status, speed, and zone.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_routes",
        "description": "Get routing table for a device.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID"}},
            "required": ["device_id"],
        },
    },
]

# ── Tool Group: Flows ──
_FLOW_TOOLS: list[dict] = [
    {
        "name": "get_top_talkers",
        "description": "Get top source-destination pairs by traffic volume within a time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "description": "Time window (e.g., '5m', '1h')", "default": "5m"},
                "limit": {"type": "integer", "description": "Max results (default 20, max 500)", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_traffic_matrix",
        "description": "Get the full traffic matrix showing bytes between all source-destination pairs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "15m"},
            },
            "required": [],
        },
    },
    {
        "name": "get_protocol_breakdown",
        "description": "Get protocol distribution (TCP/UDP/ICMP/other) by traffic volume.",
        "input_schema": {
            "type": "object",
            "properties": {"window": {"type": "string", "default": "1h"}},
            "required": [],
        },
    },
    {
        "name": "get_conversations",
        "description": "Get active network conversations with bytes, packets, and duration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "5m"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "get_applications",
        "description": "Get application-layer traffic breakdown (HTTP, DNS, SSH, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    },
    {
        "name": "get_asn_breakdown",
        "description": "Get traffic breakdown by Autonomous System Number (ASN).",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    },
    {
        "name": "get_volume_timeline",
        "description": "Get traffic volume time series data for trend analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "interval": {"type": "string", "default": "1m"},
            },
            "required": [],
        },
    },
]

# ── Tool Group: IPAM ──
_IPAM_TOOLS: list[dict] = [
    {
        "name": "search_ip",
        "description": "Search for an IP address across all subnets. Returns subnet, allocation status, hostname, and history.",
        "input_schema": {
            "type": "object",
            "properties": {"ip": {"type": "string", "description": "IP address to search"}},
            "required": ["ip"],
        },
    },
    {
        "name": "get_subnet_utilization",
        "description": "Get utilization stats for a subnet: total IPs, assigned, available, reserved, utilization percentage.",
        "input_schema": {
            "type": "object",
            "properties": {"subnet_id": {"type": "string", "description": "Subnet ID or CIDR"}},
            "required": ["subnet_id"],
        },
    },
    {
        "name": "get_ip_conflicts",
        "description": "List all detected IP address conflicts across the network.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_capacity_forecast",
        "description": "Get capacity forecast for a subnet or region based on historical allocation trends.",
        "input_schema": {
            "type": "object",
            "properties": {"subnet_id": {"type": "string"}},
            "required": ["subnet_id"],
        },
    },
    {
        "name": "list_subnets",
        "description": "List all subnets with CIDR, name, VLAN, utilization, and zone.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 100}},
            "required": [],
        },
    },
]

# ── Tool Group: Firewall ──
_FIREWALL_TOOLS: list[dict] = [
    {
        "name": "evaluate_rule",
        "description": "Check if traffic between source and destination would be allowed or denied by firewall rules on a specific device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Firewall device ID"},
                "src_ip": {"type": "string"},
                "dst_ip": {"type": "string"},
                "port": {"type": "integer"},
                "protocol": {"type": "string", "default": "tcp"},
            },
            "required": ["device_id", "src_ip", "dst_ip", "port"],
        },
    },
    {
        "name": "list_rules_for_device",
        "description": "List all firewall/ACL rules configured on a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "simulate_rule_change",
        "description": "Simulate adding/removing a firewall rule and show impact. INVESTIGATION MODE ONLY.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "action": {"type": "string", "enum": ["add", "remove"]},
                "rule": {"type": "object", "description": "Rule definition"},
            },
            "required": ["device_id", "action", "rule"],
        },
    },
    {
        "name": "get_nacls",
        "description": "Get Network ACL rules for a VPC or subnet (cloud environments).",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
]

# ── Tool Group: Device ──
_DEVICE_TOOLS: list[dict] = [
    {
        "name": "list_devices",
        "description": "List all managed network devices with name, vendor, type, management IP, and status.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 100}},
            "required": [],
        },
    },
    {
        "name": "get_device_health",
        "description": "Get current health metrics for a device: CPU, memory, uptime, temperature, interface error counts.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_interface_stats",
        "description": "Get interface-level statistics: bandwidth utilization, error rates, packet drops, CRC errors.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}, "interface_name": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_syslog_events",
        "description": "Get recent syslog events for a device, sorted by timestamp descending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "get_traps",
        "description": "Get recent SNMP traps for a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["device_id"],
        },
    },
]

# ── Tool Group: Alerts ──
_ALERT_TOOLS: list[dict] = [
    {
        "name": "get_active_alerts",
        "description": "Get all currently active alerts with severity, source device, message, and timestamps.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_alert_history",
        "description": "Get historical alerts within a time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "24h"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": [],
        },
    },
    {
        "name": "get_drift_events",
        "description": "Get detected configuration drift events — changes between baseline and live config.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        },
    },
]

# ── Tool Group: Diagnostic ──
_DIAGNOSTIC_TOOLS: list[dict] = [
    {
        "name": "diagnose_path",
        "description": "Run a full path diagnosis between two IPs using the LangGraph diagnostic pipeline. Returns hops, firewall verdicts, NAT translations, and a final verdict.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src_ip": {"type": "string"},
                "dst_ip": {"type": "string"},
                "port": {"type": "integer", "default": 80},
                "protocol": {"type": "string", "default": "tcp"},
            },
            "required": ["src_ip", "dst_ip"],
        },
    },
    {
        "name": "correlate_events",
        "description": "Correlate alerts, syslog events, and flow changes within a time window to find related events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "30m"},
                "device_id": {"type": "string", "description": "Optional device to scope correlation"},
            },
            "required": [],
        },
    },
    {
        "name": "root_cause_analyze",
        "description": "Analyze a set of symptoms (alerts, metrics anomalies) and suggest probable root causes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of observed symptoms or alert descriptions",
                },
            },
            "required": ["symptoms"],
        },
    },
]

# ── Tool Group: Control Plane ──
_CONTROL_PLANE_TOOLS: list[dict] = [
    {
        "name": "get_bgp_neighbors",
        "description": "Get BGP neighbor/peer status for a device: peer IP, ASN, state, uptime, prefixes received/advertised.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_bgp_routes",
        "description": "Get BGP routing table for a device: prefix, next-hop, AS path, local preference, MED.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "prefix": {"type": "string", "description": "Optional prefix filter (e.g., '10.0.0.0/8')"},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "get_route_flaps",
        "description": "Get recent route flap events: prefix, timestamps, peer, flap count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "get_tunnel_status",
        "description": "Get VPN/GRE/IPsec tunnel status: tunnel name, endpoints, state, uptime.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_tunnel_latency",
        "description": "Get latency and jitter measurements for tunnels on a device.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_vpn_sessions",
        "description": "Get active VPN sessions: user/site, tunnel type, duration, bytes transferred.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        },
    },
]

# ── Tool Group: Cloud Networking ──
_CLOUD_NETWORK_TOOLS: list[dict] = [
    {
        "name": "get_vpc_routes",
        "description": "Get route table for a VPC: destination, target, status.",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
    {
        "name": "get_security_group_rules",
        "description": "Get security group rules for a cloud resource.",
        "input_schema": {
            "type": "object",
            "properties": {"security_group_id": {"type": "string"}},
            "required": ["security_group_id"],
        },
    },
    {
        "name": "get_nacl_rules",
        "description": "Get Network ACL rules for a VPC subnet.",
        "input_schema": {
            "type": "object",
            "properties": {"nacl_id": {"type": "string"}},
            "required": ["nacl_id"],
        },
    },
    {
        "name": "get_load_balancer_health",
        "description": "Get health status of load balancer targets/backends.",
        "input_schema": {
            "type": "object",
            "properties": {"lb_id": {"type": "string"}},
            "required": ["lb_id"],
        },
    },
    {
        "name": "get_peering_status",
        "description": "Get VPC peering or transit gateway attachment status.",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
]

# ── Tool Group: Shared (always loaded) ──
_SHARED_TOOLS: list[dict] = [
    {
        "name": "summarize_context",
        "description": "Summarize the current visible data and conversation context. Use when the user asks for an overview.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "start_investigation",
        "description": "Escalate to a cross-view Network Investigation session. Use when the user's question spans multiple network domains.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why investigation mode is needed"},
            },
            "required": ["reason"],
        },
    },
]

# ── View → Tool Group mapping ──
_VIEW_TOOL_GROUPS: dict[str, list[list[dict]]] = {
    "observatory": [_FLOW_TOOLS, _ALERT_TOOLS, _DEVICE_TOOLS, _DIAGNOSTIC_TOOLS],
    "network-topology": [_TOPOLOGY_TOOLS, _FIREWALL_TOOLS, _DIAGNOSTIC_TOOLS],
    "ipam": [_IPAM_TOOLS, _TOPOLOGY_TOOLS],
    "device-monitoring": [_DEVICE_TOOLS, _ALERT_TOOLS, _DIAGNOSTIC_TOOLS, _CONTROL_PLANE_TOOLS],
    "network-adapters": [_FIREWALL_TOOLS, _DEVICE_TOOLS, _CLOUD_NETWORK_TOOLS],
    "matrix": [_TOPOLOGY_TOOLS, _FIREWALL_TOOLS, _CONTROL_PLANE_TOOLS],
    "mib-browser": [_DEVICE_TOOLS],
    "cloud-resources": [_CLOUD_NETWORK_TOOLS, _FIREWALL_TOOLS, _TOPOLOGY_TOOLS],
    "security-resources": [_CLOUD_NETWORK_TOOLS, _FIREWALL_TOOLS],
}

_ALL_GROUPS = [
    _TOPOLOGY_TOOLS, _FLOW_TOOLS, _IPAM_TOOLS, _FIREWALL_TOOLS,
    _DEVICE_TOOLS, _ALERT_TOOLS, _DIAGNOSTIC_TOOLS,
    _CONTROL_PLANE_TOOLS, _CLOUD_NETWORK_TOOLS,
]


class NetworkToolRegistry:
    @staticmethod
    def get_tools_for_view(view: str) -> list[dict]:
        groups = _VIEW_TOOL_GROUPS.get(view, [])
        tools: list[dict] = []
        seen: set[str] = set()
        for group in groups:
            for tool in group:
                if tool["name"] not in seen:
                    tools.append(tool)
                    seen.add(tool["name"])
        # Always include shared tools
        for tool in _SHARED_TOOLS:
            if tool["name"] not in seen:
                tools.append(tool)
                seen.add(tool["name"])
        return tools

    @staticmethod
    def get_all_tools() -> list[dict]:
        tools: list[dict] = []
        seen: set[str] = set()
        for group in _ALL_GROUPS:
            for tool in group:
                if tool["name"] not in seen:
                    tools.append(tool)
                    seen.add(tool["name"])
        for tool in _SHARED_TOOLS:
            if tool["name"] not in seen:
                tools.append(tool)
                seen.add(tool["name"])
        return tools
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_network_tool_registry.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/network/tool_registry.py backend/tests/test_network_tool_registry.py
git commit -m "feat(network-chat): add network tool registry with 10 tool groups"
```

---

## Task 4: Tool Executor (wiring tools to existing services)

**Files:**
- Create: `backend/src/agents/network/tool_executor.py`
- Test: `backend/tests/test_network_tool_executor.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_tool_executor.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.network.tool_executor import NetworkToolExecutor


@pytest.fixture
def executor():
    return NetworkToolExecutor()


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, executor):
        result = await executor.execute("nonexistent_tool", {})
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_execute_get_top_talkers(self, executor):
        mock_data = [{"src": "10.0.0.1", "dst": "10.0.0.2", "bytes": 1000}]
        with patch.object(executor, "_call_flow_api", new_callable=AsyncMock, return_value=mock_data):
            result = await executor.execute("get_top_talkers", {"window": "5m", "limit": 10})
            parsed = json.loads(result)
            assert isinstance(parsed, list)

    @pytest.mark.asyncio
    async def test_execute_summarize_context(self, executor):
        result = await executor.execute("summarize_context", {})
        parsed = json.loads(result)
        assert "message" in parsed

    @pytest.mark.asyncio
    async def test_execute_start_investigation(self, executor):
        result = await executor.execute("start_investigation", {"reason": "cross-domain issue"})
        parsed = json.loads(result)
        assert parsed["action"] == "escalate"

    @pytest.mark.asyncio
    async def test_execution_error_returns_error_json(self, executor):
        with patch.object(executor, "_call_flow_api", new_callable=AsyncMock, side_effect=Exception("connection refused")):
            result = await executor.execute("get_top_talkers", {"window": "5m"})
            parsed = json.loads(result)
            assert "error" in parsed
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_network_tool_executor.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement NetworkToolExecutor**

```python
# backend/src/agents/network/tool_executor.py
"""Executes network tools by routing to existing backend services."""
import json
from src.utils.logger import get_logger

logger = get_logger(__name__)

# API base for internal calls
_API_BASE = "http://localhost:8000"


class NetworkToolExecutor:
    """Routes tool calls to existing backend services and returns JSON results."""

    async def execute(self, tool_name: str, tool_args: dict) -> str:
        try:
            handler = self._get_handler(tool_name)
            if handler is None:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            result = await handler(tool_args)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.warning("Tool execution failed: %s(%s) — %s", tool_name, tool_args, e)
            return json.dumps({"error": f"Tool '{tool_name}' failed: {str(e)}"})

    def _get_handler(self, tool_name: str):
        handlers = {
            # Flow tools
            "get_top_talkers": self._handle_get_top_talkers,
            "get_traffic_matrix": self._handle_get_traffic_matrix,
            "get_protocol_breakdown": self._handle_get_protocol_breakdown,
            "get_conversations": self._handle_get_conversations,
            "get_applications": self._handle_get_applications,
            "get_asn_breakdown": self._handle_get_asn_breakdown,
            "get_volume_timeline": self._handle_get_volume_timeline,
            # Topology tools
            "get_topology_graph": self._handle_get_topology_graph,
            "query_path": self._handle_query_path,
            "list_devices_in_zone": self._handle_list_devices_in_zone,
            "get_device_details": self._handle_get_device_details,
            "get_interfaces": self._handle_get_interfaces,
            "get_routes": self._handle_get_routes,
            # IPAM tools
            "search_ip": self._handle_search_ip,
            "get_subnet_utilization": self._handle_get_subnet_utilization,
            "get_ip_conflicts": self._handle_get_ip_conflicts,
            "get_capacity_forecast": self._handle_get_capacity_forecast,
            "list_subnets": self._handle_list_subnets,
            # Firewall tools
            "evaluate_rule": self._handle_evaluate_rule,
            "list_rules_for_device": self._handle_list_rules_for_device,
            "simulate_rule_change": self._handle_simulate_rule_change,
            "get_nacls": self._handle_get_nacls,
            # Device tools
            "list_devices": self._handle_list_devices,
            "get_device_health": self._handle_get_device_health,
            "get_interface_stats": self._handle_get_interface_stats,
            "get_syslog_events": self._handle_get_syslog_events,
            "get_traps": self._handle_get_traps,
            # Alert tools
            "get_active_alerts": self._handle_get_active_alerts,
            "get_alert_history": self._handle_get_alert_history,
            "get_drift_events": self._handle_get_drift_events,
            # Diagnostic tools
            "diagnose_path": self._handle_diagnose_path,
            "correlate_events": self._handle_correlate_events,
            "root_cause_analyze": self._handle_root_cause_analyze,
            # Control plane tools
            "get_bgp_neighbors": self._handle_get_bgp_neighbors,
            "get_bgp_routes": self._handle_get_bgp_routes,
            "get_route_flaps": self._handle_get_route_flaps,
            "get_tunnel_status": self._handle_get_tunnel_status,
            "get_tunnel_latency": self._handle_get_tunnel_latency,
            "get_vpn_sessions": self._handle_get_vpn_sessions,
            # Cloud network tools
            "get_vpc_routes": self._handle_get_vpc_routes,
            "get_security_group_rules": self._handle_get_security_group_rules,
            "get_nacl_rules": self._handle_get_nacl_rules,
            "get_load_balancer_health": self._handle_get_load_balancer_health,
            "get_peering_status": self._handle_get_peering_status,
            # Shared tools
            "summarize_context": self._handle_summarize_context,
            "start_investigation": self._handle_start_investigation,
        }
        return handlers.get(tool_name)

    # ── Internal HTTP helper ──

    async def _call_flow_api(self, path: str, params: dict | None = None) -> dict | list:
        import httpx
        async with httpx.AsyncClient(base_url=_API_BASE, timeout=10.0) as client:
            resp = await client.get(f"/api/v4/network/flows/{path}", params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def _call_network_api(self, method: str, path: str, params: dict | None = None, json_body: dict | None = None) -> dict | list:
        import httpx
        async with httpx.AsyncClient(base_url=_API_BASE, timeout=10.0) as client:
            if method == "GET":
                resp = await client.get(f"/api/v4/network/{path}", params=params or {})
            else:
                resp = await client.post(f"/api/v4/network/{path}", json=json_body or {})
            resp.raise_for_status()
            return resp.json()

    # ── Flow tool handlers ──

    async def _handle_get_top_talkers(self, args: dict):
        return await self._call_flow_api("top-talkers", {"window": args.get("window", "5m"), "limit": args.get("limit", 20)})

    async def _handle_get_traffic_matrix(self, args: dict):
        return await self._call_flow_api("traffic-matrix", {"window": args.get("window", "15m")})

    async def _handle_get_protocol_breakdown(self, args: dict):
        return await self._call_flow_api("protocol-breakdown", {"window": args.get("window", "1h")})

    async def _handle_get_conversations(self, args: dict):
        return await self._call_flow_api("conversations", {"window": args.get("window", "5m"), "limit": args.get("limit", 50)})

    async def _handle_get_applications(self, args: dict):
        return await self._call_flow_api("applications", {"window": args.get("window", "1h"), "limit": args.get("limit", 30)})

    async def _handle_get_asn_breakdown(self, args: dict):
        return await self._call_flow_api("asn", {"window": args.get("window", "1h"), "limit": args.get("limit", 30)})

    async def _handle_get_volume_timeline(self, args: dict):
        return await self._call_flow_api("volume-timeline", {"window": args.get("window", "1h"), "interval": args.get("interval", "1m")})

    # ── Topology tool handlers ──

    async def _handle_get_topology_graph(self, args: dict):
        return await self._call_network_api("GET", "topology/graph")

    async def _handle_query_path(self, args: dict):
        return await self._call_network_api("POST", "query/path", json_body={"src_ip": args["src_ip"], "dst_ip": args["dst_ip"]})

    async def _handle_list_devices_in_zone(self, args: dict):
        return await self._call_network_api("GET", f"zones/{args['zone_id']}/devices")

    async def _handle_get_device_details(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}")

    async def _handle_get_interfaces(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/interfaces")

    async def _handle_get_routes(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/routes")

    # ── IPAM tool handlers ──

    async def _handle_search_ip(self, args: dict):
        return await self._call_network_api("POST", "ipam/search", json_body={"query": args["ip"]})

    async def _handle_get_subnet_utilization(self, args: dict):
        return await self._call_network_api("GET", f"subnets/{args['subnet_id']}/utilization")

    async def _handle_get_ip_conflicts(self, args: dict):
        return await self._call_network_api("GET", "ipam/conflicts")

    async def _handle_get_capacity_forecast(self, args: dict):
        return await self._call_network_api("GET", f"subnets/{args['subnet_id']}/forecast")

    async def _handle_list_subnets(self, args: dict):
        return await self._call_network_api("GET", "subnets", params={"limit": args.get("limit", 100)})

    # ── Firewall tool handlers ──

    async def _handle_evaluate_rule(self, args: dict):
        return await self._call_network_api("POST", f"firewall/{args['device_id']}/evaluate", json_body={
            "src_ip": args["src_ip"], "dst_ip": args["dst_ip"],
            "port": args["port"], "protocol": args.get("protocol", "tcp"),
        })

    async def _handle_list_rules_for_device(self, args: dict):
        return await self._call_network_api("GET", f"firewall/{args['device_id']}/rules", params={"limit": args.get("limit", 100)})

    async def _handle_simulate_rule_change(self, args: dict):
        return await self._call_network_api("POST", "firewall/simulate", json_body=args)

    async def _handle_get_nacls(self, args: dict):
        return await self._call_network_api("GET", f"vpcs/{args['vpc_id']}/nacls")

    # ── Device tool handlers ──

    async def _handle_list_devices(self, args: dict):
        return await self._call_network_api("GET", "devices", params={"limit": args.get("limit", 100)})

    async def _handle_get_device_health(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/health")

    async def _handle_get_interface_stats(self, args: dict):
        params = {}
        if args.get("interface_name"):
            params["interface_name"] = args["interface_name"]
        return await self._call_network_api("GET", f"devices/{args['device_id']}/interface-stats", params=params)

    async def _handle_get_syslog_events(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/syslog", params={"limit": args.get("limit", 50)})

    async def _handle_get_traps(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/traps", params={"limit": args.get("limit", 50)})

    # ── Alert tool handlers ──

    async def _handle_get_active_alerts(self, args: dict):
        return await self._call_network_api("GET", "monitor/alerts", params={"status": "active"})

    async def _handle_get_alert_history(self, args: dict):
        return await self._call_network_api("GET", "monitor/alerts", params={"window": args.get("window", "24h"), "limit": args.get("limit", 100)})

    async def _handle_get_drift_events(self, args: dict):
        return await self._call_network_api("GET", "monitor/drift", params={"limit": args.get("limit", 50)})

    # ── Diagnostic tool handlers ──

    async def _handle_diagnose_path(self, args: dict):
        return await self._call_network_api("POST", "diagnose", json_body={
            "src_ip": args["src_ip"], "dst_ip": args["dst_ip"],
            "port": args.get("port", 80), "protocol": args.get("protocol", "tcp"),
        })

    async def _handle_correlate_events(self, args: dict):
        params = {"window": args.get("window", "30m")}
        if args.get("device_id"):
            params["device_id"] = args["device_id"]
        return await self._call_network_api("GET", "monitor/correlate", params=params)

    async def _handle_root_cause_analyze(self, args: dict):
        return await self._call_network_api("POST", "diagnose/root-cause", json_body={"symptoms": args["symptoms"]})

    # ── Control plane tool handlers ──

    async def _handle_get_bgp_neighbors(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/bgp/neighbors")

    async def _handle_get_bgp_routes(self, args: dict):
        params = {}
        if args.get("prefix"):
            params["prefix"] = args["prefix"]
        return await self._call_network_api("GET", f"devices/{args['device_id']}/bgp/routes", params=params)

    async def _handle_get_route_flaps(self, args: dict):
        return await self._call_network_api("GET", "bgp/flaps", params={"window": args.get("window", "1h"), "limit": args.get("limit", 50)})

    async def _handle_get_tunnel_status(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/tunnels")

    async def _handle_get_tunnel_latency(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/tunnels/latency")

    async def _handle_get_vpn_sessions(self, args: dict):
        return await self._call_network_api("GET", "vpn/sessions", params={"limit": args.get("limit", 50)})

    # ── Cloud network tool handlers ──

    async def _handle_get_vpc_routes(self, args: dict):
        return await self._call_network_api("GET", f"vpcs/{args['vpc_id']}/routes")

    async def _handle_get_security_group_rules(self, args: dict):
        return await self._call_network_api("GET", f"security-groups/{args['security_group_id']}/rules")

    async def _handle_get_nacl_rules(self, args: dict):
        return await self._call_network_api("GET", f"nacls/{args['nacl_id']}/rules")

    async def _handle_get_load_balancer_health(self, args: dict):
        return await self._call_network_api("GET", f"load-balancers/{args['lb_id']}/health")

    async def _handle_get_peering_status(self, args: dict):
        return await self._call_network_api("GET", f"vpcs/{args['vpc_id']}/peering")

    # ── Shared tool handlers ──

    async def _handle_summarize_context(self, args: dict):
        return {"message": "Use the visible data summary and conversation history to provide an overview."}

    async def _handle_start_investigation(self, args: dict):
        return {"action": "escalate", "reason": args.get("reason", "Cross-domain investigation requested")}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_network_tool_executor.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/network/tool_executor.py backend/tests/test_network_tool_executor.py
git commit -m "feat(network-chat): add tool executor wiring to existing services"
```

---

## Task 5: NetworkAgentOrchestrator

**Files:**
- Create: `backend/src/agents/network/orchestrator.py`
- Create: `backend/src/agents/network/prompts.py`
- Test: `backend/tests/test_network_orchestrator.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_orchestrator.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.network.orchestrator import NetworkAgentOrchestrator


@pytest.fixture
def orchestrator(tmp_path):
    db_path = str(tmp_path / "test.db")
    return NetworkAgentOrchestrator(db_path=db_path)


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_handle_message_creates_thread(self, orchestrator):
        with patch.object(orchestrator, "_call_llm", new_callable=AsyncMock) as mock_llm:
            # Simulate LLM returning text-only response (no tool calls)
            mock_response = MagicMock()
            mock_response.content = [MagicMock(type="text", text="Here's what I see.")]
            mock_response.stop_reason = "end_turn"
            mock_llm.return_value = mock_response

            result = await orchestrator.handle_message(
                user_id="user-1",
                view="observatory",
                message="What's happening?",
                visible_data_summary={"alerts": 3},
            )
            assert result["response"] == "Here's what I see."
            assert result["thread_id"] is not None

    @pytest.mark.asyncio
    async def test_loads_correct_tools_for_view(self, orchestrator):
        with patch.object(orchestrator, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(type="text", text="ok")]
            mock_response.stop_reason = "end_turn"
            mock_llm.return_value = mock_response

            await orchestrator.handle_message(
                user_id="user-1",
                view="ipam",
                message="Any conflicts?",
                visible_data_summary={},
            )

            # Verify tools passed to LLM include IPAM tools
            call_args = mock_llm.call_args
            tools = call_args.kwargs.get("tools") or call_args[1].get("tools", [])
            tool_names = {t["name"] for t in tools}
            assert "search_ip" in tool_names
            assert "get_subnet_utilization" in tool_names

    @pytest.mark.asyncio
    async def test_handles_tool_calls(self, orchestrator):
        # First LLM call returns tool_use, second returns text
        tool_use_block = MagicMock(type="tool_use", name="get_active_alerts", input={}, id="tool-1")
        text_block = MagicMock(type="text", text="There are 3 active alerts.")

        call_count = 0
        async def mock_llm_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                resp.content = [tool_use_block]
                resp.stop_reason = "tool_use"
            else:
                resp.content = [text_block]
                resp.stop_reason = "end_turn"
            return resp

        with patch.object(orchestrator, "_call_llm", new_callable=AsyncMock, side_effect=mock_llm_side_effect):
            with patch.object(orchestrator._tool_executor, "execute", new_callable=AsyncMock, return_value='[{"id": "a1", "severity": "critical"}]'):
                result = await orchestrator.handle_message(
                    user_id="user-1",
                    view="observatory",
                    message="Any alerts?",
                    visible_data_summary={},
                )
                assert result["response"] == "There are 3 active alerts."
                assert len(result.get("tool_calls", [])) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_network_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create prompt templates**

```python
# backend/src/agents/network/prompts.py
"""View-specific system prompt templates for the network chat agent."""

_BASE_ROLE = """You are a senior network operations engineer assisting with live network monitoring and troubleshooting in an AI-powered SRE platform called DebugDuck.

## Constraints
- Only reference devices, IPs, and subnets that exist in the topology — never hallucinate.
- If the user asks about something outside your tool reach, say so clearly.
- When presenting large datasets, summarize the top items and mention the total count.
- All IP addresses and device names must come from tool results, not from your training data.

## Escalation
If the user's question spans multiple network domains (e.g., correlating traffic anomalies with firewall changes), suggest: "This looks like it needs a cross-view investigation. Want me to start a Network Investigation session?"
"""

_VIEW_PROMPTS: dict[str, str] = {
    "observatory": """## Current View: Observatory (NOC Dashboard)
The user is viewing the Network Operations Center dashboard with live monitoring data.
Use flow analysis, alert, device health, and diagnostic tools to answer questions.
Focus on: traffic anomalies, active alerts, device health, and correlating events.""",

    "network-topology": """## Current View: Topology Editor
The user is viewing or designing the network topology.
Use topology, firewall, and diagnostic tools to answer questions.
Focus on: path analysis, zone membership, device connectivity, design validation.""",

    "ipam": """## Current View: IPAM Dashboard
The user is managing IP address allocations.
Use IPAM and topology tools to answer questions.
Focus on: subnet utilization, IP conflicts, capacity planning, address hierarchy.""",

    "device-monitoring": """## Current View: Device Monitoring
The user is monitoring specific network devices.
Use device, alert, diagnostic, and control plane tools to answer questions.
Focus on: device health, interface errors, BGP state, tunnel status.""",

    "network-adapters": """## Current View: Network Adapters
The user is configuring firewall and cloud network adapters.
Use firewall, device, and cloud networking tools to answer questions.
Focus on: rule evaluation, adapter configuration, security group rules.""",

    "matrix": """## Current View: Reachability Matrix
The user is analyzing all-pairs network reachability.
Use topology, firewall, and control plane tools to answer questions.
Focus on: path connectivity, blocked paths, routing state.""",

    "mib-browser": """## Current View: MIB Browser
The user is exploring SNMP MIB OIDs.
Use device tools to answer questions.
Focus on: SNMP metrics, OID interpretation, device data.""",

    "cloud-resources": """## Current View: Cloud Resources
The user is managing cloud networking resources.
Use cloud networking, firewall, and topology tools to answer questions.
Focus on: VPC routes, security groups, NACLs, peering, load balancer health.""",

    "security-resources": """## Current View: Security Resources
The user is reviewing security configurations.
Use cloud networking and firewall tools to answer questions.
Focus on: security group rules, NACLs, compliance.""",
}


def build_system_prompt(view: str, visible_data_summary: dict) -> str:
    view_prompt = _VIEW_PROMPTS.get(view, f"## Current View: {view}\nThe user is viewing a network-related page.")
    summary_str = str(visible_data_summary) if visible_data_summary else "No visible data provided."
    if len(summary_str) > 2048:
        summary_str = summary_str[:2048] + "... (truncated)"

    return f"""{_BASE_ROLE}

{view_prompt}

## Visible Data Summary
{summary_str}

## Tool Instructions
Use your available tools to verify data before answering. Don't guess from the visible summary alone.
When correlating across data sources, call multiple tools and synthesize the results.
"""
```

**Step 4: Implement the orchestrator**

```python
# backend/src/agents/network/orchestrator.py
"""AI logic layer for network chat — prompt selection, tool routing, LLM calls."""
import json
from src.agents.network.prompts import build_system_prompt
from src.agents.network.tool_registry import NetworkToolRegistry
from src.agents.network.tool_guard import ToolGuard, ToolGuardError
from src.agents.network.tool_executor import NetworkToolExecutor
from src.database.network_chat_store import NetworkChatStore
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_TOOL_ROUNDS_INVESTIGATION = 10
CHAT_HISTORY_CAP = 20


class NetworkAgentOrchestrator:
    def __init__(self, db_path: str = "data/debugduck.db"):
        self._store = NetworkChatStore(db_path=db_path)
        self._guard = ToolGuard()
        self._tool_executor = NetworkToolExecutor()
        self._llm = AnthropicClient(agent_name="network_chat")

    async def handle_message(
        self,
        user_id: str,
        view: str,
        message: str,
        visible_data_summary: dict,
        thread_id: str | None = None,
    ) -> dict:
        # Resolve or create thread
        thread = None
        if thread_id:
            thread = self._store.get_thread(thread_id)
        if not thread:
            thread = self._store.get_active_thread(user_id=user_id, view=view)
        if not thread:
            thread = self._store.create_thread(user_id=user_id, view=view)

        tid = thread["thread_id"]
        is_investigation = thread.get("investigation_session_id") is not None

        # Persist user message
        self._store.add_message(thread_id=tid, role="user", content=message)

        # Build prompt and tools
        system_prompt = build_system_prompt(view, visible_data_summary)
        tools = (
            NetworkToolRegistry.get_all_tools()
            if is_investigation
            else NetworkToolRegistry.get_tools_for_view(view)
        )

        # Load history
        history = self._store.list_messages(tid, limit=CHAT_HISTORY_CAP)
        messages_for_llm = self._build_llm_messages(history)

        # Tool-calling loop
        max_rounds = MAX_TOOL_ROUNDS_INVESTIGATION if is_investigation else MAX_TOOL_ROUNDS
        tool_calls_made: list[dict] = []
        full_response = ""

        for _round in range(max_rounds + 1):
            response = await self._call_llm(
                system=system_prompt,
                messages=messages_for_llm,
                tools=tools,
            )

            text_blocks = [b for b in response.content if b.type == "text"]
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                full_response = text_blocks[0].text if text_blocks else ""
                break

            # Append assistant message with tool_use blocks
            messages_for_llm.append({"role": "assistant", "content": response.content})

            # Execute tools
            tool_results = []
            for tool_block in tool_use_blocks:
                # Guard check
                try:
                    self._guard.validate(
                        tool_name=tool_block.name,
                        tool_args=tool_block.input,
                        view=view,
                        is_investigation=is_investigation,
                    )
                    self._guard.check_rate_limit(tid)
                except ToolGuardError as e:
                    result_str = json.dumps({"error": str(e)})
                    tool_results.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": result_str})
                    tool_calls_made.append({"name": tool_block.name, "blocked": True, "reason": str(e)})
                    continue

                result_str = await self._tool_executor.execute(tool_block.name, tool_block.input)
                result_str = self._guard.truncate_result(result_str)

                tool_results.append({"type": "tool_result", "tool_use_id": tool_block.id, "content": result_str})
                tool_calls_made.append({"name": tool_block.name, "args": tool_block.input})

                # Persist tool message
                self._store.add_message(
                    thread_id=tid, role="tool", content=result_str,
                    tool_name=tool_block.name,
                    tool_args=json.dumps(tool_block.input),
                    tool_result=result_str,
                )

            messages_for_llm.append({"role": "user", "content": tool_results})
        else:
            if text_blocks:
                full_response = text_blocks[0].text
            else:
                full_response = "I hit the tool call limit. Here's what I found so far."

        # Persist assistant response
        self._store.add_message(thread_id=tid, role="assistant", content=full_response)

        return {
            "response": full_response,
            "thread_id": tid,
            "tool_calls": tool_calls_made,
        }

    async def _call_llm(self, system: str, messages: list[dict], tools: list[dict]):
        return await self._llm.chat_with_tools(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )

    def _build_llm_messages(self, history: list[dict]) -> list[dict]:
        messages = []
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        return messages
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_network_orchestrator.py -v`
Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add backend/src/agents/network/orchestrator.py backend/src/agents/network/prompts.py backend/tests/test_network_orchestrator.py
git commit -m "feat(network-chat): add NetworkAgentOrchestrator with prompt templates"
```

---

## Task 6: NetworkChatGateway (API endpoints)

**Files:**
- Create: `backend/src/api/network_chat_endpoints.py`
- Modify: `backend/src/api/routes_v4.py` (include router)
- Test: `backend/tests/test_network_chat_endpoints.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_network_chat_endpoints.py
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.api.network_chat_endpoints import network_chat_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(network_chat_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestNetworkChatEndpoints:
    def test_post_chat_message(self, client):
        mock_result = {
            "response": "I see 3 active alerts.",
            "thread_id": "thread-123",
            "tool_calls": [],
        }
        with patch("src.api.network_chat_endpoints._get_orchestrator") as mock_get:
            mock_orch = AsyncMock()
            mock_orch.handle_message.return_value = mock_result
            mock_get.return_value = mock_orch

            resp = client.post("/api/v4/network/chat", json={
                "message": "Any alerts?",
                "view": "observatory",
                "visible_data_summary": {"alerts": 3},
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["response"] == "I see 3 active alerts."
            assert data["thread_id"] == "thread-123"

    def test_get_thread_messages(self, client):
        with patch("src.api.network_chat_endpoints._get_store") as mock_get:
            mock_store = mock_get.return_value
            mock_store.list_messages.return_value = [
                {"message_id": "m1", "role": "user", "content": "hello", "timestamp": "2026-03-12T00:00:00Z"},
            ]
            resp = client.get("/api/v4/network/chat/threads/thread-123/messages")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1

    def test_post_chat_requires_message(self, client):
        resp = client.post("/api/v4/network/chat", json={
            "view": "observatory",
        })
        assert resp.status_code == 422  # validation error
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_network_chat_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the gateway**

```python
# backend/src/api/network_chat_endpoints.py
"""NetworkChatGateway — thin API layer for network AI chat."""
from fastapi import APIRouter
from pydantic import BaseModel
from src.agents.network.orchestrator import NetworkAgentOrchestrator
from src.database.network_chat_store import NetworkChatStore
from src.utils.logger import get_logger

logger = get_logger(__name__)

network_chat_router = APIRouter(prefix="/api/v4/network/chat", tags=["network-chat"])

# Lazy singletons
_orchestrator: NetworkAgentOrchestrator | None = None
_store: NetworkChatStore | None = None


def _get_orchestrator() -> NetworkAgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = NetworkAgentOrchestrator()
    return _orchestrator


def _get_store() -> NetworkChatStore:
    global _store
    if _store is None:
        _store = NetworkChatStore()
    return _store


class NetworkChatRequest(BaseModel):
    message: str
    view: str
    visible_data_summary: dict = {}
    thread_id: str | None = None
    user_id: str = "default"


class NetworkChatResponse(BaseModel):
    response: str
    thread_id: str
    tool_calls: list[dict] = []


@network_chat_router.post("", response_model=NetworkChatResponse)
async def send_network_chat(request: NetworkChatRequest):
    logger.info("Network chat message", extra={"view": request.view, "user_id": request.user_id})
    orchestrator = _get_orchestrator()
    result = await orchestrator.handle_message(
        user_id=request.user_id,
        view=request.view,
        message=request.message,
        visible_data_summary=request.visible_data_summary,
        thread_id=request.thread_id,
    )
    return NetworkChatResponse(**result)


@network_chat_router.get("/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str, limit: int = 50):
    store = _get_store()
    messages = store.list_messages(thread_id, limit=limit)
    return messages
```

**Step 4: Wire the router into routes_v4.py**

Add to `backend/src/api/routes_v4.py` near the other router includes (around line 15-20 where routers are imported):

```python
from src.api.network_chat_endpoints import network_chat_router
```

And include it on the FastAPI app (find where `network_router` is included, add nearby):

```python
app.include_router(network_chat_router)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_network_chat_endpoints.py -v`
Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add backend/src/api/network_chat_endpoints.py backend/tests/test_network_chat_endpoints.py
git commit -m "feat(network-chat): add NetworkChatGateway API endpoints"
```

---

## Task 7: Frontend — useNetworkChat hook

**Files:**
- Create: `frontend/src/hooks/useNetworkChat.ts`

**Step 1: Implement the hook**

```typescript
// frontend/src/hooks/useNetworkChat.ts
import { useState, useCallback, useRef, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';

export interface NetworkChatMessage {
  message_id?: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: string;
  tool_name?: string;
  tool_calls?: { name: string; blocked?: boolean; reason?: string }[];
}

interface UseNetworkChatOptions {
  view: string;
  userId?: string;
}

export function useNetworkChat({ view, userId = 'default' }: UseNetworkChatOptions) {
  const [messages, setMessages] = useState<NetworkChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(`network-chat-thread-${view}`);
    } catch {
      return null;
    }
  });
  const [activeToolCalls, setActiveToolCalls] = useState<string[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  // Load existing messages when thread exists
  useEffect(() => {
    if (!threadId) return;
    const load = async () => {
      try {
        const resp = await fetch(`${API_BASE_URL}/api/v4/network/chat/threads/${threadId}/messages?limit=50`);
        if (resp.ok) {
          const data = await resp.json();
          setMessages(data.map((m: Record<string, unknown>) => ({
            message_id: m.message_id,
            role: m.role as 'user' | 'assistant' | 'tool',
            content: m.content as string,
            timestamp: m.timestamp as string,
            tool_name: m.tool_name as string | undefined,
          })));
        }
      } catch {
        // silent — start fresh
      }
    };
    load();
  }, [threadId]);

  const sendMessage = useCallback(
    async (content: string, visibleData: Record<string, unknown> = {}) => {
      if (!content.trim() || isSending) return;

      const userMsg: NetworkChatMessage = {
        role: 'user',
        content: content.trim(),
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsSending(true);

      try {
        abortRef.current = new AbortController();
        const resp = await fetch(`${API_BASE_URL}/api/v4/network/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content.trim(),
            view,
            visible_data_summary: visibleData,
            thread_id: threadId,
            user_id: userId,
          }),
          signal: abortRef.current.signal,
        });

        if (!resp.ok) {
          throw new Error(await resp.text().catch(() => 'Request failed'));
        }

        const data = await resp.json();

        // Persist thread ID
        if (data.thread_id && data.thread_id !== threadId) {
          setThreadId(data.thread_id);
          try {
            localStorage.setItem(`network-chat-thread-${view}`, data.thread_id);
          } catch { /* noop */ }
        }

        // Track tool calls
        if (data.tool_calls?.length) {
          setActiveToolCalls(data.tool_calls.map((tc: { name: string }) => tc.name));
        }

        const assistantMsg: NetworkChatMessage = {
          role: 'assistant',
          content: data.response,
          timestamp: new Date().toISOString(),
          tool_calls: data.tool_calls,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setActiveToolCalls([]);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        const errorMsg: NetworkChatMessage = {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Failed to send message'}`,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsSending(false);
      }
    },
    [view, threadId, userId, isSending]
  );

  const clearThread = useCallback(() => {
    setMessages([]);
    setThreadId(null);
    try {
      localStorage.removeItem(`network-chat-thread-${view}`);
    } catch { /* noop */ }
  }, [view]);

  return {
    messages,
    isSending,
    threadId,
    activeToolCalls,
    sendMessage,
    clearThread,
  };
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useNetworkChat.ts
git commit -m "feat(network-chat): add useNetworkChat frontend hook"
```

---

## Task 8: Frontend — NetworkChatDrawer + FAB

**Files:**
- Create: `frontend/src/components/NetworkChat/NetworkChatDrawer.tsx`
- Create: `frontend/src/components/NetworkChat/NetworkChatFAB.tsx`

**Step 1: Implement NetworkChatFAB**

```typescript
// frontend/src/components/NetworkChat/NetworkChatFAB.tsx
import React from 'react';

interface NetworkChatFABProps {
  onClick: () => void;
  hasUnread?: boolean;
}

const NetworkChatFAB: React.FC<NetworkChatFABProps> = ({ onClick, hasUnread }) => (
  <button
    onClick={onClick}
    title="Network Assistant"
    aria-label="Open Network Assistant"
    className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-duck-accent text-duck-bg shadow-[0_4px_20px_rgba(7,182,213,0.3)] hover:shadow-[0_4px_24px_rgba(7,182,213,0.5)] transition-all duration-200 flex items-center justify-center hover:scale-105 active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
  >
    <span className="material-symbols-outlined text-[22px]">chat</span>
    {hasUnread && (
      <span className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-red-500 rounded-full border-2 border-duck-bg" />
    )}
  </button>
);

export default NetworkChatFAB;
```

**Step 2: Implement NetworkChatDrawer**

```typescript
// frontend/src/components/NetworkChat/NetworkChatDrawer.tsx
import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import NetworkChatFAB from './NetworkChatFAB';
import { useNetworkChat } from '../../hooks/useNetworkChat';
import type { NetworkChatMessage } from '../../hooks/useNetworkChat';

const SUGGESTED_PROMPTS: Record<string, string[]> = {
  observatory: ['Any anomalies right now?', 'Explain the top alert', 'What changed in the last hour?'],
  'network-topology': ['Review this design', 'Any redundancy gaps?', 'What breaks if this node fails?'],
  ipam: ['Which subnets are running low?', 'Any IP conflicts?', 'Forecast growth for this region'],
  'device-monitoring': ['Why is this device unhealthy?', 'Show interface errors', 'Compare to last week'],
  'network-adapters': ['Evaluate this rule', 'Show security group rules', 'Any misconfigurations?'],
  matrix: ['Any blocked paths?', 'Check reachability to 10.0.0.0/24', 'Show routing state'],
  'mib-browser': ['Explain this OID', 'Show device metrics', 'What does this counter mean?'],
  'cloud-resources': ['Show VPC routes', 'Any security group issues?', 'Check peering status'],
  'security-resources': ['Audit security groups', 'Show NACL rules', 'Any compliance issues?'],
};

interface NetworkChatDrawerProps {
  view: string;
  visibleData?: Record<string, unknown>;
  onStartInvestigation?: () => void;
}

const NetworkChatDrawer: React.FC<NetworkChatDrawerProps> = ({
  view,
  visibleData = {},
  onStartInvestigation,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { messages, isSending, activeToolCalls, sendMessage, clearThread } = useNetworkChat({
    view,
  });

  const prompts = SUGGESTED_PROMPTS[view] || ['Ask me anything about this view'];

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input, visibleData);
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePromptClick = (prompt: string) => {
    sendMessage(prompt, visibleData);
  };

  return (
    <>
      {/* FAB */}
      {!isOpen && (
        <NetworkChatFAB
          onClick={() => setIsOpen(true)}
          hasUnread={false}
        />
      )}

      {/* Drawer */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/30 z-[55]"
              onClick={() => setIsOpen(false)}
            />

            {/* Panel */}
            <motion.div
              initial={{ x: 420 }}
              animate={{ x: 0 }}
              exit={{ x: 420 }}
              transition={{ type: 'spring', stiffness: 400, damping: 40 }}
              className="fixed right-0 top-0 bottom-0 w-full sm:w-[420px] z-[70] bg-slate-900/95 backdrop-blur-xl border-l border-white/5 flex flex-col shadow-2xl"
            >
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 flex-shrink-0">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-duck-accent text-[20px]">chat</span>
                  <h2 className="text-sm font-bold text-slate-200">Network Assistant</h2>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={clearThread}
                    title="New thread"
                    className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">restart_alt</span>
                  </button>
                  <button
                    onClick={() => setIsOpen(false)}
                    title="Close"
                    className="p-1.5 rounded text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[18px]">close</span>
                  </button>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 custom-scrollbar">
                {messages.length === 0 && (
                  <div className="text-center py-8">
                    <span className="material-symbols-outlined text-[40px] text-slate-600 mb-3 block">chat</span>
                    <p className="text-xs text-slate-500 mb-4">
                      Ask me about what you see in this view.
                    </p>
                    <div className="flex flex-col gap-2">
                      {prompts.map((p) => (
                        <button
                          key={p}
                          onClick={() => handlePromptClick(p)}
                          className="text-left text-xs text-slate-400 hover:text-cyan-400 bg-white/[0.03] hover:bg-white/[0.06] px-3 py-2 rounded-lg border border-white/5 transition-colors"
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages
                  .filter((m) => m.role !== 'tool')
                  .map((msg, i) => (
                    <MessageBubble key={i} message={msg} />
                  ))}

                {/* Tool call indicators */}
                {activeToolCalls.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 px-2">
                    <span className="animate-spin material-symbols-outlined text-[14px]">progress_activity</span>
                    <span>Using: {activeToolCalls.join(', ')}</span>
                  </div>
                )}

                {/* Sending indicator */}
                {isSending && activeToolCalls.length === 0 && (
                  <div className="flex items-center gap-2 text-xs text-slate-500 px-2">
                    <span className="animate-pulse">Thinking...</span>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="px-4 py-3 border-t border-white/5 flex-shrink-0">
                <div className="flex gap-2">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask about this view..."
                    rows={1}
                    className="flex-1 bg-white/[0.04] border border-white/10 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-cyan-400/40 transition-colors"
                  />
                  <button
                    onClick={handleSend}
                    disabled={!input.trim() || isSending}
                    className="px-3 py-2 rounded-lg bg-duck-accent text-duck-bg text-xs font-semibold disabled:opacity-30 hover:brightness-110 transition-all"
                  >
                    <span className="material-symbols-outlined text-[18px]">send</span>
                  </button>
                </div>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
};

// ── Message Bubble ──

const MessageBubble: React.FC<{ message: NetworkChatMessage }> = ({ message }) => {
  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] px-3 py-2 rounded-lg text-xs leading-relaxed ${
          isUser
            ? 'bg-cyan-400/10 text-slate-200 rounded-br-none'
            : 'bg-white/[0.04] text-slate-300 rounded-bl-none'
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-xs max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        )}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.tool_calls.map((tc, i) => (
              <span
                key={i}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${
                  tc.blocked ? 'bg-red-500/10 text-red-400' : 'bg-cyan-400/10 text-cyan-400'
                }`}
              >
                <span className="material-symbols-outlined text-[11px]">build</span>
                {tc.name}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default NetworkChatDrawer;
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/components/NetworkChat/NetworkChatDrawer.tsx frontend/src/components/NetworkChat/NetworkChatFAB.tsx
git commit -m "feat(network-chat): add NetworkChatDrawer and FAB components"
```

---

## Task 9: Mount NetworkChatDrawer in Network Views

**Files:**
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`
- Modify: `frontend/src/components/TopologyEditor/TopologyEditorView.tsx`
- Modify: `frontend/src/components/IPAM/IPAMDashboard.tsx`
- Modify: `frontend/src/components/Network/DeviceMonitoring.tsx`
- Modify: `frontend/src/components/Network/NetworkAdaptersView.tsx`
- Modify: `frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx`
- Modify: `frontend/src/components/Network/MIBBrowserView.tsx`
- Modify: `frontend/src/components/Cloud/CloudResourcesView.tsx`
- Modify: `frontend/src/components/Security/SecurityResourcesView.tsx`

**Step 1: Add to each view**

For each file, add the import and component near the end of the return JSX. Example pattern for each view:

```typescript
// Add import at top:
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

// Add before the closing fragment/div of the component's return:
<NetworkChatDrawer view="observatory" />
```

The `view` prop should match the view's ID in the sidebar:

| File | `view` prop value |
|---|---|
| `ObservatoryView.tsx` | `"observatory"` |
| `TopologyEditorView.tsx` | `"network-topology"` |
| `IPAMDashboard.tsx` | `"ipam"` |
| `DeviceMonitoring.tsx` | `"device-monitoring"` |
| `NetworkAdaptersView.tsx` | `"network-adapters"` |
| `ReachabilityMatrix.tsx` | `"matrix"` |
| `MIBBrowserView.tsx` | `"mib-browser"` |
| `CloudResourcesView.tsx` | `"cloud-resources"` |
| `SecurityResourcesView.tsx` | `"security-resources"` |

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Visual verify**

Run: `cd frontend && npm run dev`
Check: Each network view should show a cyan chat FAB (bottom-right). Clicking opens the drawer with view-specific suggested prompts.

**Step 4: Commit**

```bash
git add frontend/src/components/Observatory/ObservatoryView.tsx \
       frontend/src/components/TopologyEditor/TopologyEditorView.tsx \
       frontend/src/components/IPAM/IPAMDashboard.tsx \
       frontend/src/components/Network/DeviceMonitoring.tsx \
       frontend/src/components/Network/NetworkAdaptersView.tsx \
       frontend/src/components/NetworkTroubleshooting/ReachabilityMatrix.tsx \
       frontend/src/components/Network/MIBBrowserView.tsx \
       frontend/src/components/Cloud/CloudResourcesView.tsx \
       frontend/src/components/Security/SecurityResourcesView.tsx
git commit -m "feat(network-chat): mount NetworkChatDrawer in all network views"
```

---

## Task 10: Backend `__init__.py` files + wiring

**Files:**
- Create: `backend/src/agents/network/__init__.py`

**Step 1: Create the package init**

```python
# backend/src/agents/network/__init__.py
```

Empty file — just makes it a Python package.

**Step 2: Wire network_chat_router into the app**

Find where the FastAPI app includes routers (in `backend/src/main.py` or wherever the app is created) and add:

```python
from src.api.network_chat_endpoints import network_chat_router
app.include_router(network_chat_router)
```

**Step 3: Add `httpx` dependency**

The tool executor uses `httpx` for internal API calls:

```bash
cd backend && pip install httpx && pip freeze | grep httpx >> requirements.txt
```

**Step 4: Run full backend test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All new tests pass, no regressions

**Step 5: Commit**

```bash
git add backend/src/agents/network/__init__.py backend/requirements.txt
git commit -m "feat(network-chat): wire up package and dependencies"
```

---

## Verification Checklist

After all tasks are complete:

1. `cd backend && python -m pytest tests/ -v` — All tests pass
2. `cd frontend && npx tsc --noEmit` — TypeScript compiles clean
3. `cd frontend && npm run dev` — Visual check:
   - Cyan chat FAB visible on Observatory, Topology, IPAM, Device Monitoring, Adapters, Matrix, MIB Browser, Cloud Resources, Security Resources
   - Clicking FAB opens drawer with view-specific suggested prompts
   - Typing a message and sending shows user bubble and (with backend running) assistant response
   - Tool call indicators appear when LLM uses tools
   - Closing and reopening drawer preserves chat history
4. `cd backend && uvicorn src.main:app --reload` — Backend starts without errors
5. `POST http://localhost:8000/api/v4/network/chat` with `{"message": "hello", "view": "observatory"}` returns a response
