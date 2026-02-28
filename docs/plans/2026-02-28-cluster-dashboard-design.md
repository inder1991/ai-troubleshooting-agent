# Cluster Diagnostic War Room — UI Design

**Date:** 2026-02-28
**Status:** Approved
**Wireframe references:** `stitch_action_center (13)`, `stitch_action_center (16)`

---

## 1. Information Hierarchy & Navigation

### Three Zoom Levels

| Level | View | Trigger |
|-------|------|---------|
| **Cluster Overview** | Default. 3-column war room: Fleet Heatmap + DAG (left), Domain Panels (center), Root Cause + Verdict (right) | Page load |
| **Domain Drill-Down** | Clicked domain expands to col-span-5. Others collapse to vertical pulse ribbons (~40px). Content: namespace-scoped workloads, anomaly cards with metrics | Click domain panel or heatmap pip |
| **Resource Inspector** | Drawer/modal over drill-down. Shows pod-level YAML, event timeline, container logs, metrics sparklines | Click specific pod/workload in drill-down |

### Namespace Scoping

- Filter pill in header: `All Namespaces` dropdown or typed selection
- When scoped: only that namespace's workloads shown in domain panels
- Cross-namespace causality: out-of-scope namespaces shown dimmed with dashed borders
- Healthy namespaces dimmed at opacity-40, hover to reveal (matching wireframe (16) pattern)

### Edge Cases

| Category | Scenario | Behavior |
|----------|----------|----------|
| **Data States** | 0 domain reports yet | Skeleton loading with scan-line animation per panel |
| | 1 of 4 domains complete | Show completed domain, others show "Analyzing..." pulse |
| | All HEALTHY | Green "All Clear" state, muted visual effects, show "no anomalies detected" |
| | All FAILED | Red "Investigation Failed" banner, show per-agent failure reasons |
| | Mixed healthy/degraded | Only degraded domains get attention (glow, expanded), healthy ghosted |
| | Re-dispatch in progress | "Re-analyzing" pulse on affected domain panels, re-dispatch counter badge |
| **Topology** | 1-5 nodes | Grid heatmap, comfortable spacing |
| | 6-50 nodes | Dense grid, 12-col |
| | 50-200 nodes | Tiny pips (3px), zoom on hover |
| | 200+ nodes | Show "200+ nodes" with sample heatmap, tooltip for full count |
| | 0 nodes (data missing) | Placeholder: "Waiting for fleet data..." |
| **Workloads** | Deployments, StatefulSets, DaemonSets, CronJobs, Jobs, orphan pods | Each type gets distinct icon, DaemonSets show per-node rollout |
| **Causal Chains** | 0 chains | Verdict stack shows "Correlating events..." |
| | 1 chain, high confidence | Full display with root cause card |
| | Multiple chains | Ranked by confidence, only top chain in Root Cause card, others in verdict stack |
| | Low confidence (<50%) | Amber "SUSPECTED" badge instead of red "IDENTIFIED" |
| **Chat** | Empty context | Chat shows suggested prompts: "Which pods are restarting?", "Show me node disk usage" |
| | Mid-analysis | Chat can answer partial questions, prefixes with "Analysis still running..." |
| **Errors** | API fetch fails | Error banner with retry button, last-known data preserved |
| | WebSocket disconnect | "LIVE FEED" indicator turns gray, polls instead at 5s interval |
| | Agent timeout | Domain panel shows "TIMEOUT" with duration, offer re-dispatch |

---

## 2. Layout & Component Architecture

### Grid: 12-Column CSS Grid

```
+--LEFT (col-3)--+--CENTER (col-5)--+--RIGHT (col-4)--+
| Execution DAG   | Domain Panel     | Root Cause Card  |
| Fleet Heatmap   | (expanded)       | Verdict Stack    |
| Resource         | Vertical Ribbons | Remediation      |
|   Velocity       | (collapsed 3)    |   (hold-confirm) |
+-----------------+---------+-40px---+------------------+
            COMMAND BAR (full width, sticky bottom)
```

### Component Tree

