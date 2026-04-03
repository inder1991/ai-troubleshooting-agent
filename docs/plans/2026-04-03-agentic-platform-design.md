# Agentic Platform — Approach 2 Design

**Date:** 2026-04-03
**Status:** Approved
**Scope:** Week 1 — UI layer. Week 2+ — Backend platform layer.

---

## Problem Statement

DebugDuck has 25 agents across 3 domains (app, network, database) but is not a true agentic platform. Current gaps:

- Agents are not independently callable — every agent must go through a supervisor
- New workflows require modifying a 3,331-line hardcoded state machine
- Domain orchestrators (app supervisor, network orchestrator, DB orchestrator) have incompatible interfaces — agents cannot be mixed across domains
- Results are in-memory only — lost on server restart
- No input/output contracts — bad inputs cause silent failures deep in agent logic
- No workflow composition without writing Python
- No cross-domain workflows possible
- No audit trail of who triggered what and when

---

## Architecture Overview

Three new primitives introduced on top of existing agents:

```
┌─────────────────────────────────────────────────────┐
│                   API Layer                         │
│  POST /agents/{id}/run                              │
│  POST /workflows/{id}/runs                          │
│  GET  /runs/{run_id}                                │
│  POST /runs/{run_id}/gates/{step_id}/approve        │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │    WorkflowEngine     │  Primitive 1
         │  (DAG executor)       │
         └───────────┬───────────┘
                     │ dispatches
         ┌───────────▼───────────┐
         │    AgentManifest      │  Primitive 2
         │  (contract per agent) │
         └───────────┬───────────┘
                     │ persists to
         ┌───────────▼───────────┐
         │    ExecutionStore     │  Primitive 3
         │  (SQLite → Postgres)  │
         └───────────────────────┘
```

---

## Primitive 1: AgentManifest

Every agent declares a YAML contract:

```yaml
id: metrics_agent
version: "2.0"
name: Metrics Analyst
kind: python          # or "http" for external agents

input_schema:
  type: object
  required: [service_name]
  properties:
    service_name: { type: string }
    time_window:  { type: string, default: "1h" }
    namespace:    { type: string }

output_schema:
  type: object
  properties:
    anomalies:   { type: array }
    confidence:  { type: number, minimum: 0, maximum: 1 }
    summary:     { type: string }

tools: [query_prometheus_range, detect_spikes]
timeout_s: 60
max_iterations: 10

retry:
  max_attempts: 3
  backoff: exponential

llm:
  retry:
    max_attempts: 3
    on_status: [502, 503, 529]

legacy_adapter:
  shadow_mode: true
  reads:
    service_name: "state.service_name"
    time_window:  "state.time_window"
    namespace:    "state.namespace"
    error_hints:  "state.all_findings"
  writes:
    findings:        "state.all_findings.extend"
    reasoning_entry: "state.reasoning_chain.append"
    agent_done:      "state.agents_completed.add"
    confidence:      "state.per_agent_confidence[metrics_agent]"
```

For external HTTP agents:
```yaml
id: custom_security_scanner
kind: http
endpoint: https://internal-scanner.corp/run
auth: { type: bearer, secret_env: SCANNER_TOKEN }
input_schema: { ... }
output_schema: { ... }
```

---

## Primitive 2: WorkflowEngine

Workflows defined as YAML DAGs:

