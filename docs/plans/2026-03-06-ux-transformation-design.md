# DebugDuck UX Transformation — Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** Transform DebugDuck from a troubleshooting launcher into a Datadog-class operational command center — maximizing data density, visual hierarchy, and cross-page workflow continuity.

**Style Model:** Datadog — dense data grids, metric sparklines, dark theme with color-coded severity, collapsible sections, tag-based filtering.

**Delivery:** 4 phased releases, each delivering visible improvement.

**Scope:** All pages EXCEPT App Diagnostics (Investigation/InvestigationView).

---

## Design Tokens

Extend the existing dark theme with semantic surface levels:

| Token | Hex | Usage |
|-------|-----|-------|
| `bg-surface-0` | `#0a1517` | Deepest backgrounds (terminal blocks) |
| `bg-surface-1` | `#0f2023` | Card backgrounds |
| `bg-surface-2` | `#162a2e` | Elevated surfaces, skeleton loaders |
| `bg-surface-3` | `#1a3a40` | Hover states, active items |
| `border-subtle` | `#224349` | Default borders |
| `border-strong` | `#3a5a60` | Interactive borders, handles |
| `text-primary` | `#e2e8f0` | Primary text, values |
| `text-secondary` | `#94a3b8` | Labels, descriptions |
| `text-muted` | `#64748b` | Timestamps, hints |
| `severity-ok` | `#22c55e` | Healthy, resolved |
| `severity-warn` | `#f59e0b` | Degraded, warning |
| `severity-critical` | `#ef4444` | Down, critical, root cause |
| `accent-primary` | `#07b6d5` | Interactive elements, CTA |
| `duck-cyan` | `#13b6ec` | Sparklines, highlights |
| `duck-amber` | `#f59e0b` | Warning indicators |
| `duck-red` | `#ef4444` | Critical indicators |

---

## Phase 1: Foundation + Home Dashboard

**Goal:** Establish UI primitives and transition Home from a "Launcher" to a live "Command Center."

### 1.1 Core Component Library

All components in `frontend/src/components/shared/`. No heavy charting libraries for micro-visualizations.

#### SparklineWidget

Pure SVG `<polyline>` — renders < 150 data points without DOM lag. No Recharts/D3 dependency.

```tsx
interface SparklineWidgetProps {
  data: number[];
  color?: 'cyan' | 'green' | 'amber' | 'red' | 'slate';
  width?: number | string;
  height?: number;
  strokeWidth?: number;
}
```

- Uses `useMemo` to compute normalized SVG points from data array
- Color map: cyan=#13b6ec, green=#22c55e, amber=#f59e0b, red=#ef4444, slate=#64748b
- ViewBox `0 -5 100 110` with `preserveAspectRatio="none"` to prevent stroke clipping
- Fallback: `<div>Not enough data</div>` when `data.length < 2`

#### MetricCard

KPI tile consuming SparklineWidget. The "Command Center Tile."

```tsx
interface MetricCardProps {
  title: string;
  value: string | number;
  trendValue: string;
  trendDirection: 'up' | 'down' | 'neutral';
  trendType: 'good' | 'bad' | 'neutral'; // determines color
  sparklineData: number[];
}
```

- `h-32` fixed height, `bg-[#0f2023]` with `border-[#224349]`
- Header: uppercase `text-xs` title + TrendIndicator pill (arrow icon + value, color by trendType)
- Body: `text-3xl font-mono font-bold` value + `w-24` sparkline (right-aligned)
- Hover: border transitions to `#07b6d5/50`, ambient gradient glow from bottom

#### StatusBadge

Universal status indicator — pods, sessions, integrations, devices.

```tsx
type SystemStatus = 'healthy' | 'degraded' | 'critical' | 'unknown' | 'in_progress';

interface StatusBadgeProps {
  status: SystemStatus;
  label: string;
  count?: number;
  pulse?: boolean;
}
```

- Inline-flex pill: colored dot + label + optional count
- Dot uses Tailwind `animate-ping` when `pulse=true`
- Status→color mapping: healthy=green, degraded=amber, critical=red, unknown=slate, in_progress=cyan

#### SkeletonLoader

Layout-preserving placeholder — never show generic spinners.

```tsx
interface SkeletonProps {
  type: 'text' | 'card' | 'avatar' | 'row';
  width?: string;
  height?: string;
}
```

- `animate-pulse bg-[#162a2e] border border-[#224349]`
- Type shapes: avatar=rounded-full, text=rounded h-4, card=rounded-lg h-32, row=rounded h-12

#### TrendIndicator

Standalone up/down arrow with percentage change.

- Material Symbols `arrow_upward`/`arrow_downward`/`remove`
- Color by context: green=good, red=bad, slate=neutral

#### SectionHeader

