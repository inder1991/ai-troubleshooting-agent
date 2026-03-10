# War Room Homepage Upgrade — Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan from this design.

**Goal:** Transform the Home Dashboard from a flat activity feed into an enterprise "Command Center" with situational awareness, AI transparency, and personal workspace context.

**Design Principle:** Never fill space just to fill space. Fill it with situational awareness. Follow the OODA loop: Observe → Orient → Decide → Act.

---

## Architecture: The 3-Row Command Center Grid

```
┌─────────────────────────────────────────────────────────┐
│  Row 0: Header (existing, unchanged)                    │
├───────────────────────────────┬─────────────────────────┤
│  MetricRibbon (8 cols)        │ EnvironmentHealth (4)   │
│  [4 metric cards, auto-h]     │ [NOC matrix minimap]    │
├───────────────────────────────┼─────────────────────────┤
│  Live Intelligence Feed       │ QuickActions (240px)    │
│  (8 cols, locked h-[500px])   ├─────────────────────────┤
│                               │ AgentFleetPulse (240px) │
│  Tabs: "Global Feed" |        │  ┌─ Swarm (100px) ───┐ │
│        "My Investigations"    │  │ ● ● ● ● ● ● ● ●  │ │
│                               │  └──────────────────┘ │ │
│  [scrollable internally]      │  ┌─ Ticker (140px) ──┐ │
│                               │  │ 🔄 k8s-agent...   │ │
│                               │  │ 🧠 critic...      │ │
│                               │  └──────────────────┘ │ │
├───────────────────────────────┴─────────────────────────┤
│  Capability Launcher (12 cols, full width)               │
└─────────────────────────────────────────────────────────┘
```

### Layout Constraints

- **Row 1** (Triage): `grid-cols-12 gap-6 mb-6` — MetricRibbon (8 cols) + EnvironmentHealth (4 cols), auto height
- **Row 2** (Workspace): `grid-cols-12 gap-6 mb-8 h-[500px] items-stretch` — locked height
  - Left (8 cols): `flex-col h-full` with internal scroll, tab bar at top
  - Right (4 cols): `flex-col gap-5 h-full` — QuickActions (`h-[240px] shrink-0`) + AgentFleetPulse (`h-[240px] shrink-0`)
  - Math: 240px + 20px gap + 240px = 500px ✓
- **Row 3** (Toolbelt): CapabilityLauncher, full 12 cols

---

## Component 1: Agent Fleet Pulse

**File:** `frontend/src/components/Home/AgentFleetPulse.tsx` (new)

**Data:** `useQuery({ queryKey: ['agent-fleet'], queryFn: fetchAgentFleet, refetchInterval: 5000, staleTime: 3000 })`

**API:** `GET /api/v4/agents` → returns agents with `status`, `recent_executions[]`, health probes

### Visual State Derivation

The API returns `status: 'active' | 'degraded' | 'offline'`. The frontend derives a richer visual state:

| API status | recent_executions in last 60s? | Visual State | Color |
|------------|-------------------------------|-------------|-------|
| `active` | No | **Idle** | `bg-duck-surface` (gray) |
| `active` | Yes | **Analyzing** | `bg-duck-accent animate-pulse` (cyan) |
| `degraded` | — | **Degraded** | `bg-amber-500` |
| `offline` | — | **Offline** | `bg-red-500` |

This ensures cyan only lights up when an agent is genuinely doing work right now, preserving signal strength.

### Top Half — The Swarm (~100px)

- Summary bar: `Agent Fleet  ●24 Active  ●1 Degraded  ●0 Offline`
- Dense dot-matrix grid: `grid-cols-[repeat(auto-fit,minmax(12px,1fr))] gap-1`
- Each dot: `w-2.5 h-2.5 rounded-sm` with color from visual state
- Wrapped in `<Tooltip.Provider delayDuration={0}>` for zero-delay hover
- Each dot gets `<Tooltip.Root>` → `<Tooltip.Trigger asChild>` + `<Tooltip.Content>` showing agent name, status, role
- **Overflow handling:** `overflow-y-auto custom-scrollbar pr-1` on the swarm container so 500+ agents scroll within the 100px box

