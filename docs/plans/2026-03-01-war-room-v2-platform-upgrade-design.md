# War Room v2 — Platform Upgrade Design

> Full platform upgrade transforming the diagnostics workflow from a single-root-cause diagnosis tool into a complete SRE investigation platform.

**Date:** 2026-03-01
**Status:** Approved
**Branch:** TBD (from `main`)

---

## 1. Architecture Overview

Six capabilities organized into a cohesive platform upgrade:

| # | Capability | Layer |
|---|-----------|-------|
| 1 | Multi-Root-Cause Causal Forest | Core Engine |
| 2 | Operational Recommendations (copy-paste ready) | Actionable Output |
| 3 | Surgical Telescope v2 (YAML/Logs/Events drawer) | Investigation Surface |
| 4 | NeuralChart Metrics Visualization (Recharts) | Investigation Surface |
| 5 | Click-Anywhere ResourceEntity + Drill-Down | Connective Tissue |
| 6 | Enriched Backend Schema (resource_refs) | Data Layer |

### Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WAR ROOM v2 ARCHITECTURE                        │
├───────────────┬──────────────────────┬──────────────────────────────────┤
│  INVESTIGATOR │   EVIDENCE FINDINGS  │          NAVIGATOR              │
│  (col-3)      │   (col-5)            │          (col-4)                │
│               │                      │                                 │
│  Timeline     │  Causal Forest       │  Topology SVG                   │
│  Phase Nav    │  ├─ Tree 1 (OOM)     │  NeuralChart metrics            │
│  Agent Status │  │  ├─ Findings      │  PromQL Dock                    │
│  Chat Drawer  │  │  ├─ Blast Radius  │  Infra Health                   │
│               │  │  └─ Recommendations│  Agent Matrix                  │
│               │  ├─ Tree 2 (DNS)     │                                 │
│               │  │  └─ ...           │                                 │
│               │  Evidence Pins       │                                 │
│               │  (with ResourceEntity│                                 │
│               │   click-anywhere)    │                                 │
├───────────────┴──────────────────────┴──────────────────────────────────┤
│  SURGICAL TELESCOPE (slide-out drawer, right edge, z-100)              │
│  [ YAML ]  [ LOGS ]  [ EVENTS ]                                       │
│  Breadcrumb: namespace / deployment / pod / pvc                        │
│  Smart highlighting, action bar, JSON unpacking                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Layout Pivot:** The Causal Forest occupies the center column (col-5) for horizontal breathing room. Topology and metrics move to the right column (col-4) as supporting context.

### Implementation Constraints

- **Z-Index Layering:** `TelescopeDrawer` at `z-[100]`, CommandBar (footer) at `z-[50]` or lower. Drawer covers entire right edge including chat input.
- **Context Scope:** `TelescopeContext` wraps the entire 3-column grid AND the footer. A `/describe pod=auth` command in the CommandBar must be able to fire `openTelescope()` on the resulting pin.

---

## 2. Multi-Root-Cause Engine — Causal Forest

### Problem

The current system assumes a single `patient_zero`. Real incidents have concurrent independent failures (OOM + DNS timeout + certificate expiry) that need independent triage.

### Data Model

```typescript
interface CausalTree {
  id: string;
  root_cause: Finding;
  severity: "critical" | "warning" | "info";
  blast_radius: BlastRadiusData;
  cascading_symptoms: Finding[];
  correlated_signals: CorrelatedSignalGroup[];
  operational_recommendations: OperationalRecommendation[];
  triage_status: "untriaged" | "acknowledged" | "mitigated" | "resolved";
  resource_refs: ResourceRef[];
}

// V4Findings enhanced:
interface V4Findings {
  causal_forest: CausalTree[];     // NEW — primary view
  patient_zero: PatientZero;       // KEPT for backward compat
  // ... existing fields unchanged
}
```

### Backend Changes

- Synthesizer prompt shifts from "identify THE root cause" to "identify ALL independent root causes, group cascading symptoms under each, and flag any that are correlated but not causal"
- Each `CausalTree` gets its own blast radius computed from its affected services/pods
- Triage status is persisted per-session and updatable via API

