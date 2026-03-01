# Agent Matrix: AI Workforce Directory

> Design document for the Agent Matrix page — a dedicated view that presents all diagnostic agents as a "team of specialized automated engineers" with real-time health status, execution traces, and tool visibility.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Agent roster | Only agents in actual workflows | Both app diagnostic (15) and cluster diagnostic (10) agents |
| Navigation | Dedicated `/agents` route | Always accessible, independent of active sessions |
| Grouping | Workflow tabs + role sub-groups | Two tabs (App / Cluster), within each: Orchestrators, Analysis, etc. |
| Scope | Grid + Detail view in one iteration | Full feature set from day one |
| Health source | Real-time health probe via `GET /api/v4/agents` | On-demand probing with 30s cache, no background polling |
| Thinking stream | Recent execution replay when idle, live when active | Shows last execution trace or live WebSocket stream |
| Recent cases | Real session history from session store | Last 5 sessions per agent |
| Backend architecture | Static registry + active health probing | Hardcoded `AGENT_REGISTRY` dict, matches existing `TOOL_REGISTRY` pattern |

---

## 1. Backend: Agent Registry & API

### `AGENT_REGISTRY` (Static Dict)

Each agent entry:

```python
{
    "id": "node_agent",
    "name": "NODE_AGENT",
    "workflow": "cluster_diagnostics",          # or "app_diagnostics"
    "role": "domain_expert",                    # orchestrator | analysis | validation | fix_generation | domain_expert
    "description": "Analyzes node conditions, resource utilization, pod evictions, and scheduling failures.",
    "icon": "dns",                              # Material Symbol name
    "level": 4,                                 # 1-5 autonomy level
    "llm_config": {
        "model": "claude-sonnet-4-20250514",
        "temperature": 0.1,
        "context_window": 128000,
        "mode": "autonomous",
    },
    "timeout_s": 45,
    "tools": ["k8s_lister", "prometheus_query", "list_events", "list_pods"],
    "tool_health_checks": {
        "k8s_api": "check_k8s_connectivity",
        "prometheus": "check_prom_connectivity",
    },
    "architecture_stages": ["Topology Read", "Event Fetch", "LLM Analysis", "Report Build"],
}
```

### Agent Roster

**App Diagnostics (15 agents):**

| Role | Agents |
|------|--------|
| Orchestrators | SupervisorAgent, CriticAgent, EvidenceGraphBuilder |
| Analysis | LogAnalysisAgent, MetricsAgent, K8sAgent, TracingAgent, CodeNavigatorAgent, ChangeAgent |
| Validation | ImpactAnalyzer |
| Fix Generation | FixGenerator, StaticValidator, CrossAgentReviewer, ImpactAssessor, PRStager |

**Cluster Diagnostics (10 agents):**

| Role | Agents |
|------|--------|
| Orchestrators | TopologyResolver, AlertCorrelator, CausalFirewall, DispatchRouter, Synthesizer, GuardFormatter |
| Domain Experts | CtrlPlaneAgent, NodeAgent, NetworkAgent, StorageAgent |

### `GET /api/v4/agents` Endpoint

Response schema:

```json
{
  "agents": [
    {
      "id": "node_agent",
      "name": "NODE_AGENT",
      "workflow": "cluster_diagnostics",
      "role": "domain_expert",
      "description": "...",
      "icon": "dns",
      "level": 4,
      "llm_config": { "model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous" },
      "timeout_s": 45,
      "status": "active",
      "degraded_tools": [],
      "tools": ["k8s_lister", "prometheus_query", "list_events", "list_pods"],
      "architecture_stages": ["Topology Read", "Event Fetch", "LLM Analysis", "Report Build"],
      "recent_executions": [
        {
          "session_id": "abc123",
          "timestamp": "2026-03-01T09:01:23Z",
          "status": "SUCCESS",
          "duration_ms": 1200,
          "summary": "Node capacity analysis for prod namespace"
        }
      ]
    }
  ],
  "summary": { "total": 25, "active": 23, "degraded": 1, "offline": 1 }
}
```

