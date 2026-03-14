# DB Diagnostics Merge — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge the two DB diagnostics pages (sidebar DBDiagnostics + New Mission DatabaseWarRoom) into one unified list+detail page accessible from the sidebar.

**Architecture:** Replace `DBDiagnostics.tsx` with a new `DBDiagnosticsPage.tsx` that has a session list on the left (past + active DB sessions) and the `DatabaseWarRoom` Investigation Board on the right. "New Mission → DB Diagnostics" redirects to this page and auto-opens the form. The old standalone DBDiagnostics runner is removed.

**Tech Stack:** React, TypeScript, Tailwind CSS, TanStack Query

---

## Task 1: Create DBDiagnosticsPage (list + detail layout)

**Files:**
- Create: `frontend/src/components/Database/DBDiagnosticsPage.tsx`

**Step 1: Create the unified page**

This component manages:
- Left panel: session list (DB sessions only, from `listSessionsV4` filtered by capability)
- Right panel: `DatabaseWarRoom` for the selected session
- "New Diagnostic" button that shows inline form
- Form submission creates a V4 session, then selects it

```tsx
import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session, TaskEvent, DiagnosticPhase, DatabaseDiagnosticsForm } from '../../types';
import { listSessionsV4, startSessionV4, getSessionStatus, getSessionEvents } from '../../services/api';
import DatabaseWarRoom from '../Investigation/DatabaseWarRoom';
import DatabaseDiagnosticsFields from '../ActionCenter/forms/DatabaseDiagnosticsFields';
import { useToast } from '../Toast/ToastContext';

const COMPLETED = ['complete', 'diagnosis_complete', 'error'];

const DBDiagnosticsPage: React.FC = () => {
  const { addToast } = useToast();
  const [selectedSession, setSelectedSession] = useState<V4Session | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Session events for the selected session (polled)
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [phase, setPhase] = useState<DiagnosticPhase | null>(null);
  const [confidence, setConfidence] = useState(0);

  // Fetch all sessions, filter to DB only
  const { data: allSessions = [], refetch } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 5000,
    staleTime: 3000,
  });

  const dbSessions = useMemo(
    () => allSessions.filter((s) => s.capability === 'database_diagnostics').sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    ),
    [allSessions]
  );

  // Poll events + status for selected session
  useEffect(() => {
    if (!selectedSession) { setEvents([]); setPhase(null); setConfidence(0); return; }
    let cancelled = false;
    const poll = async () => {
      try {
        const [evts, status] = await Promise.all([
          getSessionEvents(selectedSession.session_id),
          getSessionStatus(selectedSession.session_id),
        ]);
        if (cancelled) return;
        if (evts.length > 0) setEvents(evts);
        setPhase(status.phase as DiagnosticPhase);
        setConfidence(status.confidence ?? 0);
      } catch { /* silent */ }
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [selectedSession?.session_id]);

  // Auto-select first session on load
  useEffect(() => {
    if (!selectedSession && dbSessions.length > 0) {
      setSelectedSession(dbSessions[0]);
    }
  }, [dbSessions, selectedSession]);

  // Handle form submission
  const handleSubmit = useCallback(async (data: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      const dbData = data as unknown as DatabaseDiagnosticsForm;
      const session = await startSessionV4({
        service_name: `db-${dbData.profile_id}`,
        time_window: dbData.time_window,
        capability: 'database_diagnostics',
        profile_id: dbData.profile_id,
        extra: {
          profile_id: dbData.profile_id,
          focus: dbData.focus,
          database_type: dbData.database_type,
          sampling_mode: dbData.sampling_mode,
          include_explain_plans: dbData.include_explain_plans,
          parent_session_id: dbData.parent_session_id,
          table_filter: dbData.table_filter,
          time_window: dbData.time_window,
        },
      });
      const dbSession: V4Session = {
        ...session,
        service_name: session.service_name || `db-${dbData.profile_id}`,
        capability: 'database_diagnostics',
      };
      setSelectedSession(dbSession);
      setShowForm(false);
      refetch();
      addToast('success', 'Database diagnostic started');
    } catch (err) {
      addToast('error', err instanceof Error ? err.message : 'Failed to start diagnostic');
    } finally {
      setSubmitting(false);
    }
  }, [refetch, addToast]);

  const isComplete = selectedSession ? COMPLETED.includes(selectedSession.status) : false;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-duck-bg">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-duck-border shrink-0">
        <h1 className="text-base font-display font-bold text-white">Database Diagnostics</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-display font-bold bg-duck-accent text-duck-bg rounded-lg hover:brightness-110 transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
        >
          <span className="material-symbols-outlined text-[16px]" aria-hidden="true">add</span>
          New Diagnostic
        </button>
      </div>

      {/* Inline form (collapsible) */}
      {showForm && (
        <div className="border-b border-duck-border px-6 py-4 bg-duck-panel/50">
          <DatabaseDiagnosticsFields
            value={{ capability: 'database_diagnostics', profile_id: '', time_window: '1h', focus: ['queries', 'connections', 'schema'], database_type: 'postgres', sampling_mode: 'standard', include_explain_plans: false }}
            onChange={() => {}}
            onSubmit={handleSubmit}
            submitting={submitting}
          />
        </div>
      )}

      {/* List + Detail */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Session List */}
        <div className="w-[240px] shrink-0 border-r border-duck-border overflow-y-auto custom-scrollbar">
          {dbSessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <span className="material-symbols-outlined text-3xl text-slate-600 mb-2" aria-hidden="true">database</span>
              <p className="text-xs text-slate-400">No DB sessions yet</p>
              <p className="text-[10px] text-slate-500 mt-1">Click "New Diagnostic" to start</p>
            </div>
          ) : (
            <div className="py-1">
              {dbSessions.map((s) => {
                const isSelected = selectedSession?.session_id === s.session_id;
                const isRunning = !COMPLETED.includes(s.status);
                const time = new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const date = new Date(s.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' });

                return (
                  <button
                    key={s.session_id}
                    onClick={() => setSelectedSession(s)}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-left transition-colors ${
                      isSelected
                        ? 'bg-duck-accent/10 border-l-2 border-duck-accent'
                        : 'hover:bg-duck-surface/30 border-l-2 border-transparent'
                    }`}
                    aria-selected={isSelected}
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${
                      s.status === 'error' ? 'bg-red-400' :
                      isRunning ? 'bg-amber-400 animate-pulse' :
                      'bg-emerald-400'
                    }`} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] text-slate-300 truncate font-display font-bold">{s.service_name}</p>
                      <p className="text-[10px] text-slate-500">{date} {time}</p>
                    </div>
                    {isRunning && (
                      <span className="material-symbols-outlined text-[12px] text-amber-400 animate-spin shrink-0" aria-hidden="true">progress_activity</span>
                    )}
                    {!isRunning && s.confidence > 0 && (
                      <span className="text-[10px] text-slate-400 shrink-0">{s.confidence}%</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Right: Investigation Board */}
        <div className="flex-1 overflow-hidden">
          {selectedSession ? (
            <DatabaseWarRoom
              session={selectedSession}
              events={events}
              wsConnected={true}
              phase={phase}
              confidence={confidence}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <span className="material-symbols-outlined text-4xl text-slate-600 mb-3" aria-hidden="true">database</span>
              <p className="text-sm text-slate-400 font-display">Select a session or start a new diagnostic</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DBDiagnosticsPage;
```

