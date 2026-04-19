import React, { useState } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, SuggestedPromQLQuery, TimeSeriesDataPoint } from '../../types';
import { runPromQLQuery } from '../../services/api';
import { Play, Copy, Check } from 'lucide-react';
import InteractiveTopology from './topology/InteractiveTopology';
import { useTopologySelection } from '../../contexts/TopologySelectionContext';
import { useCampaignContext } from '../../contexts/CampaignContext';
import REDMethodStatusBar from './cards/REDMethodStatusBar';
import PromQLRunResult from './cards/PromQLRunResult';
import SkeletonCard from '../ui/SkeletonCard';
import EliminationLog from './EliminationLog';
import AgentsCard from './AgentsCard';

interface NavigatorProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
}

const Navigator: React.FC<NavigatorProps> = ({ findings, status, events }) => {
  const { selectedService, selectService } = useTopologySelection();
  const { hoveredRepo } = useCampaignContext();

  return (
    <div className="flex flex-col h-full bg-wr-bg/20 overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="p-4 border-b border-wr-border flex items-center sticky top-0 z-10 bg-wr-bg/90 backdrop-blur">
        <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400">Navigator</h2>
      </div>

      <div className="p-4 space-y-5">
        {/* AGENTS card — promoted to column top in PR 5. Gives the right
            panel a hero slot that answers "is the investigation alive /
            making progress?" at a glance. Fuses the old left-panel Agent
            Pulse Indicator (NOW strip at top) with the inventory matrix. */}
        <AgentsCard status={status} events={events} />

        {/* RED Method Status */}
        {findings ? (
          <REDMethodStatusBar
            metricAnomalies={findings.metric_anomalies || []}
            correlatedSignals={findings.correlated_signals || []}
          />
        ) : (
          <SkeletonCard variant="metric" />
        )}

        {/* Service Topology */}
        <section>
          <h3 className="text-body-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Service Topology</h3>
          <div className="bg-wr-bg/40 border border-wr-border rounded-lg p-3">
            {findings ? (
              <InteractiveTopology
                findings={findings}
                selectedService={selectedService}
                onSelectService={selectService}
                highlightedService={hoveredRepo}
              />
            ) : (
              <GhostTopology />
            )}
          </div>
        </section>

        {/* Metrics Validation Dock */}
        <MetricsValidationDock queries={findings?.suggested_promql_queries || []} />

        {/* Infrastructure Health */}
        <InfraHealthCards findings={findings} />

        {/* Elimination Log */}
        <EliminationLog result={findings?.hypothesis_result || null} />
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
  const copyTimeoutRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => () => { if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current); }, []);

  if (queries.length === 0) return null;

  const handleCopy = (query: string, idx: number) => {
    navigator.clipboard.writeText(query).catch(() => {});
    setCopiedIdx(idx);
    if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current);
    copyTimeoutRef.current = setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleRun = async (query: string, idx: number) => {
    setRunResults((prev) => ({
      ...prev,
      [idx]: { loading: true, dataPoints: [], currentValue: 0 },
    }));

    try {
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
    } catch {
      setRunResults((prev) => ({
        ...prev,
        [idx]: { loading: false, dataPoints: [], currentValue: 0, error: 'Network request failed' },
      }));
    }
  };

  return (
    <section>
      <h3 className="text-body-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Metrics Validation</h3>
      <div className="space-y-2">
        {queries.map((q, i) => (
          <div key={i} className="bg-wr-bg/40 border border-wr-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-body-xs font-bold text-amber-400 uppercase">{q.metric}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleCopy(q.query, i)}
                  className="p-1 rounded hover:bg-wr-inset/50 transition-colors"
                  title="Copy query"
                  aria-label="Copy query"
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
                  className="flex items-center gap-1 text-body-xs px-2 py-0.5 rounded bg-wr-severity-medium/10 text-amber-400 border border-amber-500/20 hover:bg-wr-severity-medium/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
                  title="Execute query"
                  aria-label="Execute query"
                >
                  <Play size={10} />
                  Run
                </button>
              </div>
            </div>
            <pre className="text-body-xs font-mono text-slate-300 bg-black/20 rounded p-1.5 overflow-x-auto custom-scrollbar mb-1.5">
              {q.query}
            </pre>
            <p className="text-body-xs text-slate-400">{q.rationale}</p>
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
      <h3 className="text-body-xs font-bold text-slate-400 uppercase tracking-widest mb-2">Infrastructure Health</h3>
      <div className="bg-wr-bg/40 border border-wr-border rounded-lg p-3">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <div className="text-body-xs text-slate-400">Pods</div>
            <div className="text-lg font-bold font-mono text-white">{healthy}/{totalPods}</div>
          </div>
          <div>
            <div className="text-body-xs text-slate-400">Health</div>
            <div className={`text-lg font-bold font-mono ${healthPct >= 80 ? 'text-green-400' : healthPct >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
              {healthPct}%
            </div>
          </div>
        </div>
        {restarts > 0 && (
          <div className="text-body-xs text-amber-400 mb-1">{restarts} restart{restarts > 1 ? 's' : ''}</div>
        )}
        <div className="flex gap-1.5 flex-wrap">
          {oomCount > 0 && (
            <span className="text-body-xs px-1.5 py-0.5 rounded bg-wr-severity-high/20 text-red-400 border border-wr-severity-high/30">
              {oomCount} OOM
            </span>
          )}
          {crashLoopCount > 0 && (
            <span className="text-body-xs px-1.5 py-0.5 rounded bg-wr-severity-high/20 text-red-400 border border-wr-severity-high/30">
              {crashLoopCount} CrashLoop
            </span>
          )}
        </div>
      </div>
    </section>
  );
};

// Agent status builder moved to AgentsCard.tsx in PR 5.

// ─── Ghost Topology (placeholder while loading) ─────────────────────────

const GhostTopology: React.FC = () => (
  <svg viewBox="0 0 280 100" className="w-full opacity-20 blur-[1px]" style={{ maxHeight: '120px' }}>
    <line x1="70" y1="50" x2="140" y2="50" stroke="#475569" strokeWidth={1} />
    <line x1="140" y1="50" x2="210" y2="50" stroke="#475569" strokeWidth={1} />
    <circle cx="70" cy="50" r="16" fill="#0f3443" stroke="#06b6d4" strokeWidth={1.5} />
    <circle cx="140" cy="50" r="16" fill="#0f3443" stroke="#06b6d4" strokeWidth={1.5} />
    <circle cx="210" cy="50" r="16" fill="#0f3443" stroke="#06b6d4" strokeWidth={1.5} />
    <text x="70" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-a</text>
    <text x="140" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-b</text>
    <text x="210" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-c</text>
  </svg>
);

export default Navigator;
