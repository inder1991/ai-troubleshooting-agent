# DB Investigation Board — Critique Fixes Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 10 issues from the design critique: left-border overuse, completion ceremony, right column restructure, session list context, form onboarding, severity constants, event dedup, timer overflow, empty state, HealthStrip wrapping.

**Architecture:** Pure frontend changes across 8 files. No backend changes needed.

**Tech Stack:** React, TypeScript, Tailwind CSS, Framer Motion

---

## Task 1: Consolidate severity constants + fix duplication

**Files:**
- Modify: `frontend/src/components/Investigation/db-board/constants.ts`
- Modify: `frontend/src/components/Investigation/db-board/FixRecommendations.tsx`
- Modify: `frontend/src/components/Investigation/db-board/RootCauseVerdict.tsx`
- Modify: `frontend/src/components/Investigation/db-viz/SlowQueryTimeline.tsx`

**What:** Move all severity color maps to `constants.ts`. Remove duplicate `SEV_STYLES`/`SEV_STYLE`/`severityColor` objects from individual components. Import from constants instead.

Add to constants.ts:
```ts
export const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-400',
  high: 'bg-orange-400',
  medium: 'bg-amber-400',
  low: 'bg-emerald-400',
};

export const SEV_BADGE: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-400 border-red-500/30',
  high: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  medium: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

export const SEV_LEFT_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  high: 'border-l-orange-500',
  medium: 'border-l-amber-500',
  low: 'border-l-emerald-500',
};
```

Remove local severity maps from FixRecommendations, RootCauseVerdict, SlowQueryTimeline. Import from constants.

Also add shared duration formatter:
```ts
export function formatDuration(sec: number): string {
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}
```

---

## Task 2: Fix left-border accent overuse — diversify visual patterns

**Files:**
- Modify: `frontend/src/components/Investigation/db-board/RootCauseVerdict.tsx`
- Modify: `frontend/src/components/Investigation/db-board/FixRecommendations.tsx`

**What:**

**RootCauseVerdict:** Replace left-border pattern with full-width amber background strip:
- Remove: `border-l-[3px] ${borderColor} bg-duck-surface/50 rounded-r-lg`
- Replace with: `bg-duck-accent/5 border border-duck-accent/20 rounded-lg`
- Add severity dot before "Root Cause Identified" text instead of border color

**FixRecommendations:** Replace left-border with numbered list + severity dot:
- Remove: `border-l-2 ${sev.border}` from each fix item
- Replace with: priority number + dot: `<span className="text-[11px] font-display font-bold text-slate-500 w-5 shrink-0">{fix.priority}.</span>`
- Keep severity badge inline

---

## Task 3: Add completion ceremony animation

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:** When `phase === 'complete'`, add visual shift:

1. Add a `isComplete` computed boolean
2. When complete, add a brief amber glow border on the entire board container (CSS animation, fades after 2s)
3. The center column panels get `opacity-80` class when complete (they're reference, not the focus anymore)
4. RootCauseVerdict gets a slightly delayed entrance (200ms after phase change)

Add to the root div:
```tsx
className={`flex flex-col h-full overflow-hidden bg-duck-bg transition-all duration-500 ${
  phase === 'complete' ? 'ring-1 ring-duck-accent/30' : ''
}`}
```

Add to the center column panels grid:
```tsx
className={`grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-x-4 gap-y-5 ${
  phase === 'complete' ? 'opacity-70' : ''
}`}
```

---

## Task 4: Restructure right column after completion

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:** When investigation is complete, reorder the right column:

1. Agent Status: collapse to single line `"All 4 agents complete ✓"` instead of showing each agent
2. Fix Recommendations: move to TOP of right column (above replication)
3. Replication + HealthStrip: stay but take less vertical space

Change the right column to conditionally reorder:
```tsx
{/* RIGHT: The Map */}
<div className="lg:col-span-4 border-l border-duck-border overflow-y-auto p-4 custom-scrollbar">
  {/* After completion: Fixes first */}
  {phase === 'complete' && fixes.length > 0 && (
    <div className="mb-5">
      <FixRecommendations fixes={fixes} onExportReport={dossier ? handleExportReport : undefined} />
    </div>
  )}

  {/* Agent Status: compact when complete */}
  <div className="mb-4">
    {phase === 'complete' ? (
      <div className="flex items-center gap-2 py-1">
        <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
        <span className="text-[10px] font-display font-bold text-emerald-400">All agents complete</span>
      </div>
    ) : (
      /* ... existing full agent status list ... */
    )}
  </div>

  {/* Replication Topology */}
  ...
  {/* Health Strip */}
  ...
</div>
```

Remove the old completion block at the bottom of the right column.

---

## Task 5: Add context to session list rows

**Files:**
- Modify: `frontend/src/components/Database/DBDiagnosticsPage.tsx`

**What:** Each session row should show finding count + top severity. The session object from `listSessionsV4` may not have this data, but we can derive it from the session's `confidence` and `status`.

For completed sessions, fetch a lightweight summary. Or simpler: use the confidence as a proxy:
- confidence >= 80: show "✓" in emerald
- confidence >= 50: show "⚠" in amber
- confidence > 0 but < 50: show "!" in red
- confidence === 0 and running: show spinner

Update the session row to show:
```tsx
<div className="flex items-center gap-2">
  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusDotClass(s.status)}`} />
  <span className="text-xs font-medium text-white truncate">{s.service_name}</span>
  {s.status === 'complete' && (
    <span className="text-[9px] text-emerald-400 ml-auto shrink-0">✓</span>
  )}
  {s.status === 'error' && (
    <span className="text-[9px] text-red-400 ml-auto shrink-0">!</span>
  )}
