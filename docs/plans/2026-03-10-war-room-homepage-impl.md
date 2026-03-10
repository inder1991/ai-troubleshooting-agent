# War Room Homepage Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the Home Dashboard into an enterprise Command Center with Agent Fleet Pulse, Environment Health NOC matrix, My Investigations tab, and a strict 3-row grid layout.

**Architecture:** Three new components (AgentFleetPulse, EnvironmentHealth, feed tab bar) drop into a restructured HomePage grid. Both data-fetching components use TanStack Query with aggressive polling. Radix UI provides zero-delay tooltips for dense UI elements.

**Tech Stack:** React 18, TypeScript, TanStack Query, Framer Motion, @radix-ui/react-tooltip, Tailwind CSS Grid

**Design Doc:** `docs/plans/2026-03-10-war-room-homepage-design.md`

---

### Task 1: Install @radix-ui/react-tooltip

**Files:**
- Modify: `frontend/package.json` (via npm install)

**Step 1: Install the dependency**

Run: `cd frontend && npm install @radix-ui/react-tooltip`

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (no components use it yet)

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: install @radix-ui/react-tooltip for enterprise hover states"
```

---

### Task 2: Add HealthNode type to types/index.ts

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add the HealthNode interface**

Add at the end of the file, before the closing comments or after the last export:

```typescript
// ===== Environment Health Types =====

export interface HealthNode {
  id: string;
  name: string;
  type: 'cluster' | 'database' | 'network' | 'service';
  status: 'healthy' | 'degraded' | 'critical' | 'offline';
  latencyMs?: number;
}
```

Note: `AgentInfo`, `AgentMatrixResponse`, `AgentExecution` already exist in this file (lines 1271-1299). No new agent types needed.

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add HealthNode interface for environment health matrix"
```

---

### Task 3: Add fetchEnvironmentHealth API wrapper

**Files:**
- Modify: `frontend/src/services/api.ts`

The `fetchMonitorSnapshot()` function already exists (line 756) and calls `GET /api/v4/network/monitor/snapshot`. We need a wrapper that normalizes its response to `HealthNode[]`.

**Step 1: Add the normalizer function**

Add after the existing `fetchMonitorSnapshot` function:

```typescript
import type { HealthNode } from '../types';

/** Normalize monitor snapshot into HealthNode[] for the Environment Health matrix */
export const fetchEnvironmentHealth = async (): Promise<HealthNode[]> => {
  const snapshot = await fetchMonitorSnapshot();
  const nodes: HealthNode[] = [];

  // Map devices from snapshot to HealthNode format
  if (snapshot.devices && Array.isArray(snapshot.devices)) {
    for (const device of snapshot.devices) {
      const deviceStatus = device.status?.toLowerCase() ?? 'unknown';
      let healthStatus: HealthNode['status'] = 'healthy';
      if (deviceStatus === 'critical' || deviceStatus === 'down') healthStatus = 'critical';
      else if (deviceStatus === 'degraded' || deviceStatus === 'warning') healthStatus = 'degraded';
      else if (deviceStatus === 'offline' || deviceStatus === 'unreachable') healthStatus = 'offline';

      nodes.push({
        id: device.id || device.ip || `device-${nodes.length}`,
        name: device.hostname || device.ip || 'Unknown',
        type: device.device_type?.includes('switch') || device.device_type?.includes('router') ? 'network' : 'service',
        status: healthStatus,
        latencyMs: device.latency_ms ?? device.response_time_ms,
      });
    }
  }

  // If snapshot has no devices, return fallback placeholder nodes
  // so the matrix isn't empty on first load
  if (nodes.length === 0) {
    const fallbackDomains = [
      { id: 'core-api', name: 'Core API', type: 'service' as const },
      { id: 'k8s-cluster', name: 'K8s Cluster', type: 'cluster' as const },
      { id: 'postgres-primary', name: 'PostgreSQL', type: 'database' as const },
      { id: 'redis-cache', name: 'Redis Cache', type: 'database' as const },
      { id: 'elasticsearch', name: 'Elasticsearch', type: 'service' as const },
      { id: 'edge-network', name: 'Edge Network', type: 'network' as const },
    ];
    for (const d of fallbackDomains) {
      nodes.push({ ...d, status: 'healthy' });
    }
  }

  return nodes;
};
```