```
ClusterWarRoom (state owner)
  ClusterHeader (session ID, confidence bar, live feed, namespace filter)
  NeuralPulseSVG (animated SVG overlay connecting columns)
  <grid cols-12>
    LeftColumn (col-3)
      ExecutionDAG (agent pipeline visualization)
      FleetHeatmap (node grid, clickable pips)
      ResourceVelocity (sparkline + pressure zone)
    CenterColumn (col-5)
      DomainPanel (expanded, one at a time)
        NamespaceSection (per-namespace collapsible)
          WorkloadCard (pod/deploy detail, metrics grid)
      VerticalRibbon x3 (collapsed domains, click to expand)
    RightColumn (col-4)
      RootCauseCard (red glow, key metrics)
      VerdictStack (timeline with severity dots)
      RemediationCard (kubectl command, risk assessment, hold-to-confirm)
      TeleScopeTab (edge-hover K8S manifest preview)
  CommandBar (sticky bottom, $ prompt)
  ChatDrawer (slide-up on Shift+Enter or command)
```

### Reusable Components (from App Diagnostics)

| Component | Reuse Strategy |
|-----------|---------------|
| `AgentFindingCard` | Adapt for WorkloadCard (same card structure, domain color border) |
| `CausalRoleBadge` | Direct reuse (ROOT CAUSE / CASCADING / CORRELATED) |
| `AnomalySparkline` | Direct reuse for Resource Velocity and per-pod metrics |
| `SaturationGauge` | Adapt for node CPU/Memory/Disk gauges |
| `ChatDrawer` | Direct reuse (already wired to cluster sessions) |
| `LedgerTriggerTab` | Direct reuse |
| `TimelineEntry` | Adapt for Verdict Stack timeline dots |
| `ConfidenceDot` | Direct reuse for domain confidence indicators |
| `PhaseProgress` | Adapt for Execution DAG step visualization |

### New Components (11)

| Component | Purpose |
|-----------|---------|
| `ClusterHeader` | Session ID, global confidence bar, live feed indicator, namespace filter |
| `ExecutionDAG` | Vertical agent pipeline (InputParser -> agents -> synthesizer) |
| `FleetHeatmap` | Grid of node pips with severity coloring and click selection |
| `ResourceVelocity` | SVG sparkline with pressure zone shading |
| `DomainPanel` | Expanded domain view with namespace-scoped workloads |
| `VerticalRibbon` | Collapsed domain strip (icon + sparkline + rotated label) |
| `WorkloadCard` | Pod/Deployment detail with metrics grid |
| `RootCauseCard` | Prominent root cause display with key metrics |
| `VerdictStack` | Timeline of correlated events with severity dots |
| `RemediationCard` | Kubectl command + risk assessment + hold-to-confirm button |
| `CommandBar` | Sticky bottom command input with $-prompt |

### Domain Panel Content by Type

| Domain | Key Metrics | Workload Focus |
|--------|------------|----------------|
| **Compute** | CPU%, Memory, Restarts, OOMKills | Pods, Deployments, StatefulSets |
| **Control Plane** | etcd latency, API server 5xx, scheduler queue | System pods, CRDs |
| **Network** | DNS errors, connection resets, ingress 5xx | Services, Ingress, NetworkPolicies |
| **Storage** | PVC usage%, IOPS, disk pressure, mount failures | PVCs, StorageClasses, CSI |

### Accordion Behavior ("Accordions of Truth")

- Default: most-affected domain expanded, others as vertical ribbons
- Click ribbon: that domain expands to col-span-5, previous collapses to ribbon
- Spring transition: 300ms ease-out with CSS `grid-template-columns` transition
- Collapsed ribbons show: Material icon, tiny health sparkline, vertical domain name
- Amber glow on ribbon if domain has anomalies, green for healthy

---

## 3. Interaction Refinements

### HeatMap as Global Controller

- Click any node pip in Fleet Heatmap -> center column jumps to that node's domain (Compute)
- Hover pip shows tooltip: `node-worker-3 | CPU: 94% | Disk: PRESSURE`
- Red pips pulse with `shadow-[0_0_12px_#ef4444]`
- Selected pip gets cyan ring (`ring-2 ring-duck-cyan`)
- Healthy nodes ghosted at 20% opacity (wireframe (16) "ghosting" pattern)

### Hold-to-Confirm Pattern

For destructive actions (CORDON, ISOLATE, TRACE):
- 1.5s hold duration
- Visual: red fill animation sweeps left-to-right on `active` state
- SVG progress ring (circular) fills simultaneously
- "HOLD" text in center of ring
- On release before 1.5s: resets
- On complete: vibration (mobile), flash, action dispatched to chat

### Impact Forecasts in Remediation

Show consequences, not just commands:
```
$ kubectl cordon node-worker-3
Risk Assessment: 12 pods will stop scheduling
Affected: payment-api (3), worker-main (9)
```

### Independent Panel Updates