### Health Status Logic

- **`active`** — All tool dependencies reachable
- **`degraded`** — Agent functional but one or more tools failing (e.g., Prometheus unreachable). `degraded_tools` lists which ones.
- **`offline`** — Critical dependency missing (e.g., K8s API unreachable for K8sAgent)

### Health Probe Implementation

Probes run in parallel (`asyncio.gather`), 3s timeout each, results cached 30 seconds:

- **K8s API:** `client.list_namespaces()` with 3s timeout
- **Prometheus:** `client.query("up")` with 3s timeout
- **Elasticsearch:** `client.ping()` with 3s timeout
- **GitHub:** `requests.get("https://api.github.com/rate_limit")` with 3s timeout

### `GET /api/v4/agents/{id}/executions` Endpoint

Returns last 5 sessions where this agent participated:

```json
{
  "agent_id": "node_agent",
  "executions": [
    {
      "session_id": "abc123",
      "timestamp": "2026-03-01T09:01:23Z",
      "status": "SUCCESS",
      "duration_ms": 1200,
      "confidence": 85,
      "summary": "Pod crash loop detection in staging",
      "trace": [
        { "timestamp": "09:01:23", "level": "info", "message": "Reading node conditions for 3 nodes" },
        { "timestamp": "09:01:25", "level": "warn", "message": "worker-3 NotReady, DiskPressure 97%" },
        { "timestamp": "09:01:27", "level": "info", "message": "Analysis complete. Confidence: 85/100" }
      ]
    }
  ]
}
```

---

## 2. Frontend: Agent Grid Page

### Route & Navigation

- New view state `'agents'` in `App.tsx`
- Nav button in top bar (Material Symbol: `smart_toy`)
- Route renders `<AgentMatrixView />`

### Page Structure

```
┌──────────────────────────────────────────────────────────────────────┐
│  NEURAL DIRECTORY HUD                                                │
│  /// LIVE WORKFORCE MATRIX /// AUTONOMOUS DIAGNOSTICS ///            │
├──────────────────────────────────────────────────────────────────────┤
│  [App Diagnostics]  [Cluster Diagnostics]         25 AGENTS | 23 UP │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ── ORCHESTRATORS ──────────────────────────────────                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │
│  │ Card     │  │ Card     │  │ Card     │                          │
│  └──────────┘  └──────────┘  └──────────┘                          │
│                                                                      │
│  ── ANALYSIS AGENTS / DOMAIN EXPERTS ──────────────                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Card     │  │ Card     │  │ Card     │  │ Card     │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│                                                                      │
│  (more groups as needed)                                             │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  25 AGENTS | 23 ACTIVE | 1 DEGRADED | 1 OFFLINE | NEURAL SYNC 99%  │
└──────────────────────────────────────────────────────────────────────┘
```

### `<AgentCard />` Component

```
┌─────────────────────────────────────┐
│  [icon]  NODE_AGENT        ● ACTIVE │
│          Domain Expert              │
│                                     │
│  Analyzes node conditions,          │
│  resource utilization, pod          │
│  evictions and scheduling.          │
│                                     │
│  ─── EQUIPPED TOOLS ──────         │
│  [k8s_lister] [prometheus_query]    │
│  [list_events] [list_pods]          │
└─────────────────────────────────────┘
```

- Dark bg `#0a1214`, border `border-duck-border`, hover border transitions to cyan
- Status dot with glow: active=cyan, degraded=amber+pulse, offline=red
- Monospace font for agent name, uppercase tracking for role
- Tool pills: `bg-duck-cyan/10 text-duck-cyan border-duck-cyan/20`
- Click opens detail view

---

## 3. Frontend: Agent Detail View

Full-page view rendered when clicking an agent card. Back button returns to grid.

