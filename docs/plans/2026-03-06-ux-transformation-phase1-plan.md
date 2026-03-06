# UX Transformation Phase 1: Foundation + Home Dashboard

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish a shared component library of Datadog-style UI primitives and transform the Home page from a capability launcher into a live operational command center.

**Architecture:** Build 7 shared components (SparklineWidget, MetricCard, StatusBadge, SkeletonLoader, TrendIndicator, SectionHeader, TimeRangeSelector) in `frontend/src/components/shared/`, then use them to rebuild the Home page with a metric ribbon, high-density activity feed, quick actions sidebar, and integration status panel. Refactor SidebarNav with grouped sections and collapsed mode.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Material Symbols Outlined icons, pure SVG (no Recharts/D3 for sparklines).

**Design doc:** `docs/plans/2026-03-06-ux-transformation-design.md`

---

## Task 1: SparklineWidget — Pure SVG Micro-Chart

The foundation component. Every MetricCard, ActivityFeedRow, and NocDeviceCard depends on this. Uses native SVG `<polyline>` — no charting library.

**Files:**
- Create: `frontend/src/components/shared/SparklineWidget.tsx`

**Step 1: Create the component**

```tsx
import React, { useMemo } from 'react';

interface SparklineWidgetProps {
  data: number[];
  color?: 'cyan' | 'green' | 'amber' | 'red' | 'slate';
  width?: number | string;
  height?: number;
  strokeWidth?: number;
}

const colorMap: Record<string, string> = {
  cyan: '#13b6ec',
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
  slate: '#64748b',
};

export const SparklineWidget: React.FC<SparklineWidgetProps> = ({
  data,
  color = 'cyan',
  width = '100%',
  height = 32,
  strokeWidth = 2,
}) => {
  const points = useMemo(() => {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    return data
      .map((val, i) => {
        const x = (i / (data.length - 1)) * 100;
        const y = 100 - ((val - min) / range) * 100;
        return `${x},${y}`;
      })
      .join(' ');
  }, [data]);

  if (!data || data.length < 2) {
    return <div className="h-8 text-[10px] text-slate-500">No data</div>;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 -5 100 110"
      preserveAspectRatio="none"
      className="overflow-visible"
    >
      <polyline
        fill="none"
        stroke={colorMap[color] || colorMap.cyan}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        className="transition-all duration-300 ease-in-out"
      />
    </svg>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`
Expected: No errors related to SparklineWidget.

**Step 3: Commit**

```bash
git add frontend/src/components/shared/SparklineWidget.tsx
git commit -m "feat(shared): add SparklineWidget — pure SVG polyline micro-chart"
```

---

## Task 2: StatusBadge — Universal Status Indicator

Used across Home (session status), Observatory (device status), War Room (finding severity).

**Files:**
- Create: `frontend/src/components/shared/StatusBadge.tsx`

**Step 1: Create the component**

```tsx
import React from 'react';

export type SystemStatus = 'healthy' | 'degraded' | 'critical' | 'unknown' | 'in_progress';

interface StatusBadgeProps {
  status: SystemStatus;
  label: string;
  count?: number;
  pulse?: boolean;
}

const statusStyles: Record<SystemStatus, { bg: string; text: string; border: string; dot: string }> = {
  healthy:     { bg: 'bg-green-500/10',    text: 'text-green-500',    border: 'border-green-500/20',    dot: 'bg-green-500' },
  degraded:    { bg: 'bg-[#f59e0b]/10',    text: 'text-[#f59e0b]',    border: 'border-[#f59e0b]/20',    dot: 'bg-[#f59e0b]' },
  critical:    { bg: 'bg-[#ef4444]/10',    text: 'text-[#ef4444]',    border: 'border-[#ef4444]/20',    dot: 'bg-[#ef4444]' },
  unknown:     { bg: 'bg-slate-500/10',    text: 'text-slate-400',    border: 'border-slate-500/20',    dot: 'bg-slate-400' },
  in_progress: { bg: 'bg-[#07b6d5]/10',   text: 'text-[#07b6d5]',   border: 'border-[#07b6d5]/20',   dot: 'bg-[#07b6d5]' },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, count, pulse = false }) => {
  const s = statusStyles[status] || statusStyles.unknown;

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border ${s.bg} ${s.text} ${s.border} font-mono text-[10px] uppercase tracking-wider`}>
      <span className="relative flex h-1.5 w-1.5">
        {pulse && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${s.dot}`} />}
        <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${s.dot}`} />
      </span>
      <span>{label}</span>
      {count !== undefined && (
        <span className="ml-1 px-1 bg-black/20 rounded-sm text-[9px]">{count}</span>
      )}
    </div>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**