### Frontend — Causal Forest View

Center column renders each `CausalTree` as an independent, collapsible card:
- Color-coded severity border (red/amber/slate)
- Blast radius badge showing affected service count
- Expandable tree showing root → cascading symptoms
- Triage toggle (untriaged → acknowledged → mitigated → resolved)
- Attached operational recommendations
- All resource names rendered as `<ResourceEntity>` components

---

## 3. Operational Recommendations — Copy-Paste Ready Commands

### Problem

The system diagnoses issues but only produces code fixes. SREs need immediate operational commands they can copy and run.

### Data Model

```typescript
interface OperationalRecommendation {
  id: string;
  title: string;
  urgency: "immediate" | "short_term" | "preventive";
  category: "scale" | "rollback" | "restart" | "config_patch" | "network" | "storage";
  commands: CommandStep[];
  rollback_commands: CommandStep[];
  risk_level: "safe" | "caution" | "destructive";
  prerequisites: string[];
  expected_outcome: string;
  resource_refs: ResourceRef[];
}

interface CommandStep {
  order: number;
  description: string;
  command: string;
  command_type: "kubectl" | "oc" | "helm" | "shell";
  is_dry_run: boolean;
  dry_run_command: string | null;
  validation_command: string | null;
}
```

### Backend Generation

- Each `CausalTree` gets its own recommendations from the LLM synthesizer
- Prompt includes root cause finding, current resource state, and cluster context
- LLM generates structured JSON with exact commands referencing actual resource names/namespaces
- **OpenShift dialect awareness:** Synthesizer prompt is injected with cluster distribution type. OpenShift clusters get `oc` commands, `DeploymentConfig` rollbacks, `Route` patches instead of Ingress

### Frontend — Recommendation Cards

Nested inside each `CausalTree` card:
- **Urgency badge** — red IMMEDIATE, amber SHORT TERM, slate PREVENTIVE
- **Risk indicator** — green SAFE, amber CAUTION, red DESTRUCTIVE
- **Command blocks** — monospace with one-click copy per command
- **Dry-run toggle** — shows `--dry-run=client -o yaml` variant first
- **Rollback section** — collapsible undo commands for each step
- **Validation command** — "After running, verify with:" + command

### Placeholder UX Treatment

When the LLM generates a command with a placeholder (e.g., `kubectl set image deployment/checkout main=<PREVIOUS_TAG>`), the frontend detects `<...>` syntax via regex and renders it as a highly visible, pulsing text block to prevent blind copy-paste of invalid commands.

### Future Path (Phase 2)

The architectural groundwork exists to swap `[Copy]` for `[Execute]` via the existing `POST /investigate` fast-path and hold-to-confirm UI pattern.

---

## 4. Surgical Telescope v2 — Multi-Tabbed Resource Inspector

### Problem

Backend fetches rich K8s resource data but the UI has no way to display YAML, logs, or events. SREs leave the tool to use a terminal.

### Component Architecture

```
TelescopeContext (wraps entire app — grid + footer)
  ├── ResourceEntity (trigger — anywhere in UI)
  │     • Dashed cyan underline + kind icon (Material Symbols)
  │     • Hover tooltip: status, age (zero-latency from ResourceRef)
  │     • Click → openTelescope({ type, name, namespace })
  │
  └── TelescopeDrawer (fixed right edge, w-[450px], z-[100])
        ├── Live State Indicator (pulsing green dot — "Viewing real-time cluster state")
        ├── Breadcrumb Trail (click inception: ns/deploy/pod/pvc)
        ├── Action Bar: [Edit YAML] [Scale] [Delete] (risk-colored)
        └── Tab Switcher: [ YAML ] [ LOGS ] [ EVENTS ]
```

### YAML Tab
- Syntax-highlighted via `react-syntax-highlighter`
- Smart highlighting: AI-flagged fields get amber bg + left border
- Collapsible spec/status/metadata sections
- Diff toggle: current vs last-known-good state
- Field search (Ctrl+F within YAML)

