# AI Troubleshooting System — Complete Documentation

**Product Name:** DebugDuck Command Center
**Version:** 3.0.0 (V4 API)
**Architecture:** Multi-Agent AI Diagnostic Platform
**Last Updated:** February 2026

---

## Table of Contents

1. [What Is This System?](#1-what-is-this-system)
2. [Core Concepts and AI Techniques](#2-core-concepts-and-ai-techniques)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [The Agent System — How AI Investigates](#4-the-agent-system--how-ai-investigates)
5. [End-to-End Workflow — A Complete Example](#5-end-to-end-workflow--a-complete-example)
6. [The Supervisor — Orchestrating the Investigation](#6-the-supervisor--orchestrating-the-investigation)
7. [Agent Deep Dives](#7-agent-deep-dives)
8. [Evidence System — How Confidence Is Built](#8-evidence-system--how-confidence-is-built)
9. [The Fix Pipeline — From Diagnosis to Pull Request](#9-the-fix-pipeline--from-diagnosis-to-pull-request)
10. [Human-in-the-Loop Gates](#10-human-in-the-loop-gates)
11. [The War Room UI](#11-the-war-room-ui)
12. [Real-Time Communication — WebSockets](#12-real-time-communication--websockets)
13. [API Reference](#13-api-reference)
14. [Governance and Auditability](#14-governance-and-auditability)
15. [Integration Points](#15-integration-points)
16. [Incident Memory — Learning from the Past](#16-incident-memory--learning-from-the-past)
17. [Security Model](#17-security-model)
18. [Project Structure](#18-project-structure)
19. [Setup and Running](#19-setup-and-running)
20. [Glossary](#20-glossary)

---

## 1. What Is This System?

This is an **AI-powered Site Reliability Engineering (SRE) platform** that automates the investigation of production incidents. When a service starts failing — throwing errors, spiking latency, or crashing pods — this system deploys a team of specialized AI agents to investigate the problem from multiple angles simultaneously, much like a human SRE team would in a war room.

### What It Does

1. **Accepts an incident report** — a service name, time window, and optional trace ID
2. **Deploys 7 specialized AI agents** to investigate logs, metrics, Kubernetes state, distributed traces, source code, and recent changes
3. **Correlates findings** across all data sources to identify root cause
4. **Validates conclusions** through an AI critic agent that cross-checks every finding
5. **Generates a code fix** with automated verification
6. **Creates a pull request** after human approval

### The Problem It Solves

In a typical production incident:
- An SRE manually checks 5-10 different dashboards (Grafana, Kibana, K8s, Jaeger, GitHub)
- They mentally correlate signals across these tools
- They form a hypothesis, check code, and write a fix
- Total time: 30 minutes to several hours

This system compresses that workflow into **2-3 minutes** by running AI agents in parallel across all data sources and automatically synthesizing findings.

---

## 2. Core Concepts and AI Techniques

### 2.1 Multi-Agent Architecture

Rather than using a single monolithic AI prompt, the system uses **specialized agents** — each focused on one data source. This is the "team of experts" pattern from AI research.

**Why multi-agent?**
- **Depth over breadth**: A log analysis agent has a deep system prompt about log patterns, error formats, and ELK query syntax. A metrics agent knows about RED/USE methodology and PromQL. Specialization produces better results than asking one model to do everything.
- **Parallelism**: Agents can run concurrently since they operate on independent data sources.
- **Composability**: New agents can be added without modifying existing ones.
- **Explainability**: Each agent produces its own evidence trail, making the overall conclusion auditable.

### 2.2 ReAct Pattern (Reason + Act)

Most agents use the **ReAct pattern** — an AI technique where the model alternates between:

1. **Reasoning**: "Based on the error pattern I see in logs, I should check CPU metrics for this service"
2. **Acting**: Calling a tool (e.g., `query_prometheus_range`)
3. **Observing**: Reading the tool's output
4. **Reasoning again**: "CPU is normal, but memory shows a spike at 14:23 UTC. Let me check pod restarts..."

This loop continues until the agent has enough evidence to reach a conclusion or exhausts its iteration limit.

```
┌──────────────────────────────────────────────┐
│                 ReAct Loop                    │
│                                              │
│   ┌─────────┐    ┌────────┐    ┌──────────┐ │
│   │ Reason  │───►│  Act   │───►│ Observe  │ │
│   └────▲────┘    └────────┘    └────┬─────┘ │
│        │                            │        │
│        └────────────────────────────┘        │
│                                              │
│   Repeat until: conclusion reached           │
│                  OR max iterations hit        │
└──────────────────────────────────────────────┘
```

**Concrete example — Metrics Agent:**
- **Turn 1 (Discovery)**: "What Prometheus metrics exist for `payment-service`?" → calls `list_metrics` tool
- **Turn 2 (Acquisition)**: "Let me query `http_request_duration_seconds` for the last hour with a 24h baseline offset" → calls `query_prometheus_range`
- **Turn 3 (Synthesis)**: "I see a 340% latency spike at 14:23. Error rate jumped from 0.2% to 12.4%. The CPU is normal but memory is at 92%." → outputs structured findings

### 2.3 Evidence Pins and Confidence Ledger

Every agent produces **Evidence Pins** — atomic claims backed by data:

```
Evidence Pin {
  claim: "Memory usage spiked to 92% at 14:23 UTC"
  supporting_evidence: ["prometheus_query_memory_usage_bytes"]
  source_agent: "metrics_agent"
  confidence: 0.85
  evidence_type: "metric"
}
```

These pins feed into a **Confidence Ledger** — a weighted scoring system:

```
Confidence Ledger:
  log_confidence:     75%  (weight: 0.25)
  metrics_confidence: 85%  (weight: 0.30)
  tracing_confidence: 70%  (weight: 0.20)
  k8s_confidence:     80%  (weight: 0.15)
  code_confidence:    65%  (weight: 0.05)
  change_confidence:  55%  (weight: 0.05)
  ─────────────────────────────────────
  weighted_final:     75.5%
```

### 2.4 Causal Reasoning

The system doesn't just list facts — it builds a **causal graph** connecting symptoms to root causes:

```
[Memory Leak in PaymentValidator.java:123]  ── causes ──►  [OOMKilled pods]
                                             ── causes ──►  [Latency spike at 14:23]
                                             ── causes ──►  [Error rate increase]

[Recent commit abc123 by dev@example.com]   ── contributes_to ──►  [Memory Leak]
  (changed PaymentValidator 2h before incident)
```

This graph is built by the **EvidenceGraphBuilder** (causal engine), which classifies each finding as:
- **Root Cause** (source node with no incoming edges)
- **Contributing Factor** (medium confidence, connects cause to symptoms)
- **Symptom** (observable effect of the root cause)

### 2.5 Adversarial Validation (Critic Agent)

A unique aspect of this system: after all agents complete their work, a **Critic Agent** reviews every finding. The critic is a read-only agent that:

- Cannot produce its own findings
- Can only validate or challenge existing ones
- Cross-references each finding against ALL available data
- Returns a verdict: `validated`, `challenged`, or `insufficient_data`

This is inspired by **adversarial AI techniques** where one model checks another's work, reducing hallucination and increasing trustworthiness.

### 2.6 Hybrid Deterministic + LLM Approach

Not everything is done by AI. Each agent uses a **hybrid approach**:

| Step | Method | Why |
|------|--------|-----|
| Query Elasticsearch | Deterministic (Python code) | Reliable, fast, exact |
| Parse JSON responses | Deterministic | No AI needed for structured data |
| Detect spike thresholds | Statistical (mean + 2 std dev) | Deterministic math is more reliable |
| Understand error semantics | LLM (Claude) | Requires natural language understanding |
| Correlate across signals | LLM (Claude) | Requires reasoning about causality |
| Generate fix code | LLM (Claude) | Requires code understanding |

### 2.7 Patient Zero Detection

The system identifies the **first service to fail** in a cascade — the "Patient Zero" of the incident. This is done by:

1. Sorting all log entries by timestamp across all services
2. Finding the earliest error occurrence
3. Tracing dependency chains to see which service's failure caused others to fail
4. Mapping the propagation path

---

## 3. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + TypeScript)            │
│                                                             │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐ │
│  │ Sidebar  │  │   War Room UI    │  │    Chat Panel     │ │
│  │  Nav     │  │ (CSS Grid 12col) │  │ (Human-in-Loop)   │ │
│  └──────────┘  │                  │  └───────────────────┘ │
│                │ Investigator(3)  │                         │
│                │ Evidence(5)      │                         │
│                │ Navigator(4)     │                         │
│                └──────────────────┘                         │
│                        │ REST + WebSocket                   │
└────────────────────────┼────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ FastAPI │  Port 8000
                    │ Server  │
                    └────┬────┘
                         │
┌────────────────────────┼────────────────────────────────────┐
│                    BACKEND (Python)                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              SupervisorAgent (Orchestrator)           │   │
│  │   State Machine · Agent Dispatch · Evidence Merge    │   │
│  └──────────┬──────────┬──────────┬──────────┬─────────┘   │
│             │          │          │          │               │
│  ┌──────────▼┐  ┌──────▼──────┐ ┌▼────────┐ ┌▼───────────┐│
│  │ Log Agent │  │Metrics Agent│ │K8s Agent│ │Tracing Agent││
│  │(Elastic)  │  │(Prometheus) │ │(kubectl)│ │(Jaeger/ELK) ││
│  └───────────┘  └─────────────┘ └─────────┘ └─────────────┘│
│             │          │          │          │               │
│  ┌──────────▼┐  ┌──────▼──────┐ ┌▼────────────────────────┐│
│  │Code Agent │  │Change Agent │ │    Critic Agent          ││
│  │(GitHub/FS)│  │(GitHub API) │ │ (Cross-validates ALL)    ││
│  └───────────┘  └─────────────┘ └──────────────────────────┘│
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐ │
│  │ Causal Engine │  │Impact Analyzer│  │  Memory Store   │ │
│  │(Evidence Graph)│  │(Blast Radius) │  │(Past Incidents) │ │
│  └───────────────┘  └───────────────┘  └─────────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Fix Pipeline (Agent 3)                     │   │
│  │  Generate Fix → Verify → Stage PR → Human Approval  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼─────┐   ┌─────▼────┐   ┌──────▼─────┐
    │Elastic   │   │Prometheus│   │ Kubernetes │
    │Search    │   │          │   │ / OpenShift│
    │(Logs)    │   │(Metrics) │   │            │
    └──────────┘   └──────────┘   └────────────┘
         │               │               │
    ┌────▼─────┐   ┌─────▼────┐   ┌──────▼─────┐
    │ Jaeger   │   │  GitHub  │   │Jira/Confl. │
    │(Traces)  │   │  (Code)  │   │(Ticketing) │
    └──────────┘   └──────────┘   └────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18, TypeScript, Vite | Single-page application |
| **Styling** | Tailwind CSS 3.4, Framer Motion | Dark theme, animations |
| **Visualization** | Mermaid, Custom SVG, Lucide icons | Diagrams, topology maps |
| **Backend** | Python, FastAPI | REST API + WebSocket server |
| **AI/LLM** | Anthropic Claude (via API) | All reasoning and code generation |
| **Orchestration** | LangGraph + LangChain | Agent coordination and tool calling |
| **Observability** | Elasticsearch, Prometheus, Jaeger | Log/metric/trace data sources |
| **Infrastructure** | Kubernetes client library | Pod/deployment/event queries |
| **Version Control** | GitHub API | Commit history, PR creation |

---

## 4. The Agent System — How AI Investigates

### Agent Overview

| # | Agent | Data Source | Technique | Key Output |
|---|-------|------------|-----------|------------|
| 1 | **Log Analysis Agent** | Elasticsearch | Hybrid (deterministic + 1 LLM call) | Error patterns, patient zero, stack traces |
| 2 | **Metrics Agent** | Prometheus | ReAct (3 turns) | Metric anomalies, spikes, RED/USE signals |
| 3 | **K8s Agent** | Kubernetes API | ReAct (2 turns) | Pod health, crash loops, OOM kills, events |
| 4 | **Tracing Agent** | Jaeger / Elasticsearch | ReAct (3 turns) | Service call chain, failure point, latency |
| 5 | **Code Navigator Agent** | GitHub / Local filesystem | ReAct (up to 15 turns) | Root cause location, impacted files, dependency graph |
| 6 | **Change Agent** | GitHub API | ReAct (4 turns) | Recent commits, risk scoring, change correlation |
| 7 | **Critic Agent** | All agent outputs | Read-only (1 LLM call) | Validation verdicts for every finding |

### Agent Execution Strategy

Agents don't all run. The supervisor decides which agents to activate based on available inputs:

```
ALWAYS run:  Log Agent, Metrics Agent
IF namespace provided:  + K8s Agent
IF trace_id provided:   + Tracing Agent
IF repo_url provided:   + Code Agent, Change Agent
ALWAYS last:            Critic Agent (needs all findings)
```

---

## 5. End-to-End Workflow — A Complete Example

### Scenario

Your `payment-service` starts returning 500 errors at 14:20 UTC. Users report failed checkouts. You need to find out why.

### Step 1: Start a New Mission

You open DebugDuck and click **"New Mission"** in the sidebar. The capability form appears.

You fill in:
- **Service Name:** `payment-service`
- **ELK Index:** `app-logs-*`
- **Timeframe:** `1h`
- **Trace ID:** `abc123def456` (from a failed request)
- **Namespace:** `production`
- **Cluster URL:** `https://openshift.example.com`
- **Repo URL:** `https://github.com/company/payment-service`

You click **"Start Investigation"**.

### Step 2: Backend Creates the Session

```
POST /api/v4/session/start
{
  "serviceName": "payment-service",
  "elkIndex": "app-logs-*",
  "timeframe": "1h",
  "traceId": "abc123def456",
  "namespace": "production",
  "clusterUrl": "https://openshift.example.com",
  "repoUrl": "https://github.com/company/payment-service"
}
```

The backend:
1. Generates a UUID session ID: `e7f3a291-...`
2. Generates a human-readable incident ID: `INC-20260223-A3F7`
3. Creates a `SupervisorAgent` instance
4. Creates an `EventEmitter` for WebSocket communication
5. Starts the diagnosis as a background task
6. Returns the session ID immediately — the frontend doesn't wait

### Step 3: The Investigation Begins

The frontend connects via WebSocket (`ws://localhost:8000/ws/troubleshoot/e7f3a291-...`) and starts receiving real-time events. The War Room UI opens.

**The supervisor dispatches agents.** Because all inputs were provided, ALL 7 agents activate:

#### Log Agent (5-10 seconds)

Queries Elasticsearch:
```
GET app-logs-*/_search
{
  "query": {
    "bool": {
      "must": [
        {"match": {"service": "payment-service"}},
        {"range": {"@timestamp": {"gte": "now-1h", "lte": "now"}}}
      ]
    }
  },
  "size": 2000,
  "sort": [{"@timestamp": "desc"}]
}
```

Finds 847 error logs. Extracts:
- **Primary pattern**: `NullPointerException in PaymentValidator.validate()` (423 occurrences)
- **Stack trace**: `PaymentValidator.java:123 → PaymentController.java:45 → ...`
- **Patient Zero**: `payment-service` — first error at `14:20:03 UTC`, cascade hit `order-service` at `14:20:15 UTC`
- **Suggested PromQL**: `rate(http_server_requests_seconds_count{service="payment-service",status="500"}[5m])`

**WebSocket event sent to frontend:**
```json
{
  "agent_name": "log_agent",
  "event_type": "finding",
  "message": "Identified NullPointerException in PaymentValidator — 423 occurrences in last hour"
}
```

#### Metrics Agent (10-15 seconds)

Three ReAct turns:
1. **Discovery**: Lists available Prometheus metrics for `payment-service`
2. **Acquisition**: Queries 4 key metrics with 24h baseline offset
3. **Synthesis**: Detects anomalies

Finds:
- **Latency spike**: P99 jumped from 120ms to 2,400ms at 14:20 UTC (+1900%)
- **Error rate surge**: From 0.2% to 12.4% at 14:20 UTC
- **Memory spike**: From 60% to 92% at 14:18 UTC (2 minutes BEFORE errors)
- **CPU normal**: Steady at 35%

The memory spike 2 minutes before errors is a critical clue.

#### K8s Agent (5-10 seconds)

Two ReAct turns:
1. **Cluster check**: Connectivity test, pod status, events
2. **Deep dive**: Deployment rollout, pod logs for crashers

Finds:
- **3 of 5 pods restarted** in the last hour
- **2 pods in CrashLoopBackOff** with `OOMKilled` termination reason
- **K8s event**: `Container killed by OOM (memory limit: 512Mi exceeded)`
- **HPA**: Tried to scale up but hit max replicas (5)

#### Tracing Agent (5-10 seconds)

Queries Jaeger for trace `abc123def456`:

```
payment-gateway (12ms) → payment-service (2,400ms - ERROR) → order-service (timeout)
                                                            → inventory-service (timeout)
```

Finds: The `payment-service` span shows the `NullPointerException` as the root failure. Downstream services timed out waiting for payment-service's response.

#### Code Agent (20-30 seconds)

Clones the repository and performs 15 ReAct turns:

1. Maps stack trace `PaymentValidator.java:123` to the actual file
2. Reads `PaymentValidator.java` — finds the `validate()` method
3. Identifies the null dereference: `customer.getAddress().getZipCode()` — `getAddress()` returns null
4. Traces the call chain: `PaymentController.processPayment()` → `PaymentValidator.validate()`
5. Checks recent changes to this file
6. Builds a Mermaid dependency diagram

Output: Root cause at `PaymentValidator.java:123`, impacted files list, call chain visualization.

#### Change Agent (10-15 seconds)

Queries GitHub commits in the last 48 hours:

Finds:
- **Commit `abc1234`** by `dev@company.com` at 12:15 UTC (2 hours before incident)
  - Modified `PaymentValidator.java` — changed address validation logic
  - **Risk Score: 0.92** (high temporal correlation + exact file match)
- 3 other commits with lower risk scores (unrelated files)

#### Critic Agent (10-20 seconds)

Reviews ALL findings from all agents:

```
Finding: "NullPointerException in PaymentValidator.java:123"
  Verdict: VALIDATED
  Reasoning: Consistent across logs (423 errors), code analysis (null dereference found),
             and tracing (payment-service span shows NPE). Memory spike 2 minutes before
             errors supports OOM hypothesis correlated with this code path.

Finding: "Commit abc1234 introduced the bug"
  Verdict: VALIDATED
  Reasoning: Temporal correlation is strong (2h before), file match is exact
             (PaymentValidator.java), and the diff shows address validation
             logic was changed, consistent with the NPE on getAddress().
```

### Step 4: Results Arrive in the War Room

The War Room UI now shows:

**Left Column (Investigator)**:
- **Patient Zero banner**: `payment-service` — first error at 14:20:03 UTC
- **Timeline**: Chronological events from all agents
- **Chat**: You can ask follow-up questions

**Center Column (Evidence Findings)**:
- Priority-ordered evidence cards with color-coded borders:
  - Red border (Log Agent): NullPointerException pattern
  - Cyan border (Metrics Agent): Memory spike + error rate surge
  - Orange border (K8s Agent): OOMKilled pods, CrashLoopBackOff
  - Emerald border (Code Agent): Root cause at PaymentValidator.java:123
- Each card shows a **Causal Role Badge**: `ROOT CAUSE`, `CASCADING SYMPTOM`, or `CORRELATED`

**Right Column (Navigator)**:
- **Service Topology**: SVG visualization showing `payment-service` glowing red, with arrows to downstream services
- **Metrics Validation Dock**: Live PromQL queries you can run
- **Agent Status**: All 7 agents completed with checkmarks

**Overall Confidence**: 86% (weighted from all agents)

### Step 5: Attestation Gate

Before you can request a fix, you must **attest to the findings**. A modal appears:

> **Discovery Attestation Required**
>
> The AI has completed its investigation and identified a root cause.
> Please review the findings and approve or reject them.
>
> [Approve] [Reject]

You click **Approve**. This sets `_attestation_acknowledged = True` on the supervisor, which unlocks the fix generation gate.

### Step 6: Generate Fix

You type **"fix"** in the chat (or click the Generate Fix button). The system:

1. Checks the attestation gate (must be approved)
2. The Change Agent generates a code fix using the diagnosis findings
3. The fix is statically validated (AST parsing, linting)
4. A cross-agent review checks for regressions
5. An impact assessment evaluates blast radius

The fix appears in the UI for your review:

```diff
--- a/src/main/java/com/company/PaymentValidator.java
+++ b/src/main/java/com/company/PaymentValidator.java
@@ -121,3 +121,7 @@
     public ValidationResult validate(Customer customer) {
-        String zipCode = customer.getAddress().getZipCode();
+        Address address = customer.getAddress();
+        if (address == null) {
+            return ValidationResult.invalid("Customer address is required");
+        }
+        String zipCode = address.getZipCode();
         // ... rest of validation
```

### Step 7: Approve and Create PR

You review the fix, click **"Approve"**, and the system creates a pull request on GitHub:

> **PR #142**: Fix NullPointerException in PaymentValidator address validation
>
> Root cause: `customer.getAddress()` returns null when address is not set,
> causing NPE at line 123. Added null check with descriptive error message.
>
> Incident: INC-20260223-A3F7
> Confidence: 86%
> Validated by: AI Critic Agent (cross-checked against 6 data sources)

**Total time from "Start Investigation" to PR: approximately 3 minutes.**

---

## 6. The Supervisor — Orchestrating the Investigation

### State Machine

The supervisor manages a state machine with these phases:

```
INITIAL
  │
  ▼
LOG_ANALYSIS ─────► METRICS_ANALYSIS ─────► K8S_ANALYSIS
                                                │
                                                ▼
TRACE_ANALYSIS ◄─── CODE_ANALYSIS ◄─── CHANGE_ANALYSIS
  │
  ▼
CRITIC_REVIEW ─────► IMPACT_ANALYSIS ─────► DIAGNOSIS_COMPLETE
                                                │
                                          [Attestation Gate]
                                                │
                                                ▼
                                          FIX_IN_PROGRESS ─────► FIX_COMPLETE
```

### Key Responsibilities

1. **Agent Dispatch**: Decides which agents to run based on available inputs
2. **State Management**: Tracks phase, confidence, findings across all agents
3. **Evidence Merging**: Combines findings from all agents into a unified view
4. **Human-in-the-Loop**: Manages gates for repo confirmation, attestation, fix approval
5. **Re-investigation**: Can trigger a second investigation round if confidence is low

### Round-Based Execution

The supervisor runs up to 10 rounds. Each round:

1. Calls `_decide_next_agents(state)` — returns list of agents to run
2. Runs those agents (with the full diagnostic state as context)
3. Merges their findings into the state
4. Checks if more agents are needed
5. If no more agents needed → run impact analysis → mark `DIAGNOSIS_COMPLETE`

A maximum of 1 re-investigation cycle is allowed (if the critic challenges too many findings).

---

## 7. Agent Deep Dives

### 7.1 Log Analysis Agent

**Architecture**: Hybrid (deterministic query + single LLM synthesis)

**Process**:
1. Build Elasticsearch query with configurable field mapping (supports different log formats)
2. Fetch up to 2,000 recent logs
3. Parse structured fields: timestamp, level, message, service, trace_id, stack_trace
4. Group errors by pattern (using message similarity)
5. Single LLM call to synthesize:
   - Primary error pattern
   - Root cause hypothesis from log evidence
   - Patient Zero identification (first failing service)
   - Suggested PromQL queries for metrics validation
   - Inferred service dependencies

**Field Mapping** (supports diverse log formats):
```
timestamp → [@timestamp, timestamp, time]
level     → [level, severity, log_level]
message   → [message, msg, log_message]
service   → [service, service.name, app]
trace_id  → [trace_id, traceId, tracing.trace_id]
```

### 7.2 Metrics Agent

**Architecture**: ReAct with 3-turn strategy

**Turn 1 — Discovery**:
- Tool: `list_metrics` — discovers what Prometheus metrics exist for the service
- Identifies available RED (Rate, Errors, Duration) and USE (Utilization, Saturation, Errors) metrics

**Turn 2 — Signal Acquisition**:
- Tool: `query_prometheus_range` — fetches metrics for the incident time window
- Also queries a 24-hour offset window to establish baseline

**Turn 3 — Synthesis**:
- Statistical spike detection: value > mean + 2*stddev of baseline
- Compares incident window to baseline, calculates percentage change
- Outputs anomalies, time-series data, event markers

### 7.3 Kubernetes Agent

**Architecture**: ReAct with 2-turn strategy

**Turn 1 — Health Check**:
- `test_cluster_connectivity` — verify API access
- `get_pod_status` — all pods in namespace, check ready/restart/OOM
- `get_events` — warnings and errors in the last hour

**Turn 2 — Deep Dive**:
- `get_deployment` — rollout status, replicas desired vs available
- `get_pod_logs` — fetch logs from crashing pods
- `get_hpa_status` — horizontal pod autoscaler state

**Health Signals**:
| Signal | Detection Rule |
|--------|---------------|
| Crash Loop | restart_count >= 3 AND status in (CrashLoopBackOff, Error) |
| OOM Killed | last_termination_reason == "OOMKilled" |
| Image Pull Error | init container failures or image pull errors |
| Not Ready | ready_containers < total_containers |

### 7.4 Tracing Agent

**Architecture**: ReAct with 3-turn strategy and fallback

**Primary path** (Jaeger available):
1. `list_traced_services` — discover services in Jaeger
2. `query_jaeger` — fetch full trace by trace ID
3. Analyze spans: find failure point, latency bottleneck, cascade path

**Fallback path** (Jaeger unavailable):
1. `search_elk_trace` — reconstruct trace from Elasticsearch logs using trace_id correlation
2. Build approximate service call chain from log timestamps

### 7.5 Code Navigator Agent

**Architecture**: ReAct with up to 15 turns (most complex agent)

**Four responsibilities executed in sequence**:

1. **Codebase Mapping**: Map stack trace file paths to repository files
   - Normalizes paths (e.g., `/app/service.py` → `service.py`)
   - Handles Java package → file path conversion

2. **Context Retrieval**: Read the actual source code at the error locations
   - Extracts function definitions, surrounding context
   - Reads import statements, class hierarchies

3. **Call Chain Analysis**: Build the execution path that led to the error
   - Traces method calls from entry point to failure point
   - Identifies error propagation path

4. **Dependency Tracking**: Find external and internal dependencies
   - Scans imports for shared resources
   - Identifies potential conflicts
   - Generates a Mermaid diagram of the dependency graph

### 7.6 Change Agent

**Architecture**: ReAct with 4-turn strategy

**Process**:
1. Query GitHub for commits in the last 48 hours
2. Get deployment rollout history from Kubernetes
3. Check ConfigMap/Secret changes
4. Score each change for risk:

**Risk Scoring Formula**:
| Factor | Weight | Description |
|--------|--------|-------------|
| Temporal correlation | 40% | How close to incident start time? |
| Scope overlap | 30% | Do changed files relate to the error location? |
| Change size | 15% | Larger diffs = higher risk |
| Review status | 15% | Was the PR reviewed before merge? |

### 7.7 Critic Agent

**Architecture**: Read-only, single LLM call

**Unique properties**:
- **Cannot produce findings** — only validates or challenges existing ones
- **Has access to ALL agent outputs** — cross-references across data sources
- **Verdicts are final** for display purposes (no back-and-forth)

**Verdict types**:
| Verdict | Meaning |
|---------|---------|
| `validated` | Finding is consistent across multiple data sources |
| `challenged` | Finding contradicts evidence from other sources |
| `insufficient_data` | Cannot confirm or deny — not enough evidence |

---

## 8. Evidence System — How Confidence Is Built

### Evidence Pin Structure

Every piece of evidence is an atomic, structured claim:

```
{
  "claim": "CPU usage normal at 35%, not correlated with incident",
  "supporting_evidence": ["prometheus_query_cpu_usage"],
  "source_agent": "metrics_agent",
  "source_tool": "query_prometheus_range",
  "confidence": 0.90,
  "evidence_type": "metric"
}
```

### Negative Findings

Equally important — what was NOT found:

```
{
  "agent_name": "k8s_agent",
  "what_was_checked": "Pod restarts in the last 6 hours",
  "result": "No restarts found",
  "implication": "Pods are stable — issue is not infrastructure-related"
}
```

Negative findings help narrow the search space and build trust ("we checked X and it's fine").

### Breadcrumbs (Evidence Trail)

Every tool call, every observation is recorded as a breadcrumb:

```
[14:20:05] log_agent → Queried Elasticsearch (app-logs-*, 2000 results)
[14:20:06] log_agent → Extracted 423 error entries, 3 stack traces
[14:20:07] log_agent → LLM synthesis: identified NullPointerException pattern
[14:20:10] metrics_agent → Discovered 12 Prometheus metrics for payment-service
[14:20:12] metrics_agent → Queried http_request_duration_seconds (range: 1h, step: 15s)
...
```

This creates a complete audit trail — you can see exactly what the system did, in what order, and why.

### Confidence Weights

The weighted ledger uses domain-appropriate weights:

| Source | Weight | Rationale |
|--------|--------|-----------|
| Metrics | 30% | Quantitative, high-signal, rarely ambiguous |
| Logs | 25% | Direct error evidence, but can be noisy |
| Tracing | 20% | Shows causality, but not always available |
| Kubernetes | 15% | Infrastructure state, clear signals |
| Code | 5% | Valuable but depends on repo availability |
| Change | 5% | Correlational, not causal proof |

---

## 9. The Fix Pipeline — From Diagnosis to Pull Request

### Two-Phase Design

**Phase 1: Verification (Automatic)** — runs when you request a fix:

```
Diagnosis Findings
       │
       ▼
┌─────────────────────┐
│   Fix Generation    │  LLM generates code fix based on root cause
│   (Claude API)      │  + code analysis + error pattern
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Static Validation  │  AST parsing, syntax check, import validation
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Cross-Agent Review  │  Code agent reviews the fix for regressions
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Impact Assessment  │  Evaluates blast radius, side effects
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    PR Staging       │  Local git branch, commit, PR body prepared
└──────────┬──────────┘
           │
           ▼
   [Presented to User]
```

**Phase 2: Action (On-Demand)** — runs when you approve:

```
User clicks "Approve"
       │
       ▼
┌─────────────────────┐
│  Create GitHub PR   │  Push branch, create PR via GitHub API
└──────────┬──────────┘
           │
           ▼
   PR URL returned to UI
```

### Fix Status States

```
not_started → GENERATING → VERIFICATION_IN_PROGRESS → AWAITING_REVIEW
                                                          │
                                              ┌───────────┼───────────┐
                                              │           │           │
                                          [Approve]   [Reject]   [Feedback]
                                              │           │           │
                                              ▼           ▼           ▼
                                         PR_CREATING   REJECTED   GENERATING
                                              │                    (retry with
                                              ▼                     feedback)
                                          COMPLETE
```

---

## 10. Human-in-the-Loop Gates

The system has multiple points where it pauses and waits for human input. This is a deliberate design choice — AI should assist, not replace, human judgment for critical decisions.

### Gate 1: Attestation Gate (Discovery)

**When**: After diagnosis completes, before fix generation is allowed
**Why**: Ensures the human has reviewed the AI's conclusions before any code changes
**How**: Frontend shows an attestation modal; backend blocks fix generation until `_attestation_acknowledged = True`

### Gate 2: Repository Confirmation

**When**: When the change agent discovers potential repository URLs
**Why**: Wrong repo = wrong code analysis
**How**: Supervisor pauses with `_pending_repo_confirmation = True`, presents candidates to user

### Gate 3: Repository Mismatch

**When**: When the code agent detects that the repo doesn't match the service
**Why**: Prevents analyzing the wrong codebase
**How**: Supervisor pauses, asks user to confirm or provide correct repo URL

### Gate 4: Fix Approval

**When**: After fix is generated and verified
**Why**: Human must review code before it becomes a PR
**Options**:
- **Approve** → creates PR
- **Reject** → discards fix
- **Feedback** → regenerates fix with your notes (e.g., "also handle the case where zipCode is empty")

### Gate 5: Code Agent Questions

**When**: During code analysis, if the agent needs clarification
**Why**: Agent might need to know which module is relevant, or which branch to check
**How**: Question appears in chat, user answers, agent continues

---

## 11. The War Room UI

The investigation view uses a **CSS Grid 12-column layout** inspired by real-world SRE war rooms:

```
┌─────────────────────────────────────────────────────────────────┐
│                         War Room (12 columns)                    │
│                                                                  │
│  ┌─────────────┐  ┌───────────────────────┐  ┌───────────────┐ │
│  │ Investigator │  │   Evidence Findings   │  │   Navigator   │ │
│  │  (col 1-3)  │  │     (col 4-8)        │  │  (col 9-12)   │ │
│  │             │  │                       │  │               │ │
│  │ Patient Zero│  │ ┌───────────────────┐ │  │ Service       │ │
│  │ Banner      │  │ │ Finding Card (L)  │ │  │ Topology      │ │
│  │             │  │ │ NullPointerExc... │ │  │ (SVG graph)   │ │
│  │ Timeline    │  │ │ [ROOT CAUSE]      │ │  │               │ │
│  │ ──────────  │  │ └───────────────────┘ │  │ Metrics       │ │
│  │ 14:20:03 L  │  │ ┌───────────────────┐ │  │ Validation    │ │
│  │ 14:20:05 M  │  │ │ Finding Card (M)  │ │  │ Dock          │ │
│  │ 14:20:08 K  │  │ │ Memory spike...   │ │  │               │ │
│  │ 14:20:12 T  │  │ │ [CASCADING]       │ │  │ Infra Health  │ │
│  │             │  │ └───────────────────┘ │  │               │ │
│  │ Chat        │  │ ┌───────────────────┐ │  │ Agent Status  │ │
│  │ ──────────  │  │ │ Finding Card (K)  │ │  │ ✓ Log         │ │
│  │ You: fix    │  │ │ OOMKilled pods... │ │  │ ✓ Metrics     │ │
│  │ AI: Starting│  │ │ [CORRELATED]      │ │  │ ✓ K8s         │ │
│  │             │  │ └───────────────────┘ │  │ ✓ Tracing     │ │
│  └─────────────┘  └───────────────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Finding Cards

Each finding is displayed in an `AgentFindingCard` with:
- **Color-coded left border**: Red (Log), Cyan (Metrics), Orange (K8s), Emerald (Code)
- **Causal Role Badge**: `ROOT CAUSE`, `CASCADING SYMPTOM`, or `CORRELATED`
- **Confidence score**: Visual indicator of how certain the agent is
- **Evidence details**: Expandable section with raw data
- **Stack Trace Telescope**: For code findings, splits application frames from framework frames

### Service Topology

A hand-built SVG visualization showing:
- **Nodes**: Services as circles, sized by request volume
- **Edges**: Dependency arrows between services
- **Highlighting**: Failing services glow red with `pulse-red` animation
- **Layout**: Computed by `useTopologyLayout` hook using force-directed positioning

### Metrics Validation Dock

Suggested PromQL queries from the Log Agent, with a **"Run"** button that:
1. Sends the query to the backend's `/promql/query` proxy
2. Receives time-series data points
3. Displays a mini-chart inline

---

## 12. Real-Time Communication — WebSockets

### Connection Flow

```
Frontend                                    Backend
   │                                          │
   │──── WS Connect ─────────────────────────►│
   │     ws://localhost:8000/ws/              │
   │     troubleshoot/{session_id}            │
   │                                          │
   │◄─── Connection Accepted ─────────────────│
   │                                          │
   │◄─── {type: "task_event",                │  (agent progress)
   │      agent_name: "log_agent",            │
   │      event_type: "progress"}             │
   │                                          │
   │◄─── {type: "task_event",                │  (finding discovered)
   │      event_type: "finding"}              │
   │                                          │
   │◄─── {type: "task_event",                │  (phase changed)
   │      event_type: "phase_change",         │
   │      details: {phase: "metrics"}}        │
   │                                          │
   │◄─── {type: "task_event",                │  (attestation needed)
   │      event_type: "attestation_required"} │
   │                                          │
```

### Event Types

| Event | Trigger | UI Response |
|-------|---------|-------------|
| `started` | Supervisor begins | Show "Investigation started" toast |
| `progress` | Agent doing work | Update agent status indicator |
| `finding` | Agent found something | Add finding card to evidence panel |
| `phase_change` | State machine advances | Update phase indicator |
| `summary` | Agent completed | Show completion in timeline |
| `attestation_required` | Diagnosis done | Show attestation modal |
| `fix_proposal` | Fix generated | Show fix diff for review |
| `error` | Something failed | Show error banner |

### Resilience

- **Auto-reconnect**: Frontend retries WebSocket connection with exponential backoff (1s, 2s, 4s, 8s)
- **Max reconnects**: After 10 failed attempts, shows a persistent "Connection Lost" banner
- **Event buffering**: Backend stores events locally; frontend can catch up via REST `GET /events`
- **Graceful degradation**: If WebSocket fails, the UI polls REST endpoints every 5 seconds

---

## 13. API Reference

### V4 API (Primary — Session-Based Diagnosis)

#### Start Session
```
POST /api/v4/session/start

Body:
{
  "serviceName": "payment-service",     // Required
  "elkIndex": "app-logs-*",             // Required
  "timeframe": "1h",                    // Required
  "traceId": "abc123",                  // Optional
  "namespace": "production",            // Optional (enables K8s agent)
  "clusterUrl": "https://...",          // Optional (enables K8s agent)
  "repoUrl": "https://github.com/...", // Optional (enables Code + Change agents)
  "profileId": "uuid"                   // Optional (loads saved connection profile)
}

Response: { session_id, incident_id, status, message }
```

#### Chat
```
POST /api/v4/session/{session_id}/chat

Body: { "message": "What's the root cause?" }
Response: { "response": "...", "phase": "diagnosis_complete", "confidence": 86 }
```

#### Get Findings
```
GET /api/v4/session/{session_id}/findings

Response: {
  findings: [...],           // All agent findings
  error_patterns: [...],     // From Log Agent
  metric_anomalies: [...],   // From Metrics Agent
  pod_statuses: [...],       // From K8s Agent
  trace_spans: [...],        // From Tracing Agent
  impacted_files: [...],     // From Code Agent
  change_correlations: [...],// From Change Agent
  critic_verdicts: [...],    // From Critic Agent
  patient_zero: {...},       // First failing service
  service_flow: [...],       // Request path
  suggested_promql_queries: [...],
  time_series_data: {...},
  fix_data: {...} | null,    // Fix result if generated
}
```

#### Attestation
```
POST /api/v4/session/{session_id}/attestation

Body: { "gate_type": "discovery_complete", "decision": "approve", "decided_by": "sre@company.com" }
Response: { "status": "recorded", "response": "Attestation acknowledged — fix generation is now available." }
```

#### Generate Fix
```
POST /api/v4/session/{session_id}/fix/generate

Body: { "guidance": "also check for empty strings" }  // Optional guidance
Response: { "status": "started" }

Note: Returns 403 if attestation not yet approved
```

#### Fix Status
```
GET /api/v4/session/{session_id}/fix/status

Response: {
  fix_status: "awaiting_review",
  target_file: "src/main/java/PaymentValidator.java",
  diff: "--- a/...\n+++ b/...",
  fix_explanation: "Added null check for customer address...",
  verification_result: { ... },
  pr_url: null,
  attempt_count: 1
}
```

#### Fix Decision
```
POST /api/v4/session/{session_id}/fix/decide

Body: { "decision": "approve" }  // or "reject" or free-text feedback
Response: { "status": "ok", "response": "Approved — creating pull request now." }
```

### V5 API (Governance and Enterprise)

#### Evidence Graph
```
GET /api/v5/session/{session_id}/evidence-graph
Response: { evidence_pins, nodes, edges, root_causes }
```

#### Confidence Ledger
```
GET /api/v5/session/{session_id}/confidence
Response: { log_confidence, metrics_confidence, ..., weighted_final }
```

#### Reasoning Manifest
```
GET /api/v5/session/{session_id}/reasoning
Response: { session_id, steps: [{ step_number, decision, reasoning, confidence_at_step }] }
```

#### Timeline
```
GET /api/v5/session/{session_id}/timeline
Response: { events: [{ timestamp, source, event_type, description, severity }] }
```

---

## 14. Governance and Auditability

### Why It Matters

In enterprise environments, AI-driven systems need accountability. The system provides:

1. **Evidence Pins**: Every claim is sourced and confidence-scored
2. **Breadcrumb Trail**: Every tool call and observation is logged
3. **Reasoning Manifest**: The supervisor records each decision with rationale
4. **Negative Findings**: What was checked and found normal
5. **Critic Verdicts**: Independent validation of every finding
6. **Attestation Gates**: Human sign-off required before actions
7. **Audit Logs**: All API calls and decisions are logged

### Attestation Flow

```
Diagnosis Complete
       │
       ▼
   Attestation Required (event emitted)
       │
       ▼
   Human Reviews Findings
       │
   ┌───┴───┐
   │       │
Approve  Reject
   │       │
   ▼       ▼
Fix Gen   Revise
Unlocked  Findings
```

### Compliance Data Available

For each session, you can retrieve:
- Full evidence graph with causal relationships
- Per-source confidence scores
- Step-by-step reasoning transcript
- Who approved what, when
- Complete tool call log with inputs/outputs

---

## 15. Integration Points

### Connection Profiles

The system supports **named connection profiles** — saved configurations for different clusters/environments:

```
Profile: "production-east"
├── Cluster: https://openshift-east.company.com
├── Auth: Service Account Token (encrypted)
├── Prometheus: https://prometheus-east.company.com
├── Elasticsearch: https://elk-east.company.com:9200
├── Jaeger: https://jaeger-east.company.com:16686
├── GitHub Token: ghp_... (encrypted)
├── LLM Model: claude-sonnet-4-20250514
└── LLM Model Overrides:
    ├── code_agent: claude-opus-4-6 (more capable for code)
    └── log_agent: claude-haiku-4-5-20251001 (faster for log parsing)
```

### Supported Integrations

| Integration | Purpose | Agent |
|------------|---------|-------|
| **Elasticsearch** | Log queries, trace reconstruction | Log Agent, Tracing Agent |
| **Prometheus** | Metric queries, anomaly detection | Metrics Agent |
| **Kubernetes / OpenShift** | Pod status, events, deployments | K8s Agent |
| **Jaeger** | Distributed trace analysis | Tracing Agent |
| **GitHub** | Code reading, commit history, PR creation | Code Agent, Change Agent, Fix Pipeline |
| **Jira** | Ticket creation for incidents | Closure endpoints |
| **Confluence** | Post-mortem publication | Closure endpoints |
| **BMC Remedy** | Enterprise incident management | Closure endpoints |

### Incident Closure

After the fix is deployed, the system supports closing the incident loop:

1. **Create Jira ticket** with incident details and resolution
2. **Publish Confluence post-mortem** with auto-generated timeline and findings
3. **Create Remedy incident** for enterprise ITSM tracking
4. **Store incident fingerprint** in the memory system for future matching

---

## 16. Incident Memory — Learning from the Past

### How It Works

After each incident, the system stores a **fingerprint**:

```
IncidentFingerprint {
  fingerprint_id: "fp-abc123",
  session_id: "e7f3a291-...",
  error_patterns: ["NullPointerException in PaymentValidator"],
  affected_services: ["payment-service", "order-service"],
  root_cause: "Null check missing in address validation",
  resolution_steps: ["Added null check", "Created PR #142"],
  time_to_resolve: 180,  // seconds
}
```

### Similarity Matching

When a new incident starts, the system searches past incidents using **Jaccard similarity**:

```
similarity = |intersection(patterns_A, patterns_B)| / |union(patterns_A, patterns_B)|
```

If a match is found (score > 0.5), the system presents:
- Previous root cause
- Resolution steps that worked
- Time it took to resolve

This accelerates future incidents — if the same bug recurs, you know immediately what fixed it last time.

### Novelty Detection

Before storing a new incident, the system checks if it's genuinely novel (similarity < 0.8 to all existing incidents). This prevents duplicate entries.

---

## 17. Security Model

### Credential Management

- All credentials (API tokens, cluster tokens) are **encrypted at rest** using the `cryptography` library
- Decryption only happens in-memory when a profile is loaded for a session
- Credentials are stored in a `ResolvedConnectionConfig` (frozen/immutable dataclass) — cannot be accidentally modified
- Plaintext credentials are **never logged or returned to the frontend**
- Git URLs with embedded tokens are sanitized before logging: `https://user:token@github.com` → `https://***@github.com`

### Session Isolation

- Each session has its own `SupervisorAgent` instance — no shared state between sessions
- Per-session `asyncio.Lock` prevents concurrent state mutation
- Sessions auto-expire after 24 hours
- Background cleanup task runs every 5 minutes

### Input Validation

- Session IDs are validated as UUID4 format (prevents DoS via random lookups)
- All API request bodies are validated by Pydantic models
- Tool inputs from LLM responses are sanitized before execution

### Infrastructure Error Detection

Agents detect and handle infrastructure errors gracefully:
```
connection refused, connection error, connect timeout,
name or service not known, no route to host,
404 not found, 403 forbidden, 401 unauthorized
```

If an agent hits 3 consecutive infrastructure errors, it reports the failure and stops (rather than burning tokens on retries).

---

## 18. Project Structure

```
ai-troubleshooting-system/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── main.py                  # FastAPI app entry, CORS, startup
│   │   │   ├── routes_v4.py             # V4 API: sessions, chat, findings, fix
│   │   │   ├── routes_v5.py             # V5 API: governance, attestation, memory
│   │   │   ├── routes_profiles.py        # Connection profile CRUD
│   │   │   ├── routes_closure.py         # Jira, Confluence, Remedy integration
│   │   │   ├── routes_audit.py           # Audit log endpoints
│   │   │   ├── websocket.py             # WebSocket connection manager
│   │   │   └── models.py                # Request/response Pydantic models
│   │   ├── agents/
│   │   │   ├── supervisor.py            # Main orchestrator (2600+ lines)
│   │   │   ├── log_agent.py             # Elasticsearch log analysis
│   │   │   ├── metrics_agent.py         # Prometheus metrics analysis
│   │   │   ├── k8s_agent.py             # Kubernetes state analysis
│   │   │   ├── tracing_agent.py         # Distributed trace analysis
│   │   │   ├── code_agent.py            # Source code navigation
│   │   │   ├── change_agent.py          # Git change correlation
│   │   │   ├── critic_agent.py          # Cross-validation
│   │   │   ├── causal_engine.py         # Evidence graph builder
│   │   │   ├── impact_analyzer.py       # Blast radius + severity
│   │   │   └── agent3/                  # Fix generation pipeline
│   │   │       ├── fix_generator.py
│   │   │       ├── validators.py        # Static code validation
│   │   │       ├── reviewers.py         # Cross-agent review
│   │   │       ├── assessors.py         # Impact assessment
│   │   │       └── stagers.py           # PR staging
│   │   ├── models/
│   │   │   └── schemas.py              # All data models (DiagnosticState, etc.)
│   │   ├── integrations/
│   │   │   ├── profile_store.py         # SQLite-backed profile storage
│   │   │   ├── connection_config.py     # Resolve profiles to config
│   │   │   ├── credential_resolver.py   # Encrypted credential handling
│   │   │   └── store.py                 # Integration CRUD
│   │   ├── memory/
│   │   │   ├── store.py                 # Incident fingerprint storage
│   │   │   └── models.py               # Memory data models
│   │   ├── tools/
│   │   │   └── codebase_tools.py        # File reading, search tools for agents
│   │   └── utils/
│   │       ├── llm_client.py            # Anthropic API wrapper + token tracking
│   │       ├── event_emitter.py         # WebSocket event broadcasting
│   │       ├── repo_manager.py          # Git clone/cleanup
│   │       └── logger.py               # Structured logging
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                      # Main app: view routing, session management
│   │   ├── main.tsx                     # React entry point
│   │   ├── index.css                    # Tailwind + custom dark theme styles
│   │   ├── types/
│   │   │   └── index.ts                # All TypeScript type definitions
│   │   ├── services/
│   │   │   └── api.ts                  # REST API client functions
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts          # WebSocket connection hook
│   │   │   └── useKeyboardShortcuts.ts  # Keyboard shortcut management
│   │   ├── components/
│   │   │   ├── Home/
│   │   │   │   └── HomePage.tsx         # Landing page / dashboard
│   │   │   ├── ActionCenter/
│   │   │   │   └── CapabilityForm.tsx   # New investigation form
│   │   │   ├── Investigation/
│   │   │   │   ├── InvestigationView.tsx # War Room (12-col grid)
│   │   │   │   ├── Investigator.tsx     # Left panel (timeline, chat)
│   │   │   │   ├── EvidenceFindings.tsx # Center panel (finding cards)
│   │   │   │   ├── Navigator.tsx        # Right panel (topology, metrics)
│   │   │   │   ├── AttestationGateUI.tsx# Approval modal
│   │   │   │   ├── FixPipelinePanel.tsx # Fix review panel
│   │   │   │   └── ...
│   │   │   ├── Chat/
│   │   │   │   ├── ChatPanel.tsx        # Chat interface
│   │   │   │   └── ChatMessage.tsx      # Individual message rendering
│   │   │   ├── cards/
│   │   │   │   ├── AgentFindingCard.tsx # Evidence card with agent color
│   │   │   │   ├── CausalRoleBadge.tsx  # ROOT CAUSE / SYMPTOM badge
│   │   │   │   └── StackTraceTelescope.tsx # App vs framework frame split
│   │   │   ├── topology/
│   │   │   │   ├── ServiceTopologySVG.tsx # SVG dependency graph
│   │   │   │   └── useTopologyLayout.ts  # Force-directed layout
│   │   │   ├── Foreman/
│   │   │   │   ├── ForemanHUD.tsx       # Heads-up display overlay
│   │   │   │   └── NeuralTether.tsx     # Connection status indicator
│   │   │   ├── Sessions/
│   │   │   │   └── SessionManagerView.tsx# Session list and history
│   │   │   ├── Settings/
│   │   │   │   └── IntegrationSettings.tsx # Profile management UI
│   │   │   └── ui/
│   │   │       ├── ErrorBoundary.tsx    # React error boundary
│   │   │       └── ErrorBanner.tsx      # Error notification bar
│   │   └── utils/
│   │       └── format.ts               # Safe date/number formatting
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
│
└── docs/
    └── plans/                           # Architecture and design documents
```

---

## 19. Setup and Running

### Prerequisites

- Python 3.10+
- Node.js 18+
- An Anthropic API key (Claude access)
- Optional: Elasticsearch, Prometheus, Kubernetes cluster, Jaeger, GitHub token

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY at minimum

# Start server
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Access

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8000/ws/troubleshoot/{session_id}

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-20250514` | Default LLM model |
| `ELASTICSEARCH_URL` | No | `http://localhost:9200` | Elasticsearch endpoint |
| `PROMETHEUS_URL` | No | `http://localhost:9090` | Prometheus endpoint |
| `TRACING_URL` | No | `http://localhost:16686` | Jaeger endpoint |
| `OPENSHIFT_API_URL` | No | — | Kubernetes/OpenShift API |
| `OPENSHIFT_TOKEN` | No | — | Cluster auth token |
| `GITHUB_TOKEN` | No | — | GitHub personal access token |
| `INTEGRATION_DB_PATH` | No | `./data/integrations.db` | SQLite database path |

---

## 20. Glossary

| Term | Definition |
|------|-----------|
| **Agent** | A specialized AI component that investigates one data source (logs, metrics, K8s, etc.) |
| **Attestation** | Human sign-off that AI findings are acceptable before proceeding to action |
| **Breadcrumb** | A single logged action in an agent's investigation trail |
| **Causal Graph** | A directed graph connecting root causes to symptoms via causal relationships |
| **Confidence Ledger** | Weighted scoring system that combines confidence from all agents into a single score |
| **Critic Agent** | A read-only validation agent that cross-checks findings from other agents |
| **Evidence Pin** | An atomic, sourced claim with a confidence score (e.g., "CPU spiked to 95%") |
| **Fix Pipeline** | The multi-step process from diagnosis to code fix to pull request |
| **Human-in-the-Loop** | Design pattern where AI pauses for human input at critical decision points |
| **Negative Finding** | Evidence that something was checked and found normal (equally important as positive findings) |
| **Patient Zero** | The first service to fail in a cascading incident |
| **Profile** | A saved set of connection credentials for a specific environment |
| **ReAct** | Reason + Act — an AI pattern where the model alternates between thinking and tool use |
| **Supervisor** | The orchestrator agent that dispatches work, merges findings, and manages state |
| **War Room** | The main investigation UI — a 3-panel layout showing investigation, evidence, and navigation |
| **RED** | Rate, Errors, Duration — key metrics methodology for services |
| **USE** | Utilization, Saturation, Errors — key metrics methodology for resources |
| **TOCTOU** | Time-of-Check/Time-of-Use — a race condition pattern prevented by per-session locks |
