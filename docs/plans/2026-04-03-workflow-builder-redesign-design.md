# Workflow Builder Redesign — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** Redesign the Workflow Builder into an enterprise-grade tool that is usable by both engineers and non-engineers through three synchronized views: Canvas, List, and Code.

**Users:** Mixed — engineers build and debug workflows; non-technical team leads review, configure, and trigger them.

**Architecture:** A shared workflow data model (parsed YAML) drives three synchronized view components. All three views read from and write to the same in-memory workflow state. The config sidebar is a single shared component rendered in both Canvas and List views.

**Tech Stack:** React + TypeScript + Tailwind, ReactFlow v11 (canvas), existing workflowParser.ts (data model), design tokens from `src/styles/tokens.ts`

---

## 1. Library Page Redesign

### Layout
- Full-page catalog replacing the current 2×2 card grid
- Search bar at top (filters both templates and saved workflows)
- Hero card for the recommended template (App Diagnostics) — full width, shows last run stats
- Remaining templates as compact horizontal rows (not identical cards)
- "My Workflows" section showing saved workflows with last-modified timestamp and last run status
- `[+ New Workflow]` button in the header (primary CTA)
- `[+ Request a template]` placeholder row at end of templates section

### Hero Card
```
┌─────────────────────────────────────────────────────┐
│ ⭐ RECOMMENDED                                       │
│ App Diagnostics                          [Open →]   │
│ Diagnose application errors — log analysis,         │
│ metrics, tracing, and automated fix proposal        │
│ 8 steps · 4 workflows run · 94% success rate        │
└─────────────────────────────────────────────────────┘
```

### Saved Workflows Row
- Icon + workflow name + "Modified 3h ago" + last run status badge + `[Open]` button
- Delete on hover (same pattern as before)
- Empty saved state: "No saved workflows yet — open a template and click Save."

---

## 2. Editor Toolbar

### Structure (left → right)
```
[← Workflows]  [Workflow Name ✎]        [Canvas][List][Code]        [● Valid]  [Save]  [▶ Run]
               [workflow_id mono]
```

- **Back button** — left, always visible, `textMuted` with hover to `textPrimary`
- **Workflow name** — click to rename inline (input replaces text, blur to confirm). ID shown below in `font-mono textMuted`
- **View switcher** — centered tab group with three segments: `Canvas · List · Code`. Active tab highlighted with cyan underline/fill.
- **Status badge** — `● Valid` (green) or `⚠ N errors` (red). Clicking an error badge opens Code view and highlights the first error line.
- **Save** — secondary action, saves to localStorage
- **▶ Run** — primary CTA, most visually prominent button. Triggers workflow execution (navigates to Workflow Runs or calls run API).

---

## 3. Canvas View

### Layout
- Full-width ReactFlow canvas with dark background (`bgBase`)
- Floating mini-toolbar at top of canvas: `[+ Add Step]` `[⚡ Auto-layout]` | zoom controls
- Right sidebar (320px) slides in when a node is selected, stays open until closed

### Node Design
```
┌─────────────────────┐
│ 📊  Log Analysis    │  ← human label (font-display)
│  log_analysis_agent │  ← agent ID (font-mono, small, muted)
│  ● completed        │  ← live status dot + label
└─────────────────────┘
```
- Human gate steps: amber left-border, ⏸ icon, "Human Gate" badge below agent ID
- Selected node: cyan outline ring
- Edges: smoothstep, arrowClosed marker, `rgba(7,182,213,0.3)` stroke
- Empty canvas: centered icon + "Add your first step" button

### Interactions
- **Click node** → opens config sidebar, highlights selected node
- **Click canvas** → deselects node, collapses sidebar
- **Drag node** → reposition freely (ReactFlow default)
- **⚡ Auto-layout** → reflows nodes top-to-bottom using dagre/tiered layout
- **`+ Add Step`** → opens Agent Picker modal, inserts new node after selected or at end

---

## 4. List View

### Layout
- Left/center: ordered step cards (full width minus sidebar)
- Right: same config sidebar as Canvas (320px, slides in on step click)

### Step Card
```
⠿  2  📈 Metrics Check                [···]  >
        metrics_agent
        After: Log Analysis
```
- `⠿` drag handle (reorder)
- Step number (auto-computed from order)
- Agent icon + human label (font-display)
- Agent ID below (font-mono, textMuted)
- `After: [step label]` dependency summary in plain language (not raw IDs)
- `⏸ Gate` badge if human gate enabled
- `[···]` overflow menu: Duplicate, Move Up, Move Down, Delete
- `>` chevron indicating config opens on click
- Selected step is highlighted with cyan left-border

### Add Step
- `[+ Add Step]` button at bottom of list → Agent Picker modal
- New step inserted after currently selected step (or at end)

---

## 5. Code View