### LOGS Tab (LogViewerTab)
- Severity color-coding: ERROR = red bg + left border, WARN = amber text, INFO/DEBUG = ghosted slate
- JSON unpacking: detect JSON lines → `[+]` expander → inline pretty-print
- Sticky filter bar: `[Regex search]` `[ERROR][WARN][INFO]` `[↓ Auto-scroll]`
- Auto-scroll disengages on manual scroll (`onWheel` override — "Human Override")
- Virtualization via `react-window` if > 5,000 lines

### EVENTS Tab
- K8s events for this specific resource
- Severity-colored (Warning = amber, Normal = slate)
- Grouped by reason (BackOff, Pulled, Scheduled)
- Time-relative display ("2m ago", "15m ago")

### Smart Tab Defaulting

| Originating Intent | Default Tab |
|-------------------|-------------|
| `fetch_pod_logs` | LOGS |
| `describe_resource` | YAML |
| `get_events` | EVENTS |
| Direct `ResourceEntity` click | YAML |

### API Design — Decoupled for Performance

```
GET /api/v4/sessions/{id}/resource/{namespace}/{kind}/{name}
  → { yaml: string, events: K8sEvent[] }                    # Fast, always fetched

GET /api/v4/sessions/{id}/resource/{namespace}/{kind}/{name}/logs?tailLines=500
  → { logs: string }                                         # Lazy, only on LOGS tab click
```

Logs are **never** fetched with YAML/events. A deployment with 15 pods generating gigabytes of logs would timeout the API request and break the drawer if fetched synchronously.

### Temporal Drift UX Indicator

The War Room center column is a historical forensic record (snapshot when AI ran). The Telescope fetches live cluster state. The drawer header includes a pulsing green dot with tooltip "Viewing real-time cluster state" to make this distinction clear.

### Breadcrumb Inception

- Clicking a resource name inside Telescope YAML pushes onto the breadcrumb stack
- Back-navigation pops the stack
- Max depth uncapped; breadcrumbs truncate with `...` after 5 levels

---

## 5. NeuralChart Metrics Visualization

### Problem

Only inline SVG sparklines exist. No zoomable time-series charts, no multi-metric overlay, no anomaly drill-down.

### Technology Choice: Recharts

**Why Recharts:**
- Outputs standard SVG — Tailwind classes (`stroke-duck-cyan`, `drop-shadow`) apply directly
- Charts match the War Room neural aesthetic without custom CSS
- `ResponsiveContainer` handles panel expansion (2x2 grid → full-width surgical focus)

**Why NOT uPlot:** Canvas rendering makes glow effects and custom tooltips difficult.
**Why NOT Tremor:** Too opinionated; clashes with our dense, edge-to-edge tactical layout.

### `<NeuralChart />` Wrapper Component

- **SVG glow filters** via `<defs>` + `feGaussianBlur` — lines glow in duck-cyan/amber/red
- **War Room tooltip** — `bg-[#0f2023]/95`, backdrop blur, monospace 10px
- **No dots on lines** — continuous "neural tether" look, `activeDot` only on hover
- **Color palette:** cyan (primary), amber (warning/threshold), red (anomaly), slate (baseline/ghost)
- **Client-side failsafe:** Naive decimation if data exceeds 150 points despite backend downsampling

### Backend: LTTB Downsampling

**Hard rule:** Never send more than 150 data points per line to the frontend.

LTTB (Largest Triangle Three Buckets) downsampling applied in:
- `ToolExecutor._query_prometheus()` — downsample `query_range` results
- `EvidencePinFactory.from_tool_result()` — enforce 150-point cap on time_series metadata
- Resource metrics endpoint — downsample before response

### Integration Points