```yaml
id: app_diagnostics
name: Application Diagnostics
version: "3.0"
trigger: [api, event]

triggers:
  inputs:
    - name: service_name
      label: "Service Name"
      type: string
      required: true
    - name: time_window
      label: "Time Window"
      type: select
      options: ["15m", "1h", "6h", "24h"]
      default: "1h"
    - name: namespace
      label: "Kubernetes Namespace"
      type: string
      required: false
      default: "default"

steps:
  - id: logs
    agent: log_analysis_agent
    input:
      service_name: "{{ trigger.service_name }}"
      time_window:  "{{ trigger.time_window }}"

  - id: metrics
    agent: metrics_agent
    depends_on: []
    input:
      service_name: "{{ trigger.service_name }}"

  - id: k8s
    agent: k8s_agent
    depends_on: []
    input:
      namespace: "{{ trigger.namespace }}"

  - id: critic
    agent: critic_agent
    depends_on: [logs, metrics, k8s]
    condition: "{{ steps.logs.output.confidence < 0.7 }}"
    input:
      findings: "{{ steps.logs.output.findings + steps.metrics.output.anomalies }}"

  - id: fix
    agent: fix_generator
    depends_on: [critic]
    gate: human_approval
    gate_timeout: 30m
    gate_timeout_action: skip
    input:
      root_cause: "{{ steps.critic.output.root_cause }}"
```

WorkflowEngine capabilities:
- Validates DAG at load time — detects cycles, unknown agents, missing required inputs
- Resolves parallel steps via topological sort
- Three execution modes: sync, async (job-based), event-driven
- Conditions on steps — skip based on previous outputs
- Fan-out — one step spawns N parallel child runs over a list
- Human gates with TTL and auto-resolution
- Per-step retry with exponential backoff

---

## Primitive 3: ExecutionStore

SQLite schema (Postgres-compatible — no SQLite-specific types):

```sql
CREATE TABLE workflow_runs (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  status TEXT NOT NULL,           -- queued | running | completed | failed | interrupted | abandoned
  trigger_input TEXT NOT NULL,    -- JSON
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  created_by TEXT
);

CREATE TABLE step_executions (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  step_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  agent_version TEXT NOT NULL,
  status TEXT NOT NULL,           -- pending | running | completed | failed | timed_out | skipped
  input_json TEXT,
  output_json TEXT,
  error TEXT,
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  retry_count INTEGER DEFAULT 0,
  token_usage TEXT                -- JSON
);

CREATE TABLE step_events (
  id TEXT PRIMARY KEY,
  step_execution_id TEXT NOT NULL REFERENCES step_executions(id),
  event_type TEXT NOT NULL,
  payload TEXT,
  emitted_at TIMESTAMP NOT NULL
);

CREATE TABLE human_gates (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  step_id TEXT NOT NULL,
  status TEXT NOT NULL,           -- pending | approved | rejected | timed_out
  requested_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP,
  resolved_at TIMESTAMP,
  resolved_by TEXT
);
```

---

## BaseAgent SDK

Every agent subclasses BaseAgent and implements one method:

```python
class MetricsAgent(BaseAgent):
    manifest = "agents/metrics_agent.yaml"

    async def execute(self, input: AgentInput) -> AgentOutput:
        service_name = input.get("service_name")
        result = await self.tool("query_prometheus_range", service=service_name)
        await self.emit("progress", f"Found {len(result)} anomalies")
        return AgentOutput(
            confidence=0.85,
            anomalies=result.spikes,
            summary="CPU spike detected at 14:32 UTC"
        )
```

BaseAgent provides automatically:
- Input validation against manifest schema before execute() is called
- Output validation against manifest output_schema
- Event streaming via self.emit() → WebSocket + ExecutionStore
- Budget tracking (llm_calls, tool_calls, tokens) with auto wrap-up
- Timeout enforcement via asyncio.wait_for
- Execution record written to ExecutionStore on start and finish
- Dual interface: run() for existing supervisor, execute() for platform

### DiagnosticState Compatibility

BaseAgent.run() bridges the existing shared-state supervisor:

```python
async def run(self, context, event_emitter=None):
    if isinstance(context, DiagnosticState):
        input = self._read_from_state(context)   # snapshot declared fields
        output = await self.execute(input)
        async with context._write_lock:           # serialized write-back
            self._write_to_state(context, output)
    else:
        input = AgentInput.from_dict(context)
        output = await self.execute(input)
    return output.to_legacy_result()
```

