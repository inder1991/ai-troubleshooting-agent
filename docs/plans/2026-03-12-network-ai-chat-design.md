# Network AI Chat — Design Document

**Date:** 2026-03-12
**Status:** Approved
**Phase:** 1 of 4 (Contextual Chat Drawer)

## Problem

The network views (Observatory, Topology Editor, IPAM, Device Monitoring, Adapters, Reachability Matrix, MIB Browser, Cloud Resources) are display-only. Users see data but have no way to ask questions about what they're seeing. LLM capabilities exist for app/cluster diagnostics but are absent from the network domain.

## Decision Summary

| Aspect | Decision |
|---|---|
| Architecture | Gateway (API) → Orchestrator (AI logic) → ToolGuard → ToolRegistry → Existing services |
| Storage | `network_chat_threads` + `network_chat_messages` in SQLite |
| Tool groups | 10 groups: topology, flow, ipam, firewall, device, alert, diagnostic, control_plane, cloud_network, shared |
| View mapping | Each view loads 2-4 tool groups based on relevance |
| Context injection | View-specific prompt template + 2KB visible data summary + 20-message history |
| Chat UX | Slide-out drawer with FAB trigger, view-aware suggested prompts, tool call indicators |
| Chat scope | Per-view threads by default, escalation to cross-view investigation sessions |
| Streaming | WebSocket, same pattern as existing investigation chat |
| Safety | ToolGuard: max rows, rate limits, read-only default, payload caps |

---

## 1. Architecture

Three-layer backend with explicit separation of concerns:

```
FRONTEND
  NetworkChatDrawer (reusable across all network views)
      │
      │  POST /api/v4/network/chat
      │  WS   /ws/network/{thread_id}
      ▼
Layer 1: NetworkChatGateway  (API layer — thin)
  • HTTP request/response handling
  • Auth / user identity
  • Thread lookup/creation (from DB)
  • WebSocket streaming relay
  • Message persistence (write to network_chat_messages)
      │
      ▼
Layer 2: NetworkAgentOrchestrator  (AI logic)
  ├── load_prompt(view)
  ├── select_tools(view)
  ├── call_llm(prompt, tools, history)
  └── handle_tool_calls()
          │
          ▼
      ToolGuard  (safety layer)
      • Max result rows (500 default)
      • Query rate limits per thread (20/min)
      • Allowed operations per view (read-only default)
      • Payload size caps (8KB per tool result)
      • IP range allow-list for probes
          │
          ▼
      ToolRegistry
      ├── topology_tools
      ├── flow_tools
      ├── ipam_tools
      ├── firewall_tools
      ├── device_tools
      ├── alert_tools
      ├── diagnostic_tools
      ├── control_plane_tools
      ├── cloud_network_tools
      └── shared_tools
          │
          ▼
      Existing backend services
      (topology_store, metrics_store, knowledge_graph,
       flow_receiver, adapter_registry, IPAM store)
```

**Why three layers:**
- Gateway = API plumbing. No AI logic. Testable independently.
- Orchestrator = All AI decisions. Prompt selection, tool routing, LLM calls, tool execution loop.
- ToolGuard = Safety boundary. Every tool call validated before execution. Prevents LLM from requesting huge datasets or unauthorized operations.

---

## 2. Storage

Two tables in the existing SQLite database:

