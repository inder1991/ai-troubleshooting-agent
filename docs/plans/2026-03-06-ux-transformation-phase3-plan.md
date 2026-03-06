# Phase 3: Observatory Dashboard Enhancement

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Elevate the Observatory dashboard to Datadog-grade data density using Phase 1 shared components, replacing ad-hoc Recharts usage and adding Golden Signals at-a-glance metrics.

**Architecture:** Compose existing shared components (MetricCard, SparklineWidget, StatusBadge, SkeletonLoader, SectionHeader) into Observatory tabs. No new dependencies — replace Recharts sparklines with pure SVG SparklineWidget. Add computed Golden Signals ribbon from existing snapshot data.

**Tech Stack:** React, TypeScript, existing shared components from `frontend/src/components/shared/`

---

### Task 1: Add Golden Signals Ribbon to ObservatoryView

**Files:**
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

**What:** Add a 4-column MetricCard ribbon between the header and tab content showing computed Golden Signals: Avg Latency, Packet Loss, Link Utilization, Active Alerts. These are the 4 numbers an SRE wants to see at a glance.

**Step 1: Add imports and compute metrics**

At the top of `ObservatoryView.tsx`, add import:
```tsx
import { MetricCard } from '../shared/MetricCard';
```

Inside the component, after the existing `alertCount` computation (line 20), add:

```tsx
// Golden Signals computation
const avgLatency = snapshot.devices.filter(d => d.status !== 'down').length > 0
  ? snapshot.devices.filter(d => d.status !== 'down').reduce((sum, d) => sum + d.latency_ms, 0) / snapshot.devices.filter(d => d.status !== 'down').length
  : 0;
const avgPacketLoss = snapshot.devices.length > 0
  ? snapshot.devices.reduce((sum, d) => sum + d.packet_loss, 0) / snapshot.devices.length
  : 0;
const avgUtilization = snapshot.links.length > 0
  ? snapshot.links.reduce((sum, l) => sum + l.utilization, 0) / snapshot.links.length
  : 0;
```

**Step 2: Add MetricCard ribbon JSX**

Insert between the header `</div>` (line 148) and the tab content `<div className="flex-1 overflow-auto">` (line 151):

```tsx
{/* Golden Signals Ribbon */}
{!loading && (
  <div className="grid grid-cols-4 gap-4 px-6 py-4">
    <MetricCard
      title="AVG LATENCY"
      value={`${avgLatency.toFixed(1)}ms`}
      trendValue={avgLatency < 50 ? 'Normal' : avgLatency < 100 ? 'Elevated' : 'High'}
      trendDirection={avgLatency < 50 ? 'down' : 'up'}
      trendType={avgLatency < 50 ? 'good' : avgLatency < 100 ? 'neutral' : 'bad'}
      sparklineData={snapshot.devices.filter(d => d.status !== 'down').map(d => d.latency_ms)}
    />
    <MetricCard
      title="PACKET LOSS"
      value={`${(avgPacketLoss * 100).toFixed(1)}%`}
      trendValue={avgPacketLoss === 0 ? '0% loss' : `${(avgPacketLoss * 100).toFixed(1)}%`}
      trendDirection={avgPacketLoss === 0 ? 'down' : 'up'}
      trendType={avgPacketLoss < 0.01 ? 'good' : avgPacketLoss < 0.05 ? 'neutral' : 'bad'}
      sparklineData={snapshot.devices.map(d => d.packet_loss * 100)}
    />
    <MetricCard
      title="LINK UTILIZATION"
      value={`${(avgUtilization * 100).toFixed(0)}%`}
      trendValue={avgUtilization < 0.5 ? 'Healthy' : avgUtilization < 0.8 ? 'Moderate' : 'Saturated'}
      trendDirection={avgUtilization < 0.5 ? 'down' : 'up'}
      trendType={avgUtilization < 0.5 ? 'good' : avgUtilization < 0.8 ? 'neutral' : 'bad'}
      sparklineData={snapshot.links.map(l => l.utilization * 100)}
    />
    <MetricCard
      title="ACTIVE ALERTS"
      value={alertCount}
      trendValue={alertCount === 0 ? 'Clear' : `${alertCount} active`}
      trendDirection={alertCount === 0 ? 'down' : 'up'}
      trendType={alertCount === 0 ? 'good' : alertCount > 5 ? 'bad' : 'neutral'}
      sparklineData={[alertCount, alertCount]}
    />
  </div>
)}
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): add Golden Signals MetricCard ribbon"
```

---

### Task 2: Replace Recharts Sparklines with SparklineWidget in NOCWallTab

**Files:**
- Modify: `frontend/src/components/Observatory/NOCWallTab.tsx`

**What:** Replace the `recharts` LineChart sparkline in NOC Wall device cards with the shared `SparklineWidget` (pure SVG, zero-dependency). This makes NOCWallTab consistent with the Dashboard and removes a heavy import.

