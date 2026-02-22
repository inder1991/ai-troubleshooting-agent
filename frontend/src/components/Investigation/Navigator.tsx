import React, { useState } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, SuggestedPromQLQuery, TimeSeriesDataPoint } from '../../types';
import { runPromQLQuery } from '../../services/api';
import { Play, Copy, Check } from 'lucide-react';
import ServiceTopologySVG from './topology/ServiceTopologySVG';
import REDMethodStatusBar from './cards/REDMethodStatusBar';
import PromQLRunResult from './cards/PromQLRunResult';

interface NavigatorProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
}

const Navigator: React.FC<NavigatorProps> = ({ findings, status, events }) => {

  const agentStatuses = buildAgentStatuses(status, events);
  const totalTokens = status?.token_usage?.reduce((sum, t) => sum + t.total_tokens, 0) ?? 0;

  return (
    <div className="flex flex-col h-full bg-slate-900/20 overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center gap-2 sticky top-0 z-10 bg-slate-900/90 backdrop-blur">
        <span className="material-symbols-outlined text-slate-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>explore</span>
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Navigator</h2>
      </div>

      <div className="p-4 space-y-5">
        {/* RED Method Status */}
        {findings && (
          <REDMethodStatusBar
            metricAnomalies={findings.metric_anomalies || []}
            correlatedSignals={findings.correlated_signals || []}
          />
        )}

        {/* Service Topology */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Service Topology</h3>
          <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
            <ServiceTopologySVG
              dependencies={findings?.inferred_dependencies || []}
              patientZero={findings?.patient_zero || null}
              blastRadius={findings?.blast_radius || null}
              podStatuses={findings?.pod_statuses || []}
            />
          </div>
        </section>

        {/* Metrics Validation Dock */}
        <MetricsValidationDock queries={findings?.suggested_promql_queries || []} />

        {/* Infrastructure Health */}
        <InfraHealthCards findings={findings} />

        {/* Agent Status Matrix */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Agent Status</h3>
          <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 space-y-2">
            {agentStatuses.map((agent, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold ${
                  agent.code === 'L' ? 'bg-red-500/20 text-red-400' :
                  agent.code === 'M' ? 'bg-cyan-500/20 text-cyan-400' :
                  agent.code === 'K' ? 'bg-orange-500/20 text-orange-400' :
                  agent.code === 'C' ? 'bg-emerald-500/20 text-emerald-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>
                  {agent.code}
                </span>
                <span className="text-[11px] text-slate-300 flex-1">{agent.name}</span>
                <span className={`w-2 h-2 rounded-full ${
                  agent.status === 'active' ? 'bg-cyan-400 animate-pulse' :
                  agent.status === 'complete' ? 'bg-green-500' :
                  agent.status === 'error' ? 'bg-red-500' : 'bg-slate-600'
                }`} />
                {agent.tokens > 0 && (
                  <span className="text-[9px] font-mono text-slate-500">{agent.tokens.toLocaleString()}</span>
                )}
              </div>
            ))}
            {totalTokens > 0 && (
              <div className="border-t border-slate-700 pt-2 flex justify-between">
                <span className="text-[10px] text-slate-500">Total</span>
                <span className="text-[10px] font-mono text-slate-400">{totalTokens.toLocaleString()} tokens</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

// ─── Metrics Validation Dock ──────────────────────────────────────────────

const MetricsValidationDock: React.FC<{ queries: SuggestedPromQLQuery[] }> = ({ queries }) => {
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [runResults, setRunResults] = useState<Record<number, {
    loading: boolean;
    dataPoints: TimeSeriesDataPoint[];
    currentValue: number;
    error?: string;
  }>>({});

  if (queries.length === 0) return null;

  const handleCopy = (query: string, idx: number) => {
    navigator.clipboard.writeText(query).catch(() => {});
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleRun = async (query: string, idx: number) => {
    setRunResults((prev) => ({
      ...prev,
      [idx]: { loading: true, dataPoints: [], currentValue: 0 },
    }));

    const end = Math.floor(Date.now() / 1000).toString();
    const start = (Math.floor(Date.now() / 1000) - 3600).toString(); // last 1h

    const result = await runPromQLQuery(query, start, end, '60s');
    setRunResults((prev) => ({
      ...prev,
      [idx]: {
        loading: false,
        dataPoints: result.data_points,
        currentValue: result.current_value,
        error: result.error,
      },
    }));
  };

  return (
    <section>
      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Metrics Validation</h3>
      <div className="space-y-2">
        {queries.map((q, i) => (
          <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-bold text-cyan-400 uppercase">{q.metric}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleCopy(q.query, i)}
                  className="p-1 rounded hover:bg-slate-700/50 transition-colors"
                  title="Copy query"
                >
                  {copiedIdx === i ? (
                    <Check size={12} className="text-green-400" />
                  ) : (
                    <Copy size={12} className="text-slate-400" />
                  )}
                </button>
                <button
                  onClick={() => handleRun(q.query, i)}
                  disabled={runResults[i]?.loading}
                  className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-colors disabled:opacity-50"
                  title="Execute query"
                >
                  <Play size={10} />
                  Run
                </button>
              </div>
            </div>
            <pre className="text-[10px] font-mono text-slate-300 bg-black/20 rounded p-1.5 overflow-x-auto custom-scrollbar mb-1.5">
              {q.query}
            </pre>
            <p className="text-[9px] text-slate-500">{q.rationale}</p>
            {runResults[i] && (
              <PromQLRunResult
                dataPoints={runResults[i].dataPoints}
                currentValue={runResults[i].currentValue}
                loading={runResults[i].loading}
                error={runResults[i].error}
              />
            )}
          </div>
        ))}
      </div>
    </section>
  );
};

// ─── Infra Health Cards ───────────────────────────────────────────────────

const InfraHealthCards: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const pods = findings?.pod_statuses || [];
  if (pods.length === 0) return null;

  const totalPods = pods.length;
  const restarts = pods.reduce((s, p) => s + p.restart_count, 0);
  const healthy = pods.filter((p) => p.ready).length;
  const oomCount = pods.filter((p) => p.oom_killed).length;
  const crashLoopCount = pods.filter((p) => p.crash_loop).length;
  const healthPct = totalPods > 0 ? Math.round((healthy / totalPods) * 100) : 0;

  return (
    <section>
      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Infrastructure Health</h3>
      <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <div className="text-[10px] text-slate-500">Pods</div>
            <div className="text-lg font-bold font-mono text-white">{healthy}/{totalPods}</div>
          </div>
          <div>
            <div className="text-[10px] text-slate-500">Health</div>
            <div className={`text-lg font-bold font-mono ${healthPct >= 80 ? 'text-green-400' : healthPct >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
              {healthPct}%
            </div>
          </div>
        </div>
        {restarts > 0 && (
          <div className="text-[10px] text-amber-400 mb-1">{restarts} restart{restarts > 1 ? 's' : ''}</div>
        )}
        <div className="flex gap-1.5 flex-wrap">
          {oomCount > 0 && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
              {oomCount} OOM
            </span>
          )}
          {crashLoopCount > 0 && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">
              {crashLoopCount} CrashLoop
            </span>
          )}
        </div>
      </div>
    </section>
  );
};

// ─── Agent Status Builder ─────────────────────────────────────────────────

interface AgentStatusInfo {
  name: string;
  code: string;
  status: 'pending' | 'active' | 'complete' | 'error';
  tokens: number;
}

function buildAgentStatuses(status: V4SessionStatus | null, events: TaskEvent[]): AgentStatusInfo[] {
  const agents = [
    { key: 'log_agent', name: 'Log Analyzer', code: 'L' },
    { key: 'metrics_agent', name: 'Metric Scanner', code: 'M' },
    { key: 'k8s_agent', name: 'K8s Probe', code: 'K' },
    { key: 'tracing_agent', name: 'Trace Walker', code: 'T' },
    { key: 'code_agent', name: 'Code Navigator', code: 'N' },
    { key: 'change_agent', name: 'Change Intel', code: 'C' },
  ];

  const started = new Set<string>();
  const completed = new Set<string>();
  const errored = new Set<string>();
  events.forEach((e) => {
    if (e.event_type === 'started') started.add(e.agent_name);
    if (e.event_type === 'summary' || e.event_type === 'success') completed.add(e.agent_name);
    if (e.event_type === 'error') errored.add(e.agent_name);
  });

  const tokenMap: Record<string, number> = {};
  status?.token_usage?.forEach((t) => { tokenMap[t.agent_name] = t.total_tokens; });

  return agents.map((a) => ({
    name: a.name,
    code: a.code,
    status: errored.has(a.key) ? 'error' as const :
            completed.has(a.key) ? 'complete' as const :
            started.has(a.key) ? 'active' as const : 'pending' as const,
    tokens: tokenMap[a.key] || 0,
  }));
}

export default Navigator;