```bash
git add frontend/src/components/shared/StatusBadge.tsx
git commit -m "feat(shared): add StatusBadge — universal status indicator with pulse"
```

---

## Task 3: TrendIndicator + SkeletonLoader + SectionHeader + TimeRangeSelector

Four small utility components. Create all in one task since each is < 30 lines.

**Files:**
- Create: `frontend/src/components/shared/TrendIndicator.tsx`
- Create: `frontend/src/components/shared/SkeletonLoader.tsx`
- Create: `frontend/src/components/shared/SectionHeader.tsx`
- Create: `frontend/src/components/shared/TimeRangeSelector.tsx`
- Create: `frontend/src/components/shared/index.ts`

**Step 1: Create TrendIndicator**

```tsx
import React from 'react';

interface TrendIndicatorProps {
  value: string;
  direction: 'up' | 'down' | 'neutral';
  type: 'good' | 'bad' | 'neutral';
}

export const TrendIndicator: React.FC<TrendIndicatorProps> = ({ value, direction, type }) => {
  const styles = type === 'good'
    ? 'text-green-500 bg-green-500/10'
    : type === 'bad'
      ? 'text-[#ef4444] bg-[#ef4444]/10'
      : 'text-slate-400 bg-slate-400/10';

  const icon = direction === 'up' ? 'arrow_upward' : direction === 'down' ? 'arrow_downward' : 'remove';

  return (
    <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${styles}`}>
      <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{icon}</span>
      {value}
    </div>
  );
};
```

**Step 2: Create SkeletonLoader**

```tsx
import React from 'react';