**Step 1: Replace imports**

Remove line 2:
```tsx
import { LineChart, Line, ResponsiveContainer } from 'recharts';
```

Add:
```tsx
import { SparklineWidget } from '../shared/SparklineWidget';
```

**Step 2: Replace sparkline rendering**

Find the sparkline section (lines 184-197):
```tsx
<div className="w-24 h-10">
  {m?.latencyHistory && m.latencyHistory.length > 1 ? (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={m.latencyHistory}>
        <Line type="monotone" dataKey="value" stroke="#07b6d5" strokeWidth={1.5}
          dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  ) : (
    <div className="w-full h-full flex items-center justify-center text-[9px] font-mono" style={{ color: '#224349' }}>
      —
    </div>
  )}
</div>
```

Replace with:
```tsx
<div className="w-24 h-10">
  {m?.latencyHistory && m.latencyHistory.length > 1 ? (
    <SparklineWidget
      data={m.latencyHistory.map(p => p.value)}
      color={d.status === 'down' ? 'red' : d.status === 'degraded' ? 'amber' : 'cyan'}
      height={40}
      strokeWidth={1.5}
    />
  ) : (
    <div className="w-full h-full flex items-center justify-center text-[9px] font-mono" style={{ color: '#224349' }}>
      —
    </div>
  )}
</div>
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/Observatory/NOCWallTab.tsx
git commit -m "refactor(observatory): replace Recharts sparklines with SparklineWidget"
```

---

### Task 3: Add StatusBadge to Observatory Header

**Files:**
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

**What:** Replace the raw text status spans in the header (lines 133-146) with shared `StatusBadge` components for visual consistency with the Dashboard.

**Step 1: Add import**

Add to existing imports:
```tsx
import { StatusBadge } from '../shared/StatusBadge';
```

**Step 2: Replace status badges in header**

Find the status badges section (lines 133-146):
```tsx
<div className="flex items-center gap-3 text-xs font-mono">
  {secondsAgo !== null && (
    <span style={{ color: '#64748b' }}>Updated {secondsAgo}s ago</span>
  )}
  <span style={{ color: upCount === totalCount && totalCount > 0 ? '#22c55e' : '#f59e0b' }}>
    {upCount}/{totalCount} UP
  </span>
  {driftCount > 0 && (
    <span style={{ color: '#f59e0b' }}>{driftCount} drift</span>
  )}
  {discoveryCount > 0 && (
    <span style={{ color: '#07b6d5' }}>{discoveryCount} discovered</span>
  )}
</div>
```

Replace with:
```tsx
<div className="flex items-center gap-3 text-xs font-mono">
  {secondsAgo !== null && (
    <span style={{ color: '#64748b' }}>Updated {secondsAgo}s ago</span>
  )}
  <StatusBadge
    status={upCount === totalCount && totalCount > 0 ? 'healthy' : 'degraded'}
    label={`${upCount}/${totalCount} UP`}
    pulse={upCount < totalCount}
  />
  {driftCount > 0 && (
    <StatusBadge status="degraded" label="Drift" count={driftCount} />
  )}
  {discoveryCount > 0 && (
    <StatusBadge status="in_progress" label="Discovered" count={discoveryCount} />
  )}
</div>
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): use StatusBadge in header for design consistency"
```

---

### Task 4: Add Skeleton Loading to Observatory Tabs

**Files:**
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

**What:** Replace the plain "Loading observatory data..." text with proper `SkeletonLoader` components for a polished loading state.

**Step 1: Add import**

```tsx
import { SkeletonLoader } from '../shared/SkeletonLoader';
```

**Step 2: Replace loading state**

Find (line 152-153):
```tsx
{loading ? (
  <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading observatory data...</div>
```

Replace with:
```tsx
{loading ? (
  <div className="p-6 space-y-4">
    {/* Golden Signals skeleton */}
    <div className="grid grid-cols-4 gap-4">
      {[1, 2, 3, 4].map(i => (
        <SkeletonLoader key={i} type="card" />
      ))}
    </div>
    {/* Content skeleton */}
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
        <SkeletonLoader key={i} type="card" />
      ))}
    </div>
  </div>
```

Note: `SkeletonLoader` uses `type` prop with values: `'text' | 'card' | 'avatar' | 'row'`. The `type="card"` renders a `h-32` animated pulse block.

**Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): add skeleton loading states"
```

---

### Task 5: Add Severity Summary Cards to AlertsTab

**Files:**
- Modify: `frontend/src/components/Observatory/AlertsTab.tsx`

**What:** Add a summary ribbon at the top of AlertsTab showing count cards for Critical/Warning/Info with visual urgency styling, replacing the bare filter buttons with something more informative.

**Step 1: Add imports**

```tsx
import { SectionHeader } from '../shared/SectionHeader';
```

**Step 2: Add severity summary cards**

After the filter buttons `</div>` (line 51) and before the alert list, insert:

```tsx
{/* Severity Summary */}
<div className="grid grid-cols-3 gap-3">
  {(['critical', 'warning', 'info'] as const).map(severity => {
    const count = alerts.filter(a => a.severity === severity && !a.acknowledged).length;
    const total = alerts.filter(a => a.severity === severity).length;
    const colors: Record<string, string> = { critical: '#ef4444', warning: '#f59e0b', info: '#07b6d5' };
    const color = colors[severity];
    return (
      <div
        key={severity}
        onClick={() => setFilter(severity)}
        className="rounded-lg border p-3 cursor-pointer transition-all hover:border-[#07b6d5]/50"
        style={{
          backgroundColor: '#0a1a1e',
          borderColor: count > 0 ? `${color}40` : '#224349',
          borderLeftWidth: '3px',
          borderLeftColor: color,
        }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono font-bold uppercase tracking-wider" style={{ color }}>
            {severity}
          </span>
          <span className="text-lg font-mono font-bold" style={{ color: count > 0 ? color : '#64748b' }}>
            {count}
          </span>
        </div>
        <div className="text-[10px] font-mono mt-1" style={{ color: '#64748b' }}>
          {total - count} acknowledged
        </div>
      </div>
    );
  })}
</div>
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/Observatory/AlertsTab.tsx
git commit -m "feat(observatory): add severity summary cards to AlertsTab"
```

---

### Task 6: Add SectionHeader to Traffic Flows Tab

**Files:**
- Modify: `frontend/src/components/Observatory/TrafficFlowsTab.tsx`

**What:** Replace the raw `<h3>` section headers with the shared `SectionHeader` component for visual consistency.

**Step 1: Add import**

```tsx
import { SectionHeader } from '../shared/SectionHeader';
```

**Step 2: Replace section headers**

Replace line 97-99:
```tsx
<h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
  Top Talkers
</h3>
```

With:
```tsx
<SectionHeader title="Top Talkers" />
```

Replace line 123-125:
```tsx
<h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
  Protocol Breakdown
</h3>
```

With:
```tsx
<SectionHeader title="Protocol Breakdown" />
```

Replace line 153-155:
```tsx
<h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
  Link Bandwidth
</h3>
```

With:
```tsx
<SectionHeader title="Link Bandwidth" />
```

**Step 3: Verify SectionHeader interface**

Read `SectionHeader.tsx` to confirm it accepts `title` as a prop. Adapt if needed.

**Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/components/Observatory/TrafficFlowsTab.tsx
git commit -m "refactor(observatory): use shared SectionHeader in TrafficFlowsTab"
```

---

### Task 7: Final TypeScript Verification and Visual Check

**Files:**
- All modified Observatory files

**Step 1: Full TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 2: Verify no unused imports**

Check that `recharts` imports in NOCWallTab are gone. Verify no orphaned imports.

**Step 3: Verify app starts**

Run: `cd frontend && npm run dev`
Expected: Vite dev server starts without errors

**Step 4: Visual verification checklist**

Navigate to Observatory page and verify:
- [ ] Golden Signals ribbon shows 4 MetricCards (Avg Latency, Packet Loss, Link Utilization, Active Alerts)
- [ ] MetricCards show sparklines from snapshot data
- [ ] Header uses StatusBadge components (with pulse on degraded state)
- [ ] NOC Wall device cards use SparklineWidget (no Recharts)
- [ ] Sparkline color changes based on device status (cyan=up, amber=degraded, red=down)
- [ ] AlertsTab has severity summary cards at top
- [ ] Clicking a severity card filters alerts
- [ ] TrafficFlowsTab uses SectionHeader components
- [ ] Loading state shows skeleton cards instead of text
- [ ] No TypeScript errors

**Step 5: Final commit if any cleanup needed**

```bash
git add -A frontend/src/components/Observatory/
git commit -m "chore(observatory): phase 3 cleanup"
```

---

## Execution Order

```
Task 1: Golden Signals Ribbon     (ObservatoryView.tsx — MetricCard)
Task 2: SparklineWidget in NOC    (NOCWallTab.tsx — replace Recharts)
Task 3: StatusBadge in header     (ObservatoryView.tsx — StatusBadge)
Task 4: Skeleton loading          (ObservatoryView.tsx — SkeletonLoader)
Task 5: Alert severity cards      (AlertsTab.tsx — summary ribbon)
Task 6: SectionHeader in Traffic  (TrafficFlowsTab.tsx — SectionHeader)
Task 7: Final verification        (all files — tsc + visual)
```

Tasks 1, 3, 4 all modify `ObservatoryView.tsx` so they must be sequential.
Tasks 2, 5, 6 touch different files and are independent of each other.

Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7