**Step 2: Add the HealthNode import at the top of api.ts**

The file already imports from `'../types'`. Add `HealthNode` to the existing import:

```typescript
import type {
  // ...existing imports...
  HealthNode,
} from '../types';
```

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/types/index.ts
git commit -m "feat(api): add fetchEnvironmentHealth normalizer for NOC matrix"
```

---

### Task 4: Create EnvironmentHealth.tsx

**Files:**
- Create: `frontend/src/components/Home/EnvironmentHealth.tsx`

**Step 1: Create the component**

```tsx
import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as Tooltip from '@radix-ui/react-tooltip';
import { fetchEnvironmentHealth } from '../../services/api';
import type { HealthNode } from '../../types';

const getNodeStyles = (status: HealthNode['status']) => {
  switch (status) {
    case 'critical':
      return 'bg-red-500/20 border-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)] animate-pulse';
    case 'degraded':
      return 'bg-amber-500/20 border-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)] animate-pulse';
    case 'offline':
      return 'bg-slate-800 border-slate-700 opacity-50';
    case 'healthy':
    default:
      return 'bg-duck-surface border-duck-border/40 hover:border-duck-accent/50 transition-colors';
  }
};

const statusTextColor = (status: HealthNode['status']) =>
  status === 'healthy' ? 'text-emerald-400' : status === 'degraded' ? 'text-amber-400' : 'text-red-400';

export const EnvironmentHealth: React.FC = () => {
  const { data: nodes = [], isLoading } = useQuery({
    queryKey: ['env-health-snapshot'],
    queryFn: fetchEnvironmentHealth,
    refetchInterval: 10000,
  });

  const { healthyCount, issueCount } = useMemo(() => {
    const issues = nodes.filter(n => n.status !== 'healthy');
    return {
      healthyCount: nodes.length - issues.length,
      issueCount: issues.length,
    };
  }, [nodes]);

  return (
    <div className="bg-duck-panel border border-duck-border rounded-lg h-full p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div>
          <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider">
            Environment Health
          </h3>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {isLoading ? 'Scanning...' : `${healthyCount}/${nodes.length} Systems Nominal`}
          </div>
        </div>

        {!isLoading && issueCount > 0 && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-red-500/10 border border-red-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" aria-hidden="true" />
            <span className="text-[9px] leading-none font-bold text-red-400 uppercase tracking-wider">
              {issueCount} {issueCount === 1 ? 'Issue' : 'Issues'}
            </span>
          </div>
        )}
      </div>

      {/* NOC Matrix */}
      <div className="flex-1 overflow-y-auto custom-scrollbar pr-1">
        <Tooltip.Provider delayDuration={0}>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(20px,1fr))] gap-1.5">
            {isLoading ? (
              Array.from({ length: 48 }).map((_, i) => (
                <div key={i} className="aspect-square rounded-[3px] bg-duck-surface animate-pulse" />
              ))
            ) : (
              nodes.map((node) => (
                <Tooltip.Root key={node.id}>
                  <Tooltip.Trigger asChild>
                    <button
                      className={`aspect-square rounded-[3px] border ${getNodeStyles(node.status)}`}
                      aria-label={`${node.name} status: ${node.status}`}
                    />
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      className="z-50 bg-duck-flyout border border-duck-border rounded px-2.5 py-1.5 shadow-xl"
                      sideOffset={5}
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="text-[10px] font-bold text-white uppercase tracking-wider">
                          {node.name}
                        </span>
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                          <span className={statusTextColor(node.status)}>
                            {node.status.toUpperCase()}
                          </span>
                          {node.latencyMs != null && (
                            <span className="text-slate-500">{node.latencyMs}ms</span>
                          )}
                        </div>
                      </div>
                      <Tooltip.Arrow className="fill-duck-border" />
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              ))
            )}
          </div>
        </Tooltip.Provider>
      </div>
    </div>
  );
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS (component not yet imported anywhere)