### Layout
- Full-width YAML editor with line numbers
- Status bar below editor: `● Synced` (green) when visual ↔ code are in sync; `◌ Unsaved changes` (amber) when YAML has been manually edited and not yet parsed
- Error panel below (existing behavior, improved): each error is a clickable row that scrolls to the offending line
- `[Copy]` and `[Format]` buttons in the panel header

### Sync Behavior
- Editing in Canvas/List updates YAML immediately (debounced 300ms)
- Editing YAML triggers re-parse; if valid, updates Canvas/List; if invalid, shows errors but does not break the visual views
- "Format" button normalizes indentation and field order

---

## 6. Step Config Sidebar (Shared)

Used identically in Canvas and List views. Slides in from the right (320px). Stays open across node/step selections.

### Sections

**Basic**
- Label: text input (human-readable name shown in nodes/cards)
- Agent: searchable dropdown → opens Agent Picker inline
- Description: optional textarea (shown as tooltip on nodes)

**Dependencies**
- Multi-select chip list: each chip shows the human label of the dependency
- `[+ Add dependency]` → opens step picker dropdown
- Chips are removable with `×`

**Execution**
- Timeout: number input + "seconds" label
- Retries: segmented selector 0–5 (visual: filled squares `■■□□□`)
- Retry delay: number input + "seconds" label

**Control Flow**
- Human Gate: toggle switch (when on, step pauses for approval before continuing)
- Skip if: text input for conditional expression (placeholder: `e.g. prev.confidence > 0.9`)

**Agent Parameters**
- Dynamic key-value pair list
- `[key]` `[value]` `[×]` per row
- `[+ Add parameter]` at bottom

**Danger Zone**
- `[🗑 Delete Step]` — red text button at very bottom, confirmation required

---

## 7. Agent Picker Modal

Triggered by: `+ Add Step` in Canvas/List, agent dropdown in config sidebar.

```
┌────────────────────────────────────────┐
│ Choose an Agent                  [×]   │
│ [🔍 Search agents...              ]    │
│ ─────────────────────────────────────  │
│ App Diagnostics                        │
│  ● log_analysis_agent   Log Analysis   │
│  ● metrics_agent        Metrics Check  │
│  ● tracing_agent        Tracing        │
│                                        │
│ Cluster Diagnostics                    │
│  ● k8s_agent            Kubernetes     │
│  ○ change_agent         offline        │
│ ─────────────────────────────────────  │
│                          [Cancel]      │
└────────────────────────────────────────┘
```

- Status dot: green (active), amber (degraded), red (offline)
- Offline agents shown but dimmed with "offline" label — non-engineers understand why a step might be unavailable
- Search filters both id and display name
- Click → selects agent, closes modal, updates config sidebar

---

## 8. Shared Workflow State Model

All three views derive from a single `WorkflowState` object:

```ts
interface WorkflowState {
  id: string;
  name: string;
  version: string;
  triggers: string[];
  steps: WorkflowStep[];
  yaml: string;          // source of truth for Code view
  errors: string[];      // parse errors
  dirty: boolean;        // unsaved changes
}

interface WorkflowStep {
  id: string;            // unique step ID
  label: string;         // human-readable name
  agent: string;         // agent ID
  description?: string;
  depends_on: string[];  // step IDs
  timeout?: number;
  retries?: number;
  retry_delay?: number;
  human_gate?: boolean;
  skip_if?: string;
  parameters?: Record<string, string>;
}
```

- YAML is always the serialization format; `parseWorkflowYaml` produces `WorkflowState`
- Any visual edit calls a `updateStep` / `addStep` / `removeStep` action that re-serializes to YAML
- The `yaml` field drives Code view; all other fields drive Canvas and List

---

## 9. New Files to Create

| File | Purpose |
|------|---------|
| `WorkflowBuilderView.tsx` | Rewrite — toolbar + view switcher + view routing |
| `WorkflowLibraryView.tsx` | Rewrite — hero card + template rows + saved workflows |
| `WorkflowCanvas.tsx` | New — ReactFlow canvas view |
| `WorkflowList.tsx` | New — step list view |
| `WorkflowCodeView.tsx` | New — extracted code/YAML view |
| `StepConfigSidebar.tsx` | New — shared config panel |
| `AgentPickerModal.tsx` | New — agent selection modal |
| `useWorkflowState.ts` | New — shared state hook (replaces inline yaml useState) |
| `workflowSerializer.ts` | New — `stateToYaml()` and `yamlToState()` |

### Files to Modify
| File | Change |
|------|--------|
| `workflowParser.ts` | Extend to output `WorkflowStep[]` with new fields (label, timeout, retries, etc.) |
| `WorkflowDagPreview.tsx` | Replaced by `WorkflowCanvas.tsx` |
| `AgentBrowserPanel.tsx` | Replaced by `AgentPickerModal.tsx` |

---

## 10. Out of Scope (Backend — next week)

- Actual workflow execution via `▶ Run` (button present, wired to navigate to Workflow Runs)
- Agent parameter validation per agent type
- Conditional skip expression evaluation
- Workflow version history
