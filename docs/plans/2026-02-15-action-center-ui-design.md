# Action Center UI Redesign

## Goal

Replace the current "straight into session" UI with a capability-first landing experience. Users see 4 action cards, pick a capability, fill a form, then enter the session workspace with a progressive layout that reveals the right results panel as data arrives.

## Capabilities

| Card | Label | Subtitle | Icon |
|------|-------|----------|------|
| 1 | Troubleshoot Application | Diagnose production incidents with AI agents | magnifying glass |
| 2 | PR Review | AI-powered code review for pull requests | file-text |
| 3 | GitHub Issue Fix | Analyze and fix GitHub issues automatically | bug |
| 4 | Cluster Diagnostics | OpenShift & Kubernetes health analysis | container |

## Layout States

### State 1: Home (no active session)

```
+------------+--------------------------------+
| Sidebar    |        Action Center           |
|            |                                |
| Recent     |   "What would you like to do?" |
| Sessions   |                                |
| ---------- |   [Card 1]  [Card 2]           |
| #12 order  |   [Card 3]  [Card 4]           |
| #11 pay    |                                |
|            |   Recent Activity              |
|            |   order-svc | 2m ago | Resume  |
|            |   PR #142   | 1h ago | View    |
+------------+--------------------------------+
```

- Sidebar shows recent sessions grouped by capability type
- Center shows 2x2 card grid
- Below cards: "Recent Activity" quick-access list
- No right panel

### State 2: Form (user picked a capability)

```
+------------+--------------------------------+
| Sidebar    |   <- Back                      |
|            |   Troubleshoot Application     |
|            |                                |
|            |   Service Name  [___________]  |
|            |   Time Window   [___] to [___] |
|            |   Trace ID      [___________]  |
|            |   Namespace     [___________]  |
|            |   ELK Index     [___________]  |
|            |                                |
|            |         [Start Diagnosis]      |
+------------+--------------------------------+
```

- Cards animate out, form slides in (same center area)
- Back arrow returns to action center
- Form fields differ per capability (see below)
- No right panel yet

### State 3: Active Session (diagnosis running, no results yet)

```
+------------+-------------------+-------------+
| Sidebar    |   Chat Panel      | Results     |
|            |                   | Panel       |
|            |  Starting         |             |
|            |  diagnosis...     | Waiting for |
|            |  ░░░░░░░░░░       | results...  |
|            |                   |             |
|            |  [input box]      |             |
+------------+-------------------+-------------+
|  Logs o--- Metrics o--- K8s o--- Done       |
+----------------------------------------------+
```

- Right panel slides in with empty/loading state
- Progress bar appears at bottom
- Chat is center, primary interaction

### State 4: Results Arriving (agents completing)

```
+------------+-------------------+-------------+
| Sidebar    |   Chat Panel      | Dashboard   |
|            |                   | +--------+  |
|            | Found 3 error     | |Errors  |  |
|            | patterns in       | |--------|  |
|            | order-service..   | |Pattern1|  |
|            |                   | +--------+  |
|            | +--- Log Agent 87%| +--------+  |
|            | | ConnectionTimeout| |Metrics|  |
|            | | 23 hits          | |chart   |  |
|            | |  [View Details]  | +--------+  |
|            | +----------------+| +--------+  |
|            |                   | |Activity|  |
|            | Checking metrics..| |Log     |  |
|            |                   | +--------+  |
|            |  [input box]      | Tokens: 12k |
+------------+-------------------+-------------+
|  Logs *--- Metrics o--- K8s o--- Done       |
+----------------------------------------------+
```

- Right panel: scrollable stack of cards (not tabs)
- Cards appear as agents complete
- Activity log + token summary at bottom of right panel
- Progress bar updates as phases complete

## Form Fields Per Capability

### Troubleshoot Application
- Service Name (required)
- Time Window: start, end (required)
- Trace ID (optional)
- Namespace (optional)
- ELK Index (optional, default: app-logs-*)
- Repo URL (optional)

### PR Review
- Repository URL (required)
- PR Number or URL (required)
- Focus Areas (optional): security, performance, correctness, style

### GitHub Issue Fix
- Repository URL (required)
- Issue Number or URL (required)
- Branch to fix against (optional, default: main)

### Cluster Diagnostics
- Cluster URL (required)
- Namespace (optional, default: all)
- Symptoms / description (optional textarea)
- Auth: Token or Kubeconfig (required)

## Right Panel Card Stack (per capability)

| Capability | Cards (top to bottom) |
|---|---|
| Troubleshoot App | Error Patterns, Metrics Chart, K8s Status, Trace View, Code Impact, Diagnosis Summary, Activity Log, Token Summary |
| PR Review | PR Diff Overview, Code Quality Findings, Security Issues, Performance Concerns, Summary |
| GitHub Issue Fix | Issue Details, Related Code, Root Cause Analysis, Proposed Fix Diff, Summary |
| Cluster Diagnostics | Node Health, Pod Status Grid, Events Timeline, Resource Usage Charts, Summary |

## Progress Bar

Multi-step indicator below the main content area:

```
Logs ●━━━ Metrics ●━━━ K8s ○━━━ Tracing ○━━━ Code ○━━━ Done
      done        done       running
```

- Steps vary by capability
- Green dot + solid line = complete
- Pulsing dot = running
- Empty dot + dashed line = pending

## Chat Inline Cards

Agent results appear in chat as compact inline cards:

```
+--- Log Agent ────────────── 87% ──+
| Found ConnectionTimeout pattern    |
| affecting order-service (23 hits)  |
|                  [View in Results] |
+------------------------------------+
```

"View in Results" scrolls the right panel to the corresponding card.

## Additional UX Features

### Keyboard Shortcuts
- Ctrl+N: New session (opens action center)
- Ctrl+1/2/3/4: Quick-pick capability
- Ctrl+Enter: Send chat message
- Esc: Back to action center (when in form)

### Dark Mode
Default dark theme (SRE tools used during incidents at all hours).

### Responsive Behavior
- Right panel collapses to a slide-out drawer on narrow screens
- Cards stack vertically in right panel (already scrollable)

## Technology

- React 18 + TypeScript
- Tailwind CSS (already configured)
- lucide-react for icons (already installed)
- Existing WebSocket infrastructure (useWebSocketV4)
- Existing v4 API functions

## What Changes

| Component | Change |
|---|---|
| App.tsx | Major rewrite: add layout states, right panel, progress bar |
| SessionSidebar.tsx | Add capability type badges, group by type |
| NEW: ActionCenter.tsx | Home screen with 4 capability cards |
| NEW: CapabilityForm.tsx | Dynamic form per capability type |
| NEW: ResultsPanel.tsx | Right panel with scrollable card stack |
| NEW: ProgressBar.tsx | Multi-step progress indicator |
| TabLayout.tsx | Remove (replaced by right panel card stack) |
| StatusBar.tsx | Move into progress bar area |
| ChatTab.tsx | Keep as center panel (no longer in tab) |
| DashboardTab.tsx | Remove (cards move to ResultsPanel) |
| ActivityLogTab.tsx | Move into ResultsPanel as a card |
| types/index.ts | Add CapabilityType, form types |
| services/api.ts | Add capability-specific start endpoints |