**Step 3: Commit**

```bash
git add frontend/src/components/Home/EnvironmentHealth.tsx
git commit -m "feat(health): add EnvironmentHealth NOC matrix component"
```

---

### Task 5: Create AgentFleetPulse.tsx

**Files:**
- Create: `frontend/src/components/Home/AgentFleetPulse.tsx`

**Step 1: Create the component**

```tsx
import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import * as Tooltip from '@radix-ui/react-tooltip';
import { getAgents } from '../../services/api';
import type { AgentInfo, AgentExecution } from '../../types';

type VisualStatus = 'idle' | 'analyzing' | 'degraded' | 'offline';

const RECENT_THRESHOLD_MS = 60_000; // 60 seconds

const deriveVisualStatus = (agent: AgentInfo): VisualStatus => {
  if (agent.status === 'offline') return 'offline';
  if (agent.status === 'degraded') return 'degraded';
  // active + recent execution in last 60s = analyzing
  const now = Date.now();
  const hasRecent = agent.recent_executions.some(
    (ex) => now - new Date(ex.timestamp).getTime() < RECENT_THRESHOLD_MS
  );
  return hasRecent ? 'analyzing' : 'idle';
};

const dotColor: Record<VisualStatus, string> = {
  idle: 'bg-duck-surface',
  analyzing: 'bg-duck-accent animate-pulse',
  degraded: 'bg-amber-500',
  offline: 'bg-red-500',
};

const dotLabel: Record<VisualStatus, string> = {
  idle: 'Idle',
  analyzing: 'Analyzing',
  degraded: 'Degraded',
  offline: 'Offline',
};

interface ActiveOp {
  id: string;
  agentName: string;
  summary: string;
  status: VisualStatus;
  timestamp: number;
}

export const AgentFleetPulse: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['agent-fleet'],
    queryFn: getAgents,
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const agents = data?.agents ?? [];
  const summary = data?.summary ?? { total: 0, active: 0, degraded: 0, offline: 0 };

  const agentsWithVisual = useMemo(
    () => agents.map((a) => ({ ...a, visual: deriveVisualStatus(a) })),
    [agents]
  );

  const activeOps = useMemo(() => {
    const now = Date.now();
    const ops: ActiveOp[] = [];
    for (const agent of agents) {
      for (const ex of agent.recent_executions) {
        const ts = new Date(ex.timestamp).getTime();
        if (now - ts < RECENT_THRESHOLD_MS) {
          ops.push({
            id: `${agent.id}-${ex.session_id}-${ex.timestamp}`,
            agentName: agent.name,
            summary: ex.summary || `Session ${ex.session_id.slice(0, 8)}`,
            status: deriveVisualStatus(agent),
            timestamp: ts,
          });
        }
      }
    }
    return ops.sort((a, b) => b.timestamp - a.timestamp).slice(0, 4);
  }, [agents]);

  const analyzingCount = agentsWithVisual.filter((a) => a.visual === 'analyzing').length;

  return (
    <div className="bg-duck-panel border border-duck-border rounded-lg h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2 shrink-0">
        <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider">Agent Fleet</h3>
        {!isLoading && (
          <div className="flex items-center gap-3 text-[10px] font-mono text-slate-400">
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-duck-accent" />
              {analyzingCount}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              {summary.degraded}
            </span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
              {summary.offline}
            </span>
          </div>
        )}
      </div>

      {/* Swarm */}
      <div className="px-3 pb-2 overflow-y-auto custom-scrollbar" style={{ maxHeight: 80 }}>
        <Tooltip.Provider delayDuration={0}>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(12px,1fr))] gap-1">
            {isLoading
              ? Array.from({ length: 25 }).map((_, i) => (
                  <div key={i} className="w-2.5 h-2.5 rounded-sm bg-duck-surface animate-pulse" />
                ))
              : agentsWithVisual.map((agent) => (
                  <Tooltip.Root key={agent.id}>
                    <Tooltip.Trigger asChild>
                      <div
                        className={`w-2.5 h-2.5 rounded-sm transition-colors duration-300 cursor-default ${dotColor[agent.visual]}`}
                      />
                    </Tooltip.Trigger>
                    <Tooltip.Portal>
                      <Tooltip.Content
                        className="z-50 bg-duck-flyout border border-duck-border rounded px-2.5 py-1.5 shadow-xl"
                        sideOffset={5}
                      >
                        <p className="text-[10px] font-bold text-white">{agent.name}</p>
                        <p className="text-[10px] text-duck-muted">
                          {dotLabel[agent.visual]} · {agent.role}
                        </p>
                        <Tooltip.Arrow className="fill-duck-border" />
                      </Tooltip.Content>
                    </Tooltip.Portal>
                  </Tooltip.Root>
                ))}
          </div>
        </Tooltip.Provider>
      </div>

      {/* Divider */}
      <div className="h-px bg-duck-border/50 mx-3" />

      {/* Ticker */}
      <div className="flex-1 overflow-hidden px-3 py-2">
        {activeOps.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[10px] text-duck-muted italic">All agents standing by</p>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {activeOps.map((op) => (
              <motion.div
                key={op.id}
                initial={{ opacity: 0, height: 0, y: -10 }}
                animate={{ opacity: 1, height: 'auto', y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-start gap-2 py-1.5 border-b border-duck-border/30 last:border-0"
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dotColor[op.status]}`}
                />
                <div className="min-w-0">
                  <span className="text-[10px] font-bold text-duck-accent">{op.agentName}</span>
                  <span className="text-[10px] text-duck-muted ml-1 truncate">
                    → {op.summary}
                  </span>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/Home/AgentFleetPulse.tsx