interface SkeletonLoaderProps {
  type: 'text' | 'card' | 'avatar' | 'row';
  width?: string;
  height?: string;
  className?: string;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({ type, width, height, className = '' }) => {
  const base = 'animate-pulse bg-[#162a2e] border border-[#224349]';

  if (type === 'avatar') return <div className={`${base} rounded-full ${width || 'w-8'} ${height || 'h-8'} ${className}`} />;
  if (type === 'text') return <div className={`${base} rounded ${width || 'w-full'} ${height || 'h-4'} ${className}`} />;
  if (type === 'card') return <div className={`${base} rounded-lg ${width || 'w-full'} ${height || 'h-32'} ${className}`} />;
  return <div className={`${base} rounded ${width || 'w-full'} ${height || 'h-12'} ${className}`} />;
};
```

**Step 3: Create SectionHeader**

```tsx
import React from 'react';

interface SectionHeaderProps {
  title: string;
  count?: number;
  action?: React.ReactNode;
  children?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({ title, count, action, children }) => (
  <div className="flex items-center justify-between mb-4">
    <div className="flex items-center gap-3">
      <h2 className="text-base font-bold text-white tracking-tight">{title}</h2>
      {count !== undefined && (
        <span className="px-2 py-0.5 bg-[#07b6d5]/10 text-[#07b6d5] text-[10px] font-black uppercase rounded tracking-widest border border-[#07b6d5]/20">
          {count}
        </span>
      )}
      {children}
    </div>
    {action && <div>{action}</div>}
  </div>
);
```

**Step 4: Create TimeRangeSelector**

```tsx
import React from 'react';

interface TimeRangeSelectorProps {
  options?: string[];
  selected: string;
  onChange: (range: string) => void;
}

export const TimeRangeSelector: React.FC<TimeRangeSelectorProps> = ({
  options = ['5m', '15m', '1h', '6h', '24h', '7d'],
  selected,
  onChange,
}) => (
  <div className="flex items-center gap-0.5 bg-[#0a1517] rounded-lg p-0.5 border border-[#224349]">
    {options.map((opt) => (
      <button
        key={opt}
        onClick={() => onChange(opt)}
        className={`px-2.5 py-1 text-[10px] font-mono font-bold uppercase rounded-md transition-colors ${
          selected === opt
            ? 'bg-[#07b6d5]/20 text-[#07b6d5] border border-[#07b6d5]/30'
            : 'text-slate-500 hover:text-slate-300 border border-transparent'
        }`}
      >
        {opt}
      </button>
    ))}
  </div>
);
```

**Step 5: Create barrel export**

```tsx
export { SparklineWidget } from './SparklineWidget';
export { StatusBadge } from './StatusBadge';
export type { SystemStatus } from './StatusBadge';
export { TrendIndicator } from './TrendIndicator';
export { SkeletonLoader } from './SkeletonLoader';
export { SectionHeader } from './SectionHeader';
export { TimeRangeSelector } from './TimeRangeSelector';
```

**Step 6: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 7: Commit**

```bash
git add frontend/src/components/shared/
git commit -m "feat(shared): add TrendIndicator, SkeletonLoader, SectionHeader, TimeRangeSelector + barrel export"
```

---

## Task 4: MetricCard — The Command Center Tile

Consumes SparklineWidget and TrendIndicator. The hero component of the Metric Ribbon.

**Files:**
- Create: `frontend/src/components/shared/MetricCard.tsx`
- Modify: `frontend/src/components/shared/index.ts` — add export

**Step 1: Create the component**

```tsx
import React from 'react';
import { SparklineWidget } from './SparklineWidget';

interface MetricCardProps {
  title: string;
  value: string | number;
  trendValue: string;
  trendDirection: 'up' | 'down' | 'neutral';
  trendType: 'good' | 'bad' | 'neutral';
  sparklineData: number[];
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  trendValue,
  trendDirection,
  trendType,
  sparklineData,
}) => {
  const trendStyles = trendType === 'good'
    ? 'text-green-500 bg-green-500/10'
    : trendType === 'bad'
      ? 'text-[#ef4444] bg-[#ef4444]/10'
      : 'text-slate-400 bg-slate-400/10';

  const sparkColor = trendType === 'good' ? 'green' : trendType === 'bad' ? 'red' : 'cyan';
  const arrowIcon = trendDirection === 'up' ? 'arrow_upward' : trendDirection === 'down' ? 'arrow_downward' : 'remove';

  return (
    <div className="bg-[#0f2023] border border-[#224349] rounded-lg p-4 flex flex-col justify-between h-32 hover:border-[#07b6d5]/50 transition-colors relative overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#07b6d5]/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="flex justify-between items-start z-10">
        <h3 className="text-[#94a3b8] text-xs font-semibold uppercase tracking-wider">{title}</h3>
        <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${trendStyles}`}>
          <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>{arrowIcon}</span>
          {trendValue}
        </div>
      </div>

      <div className="flex items-end justify-between mt-2 z-10">
        <div className="text-3xl font-mono font-bold text-[#e2e8f0] tracking-tight">{value}</div>
        <div className="w-24 opacity-80 group-hover:opacity-100 transition-opacity">
          <SparklineWidget data={sparklineData} color={sparkColor} height={28} />
        </div>
      </div>
    </div>
  );
};
```

**Step 2: Add export to barrel**

Add to `frontend/src/components/shared/index.ts`:
```tsx
export { MetricCard } from './MetricCard';
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 4: Commit**

```bash
git add frontend/src/components/shared/MetricCard.tsx frontend/src/components/shared/index.ts
git commit -m "feat(shared): add MetricCard — KPI tile with sparkline and trend"
```

---

## Task 5: ActivityFeedRow — High-Density Session Row

Replaces the flat 12-col grid rows in LiveIntelligenceFeed with a rich, interactive row showing service, phase, confidence bar, duration, and agent avatars.

**Files:**
- Create: `frontend/src/components/shared/ActivityFeedRow.tsx`
- Modify: `frontend/src/components/shared/index.ts` — add export

**Step 1: Create the component**

```tsx
import React from 'react';
import { StatusBadge, type SystemStatus } from './StatusBadge';

interface ActivityFeedRowProps {
  targetService: string;
  targetNamespace: string;
  timestamp: string;
  status: SystemStatus;
  phase: string;
  confidenceScore: number;
  durationStr: string;
  activeAgents: string[];
  onClick?: () => void;
}

export const ActivityFeedRow: React.FC<ActivityFeedRowProps> = ({
  targetService,
  targetNamespace,
  timestamp,
  status,
  phase,
  confidenceScore,
  durationStr,
  activeAgents,
  onClick,
}) => {
  const barColor = confidenceScore >= 80 ? 'bg-green-500' : confidenceScore >= 50 ? 'bg-[#f59e0b]' : 'bg-[#ef4444]';

  return (
    <div
      onClick={onClick}
      className="flex items-center justify-between p-3 border-b border-[#224349] hover:bg-[#0f2023] transition-colors group cursor-pointer"
    >
      <div className="flex items-center gap-4 w-1/3">
        <div className="w-8 h-8 rounded bg-[#162a2e] flex items-center justify-center border border-[#3a5a60] shrink-0 text-[#07b6d5]">
          <span className="material-symbols-outlined text-[16px]" style={{ fontFamily: 'Material Symbols Outlined' }}>memory</span>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[#e2e8f0] font-mono font-bold text-sm">{targetService}</span>
            {targetNamespace && (
              <span className="text-[#64748b] font-mono text-[10px] bg-black/20 px-1 rounded">ns:{targetNamespace}</span>
            )}
          </div>
          <span className="text-[#64748b] text-[11px] block mt-0.5">{timestamp}</span>
        </div>
      </div>

      <div className="flex flex-col gap-2 w-1/3 px-4">
        <div className="flex items-center gap-3">
          <StatusBadge status={status} label={phase} pulse={status === 'in_progress'} />
          <span className="text-[#94a3b8] font-mono text-[10px]">Conf: {confidenceScore}%</span>
        </div>
        <div className="w-full h-1 bg-[#162a2e] rounded-full overflow-hidden">
          <div className={`h-full ${barColor} transition-all duration-1000`} style={{ width: `${confidenceScore}%` }} />
        </div>
      </div>

      <div className="flex items-center justify-end gap-6 w-1/3">
        <div className="flex flex-col items-end">
          <span className="text-[#64748b] font-mono text-[10px] uppercase">Duration</span>
          <span className="text-[#e2e8f0] font-mono text-xs">{durationStr}</span>
        </div>
        <div className="flex -space-x-2">
          {activeAgents.slice(0, 4).map((agent, i) => (
            <div
              key={i}
              className="w-6 h-6 rounded-full bg-[#1a3a40] border border-[#224349] flex items-center justify-center text-[10px] font-mono text-[#07b6d5] z-10 hover:z-20 hover:-translate-y-1 transition-transform"
              title={`${agent} Agent`}
            >
              {agent.charAt(0)}
            </div>
          ))}
        </div>
        <span className="material-symbols-outlined text-[#64748b] group-hover:text-[#07b6d5] transition-colors text-[18px] opacity-0 group-hover:opacity-100" style={{ fontFamily: 'Material Symbols Outlined' }}>
          chevron_right
        </span>
      </div>
    </div>
  );
};
```

**Step 2: Add export to barrel**

Add to `frontend/src/components/shared/index.ts`:
```tsx
export { ActivityFeedRow } from './ActivityFeedRow';
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 4: Commit**

```bash
git add frontend/src/components/shared/ActivityFeedRow.tsx frontend/src/components/shared/index.ts
git commit -m "feat(shared): add ActivityFeedRow — high-density session row with confidence bar and agent avatars"
```

---

## Task 6: Transform LiveIntelligenceFeed — Use ActivityFeedRow

Replace the flat grid rows with ActivityFeedRow components. Add SectionHeader and TimeRangeSelector.

**Files:**
- Modify: `frontend/src/components/Home/LiveIntelligenceFeed.tsx`

**Step 1: Rewrite LiveIntelligenceFeed**

Keep the data fetching logic (lines 96-111), replace the render. Key changes:
- Import and use `ActivityFeedRow`, `SectionHeader`, `TimeRangeSelector`, `SkeletonLoader` from shared
- Add `timeRange` state for the selector (UI only — filtering happens later)
- Replace the 12-col grid header/rows with ActivityFeedRow components
- Map `DiagnosticPhase` to `SystemStatus` for StatusBadge
- Compute `durationStr` from `created_at` to `updated_at`
- Compute `activeAgents` from capability type (e.g., 'troubleshoot_app' → ['Log', 'Metric', 'Trace', 'Code'])
- Replace empty state with SkeletonLoader during loading, and a richer empty state when no sessions
- Show up to 15 sessions, with "Show more..." link at bottom

**Phase mapping function:**

```tsx
const phaseToStatus = (phase: DiagnosticPhase): { status: SystemStatus; label: string } => {
  if (['initial', 'collecting_context'].includes(phase)) return { status: 'in_progress', label: 'Collecting' };
  if (['logs_analyzed', 'metrics_analyzed', 'k8s_analyzed', 'tracing_analyzed', 'code_analyzed'].includes(phase)) return { status: 'in_progress', label: 'Analyzing' };
  if (['validating', 're_investigating'].includes(phase)) return { status: 'in_progress', label: 'Validating' };
  if (phase === 'fix_in_progress') return { status: 'degraded', label: 'Remediating' };
  if (['diagnosis_complete', 'complete'].includes(phase)) return { status: 'healthy', label: 'Resolved' };
  if (phase === 'error') return { status: 'critical', label: 'Error' };
  return { status: 'unknown', label: String(phase) };
};
```

**Agent mapping function:**

```tsx
const capabilityAgents = (cap?: string): string[] => {
  switch (cap) {
    case 'troubleshoot_app': return ['Log', 'Metric', 'Trace', 'Code'];
    case 'pr_review': return ['Code', 'Security'];
    case 'github_issue_fix': return ['Code', 'Patch'];
    case 'cluster_diagnostics': return ['Node', 'Network', 'Storage', 'CtrlPlane'];
    case 'network_troubleshooting': return ['Path', 'Firewall', 'NAT'];
    default: return ['Agent'];
  }
};
```

**Duration computation:**

```tsx
const computeDuration = (created: string, updated: string): string => {
  const ms = new Date(updated).getTime() - new Date(created).getTime();
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  return `${Math.round(ms / 60000)}m`;
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**

```bash
git add frontend/src/components/Home/LiveIntelligenceFeed.tsx
git commit -m "feat(home): replace flat session grid with high-density ActivityFeedRow"
```

---

## Task 7: MetricRibbon — Computed KPI Cards for Home

Add a 4-card metric ribbon above the capability launcher. Computes metrics from the sessions array.

**Files:**
- Create: `frontend/src/components/Home/MetricRibbon.tsx`

**Step 1: Create the component**

The MetricRibbon computes 4 KPIs from the sessions array:
1. **Active Sessions** — sessions where status is not 'complete'/'diagnosis_complete'/'error'
2. **Resolved Today** — sessions with 'complete'/'diagnosis_complete' status and `updated_at` is today
3. **Avg Confidence** — average of `confidence` across all sessions (as percentage)
4. **Mean Time to Resolve** — average duration of resolved sessions in minutes

Each MetricCard gets a mock sparkline from the last 8 session confidence values (or counts per hour).

```tsx
import React, { useMemo } from 'react';
import { MetricCard } from '../shared';
import type { V4Session } from '../../types';

interface MetricRibbonProps {
  sessions: V4Session[];
}

const isActive = (s: V4Session) => !['complete', 'diagnosis_complete', 'error'].includes(s.status);
const isResolvedToday = (s: V4Session) => {
  if (!['complete', 'diagnosis_complete'].includes(s.status)) return false;
  const today = new Date().toDateString();
  return new Date(s.updated_at).toDateString() === today;
};

export const MetricRibbon: React.FC<MetricRibbonProps> = ({ sessions }) => {
  const metrics = useMemo(() => {
    const active = sessions.filter(isActive);
    const resolved = sessions.filter(isResolvedToday);
    const avgConf = sessions.length > 0
      ? Math.round(sessions.reduce((sum, s) => sum + (s.confidence || 0), 0) / sessions.length)
      : 0;

    const resolvedSessions = sessions.filter(s => ['complete', 'diagnosis_complete'].includes(s.status));
    const avgDuration = resolvedSessions.length > 0
      ? resolvedSessions.reduce((sum, s) => {
          const ms = new Date(s.updated_at).getTime() - new Date(s.created_at).getTime();
          return sum + ms;
        }, 0) / resolvedSessions.length / 60000
      : 0;

    // Generate sparkline data from recent session confidence values
    const recentConf = sessions.slice(0, 8).map(s => s.confidence || 0);
    const recentActive = sessions.slice(0, 8).map((_, i) => sessions.slice(0, i + 1).filter(isActive).length);

    return {
      activeCount: active.length,
      resolvedCount: resolved.length,
      avgConfidence: avgConf,
      mttr: avgDuration > 0 ? `${avgDuration.toFixed(1)}m` : '—',
      sparkActive: recentActive.length >= 2 ? recentActive : [0, 0],
      sparkResolved: resolved.length >= 2 ? recentConf : [0, 0],
      sparkConf: recentConf.length >= 2 ? recentConf : [0, 0],
      sparkMttr: recentConf.length >= 2 ? recentConf.reverse() : [0, 0],
    };
  }, [sessions]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <MetricCard
        title="Active Sessions"
        value={metrics.activeCount}
        trendValue={String(metrics.activeCount)}
        trendDirection={metrics.activeCount > 0 ? 'up' : 'neutral'}
        trendType="neutral"
        sparklineData={metrics.sparkActive}
      />
      <MetricCard
        title="Resolved Today"
        value={metrics.resolvedCount}
        trendValue={String(metrics.resolvedCount)}
        trendDirection={metrics.resolvedCount > 0 ? 'up' : 'neutral'}
        trendType="good"
        sparklineData={metrics.sparkResolved}
      />
      <MetricCard
        title="Avg Confidence"
        value={`${metrics.avgConfidence}%`}
        trendValue={`${metrics.avgConfidence}%`}
        trendDirection={metrics.avgConfidence >= 70 ? 'up' : 'down'}
        trendType={metrics.avgConfidence >= 70 ? 'good' : 'bad'}
        sparklineData={metrics.sparkConf}
      />
      <MetricCard
        title="Mean Time to Resolve"
        value={metrics.mttr}
        trendValue={metrics.mttr}
        trendDirection="down"
        trendType="good"
        sparklineData={metrics.sparkMttr}
      />
    </div>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**

```bash
git add frontend/src/components/Home/MetricRibbon.tsx
git commit -m "feat(home): add MetricRibbon — 4 KPI cards computed from session data"
```

---

## Task 8: QuickActionsPanel — Right Sidebar Content

Create the right sidebar with quick action buttons and integration/system health status.

**Files:**
- Create: `frontend/src/components/Home/QuickActionsPanel.tsx`

**Step 1: Create the component**

```tsx
import React from 'react';
import { SparklineWidget } from '../shared';
import type { CapabilityType } from '../../types';

interface QuickActionsPanelProps {
  onSelectCapability: (capability: CapabilityType) => void;
  wsConnected: boolean;
}

const actions: { label: string; capability: CapabilityType; icon: string }[] = [
  { label: 'New Investigation', capability: 'troubleshoot_app', icon: 'troubleshoot' },
  { label: 'Network Scan', capability: 'network_troubleshooting', icon: 'lan' },
  { label: 'Cluster Check', capability: 'cluster_diagnostics', icon: 'deployed_code' },
  { label: 'PR Review', capability: 'pr_review', icon: 'code' },
];

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({ onSelectCapability, wsConnected }) => (
  <div className="flex flex-col gap-4">
    {/* Quick Actions */}
    <div className="bg-[#0a1517] border border-[#224349] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-3">Quick Actions</h3>
      <div className="flex flex-col gap-1.5">
        {actions.map((a) => (
          <button
            key={a.capability}
            onClick={() => onSelectCapability(a.capability)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-300 hover:text-white hover:bg-[#162a2e] transition-colors text-left group"
          >
            <span className="material-symbols-outlined text-[18px] text-[#07b6d5] group-hover:text-white transition-colors" style={{ fontFamily: 'Material Symbols Outlined' }}>
              {a.icon}
            </span>
            <span className="text-sm font-medium">{a.label}</span>
            <span className="material-symbols-outlined text-[14px] text-slate-600 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" style={{ fontFamily: 'Material Symbols Outlined' }}>
              arrow_forward
            </span>
          </button>
        ))}
      </div>
    </div>

    {/* System Health */}
    <div className="bg-[#0a1517] border border-[#224349] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-3">System Health</h3>
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">WebSocket</span>
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className={`text-[10px] font-mono ${wsConnected ? 'text-green-500' : 'text-red-500'}`}>
              {wsConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
        {/* Placeholder metrics — will be wired to real backend stats later */}
        {[
          { label: 'CPU', value: '23%', data: [20, 22, 25, 23, 21, 24, 23] },
          { label: 'Memory', value: '61%', data: [58, 59, 62, 60, 63, 61, 61] },
          { label: 'API Latency', value: '12ms', data: [14, 12, 13, 11, 12, 15, 12] },
        ].map((m) => (
          <div key={m.label} className="flex items-center justify-between gap-3">
            <span className="text-xs text-slate-400 w-16">{m.label}</span>
            <div className="flex-1 max-w-[60px]">
              <SparklineWidget data={m.data} color="cyan" height={16} strokeWidth={1.5} />
            </div>
            <span className="text-xs font-mono text-slate-300 w-10 text-right">{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  </div>
);
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**

```bash
git add frontend/src/components/Home/QuickActionsPanel.tsx
git commit -m "feat(home): add QuickActionsPanel — quick actions + system health sidebar"
```

---

## Task 9: Rebuild HomePage — Command Center Layout

Replace the current top-to-bottom layout with the 2-column command center. Keep the header as-is. Add MetricRibbon, 2-col grid (Activity Feed left, Quick Actions right), move Capability cards below.

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`

**Step 1: Rewrite HomePage layout**

Keep the existing header (lines 25-70) untouched. Replace the scrolling content (lines 72-105) with:

```tsx
import React from 'react';
import type { CapabilityType, V4Session } from '../../types';
import CapabilityLauncher from './CapabilityLauncher';
import LiveIntelligenceFeed from './LiveIntelligenceFeed';
import { MetricRibbon } from './MetricRibbon';
import { QuickActionsPanel } from './QuickActionsPanel';

interface HomePageProps {
  onSelectCapability: (capability: CapabilityType) => void;
  sessions: V4Session[];
  onSessionsChange: (sessions: V4Session[]) => void;
  onSelectSession: (session: V4Session) => void;
  wsConnected: boolean;
}

const HomePage: React.FC<HomePageProps> = ({
  onSelectCapability,
  sessions,
  onSessionsChange,
  onSelectSession,
  wsConnected,
}) => {
  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Top Header (unchanged) */}
      <header className="h-16 border-b border-[#224349] flex items-center justify-between px-8 shrink-0" style={{ backgroundColor: 'rgba(15,32,35,0.5)', backdropFilter: 'blur(12px)' }}>
        {/* ... existing header content stays identical ... */}
      </header>

      {/* Main Scrolling Content */}
      <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {/* Metric Ribbon */}
        <MetricRibbon sessions={sessions} />

        {/* 2-Column Layout: Activity Feed + Quick Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-10">
          <div className="lg:col-span-8">
            <LiveIntelligenceFeed
              sessions={sessions}
              onSessionsChange={onSessionsChange}
              onSelectSession={onSelectSession}
            />
          </div>
          <div className="lg:col-span-4">
            <QuickActionsPanel
              onSelectCapability={onSelectCapability}
              wsConnected={wsConnected}
            />
          </div>
        </div>

        {/* Capability Launcher (below operational content) */}
        <section>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-xl font-bold text-white tracking-tight">Capabilities</h2>
              <p className="text-sm text-slate-400 mt-1">Deploy automated diagnostics and remediations</p>
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

Note: The header JSX (lines 25-70 in the current file) should be preserved exactly as-is. The `HowItWorksSection` import and the "See how it works" anchor link are removed — they were below-the-fold documentation that gets replaced by the operational layout.

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Verify the app runs**

Run: `cd frontend && npx vite build 2>&1 | tail -5`
Expected: Build succeeds with no errors.

**Step 4: Commit**

```bash
git add frontend/src/components/Home/HomePage.tsx
git commit -m "feat(home): rebuild as command center — metric ribbon + 2-col activity/actions layout"
```

---

## Task 10: SidebarNav — Grouped Sections + Collapsed Mode

Reorganize nav items into 4 groups: Investigate, Infrastructure, Kubernetes, Tools. Add collapsed mode toggle.

**Files:**
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`

**Step 1: Rewrite SidebarNav**

Key changes:
1. Reorganize `navItems` into 4 groups:
   - **Investigate**: Home (Dashboard), Sessions
   - **Infrastructure**: Topology, Adapters, IPAM, Matrix, Observatory (expand the existing Network group)
   - **Kubernetes**: Cluster Diagnostics (new nav link — needs `NavView` type update)
   - **Tools**: Integrations, Settings, Agent Matrix

2. Add `collapsed` state — toggles between `w-64` and `w-16` sidebar width.

3. In collapsed mode: hide labels, show only icons with tooltips.

4. Add `NavView` entry for `cluster-diagnostics` if not already present.

**Updated NavView type:**

```tsx
export type NavView = 'home' | 'sessions' | 'integrations' | 'settings' | 'agents'
  | 'network-topology' | 'network-adapters' | 'ipam' | 'matrix' | 'observatory'
  | 'cluster-diagnostics';
```

**Updated navItems structure:**

```tsx
const navItems: NavItem[] = [
  {
    kind: 'group', group: 'Investigate', icon: 'search',
    children: [
      { id: 'home', label: 'Dashboard', icon: 'dashboard' },
      { id: 'sessions', label: 'Sessions', icon: 'history' },
    ],
  },
  {
    kind: 'group', group: 'Infrastructure', icon: 'lan',
    children: [
      { id: 'network-topology', label: 'Topology', icon: 'device_hub' },
      { id: 'network-adapters', label: 'Adapters', icon: 'settings_input_component' },
      { id: 'ipam', label: 'IPAM', icon: 'dns' },
      { id: 'matrix', label: 'Matrix', icon: 'grid_view' },
      { id: 'observatory', label: 'Observatory', icon: 'monitoring' },
    ],
  },
  {
    kind: 'group', group: 'Kubernetes', icon: 'deployed_code',
    children: [
      { id: 'cluster-diagnostics' as NavView, label: 'Cluster Diagnostics', icon: 'health_and_safety' },
    ],
  },
  {
    kind: 'group', group: 'Tools', icon: 'build',
    children: [
      { id: 'integrations', label: 'Integrations', icon: 'hub' },
      { id: 'settings', label: 'Settings', icon: 'settings' },
      { id: 'agents' as NavView, label: 'Agent Matrix', icon: 'smart_toy' },
    ],
  },
];
```

**Collapsed mode toggle:** Add a button at the top of the sidebar (next to the brand logo) that toggles `collapsed` state. When collapsed, sidebar width = `w-16`, labels hidden, only icons visible with `title` attribute for tooltips.

**Step 2: Update App.tsx if needed**

If `cluster-diagnostics` wasn't already in the sidebar navigation route handler (check `App.tsx` lines 181-191), add it to the navigation handler so clicking "Cluster Diagnostics" in the sidebar navigates correctly.

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 4: Commit**

```bash
git add frontend/src/components/Layout/SidebarNav.tsx frontend/src/App.tsx
git commit -m "feat(nav): reorganize sidebar into 4 groups + add collapsed mode"
```

---

## Task 11: Breadcrumb Navigation

Add a breadcrumb bar at the top of the main content area to show current location.

**Files:**
- Create: `frontend/src/components/shared/Breadcrumbs.tsx`
- Modify: `frontend/src/components/shared/index.ts` — add export
- Modify: `frontend/src/App.tsx` — render breadcrumbs above view content

**Step 1: Create the Breadcrumbs component**

```tsx
import React from 'react';

interface BreadcrumbItem {
  label: string;
  onClick?: () => void;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
}

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ items }) => {
  if (items.length <= 1) return null;

  return (
    <nav className="flex items-center gap-1.5 px-8 py-2 border-b border-[#224349]/50 bg-[#0a1517]/50">
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && (
            <span className="material-symbols-outlined text-[12px] text-slate-600" style={{ fontFamily: 'Material Symbols Outlined' }}>
              chevron_right
            </span>
          )}
          {item.onClick ? (
            <button
              onClick={item.onClick}
              className="text-[11px] font-mono text-slate-400 hover:text-[#07b6d5] transition-colors"
            >
              {item.label}
            </button>
          ) : (
            <span className="text-[11px] font-mono text-slate-300">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
};
```

**Step 2: Add export to barrel**

Add to `frontend/src/components/shared/index.ts`:
```tsx
export { Breadcrumbs } from './Breadcrumbs';
```

**Step 3: Add to App.tsx**

In `App.tsx`, compute breadcrumb items from `viewState` and render `<Breadcrumbs>` above the main content area (between sidebar and the view router, around line 418). Map each view state to its breadcrumb path:

```tsx
const breadcrumbMap: Record<string, { label: string; parent?: string }> = {
  home: { label: 'Dashboard' },
  sessions: { label: 'Sessions', parent: 'home' },
  'network-topology': { label: 'Topology', parent: 'home' },
  'network-adapters': { label: 'Adapters', parent: 'home' },
  ipam: { label: 'IPAM', parent: 'home' },
  matrix: { label: 'Matrix', parent: 'home' },
  observatory: { label: 'Observatory', parent: 'home' },
  integrations: { label: 'Integrations', parent: 'home' },
  settings: { label: 'Settings', parent: 'home' },
  agents: { label: 'Agent Matrix', parent: 'home' },
  'cluster-diagnostics': { label: 'Cluster Diagnostics', parent: 'home' },
};
```

Only render breadcrumbs when `showSidebar` is true (don't show in full-screen views like investigation/war room).

**Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -5`

**Step 5: Commit**

```bash
git add frontend/src/components/shared/Breadcrumbs.tsx frontend/src/components/shared/index.ts frontend/src/App.tsx
git commit -m "feat(nav): add breadcrumb navigation bar"
```

---

## Task 12: Final Verification

**Files:** None modified — verification only.

**Step 1: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors.

**Step 2: Build check**

Run: `cd frontend && npx vite build 2>&1 | tail -10`
Expected: Build succeeds.

**Step 3: Verify all shared components export correctly**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep 'shared'`
Expected: No errors referencing shared components.

**Step 4: Verify no unused imports**

Run: `cd frontend && npx tsc --noEmit 2>&1 | grep 'unused'`
Expected: No unused import errors from our new files.

---

## Execution Order

```
Task 1:  SparklineWidget (no dependencies)
Task 2:  StatusBadge (no dependencies)
Task 3:  TrendIndicator + SkeletonLoader + SectionHeader + TimeRangeSelector + barrel (no deps)
Task 4:  MetricCard (depends on Task 1 — SparklineWidget)
Task 5:  ActivityFeedRow (depends on Task 2 — StatusBadge)
Task 6:  LiveIntelligenceFeed rewrite (depends on Tasks 3, 5)
Task 7:  MetricRibbon (depends on Task 4 — MetricCard)
Task 8:  QuickActionsPanel (depends on Task 1 — SparklineWidget)
Task 9:  HomePage rebuild (depends on Tasks 6, 7, 8)
Task 10: SidebarNav rewrite (independent)
Task 11: Breadcrumbs (independent, but integrates into App.tsx)
Task 12: Final verification (depends on all)
```

Tasks 1-3 can run in parallel. Tasks 10-11 can run in parallel with Tasks 6-9.