### Bottom Half — The Ticker (~140px)

- Derives active operations: `useMemo` over all agents' `recent_executions`, filtered to last 60s, sorted by timestamp desc, sliced to 4
- Wrapped in `<AnimatePresence initial={false}>` for smooth terminal-like flow
- Each entry: `motion.div` with `initial={{ opacity: 0, height: 0, y: -10 }}`, `animate={{ opacity: 1, height: 'auto', y: 0 }}`, `exit={{ opacity: 0, height: 0 }}`
- Format: colored dot + agent name (bold cyan) + `→` + summary text (muted)
- **Empty state:** "All agents standing by" with `duck-muted` text when no recent executions

---

## Component 2: Environment Health (NOC Matrix)

**File:** `frontend/src/components/Home/EnvironmentHealth.tsx` (new)

**Data:** `useQuery({ queryKey: ['env-health-snapshot'], queryFn: fetchEnvironmentSnapshot, refetchInterval: 10000 })`

**API:** `/api/v4/network/monitor/snapshot` → normalized to `HealthNode[]`

### HealthNode Interface

```typescript
interface HealthNode {
  id: string;
  name: string;
  type: 'cluster' | 'database' | 'network' | 'service';
  status: 'healthy' | 'degraded' | 'critical' | 'offline';
  latencyMs?: number;
}
```

### Visual Design

**Header:**
- Title: "Environment Health" (xs, uppercase, duck-muted)
- Subtitle: `{healthyCount}/{nodes.length} Systems Nominal` (10px, mono, slate-400)
- Issue badge (conditionally): red pill with `{issueCount} Issues` when > 0

**The Matrix:**
- CSS Grid: `grid-cols-[repeat(auto-fit,minmax(20px,1fr))] gap-1.5`
- Each block: `aspect-square rounded-[3px] border` with status-driven styles
- Wrapped in `<Tooltip.Provider delayDuration={0}>` for zero-delay hover
- Tooltip shows node name, status (colored), latency

**Status → Style Mapping (The "Whisper" Rule):**

| Status | Styles | Rationale |
|--------|--------|-----------|
| `healthy` | `bg-duck-surface border-duck-border/40 hover:border-duck-accent/50` | 99% of blocks "whisper" — recede into background |
| `degraded` | `bg-amber-500/20 border-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)] animate-pulse` | Amber glow draws attention |
| `critical` | `bg-red-500/20 border-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)] animate-pulse` | Red glow screams urgency |
| `offline` | `bg-slate-800 border-slate-700 opacity-50` | Grayed out, clearly disconnected |

**Loading state:** 48 skeleton blocks with `animate-pulse`

**Scaling:** `auto-fit` + `minmax(20px, 1fr)` ensures 12 or 120 nodes justify perfectly with no ragged edges. `overflow-y-auto` handles extreme scale.

---

## Component 3: My Investigations (Tab in Live Feed)

**File:** Modified in `HomePage.tsx` (tab state) — `LiveIntelligenceFeed` unchanged

### Tab Bar

Rendered in the Row 2 left column wrapper, above the feed:

- Two tabs: "Global Feed" and "My Investigations ({count})"
- Active tab: `text-white border-b-2 border-duck-accent`
- Inactive tab: `text-duck-muted hover:text-slate-300`

### "My Investigations" v1 Logic (No Backend Schema Change)

- Reads from the same `['live-sessions']` React Query cache
- Filters for active sessions (`status` not in `['complete', 'diagnosis_complete', 'error']`)
- Sorted by `updated_at` desc, take first 5
- Approximates "my work" in a single-user context

### v2 Upgrade Path (Future)