git commit -m "feat(agents): add AgentFleetPulse swarm + ticker component"
```

---

### Task 6: Restructure HomePage.tsx to 3-Row Command Center Grid

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`

This is the main integration task. Replace the current flat layout with the 3-row grid, add the tab bar for My Investigations, and wire in the two new components.

**Step 1: Rewrite HomePage.tsx**

Replace the entire file content with:

```tsx
import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { CapabilityType, V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';
import CapabilityLauncher from './CapabilityLauncher';
import LiveIntelligenceFeed from './LiveIntelligenceFeed';
import { MetricRibbon } from './MetricRibbon';
import { QuickActionsPanel } from './QuickActionsPanel';
import { EnvironmentHealth } from './EnvironmentHealth';
import { AgentFleetPulse } from './AgentFleetPulse';
import { TimeRangeSelector } from '../shared';

interface HomePageProps {
  onSelectCapability: (capability: CapabilityType) => void;
  onSelectSession: (session: V4Session) => void;
  wsConnected: boolean;
}

const ACTIVE_PHASES = ['complete', 'diagnosis_complete', 'error'];

const HomePage: React.FC<HomePageProps> = ({
  onSelectCapability,
  onSelectSession,
  wsConnected,
}) => {
  const [feedTab, setFeedTab] = useState<'global' | 'mine'>('global');
  const [timeRange, setTimeRange] = useState<string>('1h');

  // Read from the shared live-sessions cache for the "My Investigations" count
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const myActiveCount = useMemo(
    () => sessions.filter((s) => !ACTIVE_PHASES.includes(s.status)).length,
    [sessions]
  );

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-duck-bg">
      {/* Top Header */}
      <header className="h-16 border-b border-duck-border flex items-center justify-between px-8 shrink-0 bg-duck-panel/50 backdrop-blur-md">
        <div className="flex items-center gap-6 flex-1">
          {/* System Health Badge */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-xs font-bold text-emerald-500 uppercase tracking-tighter">
              System Health: {wsConnected ? 'Online' : 'Offline'}
            </span>
          </div>

          {/* Global Search */}
          <div className="relative max-w-md w-full">
            <span
              className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-xl"
              aria-hidden="true"
            >search</span>
            <input
              className="w-full rounded-lg pl-11 py-2 text-sm text-white placeholder:text-slate-500 transition-all duration-200 ease-in-out outline-none bg-duck-card/40 border border-duck-border focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              placeholder="Search logs, agents, or PRs (⌘ + K)"
              type="text"
            />
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Notifications */}
          <button className="relative p-2 text-slate-400 hover:text-white transition-all duration-200 ease-in-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent" aria-label="View Notifications">
            <span className="material-symbols-outlined" aria-hidden="true">notifications</span>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-duck-accent shadow-[0_0_0_2px_#0f2023]" />
          </button>

          <div className="h-8 w-px bg-duck-border" />

          {/* User Profile */}
          <div className="flex items-center gap-3 cursor-pointer group focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent" role="button" tabIndex={0} aria-label="User Profile">
            <div className="text-right hidden sm:block">
              <p className="text-xs font-bold text-white leading-none">SRE Admin</p>
              <p className="text-micro text-slate-500 mt-1">Platform Engineer</p>
            </div>
            <div className="w-9 h-9 rounded-lg border border-duck-border shadow-md flex items-center justify-center bg-duck-accent/20">
              <span className="material-symbols-outlined text-lg text-duck-accent" aria-hidden="true">person</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Scrolling Content */}
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">

        {/* ROW 1: Triage & Health */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
          <div className="lg:col-span-8">
            <MetricRibbon />
          </div>
          <div className="lg:col-span-4">
            <EnvironmentHealth />
          </div>
        </div>

        {/* ROW 2: Core Workspace (locked 500px) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8 items-stretch lg:h-[500px]">

          {/* Left Column: Feed with tab bar */}
          <div className="lg:col-span-8 flex flex-col h-full bg-duck-panel border border-duck-border rounded-lg overflow-hidden">
            {/* Tab bar */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-duck-border bg-duck-card/30 shrink-0">
              <div className="flex gap-6">
                <button
                  onClick={() => setFeedTab('global')}
                  className={`text-sm font-bold pb-1 -mb-[13px] transition-colors ${
                    feedTab === 'global'
                      ? 'text-white border-b-2 border-duck-accent'
                      : 'text-duck-muted hover:text-slate-300'
                  }`}
                >
                  Global Feed
                </button>
                <button
                  onClick={() => setFeedTab('mine')}
                  className={`text-sm font-bold pb-1 -mb-[13px] transition-colors ${
                    feedTab === 'mine'
                      ? 'text-white border-b-2 border-duck-accent'
                      : 'text-duck-muted hover:text-slate-300'
                  }`}
                >
                  My Investigations ({myActiveCount})
                </button>
              </div>
              <TimeRangeSelector selected={timeRange} onChange={setTimeRange} />
            </div>

            {/* Scrollable feed */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              <LiveIntelligenceFeed
                onSelectSession={onSelectSession}
                filterActive={feedTab === 'mine'}
              />
            </div>
          </div>

          {/* Right Column: QuickActions + AgentFleetPulse */}
          <div className="lg:col-span-4 flex flex-col gap-5 h-full">
            <div className="h-[240px] shrink-0">
              <QuickActionsPanel
                onSelectCapability={onSelectCapability}
                wsConnected={wsConnected}
              />
            </div>
            <div className="h-[240px] shrink-0">
              <AgentFleetPulse />
            </div>
          </div>
        </div>

        {/* ROW 3: Capabilities (full width) */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Capabilities</h2>
              <p className="text-xs text-duck-muted mt-0.5">Deploy automated diagnostics and remediations</p>
            </div>
          </div>
          <CapabilityLauncher onSelectCapability={onSelectCapability} />
        </section>
      </div>
    </div>
  );
};

export default HomePage;
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`