</div>
```

---

## Task 6: Add form onboarding text

**Files:**
- Modify: `frontend/src/components/Database/DBDiagnosticsPage.tsx`

**What:** Add a brief safety message above the form in the `NewDiagnosticForm` component:

Before the DatabaseDiagnosticsFields, add:
```tsx
<p className="text-[11px] text-slate-400 leading-relaxed mb-3">
  Runs a read-only diagnostic scan using pg_stat views. No data is modified. Typical scan completes in 30–60 seconds.
</p>
```

---

## Task 7: Fix event deduplication + timer overflow

**Files:**
- Modify: `frontend/src/components/Investigation/DatabaseWarRoom.tsx`

**What:**

**Event dedup:** Replace the naive `polledEvents.length > events.length` merge with timestamp-based dedup:
```tsx
const mergedEvents = useMemo(() => {
  const map = new Map<string, TaskEvent>();
  for (const ev of events) {
    const key = `${ev.agent_name}-${ev.event_type}-${ev.message}`;
    map.set(key, ev);
  }
  for (const ev of polledEvents) {
    const key = `${ev.agent_name}-${ev.event_type}-${ev.message}`;
    if (!map.has(key)) map.set(key, ev);
  }
  return Array.from(map.values());
}, [events, polledEvents]);
```

**Timer overflow:** Import `formatDuration` from constants instead of inline formatting. Use it in the header and CaseFile.

---

## Task 8: Fix empty state + HealthStrip wrapping

**Files:**
- Modify: `frontend/src/components/Database/DBDiagnosticsPage.tsx`
- Modify: `frontend/src/components/Investigation/db-board/HealthStrip.tsx`

**What:**

**Empty state:** Replace the passive text with an actionable button:
```tsx
{/* When no session selected */}
<div className="flex flex-col items-center justify-center h-full text-center px-8">
  <span className="material-symbols-outlined text-4xl text-slate-600 mb-3">database</span>
  <p className="text-sm text-slate-300 font-display font-bold mb-3">No diagnostic selected</p>
  <button
    onClick={() => setShowForm(true)}
    className="flex items-center gap-1.5 px-4 py-2 text-xs font-display font-bold bg-duck-accent text-duck-bg rounded-lg hover:brightness-110 transition-all"
  >
    <span className="material-symbols-outlined text-[14px]">add</span>
    Start New Diagnostic
  </button>
</div>
```

**HealthStrip wrapping:** Change from `flex flex-wrap gap-2 md:gap-4` to `grid grid-cols-2 gap-2` so it always shows as 2x2 on narrow widths:
```tsx
<div className="grid grid-cols-2 md:flex md:items-center md:gap-4 gap-2 px-3 py-2 bg-duck-surface/30 rounded-lg">
```