```sql
CREATE TABLE network_chat_threads (
    thread_id                TEXT PRIMARY KEY,
    user_id                  TEXT NOT NULL,
    view                     TEXT NOT NULL,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    investigation_session_id TEXT NULL
);

CREATE TABLE network_chat_messages (
    message_id  TEXT PRIMARY KEY,
    thread_id   TEXT NOT NULL REFERENCES network_chat_threads(thread_id),
    role        TEXT NOT NULL,  -- user | assistant | tool
    content     TEXT NOT NULL,
    tool_name   TEXT NULL,
    tool_args   TEXT NULL,      -- JSON
    tool_result TEXT NULL,      -- JSON
    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Enables: chat history reload, tool call auditing, debugging, future training data.

---

## 3. Tool Groups

### Tool Definitions

| Tool Group | Tools | Wraps |
|---|---|---|
| **topology_tools** | `get_topology_graph`, `query_path`, `list_devices_in_zone`, `get_device_details`, `get_interfaces`, `get_routes` | topology_store, knowledge_graph |
| **flow_tools** | `get_top_talkers`, `get_traffic_matrix`, `get_protocol_breakdown`, `get_conversations`, `get_applications`, `get_asn_breakdown`, `get_volume_timeline` | metrics_store, flow_receiver |
| **ipam_tools** | `search_ip`, `get_subnet_utilization`, `get_ip_conflicts`, `get_capacity_forecast`, `get_allocation_history`, `list_subnets` | IPAM store, topology_store |
| **firewall_tools** | `evaluate_rule`, `list_rules_for_device`, `simulate_rule_change`, `get_nacls` | adapter_registry, firewall adapters |
| **device_tools** | `list_devices`, `get_device_health`, `get_interface_stats`, `get_snmp_metrics`, `get_syslog_events`, `get_traps` | SNMP collectors, event store |
| **alert_tools** | `get_active_alerts`, `get_alert_history`, `get_drift_events` | event store, drift detector |
| **diagnostic_tools** | `diagnose_path`, `explain_finding`, `correlate_events`, `root_cause_analyze` | knowledge_graph, LangGraph pipeline |
| **control_plane_tools** | `get_bgp_neighbors`, `get_bgp_routes`, `get_route_flaps`, `get_tunnel_status`, `get_tunnel_latency`, `get_vpn_sessions` | routing store, VPN/tunnel models |
| **cloud_network_tools** | `get_vpc_routes`, `get_security_group_rules`, `get_nacl_rules`, `get_load_balancer_health`, `get_peering_status` | cloud adapters (AWS SG, Azure NSG, Oracle NSG) |
| **shared_tools** | `summarize_context`, `start_investigation` | Utility (always loaded) |

### View → Tool Group Mapping

| View | Tool Groups |
|---|---|
| Observatory | flow_tools + alert_tools + device_tools + diagnostic_tools |
| Topology Editor | topology_tools + firewall_tools + diagnostic_tools |
| IPAM Dashboard | ipam_tools + topology_tools |
| Device Monitoring | device_tools + alert_tools + diagnostic_tools + control_plane_tools |
| Network Adapters | firewall_tools + device_tools + cloud_network_tools |
| Reachability Matrix | topology_tools + firewall_tools + control_plane_tools |
| MIB Browser | device_tools |
| Cloud Resources | cloud_network_tools + firewall_tools + topology_tools |

### ToolGuard Defaults

| Rule | Default | Investigation Mode |
|---|---|---|
| Max result rows | 500 | 500 |
| Max tool calls per message | 5 | 10 |
| Allowed operations | Read-only | simulate_* enabled |
| Query rate limit | 20 calls/min/thread | 20 calls/min/thread |
| Payload size cap | 8KB per tool result | 8KB per tool result |

---

## 4. System Prompts & Context Injection

### Prompt Template Structure

Each view has a template with five sections:

```
[ROLE]         — Network engineer persona
[VIEW CONTEXT] — Current view + visible data summary
[TOOL INSTRUCTIONS] — How to use loaded tools
[CONSTRAINTS]  — Don't guess IPs, don't hallucinate devices
[ESCALATION]   — When to suggest investigation session
```

### Visible Data Summary

Frontend serializes a lightweight summary (max 2KB) of what's currently rendered:

| View | Summary Contents |
|---|---|
| Observatory | Active tab, top 5 alerts, top 5 talkers, device count + status breakdown |
| Topology Editor | Active design name, node count, selected node, validation warnings |
| IPAM | Selected subnet/region, utilization %, conflict count, selected IP |
| Device Monitoring | Selected device name/IP, current metrics (CPU/mem/latency), interface count |
| Reachability Matrix | Matrix dimensions, failed pairs highlighted |

### Chat History

- Last 20 messages sent to LLM (older messages stay in DB, not in context)
- Tool-role messages included so LLM sees what it already queried
- History loaded from `network_chat_messages` on thread open

---

## 5. Frontend Components

### NetworkChatDrawer

Slide-out drawer component, reusable across all network views:

- **Props:** `view`, `visibleData`, `onClose`, `onStartInvestigation`
- Thread created on first message, reused on subsequent
- Tool call indicators while LLM uses tools
- View-aware suggested prompts
- Streaming response rendering

### useNetworkChat Hook

- `sendMessage(text)` → POST `/api/v4/network/chat`
- `messages[]` — loaded from thread history on mount
- `isStreaming` — true while receiving WS chunks
- `activeToolCalls[]` — tool calls in progress
- Thread ID managed per view (persisted in localStorage)

### NetworkChatFAB

Floating action button (bottom-right) to toggle the drawer. Shows unread indicator. Uses `chat` Material Symbol with cyan accent.

### Suggested Prompts Per View

| View | Quick Prompts |
|---|---|
| Observatory | "Any anomalies right now?", "Explain the top alert", "What changed in the last hour?" |
| Topology Editor | "Review this design", "Any redundancy gaps?", "What breaks if [selected node] fails?" |
| IPAM | "Which subnets are running low?", "Any IP conflicts?", "Forecast growth for this region" |
| Device Monitoring | "Why is this device unhealthy?", "Show interface errors", "Compare to last week" |

### Mounting

Each network view adds:
```tsx
<NetworkChatDrawer
  view="observatory"
  visibleData={currentVisibleData}
  onStartInvestigation={handleEscalate}
/>
```

---

## 6. Investigation Escalation

### Flow

1. LLM suggests escalation when question spans multiple domains
2. User confirms via inline "Start Investigation" button
3. Backend creates new thread with `investigation_session_id` set
4. Current thread messages copied into investigation thread
5. All tool groups loaded, ToolGuard relaxed (simulate_* enabled, max calls bumped)
6. Drawer persists across view navigation (doesn't close on view switch)
7. View context appended as system message when user navigates between views
8. User ends investigation via "End Investigation" button → thread archived

### UX Changes in Investigation Mode

- Cyan "Investigation" badge in drawer header
- Drawer stays open across network view navigation
- Tool calls may reference tools from other domains
- Banner: "Investigation mode — context spans all network views"

---

## 7. Future Phases (for architectural awareness)

These are NOT in Phase 1 scope but the architecture supports them:

- **Phase 2: Inline AI Insights** — Orchestrator in proactive mode generates insights on view load. `<AIInsightCard>` component embedded in views.
- **Phase 3: NL Query Bar** — Cmd+K command palette. Orchestrator returns structured data instead of prose.
- **Phase 4: Proactive Alerts** — Background orchestrator on event triggers. Push notifications with explanations.