Expected: TypeScript error — `LiveIntelligenceFeed` doesn't accept `filterActive` prop yet. That's expected, we'll fix it in the next task.

Note: If you see the error `Property 'filterActive' does not exist on type 'LiveIntelligenceFeedProps'`, proceed to Task 7.

**Step 3: Do NOT commit yet** — wait for Task 7 to make the build green.

---

### Task 7: Add filterActive prop to LiveIntelligenceFeed

**Files:**
- Modify: `frontend/src/components/Home/LiveIntelligenceFeed.tsx`

**Step 1: Add the filterActive prop**

Update the interface (around line 8):

```typescript
interface LiveIntelligenceFeedProps {
  onSelectSession: (session: V4Session) => void;
  filterActive?: boolean;
}
```

**Step 2: Destructure the new prop and apply filtering**

Update the component function signature and add filtering logic after the useQuery call:

```typescript
const LiveIntelligenceFeed: React.FC<LiveIntelligenceFeedProps> = ({
  onSelectSession,
  filterActive = false,
}) => {
```

After the existing `useQuery` block (around line 51), add:

```typescript
  const COMPLETED_PHASES = ['complete', 'diagnosis_complete', 'error'];

  const displaySessions = useMemo(
    () => filterActive
      ? sessions.filter((s) => !COMPLETED_PHASES.includes(s.status))
      : sessions,
    [sessions, filterActive]
  );
```

