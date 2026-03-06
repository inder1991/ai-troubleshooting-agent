# Phase 4: Cluster Diagnostics — Design Consistency

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bring the Cluster War Room to the same design standard as Observatory and Home Dashboard by integrating Phase 1 shared components, fixing color inconsistency (#13b6ec → #07b6d5), and adding skeleton loading.

**Architecture:** No new features — purely composing existing shared components (MetricCard, StatusBadge, SkeletonLoader, SectionHeader) into the ClusterWarRoom and fixing the `#13b6ec` vs `#07b6d5` color drift across 8 cluster components.

**Tech Stack:** React, TypeScript, existing shared components from `frontend/src/components/shared/`

---

### Task 1: Fix Color Inconsistency — #13b6ec → #07b6d5

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterHeader.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/ExecutionDAG.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/VerdictStack.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/RemediationCard.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/FleetHeatmap.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/RootCauseCard.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/NeuralPulseSVG.tsx`
- Modify: `frontend/src/components/ClusterDiagnostic/CommandBar.tsx`

**What:** The entire ClusterWarRoom uses `#13b6ec` (duck-cyan from original design tokens) while Phase 1 standardized on `#07b6d5` (accent-primary). This creates visual inconsistency when navigating between pages. Replace ALL occurrences of `#13b6ec` with `#07b6d5` in cluster diagnostic components.

**Step 1: Global find-and-replace `#13b6ec` → `#07b6d5`**

In each file listed above, replace every instance of `#13b6ec` with `#07b6d5`. This includes:
- ClusterHeader.tsx: session ID color, confidence bar, title highlight
- ExecutionDAG.tsx: connector lines, node border colors, status colors
- VerdictStack.tsx: INFO severity color
- RemediationCard.tsx: command text color, button borders, hold indicator
- FleetHeatmap.tsx: selected node ring color
- NeuralPulseSVG.tsx: pulse animation colors
- CommandBar.tsx: input accent colors

**Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors (this is a pure color value change, no type implications)

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/
git commit -m "fix(cluster): standardize #13b6ec → #07b6d5 for color consistency"
```

---

### Task 2: Replace Loading Spinner with SkeletonLoader

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`

**What:** The current loading state (lines 218-225) shows a spinning icon + "Initializing cluster diagnostics..." text. Replace with a 3-column skeleton grid that matches the war room layout.

**Step 1: Add import**

```tsx
import { SkeletonLoader } from '../shared/SkeletonLoader';
```

**Step 2: Replace loading state**

Find (lines 218-225):
```tsx
{loading && !findings && !error && (
  <div className="col-span-12 flex items-center justify-center">
    <div className="text-center">
      <span className="material-symbols-outlined animate-spin text-4xl text-[#13b6ec] mb-4 block" style={{ fontFamily: 'Material Symbols Outlined' }}>progress_activity</span>
      <p className="text-slate-500 text-sm">Initializing cluster diagnostics...</p>
    </div>
  </div>
)}
```

Replace with:
```tsx
{loading && !findings && !error && (
  <>
    {/* Left column skeleton */}
    <section className="col-span-3 border-r border-[#1f3b42] p-4 flex flex-col gap-4">
      <SkeletonLoader type="card" height="h-48" />
      <SkeletonLoader type="card" height="h-28" />
      <SkeletonLoader type="card" height="h-24" />
    </section>
    {/* Center column skeleton */}
    <section className="col-span-5 border-r border-[#1f3b42] p-4 flex flex-col gap-3">
      <SkeletonLoader type="row" />
      <SkeletonLoader type="card" height="h-64" />
      <SkeletonLoader type="row" />
      <SkeletonLoader type="row" />
    </section>
    {/* Right column skeleton */}
    <section className="col-span-4 p-4 flex flex-col gap-4">
      <SkeletonLoader type="card" height="h-36" />
      <SkeletonLoader type="card" height="h-48" />
      <SkeletonLoader type="card" height="h-32" />
    </section>
  </>
)}
```

**Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
git commit -m "feat(cluster): replace loading spinner with skeleton layout"
```

---

### Task 3: Use StatusBadge in ClusterHeader

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterHeader.tsx`

**What:** Replace the raw colored dot + text for platform health with the shared `StatusBadge` component, and add WebSocket connection StatusBadge.

**Step 1: Add import**

```tsx
import { StatusBadge } from '../shared/StatusBadge';
import type { SystemStatus } from '../shared/StatusBadge';
```

**Step 2: Map health to SystemStatus**

Add mapping function:
```tsx
const healthToStatus = (health: string): SystemStatus =>
  health === 'HEALTHY' ? 'healthy'
    : health === 'DEGRADED' ? 'degraded'
    : health === 'CRITICAL' ? 'critical'
    : 'unknown';
```

**Step 3: Replace platform health display**

Find the health display section (lines 51-54):
```tsx
<div className="flex items-center gap-2 font-mono font-bold text-sm" style={{ color }}>
  <span className={`w-2 h-2 rounded-full animate-pulse`} style={{ backgroundColor: color }} />
  {platformHealth || 'ANALYZING'}
</div>
```

Replace with:
```tsx
<StatusBadge
  status={healthToStatus(platformHealth)}
  label={platformHealth || 'ANALYZING'}
  pulse={platformHealth === 'CRITICAL' || platformHealth === 'DEGRADED'}
/>
```

**Step 4: Replace WebSocket indicator**

Find the WS connection dot (line 29):
```tsx
<span className={`w-3 h-3 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600'}`} />
```

Replace with:
```tsx
<StatusBadge
  status={wsConnected ? 'healthy' : 'critical'}
  label={wsConnected ? 'LIVE' : 'OFFLINE'}
  pulse={wsConnected}
/>
```

**Step 5: Remove the now-unused `healthColor` function and `color` variable**

**Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 7: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterHeader.tsx
git commit -m "feat(cluster): use StatusBadge in ClusterHeader"
```

---

### Task 4: Add Domain Health MetricCards Ribbon

**Files:**
- Modify: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`

**What:** Add a 4-column MetricCard ribbon between the ClusterHeader and the main grid, showing each domain's health status (Control Plane, Node, Network, Storage) with anomaly counts and status-based trends.

**Step 1: Add import**

```tsx
import { MetricCard } from '../shared/MetricCard';
```

**Step 2: Add domain label and icon maps**

```tsx
const DOMAIN_LABELS: Record<ClusterDomainKey, string> = {
  ctrl_plane: 'Control Plane',
  node: 'Compute',
  network: 'Network',
  storage: 'Storage',
};
```

**Step 3: Insert MetricCard ribbon**

Between `ClusterHeader` closing tag and the error banner, insert:

```tsx
{/* Domain Health Ribbon */}
{findings && (
  <div className="grid grid-cols-4 gap-3 px-6 py-3 border-b border-[#1f3b42]">
    {ALL_DOMAINS.map(domain => {
      const report = domainReports.find(r => r.domain === domain);
      const anomalyCount = report?.anomalies.length || 0;
      const status = report?.status || 'PENDING';
      const isHealthy = status === 'SUCCESS' && anomalyCount === 0;
      return (
        <MetricCard
          key={domain}
          title={DOMAIN_LABELS[domain]}
          value={isHealthy ? 'Healthy' : `${anomalyCount} issues`}
          trendValue={status === 'RUNNING' ? 'Scanning...' : status}
          trendDirection={isHealthy ? 'down' : anomalyCount > 0 ? 'up' : 'neutral'}
          trendType={isHealthy ? 'good' : anomalyCount > 0 ? 'bad' : 'neutral'}
          sparklineData={[anomalyCount, anomalyCount]}
        />
      );
    })}
  </div>
)}
```

**Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 5: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
git commit -m "feat(cluster): add domain health MetricCard ribbon"
```

---

### Task 5: Final TypeScript Verification

**Files:**
- All modified Cluster Diagnostic files

**Step 1: Full TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 2: Verify color consistency**

Grep for `#13b6ec` in cluster components — should be 0 results:
```bash
grep -r "13b6ec" frontend/src/components/ClusterDiagnostic/
```

**Step 3: Verify app starts**

Run: `cd frontend && npm run dev`
Expected: Vite dev server starts without errors

**Step 4: Commit if cleanup needed**

---

## Execution Order

```
Task 1: Color consistency fix    (#13b6ec → #07b6d5 across 8 files)
Task 2: Skeleton loading         (ClusterWarRoom.tsx)
Task 3: StatusBadge in header    (ClusterHeader.tsx)
Task 4: Domain MetricCards       (ClusterWarRoom.tsx)
Task 5: Final verification       (all files — tsc + grep)
```

Task 1 touches 8 files but is a simple find-replace.
Tasks 2 and 4 both modify ClusterWarRoom.tsx — must be sequential.
Task 3 modifies ClusterHeader.tsx — independent of Tasks 2/4.

Recommended order: 1 → (2 + 3 parallel) → 4 → 5
