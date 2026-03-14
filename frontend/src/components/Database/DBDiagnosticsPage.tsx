/**
 * DBDiagnosticsPage — Unified DB Diagnostics page merging session list + DatabaseWarRoom.
 * Left panel: session list filtered to database_diagnostics capability.
 * Right panel: DatabaseWarRoom investigation board for the selected session.
 * Inline "New Diagnostic" form using DatabaseDiagnosticsFields.
 */
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { V4Session, TaskEvent, DiagnosticPhase, DatabaseDiagnosticsForm } from '../../types';
import { listSessionsV4, startSessionV4, getSessionStatus, getSessionEvents } from '../../services/api';
import DatabaseWarRoom from '../Investigation/DatabaseWarRoom';
import DatabaseDiagnosticsFields from '../ActionCenter/forms/DatabaseDiagnosticsFields';
import { useToast } from '../Toast/ToastContext';

/* ------------------------------------------------------------------ */
/*  Inline "New Diagnostic" form wrapper                              */
/* ------------------------------------------------------------------ */
function NewDiagnosticForm({
  onSubmit,
  onCancel,
  submitting,
}: {
  onSubmit: (data: DatabaseDiagnosticsForm) => void;
  onCancel: () => void;
  submitting: boolean;
}) {
  const [formData, setFormData] = useState<DatabaseDiagnosticsForm>({
    capability: 'database_diagnostics',
    profile_id: '',
    time_window: '1h',
    focus: ['queries', 'connections', 'schema'],
    database_type: 'postgres',
    sampling_mode: 'standard',
    include_explain_plans: false,
  });

  return (
    <div className="border border-duck-border rounded-xl bg-duck-panel/60 p-4 space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="material-symbols-outlined text-amber-400 text-base">add_circle</span>
        <h3 className="text-xs font-display font-bold text-white uppercase tracking-wider">New Diagnostic</h3>
      </div>

      <p className="text-[11px] text-slate-400 leading-relaxed mb-3">
        Read-only diagnostic scan using pg_stat views. No data is modified. Typical scan: 30–60 seconds.
      </p>

      <DatabaseDiagnosticsFields
        data={formData}
        onChange={(updated) => setFormData(updated)}
      />

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => onSubmit(formData)}
          disabled={submitting || !formData.profile_id}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-display font-bold bg-duck-accent text-duck-bg rounded-lg hover:brightness-110 disabled:opacity-50 transition-all"
        >
          {submitting ? (
            <>
              <span className="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
              Starting...
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-[14px]">play_arrow</span>
              Start Diagnostic
            </>
          )}
        </button>
        <button
          onClick={onCancel}
          className="text-xs text-slate-400 hover:text-white transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Status dot color helper                                           */
/* ------------------------------------------------------------------ */
function statusDotClass(status: string): string {
  switch (status) {
    case 'complete':
      return 'bg-emerald-400';
    case 'error':
      return 'bg-red-400';
    case 'investigating':
    case 'analyzing':
      return 'bg-amber-400 animate-pulse';
    default:
      return 'bg-slate-500';
  }
}

/* ------------------------------------------------------------------ */
/*  Main page component                                               */
/* ------------------------------------------------------------------ */
const DBDiagnosticsPage: React.FC = () => {
  const { addToast } = useToast();
  const queryClient = useQueryClient();

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  /* ---- Session list ---- */
  const { data: allSessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10_000,
  });

  const dbSessions = allSessions
    .filter((s) => s.capability === 'database_diagnostics')
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  const selectedSession = dbSessions.find((s) => s.session_id === selectedSessionId) ?? null;

  /* ---- Poll events + status for selected session ---- */
  const { data: events = [] } = useQuery({
    queryKey: ['db-session-events', selectedSessionId],
    queryFn: () => (selectedSessionId ? getSessionEvents(selectedSessionId) : Promise.resolve([])),
    enabled: !!selectedSessionId,
    refetchInterval: 3_000,
  });

  const { data: statusData } = useQuery({
    queryKey: ['db-session-status', selectedSessionId],
    queryFn: () => (selectedSessionId ? getSessionStatus(selectedSessionId) : Promise.resolve(null)),
    enabled: !!selectedSessionId,
    refetchInterval: 3_000,
  });

  const phase: DiagnosticPhase | null = statusData?.phase ?? selectedSession?.status ?? null;
  const confidence: number = statusData?.confidence ?? selectedSession?.confidence ?? 0;

  /* ---- Create new diagnostic ---- */
  const handleNewDiagnostic = useCallback(
    async (formData: DatabaseDiagnosticsForm) => {
      // Check for running session against same profile
      const running = dbSessions.find(s =>
        !['complete', 'diagnosis_complete', 'error', 'cancelled'].includes(s.status)
      );
      if (running) {
        addToast('warning', `A diagnostic is already running (${running.incident_id || running.session_id.slice(0, 8)}). Wait for completion or cancel it first.`);
        return;
      }

      setSubmitting(true);
      try {
        // Resolve profile name for readable session name
        let profileName = formData.profile_id.slice(0, 8);
        try {
          const profiles = await import('../../services/api').then(m => m.fetchDBProfiles());
          const match = profiles.find((p: { id: string; name: string }) => p.id === formData.profile_id);
          if (match) profileName = match.name;
        } catch { /* use truncated ID */ }

        const session = await startSessionV4({
          service_name: profileName,
          time_window: formData.time_window,
          capability: 'database_diagnostics',
          profile_id: formData.profile_id,
          extra: {
            profile_id: formData.profile_id,
            focus: formData.focus,
            database_type: formData.database_type,
            sampling_mode: formData.sampling_mode,
            include_explain_plans: formData.include_explain_plans,
            parent_session_id: formData.parent_session_id,
            table_filter: formData.table_filter,
            time_window: formData.time_window,
          },
        });
        addToast('success', 'Diagnostic session started');
        setSelectedSessionId(session.session_id);
        setShowForm(false);
        queryClient.invalidateQueries({ queryKey: ['live-sessions'] });
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Failed to start diagnostic';
        addToast('error', msg);
      } finally {
        setSubmitting(false);
      }
    },
    [addToast, queryClient, dbSessions],
  );

  /* No auto-select — user picks from session list or starts new */

  /* ---- Render ---- */
  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-duck-border bg-duck-panel/40 shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="material-symbols-outlined text-violet-400 text-xl">database</span>
          <h1 className="text-sm font-display font-bold text-white">DB Diagnostics</h1>
          <span className="text-[10px] text-slate-500 font-mono">{dbSessions.length} sessions</span>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-display font-bold rounded-lg border transition-all bg-duck-accent/10 border-duck-accent/40 text-duck-accent hover:bg-duck-accent/20"
        >
          <span className="material-symbols-outlined text-[14px]">{showForm ? 'close' : 'add'}</span>
          {showForm ? 'Cancel' : 'New Diagnostic'}
        </button>
      </div>

      {/* When form is open: full-page form only */}
      {showForm ? (
        <div className="flex-1 overflow-y-auto px-8 py-6">
          <div className="max-w-xl mx-auto">
            <NewDiagnosticForm
              onSubmit={handleNewDiagnostic}
              onCancel={() => setShowForm(false)}
              submitting={submitting}
            />
          </div>
        </div>
      ) : selectedSession ? (
        /* Active investigation — full-width board, no session list */
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* Back bar */}
          <div className="flex items-center gap-2 px-4 py-1.5 border-b border-duck-border/50 bg-duck-panel/20 shrink-0">
            <button
              onClick={() => setSelectedSessionId(null)}
              className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-white transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
            >
              <span className="material-symbols-outlined text-[14px]">arrow_back</span>
              All Sessions
            </button>
            <span className="text-[10px] text-slate-600">/ {selectedSession.service_name}</span>
          </div>
          <div className="flex-1 overflow-hidden">
            <DatabaseWarRoom
              session={selectedSession}
              events={events}
              wsConnected={false}
              phase={phase}
              confidence={confidence}
            />
          </div>
        </div>
      ) : (
        /* Session list — no active investigation */
        <div className="flex-1 overflow-y-auto">
          {dbSessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center px-8">
              <span className="material-symbols-outlined text-4xl text-slate-600 mb-3" aria-hidden="true">database</span>
              <p className="text-sm text-slate-300 font-display font-bold mb-3">No diagnostics yet</p>
              <button
                onClick={() => setShowForm(true)}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-display font-bold bg-duck-accent text-duck-bg rounded-lg hover:brightness-110 transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              >
                <span className="material-symbols-outlined text-[14px]" aria-hidden="true">add</span>
                Start New Diagnostic
              </button>
            </div>
          ) : (
            <div className="p-4 space-y-1">
              {dbSessions.map((s) => {
                const isRunning = !['complete', 'diagnosis_complete', 'error'].includes(s.status);
                const createdDate = new Date(s.created_at);
                const dateStr = createdDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                const timeStr = createdDate.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

                return (
                  <button
                    key={s.session_id}
                    onClick={() => setSelectedSessionId(s.session_id)}
                    className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-duck-surface/30 transition-colors text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotClass(s.status)}`} aria-hidden="true" />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-display font-bold text-white block truncate">{s.service_name}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-duck-accent font-mono">{s.incident_id || s.session_id.slice(0, 8)}</span>
                        <span className="text-[10px] text-slate-500">{dateStr} {timeStr}</span>
                      </div>
                    </div>
                    {isRunning && (
                      <span className="material-symbols-outlined text-[14px] text-amber-400 animate-spin shrink-0" aria-hidden="true">progress_activity</span>
                    )}
                    {!isRunning && s.status === 'complete' && (
                      <span className="text-[10px] text-emerald-400 shrink-0">✓ Complete</span>
                    )}
                    {s.status === 'error' && (
                      <span className="text-[10px] text-red-400 shrink-0">✗ Error</span>
                    )}
                    <span className="material-symbols-outlined text-slate-600 text-[16px] shrink-0">chevron_right</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DBDiagnosticsPage;