Title + optional count badge + optional action buttons + optional TimeRangeSelector.

#### TimeRangeSelector

Pill group: `5m | 15m | 1h | 6h | 24h | 7d`. Active pill highlighted with `bg-[#07b6d5]/20`.

#### DataTable

Sortable, filterable table with row hover and column alignment. Used in Activity Feed, NOC Wall list view, and Workload table.

### 1.2 Home Dashboard Layout

**Current:** Capability launcher cards + text-only session feed.
**Target:** Operational command center.

```
+-----------------------------------------------------------+
| HEADER: System Health Badge + Global Search + Notifications|
+-----------------------------------------------------------+
| METRIC RIBBON (4 MetricCards in grid-cols-4):              |
| [Active Sessions] [Resolved Today] [Avg Conf.] [MTTR]     |
| Each with value + trend arrow + 1h sparkline               |
+-----------------------------------------------------------+
| LEFT (col-8): Activity Feed    | RIGHT (col-4):           |
| +-----------------------------+| +----------------------+ |
| | SectionHeader: Recent       || | Quick Actions         | |
| | [TimeRangeSelector]         || |   > New Investigation | |
| +-----------------------------+| |   > Network Scan      | |
| | ActivityFeedRow: icon +     || |   > Cluster Check     | |
| |   service + namespace +     || |   > View Topology     | |
| |   phase badge + confidence  || +----------------------+ |
| |   bar + duration + agents   || | Integration Status    | |
| | ------------------------------- | Datadog     [green]  | |
| | ActivityFeedRow: ...        || |   K8s Prod  [green]  | |
| | ------------------------------- | PagerDuty   [red]    | |
| | [Show more...]              || +----------------------+ |
| +-----------------------------+| | System Health         | |
|                                | |   CPU: 23%  [spark]  | |
|                                | |   Mem: 61%  [spark]  | |
|                                | |   API: 12ms [spark]  | |
|                                | +----------------------+ |
+-----------------------------------------------------------+
| CAPABILITY CARDS (existing, refined with StatusBadge)      |
+-----------------------------------------------------------+
```

#### ActivityFeedRow

Dense session row — the heart of the Home feed.

```tsx
interface ActivityFeedRowProps {
  targetService: string;
  targetNamespace: string;
  timestamp: string;
  status: 'healthy' | 'critical' | 'degraded' | 'in_progress';
  phase: string;
  confidenceScore: number; // 0-100
  durationStr: string;
  activeAgents: string[]; // e.g., ['Network', 'Storage']
}
```

- 3-column layout: Identity (icon + service + namespace + time), Status (StatusBadge + confidence bar), Telemetry (duration + overlapping agent avatars + hover chevron)
- Confidence bar: `h-1 bg-[#162a2e]` track with colored fill (green >= 80, amber >= 50, red < 50)
- Agent avatars: `w-6 h-6 rounded-full -space-x-2` with initial letter, hover lifts with `-translate-y-1`
- Row hover: `bg-[#0f2023]` + chevron_right appears

### 1.3 Sidebar Navigation Overhaul

**Changes:**
- **Breadcrumb bar** at top of main content area
- **Grouped nav items:** Investigate (Home, Sessions), Infrastructure (Network group, Observatory), Kubernetes (Cluster Diagnostics), Tools (Topology Editor, Integrations, Settings)
- **Collapsed mode:** icon-only `w-16` with tooltip labels
- **Active section highlight:** entire group subtly highlighted
- **Recent items:** bottom section showing last 3 visited pages

---

## Phase 2: War Room Enhancement

**Goal:** Solve the "Wall of Text" problem. SREs scan shapes and colors, not paragraphs. Implement progressive disclosure and strict visual hierarchy.

### 2.1 Evidence Stack Grouping (EvidenceStackGroup)

Groups findings by causal role — visually enforces the Multi-Root-Cause CausalForest from the backend.

```tsx
interface CausalTreeProps {
  treeId: string;
  rootCause: FindingData;
  cascadingSymptoms: FindingData[];
  correlatedSignals: FindingData[];
}
```

**Structure:**
1. **Root Cause card** — always visible, highest prominence (red tint, pulsing left border)
2. **Toggle button** — "HIDE IMPACT" / "SHOW IMPACT (N)" with expand/collapse
3. **Nested findings** — indented `pl-8` with dashed SVG "Neural Tether" lines connecting to root
   - Cascading symptoms: normal opacity, `border-[#224349]`
   - Correlated signals: `opacity-70`, `border-duck-cyan/30`

**Visual tethers:** Vertical dashed line (`border-l border-dashed border-duck-border`) with horizontal elbow connectors to each child card.

### 2.2 High-Density Finding Cards (AgentFindingCard)

Progressive disclosure — defaults to scannable summary, expands on click.