| Location | Height | Data Source |
|----------|--------|-------------|
| Navigator — metric anomaly cards | 80px | `metric_anomalies[].time_series` |
| Telescope YAML — resource usage | 120px | Live Prometheus metrics |
| Causal Tree — correlated signals | 80px, 2-line overlay | `correlated_signals[].time_series` |
| PromQL Dock — query results | 200px, full-width | `SuggestedPromQLQuery` execution |
| Evidence Pin — metric pins | 60px, sparkline replacement | Pin `raw_output` parsed |

### React Rendering Optimization

**Deep memoization directive:** The `data` array passed to `<NeuralChart />` must be deeply memoized (`useMemo` or state selector) when fed by WebSocket. SVG glow filter repainting (`feGaussianBlur`) is GPU-intensive — Recharts must not recalculate filters when a parent component re-renders for unrelated reasons (e.g., triage status toggle on a Causal Tree card).

---

## 6. Enriched Backend Schema — ResourceEntity & Resource Refs

### Problem

The AI returns plain text claims. The frontend can't identify clickable resource names without explicit backend tagging.

### The `@[kind:namespace/name]` Inline Syntax

LLM agents are prompted to use inline resource references:

```
"Pod @[pod:payment-api/auth-5b6q] is crashing due to @[pvc:payment-api/auth-data-vol] exhaustion"
```

**Fully qualified format:** `@[kind:namespace/name]` (preferred — avoids namespace collisions).
**Short format:** `@[kind:name]` (fallback — frontend defaults to `active_namespace` from context).

### ResourceRef Model

```python
class ResourceRef(BaseModel):
    type: str            # pod, deployment, service, configmap, pvc, node, ingress,
                         # replicaset, deploymentconfig, route, buildconfig, imagestream
    name: str
    namespace: str | None = None
    status: str | None = None    # Running, CrashLoopBackOff — for zero-latency hover tooltip
    age: str | None = None       # "2d", "15m" — for hover tooltip
```

### Backend Processing

1. **Synthesizer prompt** instructs LLM to use `@[kind:namespace/name]` notation
2. **`resource_refs` field** added to `Finding`, `EvidencePin`, `OperationalRecommendation`, `CausalTree`
3. **Post-processing pass** — regex extracts `@[kind:name]` tokens and auto-populates `resource_refs`
4. **OpenShift support** — `type` field supports `deploymentconfig`, `route`, `buildconfig`, `imagestream`

### Frontend Parser — `parseResourceEntities()`

Converts `@[kind:namespace/name]` tokens in any string into `<ResourceEntity>` components:
- Primary: regex match on `@[kind:namespace/name]` pattern
- Fallback: if LLM omits syntax, match known resource names from `resource_refs` against plain text
- Namespace fallback: if namespace omitted, use `active_namespace` from `TelescopeContext` or `RouterContext`

Called everywhere text is rendered: finding cards, causal tree descriptions, recommendations, chat messages, evidence pin claims.

### Resource Kind Icons (Material Symbols)

| Kind | Icon | Color |
|------|------|-------|
| pod | `deployed_code` | cyan |
| deployment | `layers` | cyan |
| service | `router` | cyan |
| node | `dns` | cyan |
| configmap | `settings` | cyan |
| pvc | `storage` | cyan |
| ingress / route | `language` | cyan |
| namespace | `folder` | cyan |
| deploymentconfig | `swap_horiz` | cyan |

---

## Data Sources

The platform integrates with:
- **Prometheus** — metrics, anomaly detection, time-series (already wired)
- **Elasticsearch/ELK** — log aggregation, full-text search (already wired)
- **Jaeger** — distributed tracing, service discovery (already wired via `TracingAgent`)
- **Kubernetes API** — resource state, events, logs (already wired via `ToolExecutor`)

No new data source integrations required for v2. All four are already connected.

---

## Tech Stack Additions

| Addition | Purpose | Size |
|----------|---------|------|
| `recharts` | Time-series chart library | ~45KB gzip |
| `react-syntax-highlighter` | YAML syntax highlighting in Telescope | ~15KB gzip |
| `react-window` | Log viewer virtualization (>5K lines) | ~6KB gzip |
| LTTB algorithm (backend) | Prometheus data downsampling | Pure Python, no dependency |