### Layout: Two-Column

**Left column (40%):**
- Agent header: icon, name, level badge, system status
- Neural Architecture: vertical flow diagram of `architecture_stages`
- Core Configuration: LLM model, temperature, context window, mode, timeout
- Active Toolbelt: tool list with green/red health dots, `X/Y` count

**Right column (60%):**
- Execution Trace: scrollable log area
  - When idle: last execution trace labeled "LAST EXECUTION"
  - When active session running: live WebSocket stream labeled "LIVE_THINKING_STREAM"
- Recent Cases: last 5 sessions with relative timestamps, one-line summaries, outcome badges

**Footer:**
- Heartbeat (health probe latency), lifetime token usage, version

---

## 4. Data Flow

```
Page Load
  → GET /api/v4/agents (health probes run, 30s cache)
  → Frontend renders grid with status dots

Card Click
  → Frontend reads agent detail from already-fetched data
  → GET /api/v4/agents/{id}/executions (last 5 sessions with traces)
  → If active session: subscribe to WebSocket for live trace

Tab Switch
  → Filter already-loaded agents by workflow (no new API call)
```

### Error Handling

- **Health probe timeout (3s):** Tool marked degraded, agent card shows amber. Tooltip lists failing tools.
- **No active session:** Trace area shows "AWAITING DISPATCH" placeholder.
- **API failure:** Grid shows cached data or "Connection lost" banner with retry button.

---

## 5. Component Tree

```
AgentMatrixView
├── AgentMatrixHeader (title, subtitle, summary stats)
├── WorkflowTabs (App Diagnostics | Cluster Diagnostics)
├── AgentGrid
│   ├── RoleGroup (label, agents[])
│   │   └── AgentCard (identity, status, tools)
│   └── RoleGroup ...
├── AgentDetailView (when agent selected)
│   ├── AgentDetailHeader (name, level, status)
│   ├── NeuralArchitectureDiagram (stages flow)
│   ├── CoreConfigPanel (LLM settings)
│   ├── ToolbeltPanel (tools + health dots)
│   ├── ExecutionTracePanel (last/live trace)
│   └── RecentCasesPanel (session history)
└── AgentMatrixFooter (agent count, status summary)
```

---

## 6. New Files

### Backend
- `backend/src/api/agent_registry.py` — `AGENT_REGISTRY` dict + health probe functions
- `backend/src/api/agent_endpoints.py` — `GET /api/v4/agents`, `GET /api/v4/agents/{id}/executions`
- `backend/tests/test_agent_registry.py` — Registry structure, health probe, endpoint tests

### Frontend
- `frontend/src/components/AgentMatrix/AgentMatrixView.tsx` — Main page container
- `frontend/src/components/AgentMatrix/AgentMatrixHeader.tsx` — Title, subtitle, stats
- `frontend/src/components/AgentMatrix/WorkflowTabs.tsx` — Tab switcher
- `frontend/src/components/AgentMatrix/AgentGrid.tsx` — Grid with role groups
- `frontend/src/components/AgentMatrix/AgentCard.tsx` — Individual agent card
- `frontend/src/components/AgentMatrix/AgentDetailView.tsx` — Full detail page
- `frontend/src/components/AgentMatrix/NeuralArchitectureDiagram.tsx` — Stage flow SVG
- `frontend/src/components/AgentMatrix/CoreConfigPanel.tsx` — LLM config display
- `frontend/src/components/AgentMatrix/ToolbeltPanel.tsx` — Tools with health
- `frontend/src/components/AgentMatrix/ExecutionTracePanel.tsx` — Trace log display
- `frontend/src/components/AgentMatrix/RecentCasesPanel.tsx` — Session history
- `frontend/src/components/AgentMatrix/AgentMatrixFooter.tsx` — Summary footer

### Types
- Add `AgentInfo`, `AgentExecution`, `AgentMatrixResponse` to `frontend/src/types/index.ts`