Migration safety:
- `shadow_mode: true` in manifest — runs both old and new paths, uses old result, logs diffs
- Zero diffs observed for 1 week → flip to `shadow_mode: false`
- Supervisor never knows anything changed — it still calls run()

---

## Edge Cases Handled

| Edge Case | Handling |
|---|---|
| Agent hangs | asyncio.wait_for(timeout_s) — step marked timed_out, workflow continues with NegativeFinding |
| Server crash mid-run | ExecutionStore has all completed steps — run marked interrupted, inspectable post-mortem |
| Bad input to agent | Schema validation at API boundary — 422 with clear field-level error |
| Concurrent agents writing shared state | asyncio.Lock per DiagnosticState instance — writes serialized |
| LLM provider down | Per-manifest retry with backoff on 502/503/529 |
| Circular workflow dependency | DAG validation at load time — WorkflowDefinitionError before registration |
| Human gate abandoned | gate_timeout + gate_timeout_action in manifest — auto-resolved by background cleanup |
| Low confidence findings | Workflow condition branches on step output confidence — declarative, not hardcoded |
| Cross-domain workflow | All agents share BaseAgent contract — any agent usable in any workflow |
| No audit trail | ExecutionStore records created_by, trigger_input, started_at on every run |

---

## Frontend UI (Week 1 — Existing API Only)

### View 1: Agent Catalog
- API: `GET /api/v4/agents`, `GET /api/v4/agents/{id}/executions`
- 25 agents in a grid — name, version, kind, live health status
- Click → detail panel: input/output schema table, last 5 executions
- "Try it" disabled (tooltip: "Available after platform backend ships")
- "Copy YAML" generates a workflow step stub

### View 2: Workflow Builder
- No backend needed — pure frontend
- Monaco/CodeMirror YAML editor + ReactFlow DAG preview side by side
- Pre-loaded with app_diagnostics as starting template
- Live validation: unknown agents, cycles, missing fields
- "Run" disabled (tooltip: "Workflow execution available next week")
- "Save" persists to localStorage

### View 3: Workflow Runs
- API: existing sessions API + WebSocket stream
- Lists past investigations reframed as "runs"
- Step-by-step breakdown per run (agent → status → duration → one-line summary)
- Live steps stream via existing WebSocket
- Human gate renders inline for pending approvals

### Trigger Flow (Week 2+ once backend ships)

1. Developer clicks "▶ Run" on any workflow
2. Modal renders input form from workflow's `triggers.inputs` YAML — no hardcoded forms
3. On submit → `POST /api/v4/workflows/{id}/runs`
4. Response: `{ run_id, status: "queued", stream_url }`
5. UI navigates to live run view — steps light up via WebSocket
6. Human gates render inline — approve calls `POST /runs/{id}/gates/{step_id}/approve`

---

## Migration Sequence (Backend — Week 2+)

| Phase | Work | Supervisor affected? |
|---|---|---|
| 1 | Add BaseAgent SDK, AgentManifest loader, ExecutionStore, DiagnosticStateAdapter | No |
| 2 | Add `POST /api/v4/agents/{id}/run`. Migrate MetricsAgent + LogAgent with shadow_mode: true | No |
| 3 | Build WorkflowEngine. Convert app_diagnostics supervisor → YAML (shadow mode) | No |
| 4 | Migrate remaining agents. Convert network + DB orchestrators → YAML | No |
| 5 | Ship first cross-domain workflow. Add HttpAgentAdapter for external agents | No |

---

## Storage Strategy

- **Week 1–2:** SQLite (existing infra, zero new dependencies)
- **Future:** Postgres — schema is compatible, switch by changing connection string
- No SQLite-specific types used (no AUTOINCREMENT, no BLOB for JSON)

---

## What Is Explicitly Out of Scope (This Design)

- Agent versioning with rollout controls
- Visual drag-and-drop workflow builder (YAML editor ships first)
- Multi-tenant execution isolation
- Event bus (Redis-backed pub/sub)
- Agent marketplace / public registry
