# Cluster Diagnostic War Room Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the basic flat ClusterWarRoom with a 3-column cyberpunk war room featuring accordion domain panels, fleet heatmap, neural glow effects, hold-to-confirm remediation, and a tactical command bar.

**Architecture:** The existing `ClusterWarRoom.tsx` becomes the orchestrator component owning all state. It renders a 12-column CSS grid with three column groups: Left (DAG, Heatmap, Velocity), Center (expanded DomainPanel + 3 collapsed VerticalRibbons), Right (RootCauseCard, VerdictStack, RemediationCard). All data flows from a single `ClusterHealthReport` state fetched via polling. An SVG neural-pulse overlay connects columns visually.

**Tech Stack:** React 18 + TypeScript, Tailwind CSS, SVG for visualizations, CSS keyframe animations, existing ChatDrawer/LedgerTriggerTab via ChatContext.

**Design doc:** `docs/plans/2026-02-28-cluster-dashboard-design.md`

**Wireframe references:** `stitch_action_center (13)` and `stitch_action_center (16)` in Downloads.

---

## Pre-flight: Worktree Setup

```bash
cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm
git worktree add .worktrees/cluster-dashboard -b feature/cluster-war-room
cd .worktrees/cluster-dashboard/frontend
npm install
npx tsc --noEmit   # baseline: 0 errors
```

**All file paths below are relative to the worktree root.**

---

### Task 1: CSS Animations & Type Extensions

**Files:**
- Modify: `frontend/src/index.css` (append after line ~385)
- Modify: `frontend/src/types/index.ts` (append after line ~625)

**Step 1: Add cluster war room CSS animations to `index.css`**

Append these animations after the existing content:

```css
/* ── Cluster War Room ─────────────────────────── */

/* CRT scan-lines overlay */
.crt-scanlines::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0, 0, 0, 0.03) 2px,
    rgba(0, 0, 0, 0.03) 3px
  );
  pointer-events: none;
  z-index: 50;
}

/* Neural pulse flowing between columns */
@keyframes neural-dash-pulse {
  0% { stroke-dashoffset: 200; opacity: 0; }
  10% { opacity: 1; }
  100% { stroke-dashoffset: 0; opacity: 0; }
}
.neural-pulse-path {
  stroke-dasharray: 10 200;
  animation: neural-dash-pulse 2s linear infinite;
  filter: drop-shadow(0 0 4px #13b6ec);
}

/* Tether path (dashed connecting lines) */
@keyframes tether-dash {
  to { stroke-dashoffset: -20; }
}
.tether-path {
  stroke-dasharray: 5;
  animation: tether-dash 1s linear infinite;
}
.tether-path-flow {
  stroke-dasharray: 8 4;
  filter: drop-shadow(0 0 3px #13b6ec);
}

/* Vertical ribbon writing mode */
.vertical-label {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
}

/* Hold-to-confirm fill animation */
.hold-fill {
  width: 0;
  height: 100%;
  transition: width 1.5s linear;
}
.hold-fill.active {
  width: 100%;
}

/* Pressure zone SVG fill */
.pressure-zone-fill {
  fill: rgba(239, 68, 68, 0.15);
}

/* Amber pulse for active nodes */
@keyframes pulse-amber {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
  50% { box-shadow: 0 0 15px 5px rgba(245, 158, 11, 0.6); }
}
.animate-pulse-amber { animation: pulse-amber 2s infinite; }
```

**Step 2: Add cluster war room types to `types/index.ts`**

Append after the existing `ClusterHealthReport` interface (after line ~625):

```typescript
/* ── Cluster War Room UI types ─────────────────── */

export type ClusterDomainKey = 'ctrl_plane' | 'node' | 'network' | 'storage';

export interface FleetNode {
  name: string;
  status: 'healthy' | 'warning' | 'critical' | 'unknown';
  cpu_pct?: number;
  memory_pct?: number;
  disk_pressure?: boolean;
  pod_count?: number;
}

export interface NamespaceWorkload {
  namespace: string;
  status: 'Healthy' | 'Degraded' | 'Critical' | 'Unknown';
  replica_status?: string;
  last_deploy?: string;
  workloads?: WorkloadDetail[];
}

export interface WorkloadDetail {
  name: string;
  kind: 'Deployment' | 'StatefulSet' | 'DaemonSet' | 'CronJob' | 'Job' | 'Pod';
  status: 'Running' | 'CrashLoopBackOff' | 'Pending' | 'Failed' | 'Completed';
  restarts?: number;
  cpu_usage?: string;
  memory_usage?: string;
  age?: string;
  is_trigger?: boolean;
}

export interface VerdictEvent {
  timestamp: string;
  severity: 'FATAL' | 'WARN' | 'INFO';
  message: string;
  domain?: ClusterDomainKey;
}
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/index.css frontend/src/types/index.ts
git commit -m "feat: add cluster war room CSS animations and UI types"
```

---

### Task 2: ClusterHeader + CommandBar

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/ClusterHeader.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/CommandBar.tsx`

**Step 1: Create `ClusterHeader.tsx`**

```tsx
import React from 'react';

interface ClusterHeaderProps {
  sessionId: string;
  confidence: number;
  platformHealth: string;
  wsConnected: boolean;
  onGoHome: () => void;
}

const healthColor = (health: string) =>
  health === 'HEALTHY' ? '#10b981'
    : health === 'DEGRADED' ? '#f59e0b'
    : health === 'CRITICAL' ? '#ef4444'
    : '#6b7280';