```tsx
interface FindingData {
  id: string;
  title: string;
  description: string;
  severity: 'critical' | 'warn' | 'info';
  agentSource: string;
  metricData?: number[];
  resourceRefs: string[];
  rawEvidence?: string;
}
```

**Collapsed state (header only):**
- StatusBadge (ROOT CAUSE / CASCADING / CORRELATED) + title (truncated) + agent source badge + inline SparklineWidget (when metricData exists, `w-24 h-20`)
- Expand chevron

**Root cause styling:**
- `border-[#ef4444]` + `shadow-[0_0_15px_rgba(239,68,68,0.1)]`
- Red tint overlay: `bg-[#ef4444]/5` over entire card
- Pulsing left border: `w-1 bg-[#ef4444] animate-pulse`
- Default expanded

**Expanded state (body):**
- Description text
- Connected resource tags: clickable pills (`bg-duck-cyan/10 border-duck-cyan/30 text-duck-cyan`)
- Action bar: "View Raw Evidence" + "Copy Summary" buttons

### 2.3 Operational Recommendation Block

Sits at bottom of expanded Root Cause card. Transforms War Room from read-only to actionable.

```tsx
interface CommandStep {
  description: string;
  command: string;
  isDestructive: boolean;
  dryRunCommand?: string;
  validationCommand?: string;
}
```

**Features:**
- **Dry-Run toggle** per step — switches displayed command between destructive and safe versions
- **Terminal block:** `bg-[#050a0b]` with `text-duck-cyan font-mono text-[11px]`, one-click copy
- **Destructive warning badge:** `bg-duck-red/20 text-duck-red` "DESTRUCTIVE" pill
- **Validation commands:** shown below each step with `verified` icon, `select-all cursor-pointer`

### 2.4 War Room Polish

- **SkeletonLoader** in EvidenceFindings during initial fetch (3 shimmer cards)
- **Stagger animations** for card entrance (Framer Motion, already integrated)
- **Navigator enrichment:** agent status panel, inline mini line charts in REDMethodStatusBar
- **Network path nodes:** latency sparkline + packet loss indicator per hop

---

## Phase 3: Observatory Dashboard (NOC Wall)

**Goal:** Persistent "pane of glass" for NOC. Must be readable from 10 feet away on a 70-inch monitor. Highly performant and visually stable.

### 3.1 Golden Signals Ribbon

4 MetricCards at top of Observatory: Avg Latency, Packet Loss Rate, Link Utilization, Active Alerts. Each with 1h sparkline + trend indicator vs. baseline.

### 3.2 NOC Wall Grid (NocDeviceCard)

Dense device card combining SparklineWidget + StatusBadge.

```tsx
interface NocDeviceProps {
  name: string;
  ip: string;
  type: 'router' | 'switch' | 'firewall' | 'workload';
  status: 'healthy' | 'degraded' | 'critical';
  metrics: {
    cpu: { value: number; trend: number[] };
    latency: { value: string; trend: number[] };
  };
  activeAlerts: number;
}
```

**Layout:**
- Header: device icon + name/IP + StatusBadge (with pulse for non-healthy)
- Telemetry grid (2 cols): CPU% with sparkline + Latency with sparkline
- Footer (conditional): alert count with "View >" link
- Critical styling: `border-duck-red/50` + red blur glow in corner
- Hover: `shadow-[0_0_15px_rgba(19,182,236,0.1)]`

**View modes:**
- **Grid view** (default): responsive CSS grid of NocDeviceCards
- **List view**: sortable DataTable (Name, Status, Latency, CPU, MEM, Loss, Uptime)
- **Group-by dropdown**: type (router/switch/firewall), zone, status
- **Search + filter bar**: filter by name/IP/zone/status

### 3.3 Semantic Zoom Topology

**PERFORMANCE GUARDRAIL:** D3-force with 5,000 nodes will freeze the browser.

**Solution: Node Clustering based on `d3.zoomTransform` scale factor.**

| Zoom Level | `transform.k` | Renders |
|-----------|---------------|---------|
| Level 1 (zoomed out) | < 1.5 | VPCs, Cloud Regions, Transit Gateways as single massive nodes |
| Level 2 (mid-zoom) | 1.5 - 3.0 | VPC expands to bounding box, Subnet nodes spawn inside |
| Level 3 (deep zoom) | > 3.0 | Subnets expand to reveal individual pods, VMs, firewalls |

- Collision forces (`forceManyBody`, `forceLink`) dynamically update when nodes expand
- Anomaly badges on nodes (alert count, severity color)
- Link width = bandwidth utilization (visual encoding)
- Overlay toggle: latency labels, utilization %, error counts

### 3.4 Traffic Flow Analytics