Then add `useMemo` to the imports at line 1:

```typescript
import React, { useState, useMemo } from 'react';
```

**Step 3: Use displaySessions instead of sessions in the render**

Replace all occurrences of `sessions` in the JSX render section with `displaySessions`:

- The SectionHeader count: `count={displaySessions.length}`
- The loading check: `isLoading && displaySessions.length === 0`
- The empty check: `displaySessions.length === 0`
- The map: `displaySessions.slice(0, 15).map(...)`

**Important:** Do NOT replace the `sessions` in the `isLoading && sessions.length === 0` check — use `displaySessions` there too, since the filter applies before render.

**Step 4: Remove the internal SectionHeader and TimeRangeSelector**

Since the tab bar in HomePage now provides the header and the TimeRangeSelector, remove the `<SectionHeader>` wrapper from LiveIntelligenceFeed's render output. The component should now just render the content area directly:

Remove the `<section>` / `<SectionHeader>` wrapper and the `bg-duck-panel border...` div. The component should render only the scrollable content (skeleton/error/empty/list). The parent `HomePage.tsx` already wraps it in the panel with the tab bar.

The render should simplify to:

```tsx
  return (
    <>
      {isLoading && displaySessions.length === 0 ? (
        <div className="space-y-2 p-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-md bg-duck-surface animate-pulse" style={{ opacity: 1 - i * 0.3 }} />
          ))}
        </div>
      ) : isError && !isLoading ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <span className="material-symbols-outlined text-4xl text-red-500 mb-3" aria-hidden="true">wifi_off</span>
          <p className="text-sm font-semibold text-slate-300 mb-1">Feed Disconnected</p>
          <p className="text-xs text-slate-500">Failed to sync with the intelligence server. Retrying...</p>
        </div>
      ) : displaySessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <div className="w-16 h-16 rounded-full bg-duck-border/30 flex items-center justify-center mb-4">
            <span className="material-symbols-outlined text-2xl text-duck-accent" aria-hidden="true">satellite_alt</span>
          </div>
          <p className="text-sm font-semibold text-slate-300 mb-1">
            {filterActive ? 'No Active Investigations' : 'No Active Sessions'}
          </p>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {filterActive
              ? 'Start an investigation to see it here.'
              : 'Launch an investigation from Quick Actions to begin monitoring.'}
          </p>
        </div>
      ) : (
        displaySessions.slice(0, 15).map((session) => {
          // ...existing row rendering...
        })
      )}
    </>
  );
```