const ClusterHeader: React.FC<ClusterHeaderProps> = ({
  sessionId, confidence, platformHealth, wsConnected, onGoHome,
}) => {
  const color = healthColor(platformHealth);

  return (
    <header className="h-14 border-b border-[#1f3b42] bg-[#152a2f] flex items-center justify-between px-6 z-50 shadow-md shrink-0">
      <div className="flex items-center gap-4">
        <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
          <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
        </button>
        <div className="flex items-center gap-2">
          <span className={`w-3 h-3 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600'}`} />
          <h1 className="text-xl font-bold tracking-tight text-white">
            DebugDuck <span className="text-[#13b6ec]">Cluster War Room</span>
          </h1>
        </div>
        <div className="px-3 py-1 bg-[#0f2023] border border-[#1f3b42] rounded text-xs font-mono flex items-center gap-2">
          <span className="text-slate-500 uppercase tracking-widest text-[10px]">Session:</span>
          <span className="text-[#13b6ec]">#{sessionId.slice(0, 8).toUpperCase()}</span>
        </div>
      </div>

      <div className="flex items-center gap-8">
        {/* Global Confidence */}
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase tracking-tighter text-slate-500">Global Confidence</span>
          <div className="w-48 h-2 bg-[#0f2023] border border-[#1f3b42] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[#13b6ec] transition-all duration-700"
              style={{ width: `${confidence}%`, boxShadow: '0 0 8px #13b6ec' }}
            />
          </div>
        </div>

        {/* Live Feed */}
        <div className="flex items-center gap-2 font-mono font-bold text-sm" style={{ color }}>
          <span className={`w-2 h-2 rounded-full animate-pulse`} style={{ backgroundColor: color }} />
          {platformHealth || 'ANALYZING'}
        </div>
      </div>
    </header>
  );
};

export default ClusterHeader;
```

**Step 2: Create `CommandBar.tsx`**

```tsx
import React, { useState, useCallback } from 'react';
import { useChatUI } from '../../contexts/ChatContext';

const CommandBar: React.FC = () => {
  const [input, setInput] = useState('');
  const { sendMessage, openDrawer } = useChatUI();

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) return;
    sendMessage(trimmed);
    openDrawer();
    setInput('');
  }, [input, sendMessage, openDrawer]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <footer className="h-12 bg-[#152a2f] border-t border-[#1f3b42] sticky bottom-0 z-50 flex items-center px-4 shrink-0">
      <div className="flex items-center gap-3 w-full max-w-4xl mx-auto">
        <span className="text-[#13b6ec] font-mono text-sm font-bold">$</span>
        <input
          className="bg-transparent border-none text-sm font-mono text-white w-full placeholder-slate-600 focus:outline-none focus:ring-0"
          placeholder="Type tactical command (e.g., /cordon --node=3) or press 'K' for quick search..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="flex gap-2 shrink-0">
          <kbd className="px-2 py-0.5 bg-[#0f2023] border border-[#1f3b42] rounded text-[10px] font-mono text-slate-400 uppercase">Shift</kbd>
          <kbd className="px-2 py-0.5 bg-[#0f2023] border border-[#1f3b42] rounded text-[10px] font-mono text-slate-400 uppercase">Enter</kbd>
        </div>
      </div>
    </footer>
  );
};

export default CommandBar;
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterHeader.tsx frontend/src/components/ClusterDiagnostic/CommandBar.tsx
git commit -m "feat: add ClusterHeader and CommandBar components"
```

---

### Task 3: FleetHeatmap

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/FleetHeatmap.tsx`

**Step 1: Create `FleetHeatmap.tsx`**

```tsx
import React, { useMemo } from 'react';
import type { FleetNode } from '../../types';

interface FleetHeatmapProps {
  nodes: FleetNode[];
  selectedNode?: string;
  onSelectNode?: (nodeName: string) => void;
}

const statusColor = (status: FleetNode['status']) => {
  switch (status) {
    case 'critical': return 'bg-red-500';
    case 'warning': return 'bg-amber-500';
    case 'healthy': return 'bg-[#1f3b42]';
    default: return 'bg-slate-700';
  }
};

const FleetHeatmap: React.FC<FleetHeatmapProps> = ({ nodes, selectedNode, onSelectNode }) => {
  const nodeCount = nodes.length || 0;

  // Generate mock nodes if none provided yet
  const displayNodes = useMemo(() => {
    if (nodes.length > 0) return nodes;
    return Array.from({ length: 60 }, (_, i) => ({
      name: `node-${i}`,
      status: 'unknown' as const,
    }));
  }, [nodes]);

  return (
    <div className="bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3 flex justify-between">
        Fleet Heatmap <span>{nodeCount} Nodes</span>
      </h3>
      <div className="grid grid-cols-12 gap-1 min-h-[80px]">
        {displayNodes.map((node, i) => {
          const isCritical = node.status === 'critical';
          const isSelected = node.name === selectedNode;
          return (
            <div
              key={node.name || i}
              className={`
                aspect-square rounded-[1px] transition-all duration-500 cursor-pointer
                ${statusColor(node.status)}
                ${isCritical ? 'animate-pulse opacity-100 z-10 shadow-[0_0_12px_#ef4444]' : 'opacity-20 hover:opacity-60'}
                ${isSelected ? 'ring-2 ring-[#13b6ec] ring-offset-1 ring-offset-[#0f2023] z-20' : ''}
              `}
              onClick={() => onSelectNode?.(node.name)}
              title={`${node.name} | ${node.cpu_pct ?? '—'}% CPU${node.disk_pressure ? ' | DISK PRESSURE' : ''}`}
            />
          );
        })}
      </div>
    </div>
  );
};

export default FleetHeatmap;
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/FleetHeatmap.tsx
git commit -m "feat: add FleetHeatmap node grid component"
```

---