- Each domain panel memoized on its domain slice of findings
- Namespace sections independently collapsible
- Healthy namespaces at opacity-40 with `hover:opacity-80 transition-opacity`
- Only troubled namespace fully expanded with pod-level detail

### Verdict Stack Tether Paths

- SVG cyan dotted paths connecting timeline events to related domain panels
- Severity-colored transitions (red for FATAL, amber for WARN, cyan for INFO)
- Ring-4 hover effect on timeline dots (matching wireframe (16))
- Dashed vertical line connecting all events

### TELE-SCOPE Edge Tab

- ~16px wide hoverable tab on right edge of right column
- On hover: expands to show K8S manifest preview (YAML-like)
- Context-aware: shows manifest for currently selected resource
- Subtle backdrop-blur effect

---

## 4. Visual Effects

### CRT Scan-Lines Overlay
- Full-screen `pointer-events-none` overlay with 1px horizontal lines at 3px intervals
- Very low opacity (0.03) so it's felt, not seen
- Uses `repeating-linear-gradient` for performance

### Neural Glow Paths
- Animated SVG paths between columns using `dash-pulse` keyframes
- Cyan paths from left->center, red paths from root cause->domain panels
- `filter: drop-shadow(0 0 4px #13b6ec)` for glow effect
- `mix-blend-mode: screen` on SVG container

### Radar Ripple on Domain Status Change
- When domain status updates, origin-center ripple using `box-shadow` animation
- Color matches severity (red for degraded, emerald for resolved)

### Node Glow in Heatmap
- Red nodes: `shadow-[0_0_12px_#ef4444]` with pulse animation
- Selected node: `ring-2 ring-duck-cyan ring-offset-1 ring-offset-duck-bg`
- Healthy nodes: 20% opacity, no glow

### Pressure Zone in Resource Velocity
- Area fill above REQUEST_LIMIT threshold line
- `fill: rgba(239, 68, 68, 0.2)` for the pressure zone
- Sparkline path with cyan stroke, gradient fill below

### Spring Expansion Transitions
- Domain panel expand/collapse: 300ms ease-out
- `transition-transform duration-300 hover:scale-[1.01]` on expanded panel
- Origin-center scaling for subtle depth effect

---

## 5. Data Flow

### Single Source of Truth

```
ClusterWarRoom
  state: { findings: ClusterHealthReport | null, loading, error }
  polling: 5s interval on GET /api/v4/session/{id}/findings

  -> ClusterHeader: confidence, platform_health, session_id
  -> LeftColumn: findings.domain_reports (for DAG), node heatmap data, resource metrics
  -> CenterColumn: findings.domain_reports[expanded_domain], namespace workloads
  -> RightColumn: findings.causal_chains[0], verdict timeline, remediation
  -> CommandBar: dispatch to chat context
```

### Memoization Strategy

- Each column receives only its data slice via props
- `useMemo` on domain report extraction per panel
- Namespace filter applied at ClusterWarRoom level before passing down
- VerdictStack and RootCauseCard memoized on causal_chains reference

### WebSocket Integration

- Reuse existing WebSocket from session for live task events
- Event types: `agent_started`, `agent_completed`, `agent_error`, `domain_update`
- On `domain_update`: merge into findings state without full re-fetch
- On disconnect: fall back to polling (already implemented)

---

## 6. Files Changed

### New Files (11 components + 1 CSS)

```
frontend/src/components/ClusterDiagnostic/
  ClusterHeader.tsx
  ExecutionDAG.tsx
  FleetHeatmap.tsx
  ResourceVelocity.tsx
  DomainPanel.tsx
  VerticalRibbon.tsx
  WorkloadCard.tsx
  RootCauseCard.tsx
  VerdictStack.tsx
  RemediationCard.tsx
  CommandBar.tsx
```

### Modified Files

```
frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx  (full rewrite - becomes orchestrator)
frontend/src/index.css  (add CRT scan-lines, neural-pulse, dash-flow animations)
frontend/src/types/index.ts  (extend ClusterHealthReport with namespace/workload types)
```

### Design Tokens (from wireframe)

```
Colors:
  duck-bg: #0f2023
  duck-surface: #152a2f
  duck-border: #1f3b42
  duck-cyan: #13b6ec
  duck-amber: #f59e0b
  duck-red: #ef4444
  duck-emerald: #10b981

Fonts:
  Display: Space Grotesk (300, 500, 700)
  Mono: JetBrains Mono (400, 700)
```