Remove the now-unused imports: `SectionHeader`, `TimeRangeSelector` from `'../shared'`. Also remove the `timeRange` useState since the parent owns it now.

**Step 5: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS — both HomePage and LiveIntelligenceFeed compile clean.

**Step 6: Commit both files together**

```bash
git add frontend/src/components/Home/HomePage.tsx frontend/src/components/Home/LiveIntelligenceFeed.tsx
git commit -m "feat(home): restructure to 3-row Command Center grid with feed tabs"
```

---

### Task 8: Lock QuickActionsPanel height to h-full

**Files:**
- Modify: `frontend/src/components/Home/QuickActionsPanel.tsx`

The QuickActionsPanel needs to fill its 240px parent container. Currently it uses `flex flex-col gap-4` at the root but doesn't have `h-full`.

**Step 1: Add h-full to the root div**

Change the root element from:

```tsx
<div className="flex flex-col gap-4">
```

To:

```tsx
<div className="flex flex-col gap-4 h-full">
```

Also ensure the two child panels (`Quick Actions` and `System Health`) use `flex-1` or appropriate sizing to split the space evenly:

The first panel (Quick Actions): add `flex-1` so it takes available space.
The second panel (System Health): add `flex-1` so it takes available space.

Update both panels:

```tsx
<div className="bg-duck-panel border border-duck-border rounded-lg p-4 flex-1 flex flex-col">
```

For the Quick Actions panel, make the button list scrollable if it overflows:

```tsx
<div className="flex flex-col gap-1.5 flex-1 overflow-y-auto">
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/Home/QuickActionsPanel.tsx
git commit -m "fix(quick-actions): add h-full and flex-1 for 240px panel constraint"
```

---

### Task 9: Final Verification Audit

**Files:** None (verification only)

**Step 1: Full build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Zero errors, successful build

**Step 2: Audit for remaining inline styles in new files**

Run:
```bash
grep -n 'style={{' frontend/src/components/Home/AgentFleetPulse.tsx frontend/src/components/Home/EnvironmentHealth.tsx
```

Expected: Only `style={{ maxHeight: 80 }}` in AgentFleetPulse (legitimate dynamic constraint) and `style={{ opacity: 1 - i * 0.3 }}` in LiveIntelligenceFeed loading skeleton.

**Step 3: Verify new components use duck-* tokens**

Run:
```bash
grep -n '#[0-9a-fA-F]\{6\}' frontend/src/components/Home/AgentFleetPulse.tsx frontend/src/components/Home/EnvironmentHealth.tsx
```

Expected: Zero hardcoded hex values in new components.

**Step 4: Verify Radix tooltip imports**

Run:
```bash
grep -rn '@radix-ui/react-tooltip' frontend/src/components/Home/
```

Expected: Matches in AgentFleetPulse.tsx and EnvironmentHealth.tsx.

**Step 5: Run backend tests (sanity check)**

Run: `cd backend && python3 -m pytest tests/ -x -q`
Expected: All pass (no backend changes in this plan)

**Step 6: Commit (if any audit fixes were needed)**

```bash
git commit -m "chore: final verification audit for war room homepage"
```

---

## Dependency Graph

```
Phase 1 (Prereqs):
  Task 1 (Radix install)
  Task 2 (HealthNode type)

Phase 2 (API layer):
  Task 3 (fetchEnvironmentHealth)  ← depends on Task 2

Phase 3 (Components):
  Task 4 (EnvironmentHealth.tsx)   ← depends on Tasks 1, 3
  Task 5 (AgentFleetPulse.tsx)     ← depends on Task 1

Phase 4 (Integration):
  Task 6 (HomePage grid)           ← depends on Tasks 4, 5
  Task 7 (LiveIntelligenceFeed)    ← depends on Task 6
  Task 8 (QuickActionsPanel)       ← depends on Task 6

Phase 5 (Verification):
  Task 9 (Final audit)             ← depends on Tasks 7, 8
```
