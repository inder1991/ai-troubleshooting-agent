/**
 * DBDiagnostics — Start diagnostics, view run history, and inspect findings.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchDBProfiles,
  startDBDiagnostic,
  fetchDBDiagnosticRun,
  fetchDBDiagnosticHistory,
} from '../../services/api';

interface Finding {
  finding_id: string;
  category: string;
  severity: string;
  confidence: number;
  title: string;
  detail: string;
  evidence?: string[];
  recommendation?: string;
}

interface DiagnosticRun {
  run_id: string;
  profile_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  findings: Finding[];
  summary?: string;
}

interface Profile {
  id: string;
  name: string;
  engine: string;
}

const severityColor: Record<string, string> = {
  critical: 'bg-wr-severity-high/20 text-red-400 border-wr-severity-high/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-wr-severity-medium/20 text-amber-400 border-wr-severity-medium/30',
  low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  info: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
};

const severityIcon: Record<string, string> = {
  critical: 'error', high: 'warning', medium: 'info', low: 'info', info: 'info',
};

const DBDiagnostics: React.FC = () => {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [runs, setRuns] = useState<DiagnosticRun[]>([]);
  const [activeRun, setActiveRun] = useState<DiagnosticRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [polling, setPolling] = useState(false);

  // Load profiles
  useEffect(() => {
    fetchDBProfiles().then((list: Profile[]) => {
      setProfiles(list);
      if (list.length > 0 && !selectedProfileId) {
        setSelectedProfileId(list[0].id);
      }
    }).catch(() => setProfiles([]));
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Load history when profile changes
  const loadHistory = useCallback(async () => {
    if (!selectedProfileId) return;
    setLoading(true);
    try {
      setRuns(await fetchDBDiagnosticHistory(selectedProfileId));
    } catch {
      setRuns([]);
    } finally {
      setLoading(false);
    }
  }, [selectedProfileId]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  // Start diagnostic
  const handleStart = async () => {
    if (!selectedProfileId) return;
    setStarting(true);
    try {
      const run = await startDBDiagnostic(selectedProfileId);
      setActiveRun(run);
      setPolling(true);

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const updated = await fetchDBDiagnosticRun(run.run_id);
          setActiveRun(updated);
          if (updated.status === 'completed' || updated.status === 'failed') {
            clearInterval(pollInterval);
            setPolling(false);
            await loadHistory();
          }
        } catch {
          clearInterval(pollInterval);
          setPolling(false);
        }
      }, 2000);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to start diagnostic');
    } finally {
      setStarting(false);
    }
  };

  const handleViewRun = async (runId: string) => {
    try {
      const run = await fetchDBDiagnosticRun(runId);
      setActiveRun(run);
    } catch {
      // ignore
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header with profile selector + start button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-slate-100">Diagnostics</h2>
          <select
            value={selectedProfileId}
            onChange={(e) => { setSelectedProfileId(e.target.value); setActiveRun(null); }}
            className="px-3 py-1.5 rounded-lg bg-wr-surface border border-wr-border-strong text-sm text-slate-100 focus:border-amber-500 outline-none"
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.engine})</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleStart}
          disabled={starting || polling || !selectedProfileId}
          className="flex items-center gap-1.5 px-4 py-2 text-sm bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          <span className={`material-symbols-outlined text-[16px] ${polling ? 'animate-spin' : ''}`}>
            {polling ? 'progress_activity' : 'play_arrow'}
          </span>
          {polling ? 'Running...' : 'Start Diagnostic'}
        </button>
      </div>

      {/* Active run results */}
      {activeRun && (
        <div className="rounded-xl border border-wr-border-strong/50 bg-[#0d2328] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`material-symbols-outlined text-lg ${
                activeRun.status === 'completed' ? 'text-emerald-400'
                : activeRun.status === 'failed' ? 'text-red-400'
                : 'text-amber-400 animate-pulse'
              }`}>
                {activeRun.status === 'completed' ? 'task_alt' : activeRun.status === 'failed' ? 'error' : 'pending'}
              </span>
              <div>
                <p className="text-sm font-medium text-slate-100">Run {activeRun.run_id.slice(0, 8)}</p>
                <p className="text-xs text-slate-400">
                  {activeRun.status} • {new Date(activeRun.started_at).toLocaleString()}
                </p>
              </div>
            </div>
            {activeRun.status === 'completed' && (
              <span className="text-xs text-slate-400">
                {activeRun.findings.length} finding(s)
              </span>
            )}
          </div>

          {activeRun.summary && (
            <p className="text-sm text-slate-300 bg-wr-surface/50 rounded-lg px-3 py-2">{activeRun.summary}</p>
          )}

          {/* Findings */}
          {activeRun.findings.length > 0 && (
            <div className="space-y-2">
              {activeRun.findings.map((f) => (
                <div key={f.finding_id} className={`rounded-lg border p-3 space-y-1.5 ${severityColor[f.severity] || severityColor.info}`}>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[16px]">{severityIcon[f.severity] || 'info'}</span>
                    <span className="text-sm font-medium">{f.title}</span>
                    <span className="text-xs opacity-60 ml-auto">{f.category} • {(f.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <p className="text-xs opacity-80">{f.detail}</p>
                  {f.evidence && f.evidence.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {f.evidence.map((e, i) => (
                        <span key={i} className="text-xs bg-black/20 rounded px-1.5 py-0.5">{e}</span>
                      ))}
                    </div>
                  )}
                  {f.recommendation && (
                    <p className="text-xs opacity-70 italic">{f.recommendation}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Run history */}
      <div>
        <h3 className="text-sm font-medium text-slate-400 mb-2">History</h3>
        {loading ? (
          <div className="text-center py-8 text-slate-400">
            <span className="material-symbols-outlined animate-spin">progress_activity</span>
          </div>
        ) : runs.length === 0 ? (
          <p className="text-sm text-slate-400 py-4 text-center">No diagnostic runs yet for this profile.</p>
        ) : (
          <div className="space-y-1">
            {runs.map((r) => (
              <button
                key={r.run_id}
                onClick={() => handleViewRun(r.run_id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-left transition-colors ${
                  activeRun?.run_id === r.run_id ? 'bg-wr-severity-medium/10 border border-wr-severity-medium/30' : 'hover:bg-wr-surface/50 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${
                    r.status === 'completed' ? 'bg-emerald-400' : r.status === 'failed' ? 'bg-red-400' : 'bg-amber-400'
                  }`} />
                  <span className="text-sm text-slate-300">{r.run_id.slice(0, 8)}</span>
                  <span className="text-xs text-slate-400">{new Date(r.started_at).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">{r.findings?.length || 0} findings</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    r.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' : r.status === 'failed' ? 'bg-wr-severity-high/20 text-red-400' : 'bg-wr-severity-medium/20 text-amber-400'
                  }`}>{r.status}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DBDiagnostics;