### Task 4: ExecutionDAG + ResourceVelocity

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/ExecutionDAG.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/ResourceVelocity.tsx`

**Step 1: Create `ExecutionDAG.tsx`**

```tsx
import React from 'react';
import type { ClusterDomainReport } from '../../types';

interface ExecutionDAGProps {
  domainReports: ClusterDomainReport[];
  phase: string;
}

interface DAGNode {
  label: string;
  status: 'pending' | 'running' | 'complete' | 'failed';
}

const nodeStyle = (status: DAGNode['status']) => {
  switch (status) {
    case 'running': return 'border-amber-500 text-amber-500 animate-pulse-amber shadow-[0_0_10px_rgba(245,158,11,0.2)]';
    case 'complete': return 'border-[#13b6ec] text-[#13b6ec]';
    case 'failed': return 'border-red-500 text-red-500';
    default: return 'border-[#1f3b42] text-slate-600 italic';
  }
};

const ExecutionDAG: React.FC<ExecutionDAGProps> = ({ domainReports, phase }) => {
  const agentsDone = domainReports.filter(r => r.status === 'SUCCESS' || r.status === 'PARTIAL' || r.status === 'FAILED').length;
  const anyRunning = domainReports.some(r => r.status === 'RUNNING');

  const dagNodes: DAGNode[] = [
    { label: 'InputParser', status: phase !== 'pre_flight' ? 'complete' : 'running' },
    {
      label: `Agents (${agentsDone}/4)`,
      status: agentsDone === 4 ? 'complete' : anyRunning ? 'running' : agentsDone > 0 ? 'running' : 'pending',
    },
    {
      label: 'Synthesizer',
      status: phase === 'complete' ? 'complete' : agentsDone === 4 ? 'running' : 'pending',
    },
  ];

  return (
    <div className="flex-1 min-h-[200px] bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3 flex flex-col">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-4">Execution DAG</h3>
      <div className="relative flex flex-col items-center gap-6 h-full py-2">
        {dagNodes.map((node, i) => (
          <React.Fragment key={node.label}>
            {i > 0 && <div className="w-px h-6 bg-[#13b6ec]/30" />}
            <div className={`px-4 py-2 border rounded bg-[#0f2023] flex items-center justify-center text-[10px] font-mono ${nodeStyle(node.status)}`}>
              {node.label}
            </div>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default ExecutionDAG;
```

**Step 2: Create `ResourceVelocity.tsx`**

```tsx
import React from 'react';

interface ResourceVelocityProps {
  label?: string;
}

const ResourceVelocity: React.FC<ResourceVelocityProps> = ({ label = 'Resource Velocity' }) => {
  return (
    <div className="h-40 bg-[#152a2f]/40 rounded border border-[#1f3b42] p-3">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-2">{label}</h3>
      <svg className="w-full h-full" viewBox="0 0 200 80" preserveAspectRatio="none">
        {/* Threshold line */}
        <path d="M0 40 L200 40" stroke="#1f3b42" strokeDasharray="2" strokeWidth="1" />
        <text x="5" y="35" fill="#1f3b42" fontFamily="monospace" fontSize="6">REQUEST_LIMIT</text>

        {/* Area fill under sparkline */}
        <path
          d="M0 70 Q 20 65, 40 68 T 80 50 T 120 20 T 160 30 T 200 15 L 200 80 L 0 80 Z"
          fill="rgba(19, 182, 236, 0.1)"
        />

        {/* Sparkline */}
        <path
          d="M0 70 Q 20 65, 40 68 T 80 50 T 120 20 T 160 30 T 200 15"
          fill="none"
          stroke="#13b6ec"
          strokeWidth="1.5"
        />

        {/* Pressure zone (above threshold) */}
        <path
          d="M85 40 Q 120 20, 160 30 T 200 15 L 200 40 Z"
          className="pressure-zone-fill"
        />
      </svg>
    </div>
  );
};

export default ResourceVelocity;
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ExecutionDAG.tsx frontend/src/components/ClusterDiagnostic/ResourceVelocity.tsx
git commit -m "feat: add ExecutionDAG and ResourceVelocity left-column components"
```

---

### Task 5: VerticalRibbon + WorkloadCard

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/VerticalRibbon.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/WorkloadCard.tsx`

**Step 1: Create `VerticalRibbon.tsx`**

```tsx
import React from 'react';
import type { ClusterDomainKey, ClusterDomainReport } from '../../types';

interface VerticalRibbonProps {
  domain: ClusterDomainKey;
  report?: ClusterDomainReport;
  onClick: () => void;
}

const DOMAIN_META: Record<ClusterDomainKey, { icon: string; label: string; color: string }> = {
  ctrl_plane: { icon: 'settings_system_daydream', label: 'CONTROL PLANE', color: '#f59e0b' },
  node: { icon: 'memory', label: 'COMPUTE', color: '#13b6ec' },
  network: { icon: 'network_check', label: 'NETWORK', color: '#10b981' },
  storage: { icon: 'database', label: 'STORAGE', color: '#10b981' },
};

const VerticalRibbon: React.FC<VerticalRibbonProps> = ({ domain, report, onClick }) => {
  const meta = DOMAIN_META[domain];
  const hasAnomaly = report && report.anomalies.length > 0;
  const isRunning = report?.status === 'RUNNING';
  const iconColor = hasAnomaly ? '#f59e0b' : report?.status === 'SUCCESS' ? '#10b981' : '#64748b';

  return (
    <div
      className={`
        flex-1 border-b border-[#1f3b42] last:border-b-0 relative group cursor-pointer
        hover:bg-[#152a2f]/80 transition-colors flex flex-col items-center py-2 gap-2 overflow-hidden
        ${hasAnomaly ? 'bg-amber-500/5' : ''}
      `}
      onClick={onClick}
    >
      <span
        className={`material-symbols-outlined text-sm ${isRunning ? 'animate-pulse' : ''}`}
        style={{ fontFamily: 'Material Symbols Outlined', color: iconColor }}
      >
        {meta.icon}
      </span>

      {/* Mini sparkline */}
      <svg className="w-full h-12 fill-none" preserveAspectRatio="none" viewBox="0 0 40 100" style={{ stroke: iconColor }}>
        <path d="M20 100 L20 60 L35 50 L5 40 L20 30 L20 0" strokeWidth="1.5" />
      </svg>

      <div className="vertical-label text-[10px] font-bold tracking-widest text-slate-400 whitespace-nowrap py-2 flex-1 text-center">
        {meta.label}
      </div>
    </div>
  );
};

export default VerticalRibbon;
```

**Step 2: Create `WorkloadCard.tsx`**

```tsx
import React from 'react';
import type { WorkloadDetail } from '../../types';

interface WorkloadCardProps {
  workload: WorkloadDetail;
  domainColor: string;
}

const statusIcon: Record<string, string> = {
  CrashLoopBackOff: 'restart_alt',
  Pending: 'hourglass_top',
  Failed: 'error',
  Running: 'check_circle',
  Completed: 'task_alt',
};

const WorkloadCard: React.FC<WorkloadCardProps> = ({ workload, domainColor }) => {
  const isTrigger = workload.is_trigger;
  const isCrashing = workload.status === 'CrashLoopBackOff' || workload.status === 'Failed';

  return (
    <div className={`bg-[#0f2023]/60 border rounded p-3 ${isTrigger ? 'border-red-500 shadow-lg' : 'border-[#1f3b42]'}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded border flex items-center justify-center ${
            isCrashing ? 'border-red-500 bg-red-500/10 text-red-500' : `border-[#1f3b42] text-slate-500`
          }`}>
            <span
              className={`material-symbols-outlined ${isCrashing ? 'animate-pulse' : ''}`}
              style={{ fontFamily: 'Material Symbols Outlined' }}
            >
              {statusIcon[workload.status] || 'deployed_code'}
            </span>
          </div>
          <div>
            <div className="text-sm font-bold text-white">
              {workload.status === 'CrashLoopBackOff' ? 'Pod Restart Loop' : workload.status}
            </div>
            <div className="text-[10px] font-mono text-slate-500">{workload.name}</div>
          </div>
        </div>
        {isTrigger && (
          <div className="flex flex-col items-end gap-1">
            <span className="px-2 py-1 bg-red-500/20 text-red-500 text-[10px] font-bold border border-red-500 rounded tracking-tighter">TRIGGER</span>
            {workload.age && <span className="text-[9px] text-slate-500 font-mono">{workload.age}</span>}
          </div>
        )}
      </div>

      {/* Metrics grid */}
      {(workload.cpu_usage || workload.memory_usage || workload.restarts != null) && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          {workload.cpu_usage && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">CPU Usage</div>
              <div className={`text-xs font-mono ${parseInt(workload.cpu_usage) > 80 ? 'text-amber-500' : 'text-slate-300'}`}>
                {workload.cpu_usage}
              </div>
            </div>
          )}
          {workload.memory_usage && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">Memory</div>
              <div className="text-xs font-mono text-slate-300">{workload.memory_usage}</div>
            </div>
          )}
          {workload.restarts != null && (
            <div className="bg-[#0f2023] p-2 rounded border border-[#1f3b42]/30">
              <div className="text-[9px] text-slate-500 uppercase">Restarts</div>
              <div className={`text-xs font-mono ${workload.restarts > 5 ? 'text-red-500' : 'text-slate-300'}`}>
                {workload.restarts}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WorkloadCard;
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/VerticalRibbon.tsx frontend/src/components/ClusterDiagnostic/WorkloadCard.tsx
git commit -m "feat: add VerticalRibbon and WorkloadCard center-column components"
```

---

### Task 6: DomainPanel

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/DomainPanel.tsx`

**Step 1: Create `DomainPanel.tsx`**

```tsx
import React from 'react';
import type { ClusterDomainKey, ClusterDomainReport, NamespaceWorkload, WorkloadDetail } from '../../types';
import WorkloadCard from './WorkloadCard';

interface DomainPanelProps {
  domain: ClusterDomainKey;
  report?: ClusterDomainReport;
  namespaces: NamespaceWorkload[];
}

const DOMAIN_META: Record<ClusterDomainKey, { icon: string; label: string; color: string }> = {
  ctrl_plane: { icon: 'settings_system_daydream', label: 'CONTROL PLANE', color: '#f59e0b' },
  node: { icon: 'memory', label: 'COMPUTE', color: '#13b6ec' },
  network: { icon: 'network_check', label: 'NETWORK', color: '#10b981' },
  storage: { icon: 'database', label: 'STORAGE', color: '#10b981' },
};

const statusBadge = (status?: string) => {
  switch (status) {
    case 'SUCCESS': return { text: 'HEALTHY', cls: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20' };
    case 'RUNNING': return { text: 'ACTIVE_TRACING', cls: 'text-[#13b6ec] bg-[#13b6ec]/10 border-[#13b6ec]/20' };
    case 'PARTIAL': return { text: 'PARTIAL', cls: 'text-amber-400 bg-amber-400/10 border-amber-400/20' };
    case 'FAILED': return { text: 'FAILED', cls: 'text-red-400 bg-red-400/10 border-red-400/20' };
    default: return { text: 'PENDING', cls: 'text-slate-400 bg-slate-400/10 border-slate-400/20' };
  }
};

const DomainPanel: React.FC<DomainPanelProps> = ({ domain, report, namespaces }) => {
  const meta = DOMAIN_META[domain];
  const badge = statusBadge(report?.status);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#152a2f]/20 transition-transform duration-300 hover:scale-[1.005] origin-center z-10 shadow-2xl">
      {/* Header */}
      <div className="px-4 py-3 bg-[#152a2f] border-b border-[#1f3b42] flex items-center justify-between shrink-0">
        <h2 className="font-bold text-sm tracking-wide flex items-center gap-2">
          <span className="material-symbols-outlined text-base" style={{ fontFamily: 'Material Symbols Outlined', color: meta.color }}>
            {meta.icon}
          </span>
          DOMAIN: {meta.label}
        </h2>
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${badge.cls}`}>
          {badge.text}
        </span>
      </div>

      {/* Namespace list */}
      <div className="p-4 space-y-4 overflow-y-auto flex-1 custom-scrollbar">
        {namespaces.length === 0 && !report && (
          <div className="text-xs text-slate-600 animate-pulse">Scanning namespaces...</div>
        )}

        {namespaces.map(ns => {
          const isHealthy = ns.status === 'Healthy';
          const hasTrigger = ns.workloads?.some(w => w.is_trigger);

          return (
            <div
              key={ns.namespace}
              className={`border-l-2 pl-4 py-2 ${
                hasTrigger
                  ? `border-[#13b6ec] bg-[#152a2f]/40 rounded-r border-y border-r border-[#1f3b42]/50`
                  : `border-[#1f3b42] ${isHealthy ? 'opacity-40 hover:opacity-80 transition-opacity' : ''}`
              }`}
            >
              <h4 className={`text-xs font-mono flex items-center gap-2 ${hasTrigger ? 'text-[#13b6ec]' : 'text-slate-500'}`}>
                <span className="material-symbols-outlined text-[14px]" style={{ fontFamily: 'Material Symbols Outlined' }}>grid_view</span>
                namespace: {ns.namespace}
              </h4>

              {/* Expanded: show workloads */}
              {hasTrigger && ns.workloads?.map(w => (
                <div key={w.name} className="mt-2">
                  <WorkloadCard workload={w} domainColor={meta.color} />
                </div>
              ))}

              {/* Collapsed: one-line summary */}
              {!hasTrigger && (
                <div className="mt-2 bg-[#0f2023]/30 p-2 rounded text-[10px] text-slate-600 font-mono">
                  Status: {ns.status} | {ns.replica_status || '—'} | Last Deploy: {ns.last_deploy || '—'}
                </div>
              )}
            </div>
          );
        })}

        {/* Anomalies from report (fallback when no namespace data) */}
        {namespaces.length === 0 && report?.anomalies?.map((a, i) => (
          <div key={a.anomaly_id || i} className="text-xs text-slate-300 mb-1 pl-3 border-l-2" style={{ borderColor: meta.color + '60' }}>
            {a.description}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DomainPanel;
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/DomainPanel.tsx
git commit -m "feat: add DomainPanel with namespace-scoped workloads"
```

---

### Task 7: RootCauseCard + VerdictStack

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/RootCauseCard.tsx`
- Create: `frontend/src/components/ClusterDiagnostic/VerdictStack.tsx`

**Step 1: Create `RootCauseCard.tsx`**

```tsx
import React from 'react';
import type { ClusterCausalChain } from '../../types';

interface RootCauseCardProps {
  chain?: ClusterCausalChain;
  confidence: number;
}

const RootCauseCard: React.FC<RootCauseCardProps> = ({ chain, confidence }) => {
  if (!chain) {
    return (
      <div className="border border-[#1f3b42] rounded-lg bg-[#152a2f]/40 p-5">
        <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>search</span>
          Root Cause Analysis
        </h3>
        <p className="text-sm text-slate-500 animate-pulse">Correlating events...</p>
      </div>
    );
  }

  const isConfident = confidence >= 50;
  const badgeText = isConfident ? 'Identified Root Cause' : 'Suspected Root Cause';
  const badgeColor = isConfident ? '#ef4444' : '#f59e0b';

  return (
    <div
      className="border-2 rounded-lg p-5 relative overflow-hidden"
      style={{
        borderColor: badgeColor,
        backgroundColor: `${badgeColor}08`,
        boxShadow: `0 0 20px ${badgeColor}15`,
      }}
    >
      {/* Glow background */}
      <div className="absolute inset-0 blur-3xl -z-10" style={{ backgroundColor: `${badgeColor}08` }} />

      <h3 className="text-[10px] uppercase font-bold tracking-widest mb-1 flex items-center gap-2" style={{ color: badgeColor }}>
        <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>warning</span>
        {badgeText}
      </h3>
      <h2 className="text-xl font-bold text-white mb-4 leading-tight">
        {chain.root_cause.description}
      </h2>

      {/* Confidence */}
      <div className="grid grid-cols-2 gap-4">
        <div className="p-2 bg-[#0f2023]/40 border border-[#1f3b42] rounded flex flex-col justify-between">
          <div className="text-[8px] uppercase text-slate-500">Confidence</div>
          <div className="text-lg font-mono" style={{ color: badgeColor }}>
            {Math.round(chain.confidence * 100)}%
          </div>
        </div>
        <div className="p-2 bg-[#0f2023]/40 border border-[#1f3b42] rounded flex flex-col justify-between">
          <div className="text-[8px] uppercase text-slate-500">Cascading Effects</div>
          <div className="text-lg font-mono text-amber-500">
            {chain.cascading_effects.length}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RootCauseCard;
```

**Step 2: Create `VerdictStack.tsx`**

```tsx
import React from 'react';
import type { VerdictEvent } from '../../types';

interface VerdictStackProps {
  events: VerdictEvent[];
}

const severityColor = (severity: VerdictEvent['severity']) => {
  switch (severity) {
    case 'FATAL': return '#ef4444';
    case 'WARN': return '#f59e0b';
    case 'INFO': return '#13b6ec';
  }
};

const VerdictStack: React.FC<VerdictStackProps> = ({ events }) => {
  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-4 px-2">Verdict Stack</h3>

      {events.length === 0 && (
        <p className="text-xs text-slate-600 animate-pulse px-4">Correlating events...</p>
      )}

      <div className="relative flex-1 px-4 border-l border-[#1f3b42] ml-2 space-y-6 pt-2 overflow-y-auto custom-scrollbar">
        {events.map((evt, i) => {
          const color = severityColor(evt.severity);
          return (
            <div key={i} className="relative group">
              {/* Timeline dot */}
              <div
                className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full ring-4 ring-[#0f2023] group-hover:ring-opacity-50 transition-all"
                style={{ backgroundColor: color, ['--tw-ring-color' as string]: `${color}30` }}
              />

              <div className="text-xs font-mono" style={{ color }}>
                {evt.timestamp} - {evt.severity}
              </div>
              <p className="text-[11px] text-slate-400 mt-1 italic">{evt.message}</p>
            </div>
          );
        })}

        {/* Vertical dashed line behind dots */}
        <svg className="absolute left-[-16px] top-0 w-2 h-full pointer-events-none -z-10">
          <line x1="0" y1="0" x2="0" y2="100%" stroke="#1f3b42" strokeDasharray="4 4" />
        </svg>
      </div>
    </div>
  );
};

export default VerdictStack;
```

**Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/RootCauseCard.tsx frontend/src/components/ClusterDiagnostic/VerdictStack.tsx
git commit -m "feat: add RootCauseCard and VerdictStack right-column components"
```

---

### Task 8: RemediationCard with Hold-to-Confirm

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/RemediationCard.tsx`

**Step 1: Create `RemediationCard.tsx`**

```tsx
import React, { useState, useRef, useCallback } from 'react';
import type { ClusterRemediationStep, ClusterBlastRadius } from '../../types';
import { useChatUI } from '../../contexts/ChatContext';

interface RemediationCardProps {
  steps: ClusterRemediationStep[];
  blastRadius?: ClusterBlastRadius;
}

const HOLD_DURATION_MS = 1500;

const RemediationCard: React.FC<RemediationCardProps> = ({ steps, blastRadius }) => {
  const [holdingIndex, setHoldingIndex] = useState<number | null>(null);
  const [holdProgress, setHoldProgress] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef(0);
  const { sendMessage, openDrawer } = useChatUI();

  const startHold = useCallback((index: number, command: string) => {
    setHoldingIndex(index);
    startRef.current = Date.now();
    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - startRef.current;
      const pct = Math.min(elapsed / HOLD_DURATION_MS, 1);
      setHoldProgress(pct);
      if (pct >= 1) {
        // Action confirmed
        if (timerRef.current) clearInterval(timerRef.current);
        setHoldingIndex(null);
        setHoldProgress(0);
        sendMessage(`Execute: ${command}`);
        openDrawer();
      }
    }, 30);
  }, [sendMessage, openDrawer]);

  const cancelHold = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    setHoldingIndex(null);
    setHoldProgress(0);
  }, []);

  if (steps.length === 0) return null;

  const primaryStep = steps[0];

  return (
    <div className="bg-[#152a2f] border border-[#1f3b42] rounded-lg p-4 shadow-lg">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-3">Proposed Remediation</h3>

      {/* Command block */}
      {primaryStep.command && (
        <div className="bg-black/40 rounded p-3 font-mono text-xs text-emerald-400 mb-3 border border-[#1f3b42]/30 flex items-center gap-2">
          <span className="text-slate-500">$</span>
          {primaryStep.command}
        </div>
      )}

      {/* Risk assessment */}
      {blastRadius && (
        <div className="text-[10px] text-slate-500 mb-4 leading-relaxed">
          <span className="text-amber-500 font-bold">Risk Assessment:</span>{' '}
          {blastRadius.affected_pods} pods affected across {blastRadius.affected_namespaces} namespace(s) on {blastRadius.affected_nodes} node(s).
          {blastRadius.summary && <span className="text-white ml-1">{blastRadius.summary}</span>}
        </div>
      )}

      {/* Hold-to-confirm button */}
      {primaryStep.command && (
        <button
          className="w-full bg-[#13b6ec]/10 border border-[#13b6ec] rounded h-12 flex items-center justify-between px-4 relative overflow-hidden cursor-pointer select-none transition-colors"
          onMouseDown={() => startHold(0, primaryStep.command!)}
          onMouseUp={cancelHold}
          onMouseLeave={cancelHold}
          onTouchStart={() => startHold(0, primaryStep.command!)}
          onTouchEnd={cancelHold}
        >
          {/* Red fill sweep */}
          <div
            className="absolute inset-0 bg-red-900/80 z-0 transition-none"
            style={{ width: holdingIndex === 0 ? `${holdProgress * 100}%` : '0%' }}
          />

          <span className={`font-bold tracking-widest text-xs uppercase z-10 transition-colors ${
            holdingIndex === 0 ? 'text-white' : 'text-[#13b6ec]'
          }`}>
            Confirm {primaryStep.description || 'Action'}
          </span>

          {/* Progress ring */}
          <div className="relative w-8 h-8 z-10">
            <svg className="w-full h-full rotate-[-90deg]" viewBox="0 0 36 36">
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#ffffff30' : '#13b6ec30'}
                strokeWidth="3"
              />
              <path
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke={holdingIndex === 0 ? '#fff' : '#13b6ec'}
                strokeWidth="3"
                strokeDasharray={`${(holdingIndex === 0 ? holdProgress : 0) * 100}, 100`}
                style={{ filter: 'drop-shadow(0 0 2px rgba(19,182,236,0.8))' }}
              />
            </svg>
            <div className={`absolute inset-0 flex items-center justify-center text-[8px] font-mono font-bold transition-colors ${
              holdingIndex === 0 ? 'text-white' : 'text-[#13b6ec]'
            }`}>
              HOLD
            </div>
          </div>
        </button>
      )}

      {/* Additional steps */}
      {steps.length > 1 && (
        <div className="mt-3 space-y-2">
          {steps.slice(1).map((step, i) => (
            <div key={i} className="text-xs text-slate-400">
              <p>{step.description}</p>
              {step.command && (
                <code className="text-[10px] text-[#13b6ec] block mt-1 font-mono">$ {step.command}</code>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RemediationCard;
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/RemediationCard.tsx
git commit -m "feat: add RemediationCard with hold-to-confirm pattern"
```

---

### Task 9: NeuralPulseSVG Overlay

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/NeuralPulseSVG.tsx`

**Step 1: Create `NeuralPulseSVG.tsx`**

```tsx
import React from 'react';

interface NeuralPulseSVGProps {
  hasRootCause: boolean;
}

const NeuralPulseSVG: React.FC<NeuralPulseSVGProps> = ({ hasRootCause }) => {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none z-20"
      style={{ mixBlendMode: 'screen' }}
    >
      {/* Left → Center connecting paths */}
      <path
        className="neural-pulse-path"
        d="M280 420 Q 450 420, 600 350"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.8"
      />
      <path
        className="neural-pulse-path"
        d="M280 200 Q 400 200, 600 300"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.6"
        style={{ animationDelay: '0.5s' }}
      />

      {/* Right → Center root cause paths (red when active) */}
      {hasRootCause && (
        <path
          className="neural-pulse-path"
          d="M1050 200 Q 900 200, 750 300"
          fill="none"
          stroke="#ef4444"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.9"
          style={{ animationDuration: '1.5s' }}
        />
      )}

      {/* Ambient tether paths */}
      <path
        className="tether-path"
        d="M280 420 Q 450 420, 500 350"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1"
        opacity="0.1"
      />
      <path
        className="tether-path-flow"
        d="M1050 200 Q 900 200, 700 300"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1"
        opacity="0.3"
      />
    </svg>
  );
};

export default NeuralPulseSVG;
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/NeuralPulseSVG.tsx
git commit -m "feat: add NeuralPulseSVG animated overlay"
```

---

### Task 10: ClusterWarRoom Rewrite (Orchestrator)

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx` (full rewrite)

**Step 1: Rewrite `ClusterWarRoom.tsx` as orchestrator**

Replace the entire file with:

```tsx
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterDomainKey, TaskEvent, NamespaceWorkload, VerdictEvent,
  FleetNode,
} from '../../types';
import { API_BASE_URL } from '../../services/api';
import ChatDrawer from '../Chat/ChatDrawer';
import LedgerTriggerTab from '../Chat/LedgerTriggerTab';
import ClusterHeader from './ClusterHeader';
import CommandBar from './CommandBar';
import ExecutionDAG from './ExecutionDAG';
import FleetHeatmap from './FleetHeatmap';
import ResourceVelocity from './ResourceVelocity';
import DomainPanel from './DomainPanel';
import VerticalRibbon from './VerticalRibbon';
import RootCauseCard from './RootCauseCard';
import VerdictStack from './VerdictStack';
import RemediationCard from './RemediationCard';
import NeuralPulseSVG from './NeuralPulseSVG';

interface ClusterWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: string | null;
  confidence: number;
  onGoHome: () => void;
}

const ALL_DOMAINS: ClusterDomainKey[] = ['node', 'ctrl_plane', 'network', 'storage'];

const ClusterWarRoom: React.FC<ClusterWarRoomProps> = ({
  session, events, wsConnected, phase, confidence, onGoHome,
}) => {
  const [findings, setFindings] = useState<ClusterHealthReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDomain, setExpandedDomain] = useState<ClusterDomainKey>('node');
  const [selectedNode, setSelectedNode] = useState<string | undefined>();

  // ── Data Fetching ──
  const fetchFindings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v4/session/${session.session_id}/findings`);
      if (!res.ok) {
        setError(`Failed to fetch findings (HTTP ${res.status})`);
        return;
      }
      const data = await res.json();
      if (data.platform_health && data.platform_health !== 'PENDING') {
        setFindings(data as ClusterHealthReport);
        setError(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch findings');
    } finally {
      setLoading(false);
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchFindings();
    const interval = setInterval(fetchFindings, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings]);

  // ── Derived Data ──
  const domainReports = useMemo(() => findings?.domain_reports || [], [findings]);
  const expandedReport = useMemo(
    () => domainReports.find(r => r.domain === expandedDomain),
    [domainReports, expandedDomain]
  );
  const collapsedDomains = useMemo(
    () => ALL_DOMAINS.filter(d => d !== expandedDomain),
    [expandedDomain]
  );
  const primaryChain = useMemo(
    () => findings?.causal_chains?.[0],
    [findings]
  );
  const immediateSteps = useMemo(
    () => findings?.remediation?.immediate || [],
    [findings]
  );

  // ── Mock Data (until backend provides namespace-level detail) ──
  const mockNamespaces = useMemo((): NamespaceWorkload[] => {
    if (!expandedReport || expandedReport.anomalies.length === 0) {
      return [{ namespace: 'default', status: 'Healthy', replica_status: 'All healthy', last_deploy: '—' }];
    }
    return [
      {
        namespace: 'checkout-api',
        status: 'Critical',
        workloads: [{
          name: expandedReport.anomalies[0]?.evidence_ref || 'pod-unknown',
          kind: 'Deployment',
          status: 'CrashLoopBackOff',
          restarts: 14,
          cpu_usage: '92%',
          memory_usage: '450Mi',
          is_trigger: true,
          age: '23s ago',
        }],
      },
      { namespace: 'payment-gateway', status: 'Healthy', replica_status: 'Replicas: 3/3', last_deploy: '2h ago' },
      { namespace: 'auth-service', status: 'Healthy', replica_status: 'Replicas: 5/5', last_deploy: '1d ago' },
    ];
  }, [expandedReport]);

  const mockFleetNodes = useMemo((): FleetNode[] => {
    const count = 120;
    const criticalIndices = [12, 45, 87, 88, 102];
    return Array.from({ length: count }, (_, i) => ({
      name: `node-${i}`,
      status: criticalIndices.includes(i) ? 'critical' as const : 'healthy' as const,
      cpu_pct: criticalIndices.includes(i) ? 94 : Math.random() * 40 + 10,
      disk_pressure: i === 87,
    }));
  }, []);

  const mockVerdictEvents = useMemo((): VerdictEvent[] => {
    if (!primaryChain) return [];
    return [
      { timestamp: '14:02:11', severity: 'FATAL', message: primaryChain.root_cause.description },
      ...primaryChain.cascading_effects.map(e => ({
        timestamp: '—',
        severity: 'WARN' as const,
        message: e.description,
        domain: e.domain as ClusterDomainKey,
      })),
    ];
  }, [primaryChain]);

  // ── Auto-expand most affected domain ──
  useEffect(() => {
    if (domainReports.length === 0) return;
    const worst = domainReports.reduce((prev, curr) =>
      curr.anomalies.length > prev.anomalies.length ? curr : prev
    , domainReports[0]);
    if (worst.anomalies.length > 0) {
      setExpandedDomain(worst.domain as ClusterDomainKey);
    }
  }, [domainReports]);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0f2023] crt-scanlines relative font-sans text-slate-300">
      <ClusterHeader
        sessionId={session.session_id}
        confidence={confidence}
        platformHealth={findings?.platform_health || ''}
        wsConnected={wsConnected}
        onGoHome={onGoHome}
      />

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-2 p-3 rounded-lg border border-red-500/30 bg-red-500/10 flex items-center justify-between">
          <span className="text-sm text-red-400">{error}</span>
          <button onClick={fetchFindings} className="text-xs text-red-300 hover:text-white px-3 py-1 rounded border border-red-500/30 hover:bg-red-500/20 transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* Main War Room Grid */}
      <main className="flex-1 grid grid-cols-12 overflow-hidden relative">
        <NeuralPulseSVG hasRootCause={!!primaryChain} />

        {/* ── LEFT COLUMN (col-3) ── */}
        <section className="col-span-3 border-r border-[#1f3b42] bg-[#0f2023]/50 p-4 flex flex-col gap-4 overflow-hidden z-10">
          <ExecutionDAG domainReports={domainReports} phase={phase || 'pre_flight'} />
          <FleetHeatmap nodes={mockFleetNodes} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
          <ResourceVelocity />
        </section>

        {/* ── CENTER COLUMN (col-5) ── */}
        <section className="col-span-5 flex h-full bg-[#0f2023] overflow-hidden relative border-r border-[#1f3b42]">
          {/* Expanded domain panel */}
          <DomainPanel domain={expandedDomain} report={expandedReport} namespaces={mockNamespaces} />

          {/* Collapsed vertical ribbons */}
          <div className="w-[40px] flex flex-col bg-[#152a2f] border-l border-[#1f3b42] shrink-0 z-10">
            {collapsedDomains.map(d => (
              <VerticalRibbon
                key={d}
                domain={d}
                report={domainReports.find(r => r.domain === d)}
                onClick={() => setExpandedDomain(d)}
              />
            ))}
          </div>
        </section>

        {/* ── RIGHT COLUMN (col-4) ── */}
        <section className="col-span-4 bg-[#0f2023]/50 p-4 flex flex-col gap-4 overflow-hidden relative z-10">
          <RootCauseCard chain={primaryChain} confidence={confidence} />
          <VerdictStack events={mockVerdictEvents} />
          <RemediationCard steps={immediateSteps} blastRadius={findings?.blast_radius} />
        </section>
      </main>

      <CommandBar />
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  );
};

export default ClusterWarRoom;
```

**Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 3: Verify Vite builds**

```bash
cd frontend && npx vite build
```
Expected: Build succeeds with 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
git commit -m "feat: rewrite ClusterWarRoom as 3-column war room orchestrator"
```

---

### Task 11: Final Verification & Build

**Step 1: Run TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors

**Step 2: Run Vite build**

```bash
cd frontend && npx vite build
```
Expected: Build succeeds

**Step 3: Run backend tests (ensure nothing broken)**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: All tests pass (593+)

**Step 4: Visual smoke test**

```bash
cd frontend && npx vite --port 5173 &
```
Open `http://localhost:5173`, start a cluster diagnostics session, verify:
- 3-column layout renders
- Header shows session ID and confidence bar
- Left column: DAG, heatmap, velocity
- Center: domain panel with namespace sections
- Right: root cause card, verdict stack, remediation
- Clicking vertical ribbons switches expanded domain
- Command bar at bottom
- Chat drawer still works
- Neural pulse SVG overlay visible

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A && git commit -m "fix: address visual review feedback"
```