- Add `assigned_to: string` and `pinned: boolean` to V4Session schema
- Backend endpoint: `GET /api/v4/sessions?assigned_to=me&pinned=true`
- True multi-user personalization

---

## HomePage.tsx Grid Restructure

The main scrollable content area becomes:

```tsx
<div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
  {/* ROW 1: Triage & Health */}
  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
    <div className="lg:col-span-8"><MetricRibbon /></div>
    <div className="lg:col-span-4"><EnvironmentHealth /></div>
  </div>

  {/* ROW 2: Core Workspace (locked 500px) */}
  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8 items-stretch lg:h-[500px]">
    {/* Left: Feed with tab bar */}
    <div className="lg:col-span-8 flex flex-col h-full bg-duck-panel border border-duck-border rounded-lg overflow-hidden">
      {/* Tab bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-duck-border bg-duck-card/30 shrink-0">
        <div className="flex gap-6">
          <button>Global Feed</button>
          <button>My Investigations (N)</button>
        </div>
        <TimeRangeSelector />
      </div>
      {/* Scrollable feed */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <LiveIntelligenceFeed onSelectSession={onSelectSession} />
      </div>
    </div>

    {/* Right: QuickActions + AgentFleetPulse */}
    <div className="lg:col-span-4 flex flex-col gap-5 h-full">
      <div className="h-[240px] shrink-0">
        <QuickActionsPanel ... />
      </div>
      <div className="h-[240px] shrink-0">
        <AgentFleetPulse />
      </div>
    </div>
  </div>

  {/* ROW 3: Capabilities */}
  <section>
    <h2>Capabilities</h2>
    <CapabilityLauncher ... />
  </section>
</div>
```

---

## New Dependencies

| Package | Purpose | Status |
|---------|---------|--------|
| `@radix-ui/react-tooltip` | Zero-delay, accessible tooltips for swarm dots and heatmap blocks | **New install** |
| `@tanstack/react-query` | Polling for agent fleet (5s) and env health (10s) | Already installed |
| `framer-motion` | AnimatePresence for ticker animations | Already installed |

---

## New API Wrapper Functions

**File:** `frontend/src/services/api.ts`

```typescript
// Fetch agent fleet status
export async function fetchAgentFleet(): Promise<AgentFleetResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v4/agents`);
  if (!res.ok) throw new Error('Failed to fetch agent fleet');
  return res.json();
}

// Fetch environment health snapshot, normalized to HealthNode[]
export async function fetchEnvironmentSnapshot(): Promise<HealthNode[]> {
  const res = await fetch(`${API_BASE_URL}/api/v4/network/monitor/snapshot`);
  if (!res.ok) throw new Error('Failed to fetch environment snapshot');
  const data = await res.json();
  // Normalize snapshot data to HealthNode[]
  return normalizeSnapshotToHealthNodes(data);
}
```

---

## New Types

**File:** `frontend/src/types/index.ts`

```typescript
// Agent Fleet
interface AgentFleetAgent {
  id: string;
  name: string;
  workflow: string;
  role: string;
  status: 'active' | 'degraded' | 'offline';
  recent_executions: {
    session_id: string;
    timestamp: string;
    status: 'SUCCESS' | 'ERROR';
    duration_ms: number;
    summary: string;
  }[];
}

interface AgentFleetResponse {
  agents: AgentFleetAgent[];
  summary: { total: number; active: number; degraded: number; offline: number };
}

// Environment Health
interface HealthNode {
  id: string;
  name: string;
  type: 'cluster' | 'database' | 'network' | 'service';
  status: 'healthy' | 'degraded' | 'critical' | 'offline';
  latencyMs?: number;
}
```

---

## Not In Scope (Deferred)

- **Token Budget / ROI cards** — Needs aggregate cross-session endpoint
- **True session pinning** — Needs `assigned_to`/`pinned` schema fields
- **Global search handler (Cmd+K)** — Separate initiative
- **Real system health metrics** in QuickActionsPanel (CPU/Memory/Latency still hardcoded)