**Step 2: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**
```bash
git add frontend/src/components/Database/DBDiagnosticsPage.tsx
git commit -m "feat(db): add unified DBDiagnosticsPage with list+detail layout"
```

---

## Task 2: Check DatabaseDiagnosticsFields accepts onSubmit prop

**Files:**
- Read: `frontend/src/components/ActionCenter/forms/DatabaseDiagnosticsFields.tsx`

**Step 1: Check the component interface**

The `DatabaseDiagnosticsFields` component may not accept `onSubmit` and `submitting` props — it was designed for the CapabilityForm wrapper. If it doesn't have these props, we need to add a submit button wrapper in DBDiagnosticsPage instead.

Read the file and check its props. If `onSubmit` is not part of its interface, modify DBDiagnosticsPage to track form state and add its own submit button:

Replace the `DatabaseDiagnosticsFields` usage with:
```tsx
{showForm && (
  <div className="border-b border-duck-border px-6 py-4 bg-duck-panel/50">
    <DatabaseDiagnosticsFieldsWrapper onSubmit={handleSubmit} submitting={submitting} onCancel={() => setShowForm(false)} />
  </div>
)}
```

Where `DatabaseDiagnosticsFieldsWrapper` is a small local component that manages the form state and renders the fields + a submit button.

**Step 2: Commit any fixes**

---

## Task 3: Wire into App.tsx routing

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Replace DBDiagnostics import with DBDiagnosticsPage**

Find and replace:
```tsx
import DBDiagnostics from './components/Database/DBDiagnostics';
```
With:
```tsx
import DBDiagnosticsPage from './components/Database/DBDiagnosticsPage';
```

**Step 2: Replace the render**

Find:
```tsx
{viewState === 'db-diagnostics' && <DBDiagnostics />}
```
Replace with:
```tsx
{viewState === 'db-diagnostics' && <DBDiagnosticsPage />}
```

**Step 3: Redirect "New Mission → DB Diagnostics" to the same page**

Find the `database_diagnostics` handler in `handleFormSubmit` (around line 393). Change it to navigate to the DB diagnostics page instead of creating a session and going to investigation view:

Replace the entire `} else if (data.capability === 'database_diagnostics') {` block with:
```tsx
} else if (data.capability === 'database_diagnostics') {
  // Redirect to unified DB Diagnostics page — it handles session creation
  setViewState('db-diagnostics');
```

**Step 4: Verify TypeScript compiles**
```bash
cd frontend && npx tsc --noEmit
```

**Step 5: Commit**
```bash
git add frontend/src/App.tsx
git commit -m "feat(db): route both sidebar and New Mission to unified DBDiagnosticsPage"
```

---

## Task 4: Verify end-to-end flow

**Step 1: Test sidebar path**
1. Click sidebar → Database → Diagnostics
2. Should see DBDiagnosticsPage with session list on left
3. Click "+ New Diagnostic" → form appears
4. Select profile, click submit → session created, Investigation Board loads on right

**Step 2: Test New Mission path**
1. Click "New Mission" → DB Diagnostics capability card
2. Should navigate to db-diagnostics view (same page)
3. Form should be ready to fill

**Step 3: Test session switching**
1. With multiple DB sessions, click different sessions in left list
2. Right panel should switch to show that session's Investigation Board

**Step 4: Final commit**
```bash
git commit -m "feat(db): unified DB diagnostics — one page, list+detail"
```