- **Time series chart** (Recharts) — flow throughput over selected time range
- **Hot paths highlighting** — top-N flows by throughput/latency/errors
- **Retransmission trend** — separate sparkline for retransmits
- **Conversations with issues** — flagged flows with "Investigate" button

### 3.5 Enhanced Alert Management

- **Grouped alerts** by device, severity, or alert type
- **Acknowledge + snooze** action buttons
- **Alert correlation:** "3 alerts share common root: border-2 CPU spike"
- **Drift event integration:** show config changes correlated with performance degradation

---

## Phase 4: Cluster Diagnostics + Cross-Cutting

**Goal:** Bind the platform together with chronological tracking and seamless context preservation.

### 4.1 Event Timeline

Vertical chronological ledger — the "Operational Ledger" for post-mortems.

```tsx
interface TimelineEvent {
  id: string;
  timestamp: string;
  type: 'alert' | 'config_change' | 'pod_crash' | 'drift';
  severity: 'critical' | 'warn' | 'info';
  title: string;
  description: string;
  relatedEntity: string;
}
```

**Layout:**
- 3-column per row: time (right-aligned, `text-[10px]`), axis (color-coded circle node + vertical line), content (card with title + type badge + description + entity link)
- Severity colors: critical=red, warn=amber, info=cyan
- Icons by type: alert=warning, config_change=code_blocks, pod_crash=heart_broken, drift=difference
- Hover: vertical line transitions to `duck-cyan/50`

### 4.2 Cluster Health Heatmap

Grid of tiny interactive blocks representing nodes/pods.

**PERFORMANCE GUARDRAIL:**
- **< 500 items:** CSS Grid with React components
- **500+ items:** HTML5 `<canvas>` element — single React component manages canvas context + mouse-move tooltips

**Colors:** green (healthy) → amber (pressure) → red (critical) → gray (unknown)

### 4.3 Cluster Health Dashboard (new tab/view)

- Node utilization heatmap
- Pod status summary (Running/Pending/Failed/Unknown counts as MetricCards)
- Workload table (DataTable: Deployment name, ready replicas, last rollout, status)
- API server latency + etcd performance sparklines

### 4.4 URL State Management (Cross-Page Workflows)

**The URL is the single source of truth for DiagnosticScope.**

**Bad:** `/war-room/investigate`
**Enterprise standard:** `/war-room/investigate?scopeLevel=workload&workloadKey=deployment/payment/checkout&timeStart=1710500000&timeEnd=1710503600`

**Why:** When an SRE finds root cause at 3 AM, they copy the URL into Slack. The networking team must see the exact same view, not a blank dashboard.

**Implementation:**
- Create `useSearchParamsScope()` hook — reads/writes `scopeLevel`, `workloadKey`, `timeStart`, `timeEnd`, `namespace` from URL search params
- All pages consume this hook to initialize their state
- Navigation actions (click "Investigate in War Room" from Observatory) push new URL with current scope params
- TimeRangeSelector updates URL params on change

### 4.5 Cross-Page Navigation

- **Breadcrumbs** everywhere (built in Phase 1)
- **"View in..."** links — Observatory device → Topology Editor, finding → related investigation
- **Context preservation** — time range, namespace, filters carry across pages

---

## Execution Order

```
Phase 1 — Foundation + Home Dashboard (sequential):
  1.1: Core component library (shared/)
  1.2: Home page dashboard transformation
  1.3: Sidebar navigation overhaul

Phase 2 — War Room Enhancement (sequential):
  2.1: EvidenceStackGroup + causal grouping
  2.2: AgentFindingCard progressive disclosure
  2.3: OperationalRecommendationBlock
  2.4: War Room polish (skeletons, animations, navigator)

Phase 3 — Observatory Dashboard (sequential):
  3.1: Golden signals ribbon
  3.2: NOC Wall grid + list view
  3.3: Semantic zoom topology
  3.4: Traffic flow analytics
  3.5: Alert management enhancement

Phase 4 — Cluster Diagnostics + Cross-Cutting (sequential):
  4.1: Event timeline
  4.2: Cluster health heatmap
  4.3: Cluster health dashboard
  4.4: URL state management
  4.5: Cross-page navigation
```

## Verification

1. `npx tsc --noEmit` — 0 TypeScript errors after each phase
2. Phase 1: Home page shows metric ribbon with live sparklines, activity feed with confidence bars, quick actions sidebar
3. Phase 2: War Room groups findings by causal role, root cause pulses red, cards expand/collapse, remediation block has dry-run toggle
4. Phase 3: Observatory shows golden signals, NOC grid with sparklines, semantic zoom works at 3 zoom levels, 50+ nodes render at 60fps
5. Phase 4: Event timeline shows chronological events, URL carries context between pages, "Investigate in War Room" from Observatory preserves scope
