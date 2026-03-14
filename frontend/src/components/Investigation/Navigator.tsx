import React, { useState, useEffect } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, SuggestedPromQLQuery, TimeSeriesDataPoint, AgentConfidence, ReasoningStep } from '../../types';
import { runPromQLQuery, getConfidence, getReasoning } from '../../services/api';
import { Play, Copy, Check } from 'lucide-react';
import InteractiveTopology from './topology/InteractiveTopology';
import { useTopologySelection } from '../../contexts/TopologySelectionContext';
import { useCampaignContext } from '../../contexts/CampaignContext';
import REDMethodStatusBar from './cards/REDMethodStatusBar';
import PromQLRunResult from './cards/PromQLRunResult';
import SkeletonCard from '../ui/SkeletonCard';
import NeuralChart from './charts/NeuralChart';
import ClusterInfoBanner from './cluster/ClusterInfoBanner';
import FirewallAuditBadge from './cluster/FirewallAuditBadge';
import DomainAgentStatus from './cluster/DomainAgentStatus';
import DomainHealthGrid from './cluster/DomainHealthGrid';

interface NavigatorProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
  sessionId: string;
}

const Navigator: React.FC<NavigatorProps> = ({ findings, status, events, sessionId }) => {
  const { selectedService, selectService } = useTopologySelection();
  const { hoveredRepo } = useCampaignContext();
  const agentStatuses = buildAgentStatuses(status, events);
  const totalTokens = status?.token_usage?.reduce((sum, t) => sum + t.total_tokens, 0) ?? 0;

  const [agentConfidence, setAgentConfidence] = useState<AgentConfidence[]>([]);
  const [reasoning, setReasoning] = useState<ReasoningStep[]>([]);
  const [reasoningOpen, setReasoningOpen] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    getConfidence(sessionId).then((data) => setAgentConfidence(Array.isArray(data) ? data : data.agents || [])).catch(() => {});
    getReasoning(sessionId).then((data) => setReasoning(Array.isArray(data) ? data : data.steps || [])).catch(() => {});
  }, [sessionId]);

  return (
    <div className="flex flex-col h-full bg-slate-900/20 overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center gap-2 sticky top-0 z-10 bg-slate-900/90 backdrop-blur">
        <span className="material-symbols-outlined text-slate-400 text-sm">explore</span>
        <h2 className="text-xs font-bold font-display text-slate-400">Navigator</h2>
      </div>

      <div className="p-4 space-y-5">
        {/* Cluster diagnostics info */}
        {findings?.scan_mode && (
          <>
            <ClusterInfoBanner
              platform={findings.platform || 'kubernetes'}
              platformVersion={findings.platform_version || ''}
              namespaceCount={findings.topology_snapshot ? Object.keys(findings.topology_snapshot.nodes).length : 0}
              scanMode={findings.scan_mode}
              scope={findings.diagnostic_scope}
            />
            {findings.domain_reports && findings.domain_reports.length > 0 && (
              <>
                <DomainAgentStatus reports={findings.domain_reports} />
                <DomainHealthGrid domains={findings.domain_reports} />
              </>
            )}
          </>
        )}
        {findings?.causal_search_space && (
          <FirewallAuditBadge searchSpace={findings.causal_search_space} />
        )}

        {/* RED Method Status */}
        {findings ? (
          <REDMethodStatusBar
            metricAnomalies={findings.metric_anomalies || []}
            correlatedSignals={findings.correlated_signals || []}
          />
        ) : (
          <SkeletonCard variant="metric" />
        )}

        {/* Metric Anomaly Charts */}
        {findings?.metric_anomalies?.map((anomaly, i) => {
          const tsData = findings.time_series_data?.[anomaly.metric_name];
          if (!tsData?.length) return null;
          return (
            <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-lg p-2">
              <div className="text-[9px] font-bold text-slate-500 mb-1">{anomaly.metric_name}</div>
              <NeuralChart
                height={80}
                data={tsData.map((p: TimeSeriesDataPoint) => ({
                  timestamp: new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                  value: typeof p.value === 'number' ? p.value : parseFloat(String(p.value)) || 0,
                }))}
                lines={[{ dataKey: 'value', color: anomaly.severity === 'critical' ? 'red' : 'amber' }]}
                showGrid={false}
              />
            </div>
          );
        })}

        {/* Service Topology */}
        <section>
          <h3 className="text-[10px] font-bold font-display text-slate-500 mb-2">Service Topology</h3>
          <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
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

        {/* Confidence Scores */}
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#e09f3e', marginBottom: 8 }}>Agent Confidence</div>
          {agentConfidence.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {agentConfidence.map((ac) => {
                const agentColors: Record<string, string> = { L: '#ef4444', M: '#e09f3e', K: '#f59e0b', C: '#10b981', D: '#8b5cf6' };
                const color = agentColors[ac.agent] || '#64748b';
                return (
                  <div key={ac.agent} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color, width: 16, textAlign: 'center' }}>{ac.agent}</span>
                    <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ width: `${ac.confidence}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.3s ease' }} />
                    </div>
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#8a7e6b', width: 32, textAlign: 'right' }}>{ac.confidence}%</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ fontSize: 11, color: '#64748b', fontStyle: 'italic' }}>No confidence data yet</div>
          )}
        </div>

        {/* Reasoning Steps */}
        <div style={{ marginTop: 16 }}>
          <button
            onClick={() => setReasoningOpen(!reasoningOpen)}
            style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer', padding: 0, width: '100%' }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#e09f3e', transform: reasoningOpen ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform 0.2s' }}>chevron_right</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#e09f3e' }}>Reasoning Steps</span>
            <span style={{ fontSize: 10, color: '#64748b', marginLeft: 'auto' }}>{reasoning.length}</span>
          </button>
          {reasoningOpen && reasoning.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {reasoning.map((step, i) => (
                <div key={i} style={{ background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.08)', borderRadius: 6, padding: '8px 10px' }}>
                  <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>Step {i + 1} • {step.agent}</div>
                  <div style={{ fontSize: 12, color: '#e8e0d4' }}>{step.description}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Agent Status Matrix */}
        <section>
          <h3 className="text-[10px] font-bold font-display text-slate-500 mb-2">Agent Status</h3>
          <div className="bg-slate-900/40 border border-slate-800 rounded-lg p-3 space-y-2">
            {agentStatuses.map((agent, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold ${
                  agent.code === 'L' ? 'bg-red-500/20 text-red-400' :
                  agent.code === 'M' ? 'bg-amber-500/20 text-amber-400' :
                  agent.code === 'K' ? 'bg-orange-500/20 text-orange-400' :
                  agent.code === 'C' ? 'bg-emerald-500/20 text-emerald-400' :
                  'bg-slate-500/20 text-slate-400'
                }`}>
                  {agent.code}
                </span>
                <span className="text-[11px] text-slate-300 flex-1">{agent.name}</span>
                <span className={`w-2 h-2 rounded-full ${
                  agent.status === 'active' ? 'bg-amber-400 animate-pulse' :
                  agent.status === 'complete' ? 'bg-green-500' :
                  agent.status === 'error' ? 'bg-red-500' : 'bg-slate-600'
                }`} />
                {agent.tokens > 0 && (
                  <span className="text-[9px] text-slate-500">{agent.tokens.toLocaleString()}</span>
                )}
              </div>
            ))}
            {totalTokens > 0 && (
              <div className="border-t border-slate-700 pt-2 flex justify-between">
                <span className="text-[10px] text-slate-500">Total</span>
                <span className="text-[10px] text-slate-400">{totalTokens.toLocaleString()} tokens</span>
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
      <h3 className="text-[10px] font-bold font-display text-slate-500 mb-2">Metrics Validation</h3>
      <div className="space-y-2">
        {queries.map((q, i) => (
          <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-lg p-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-bold text-amber-400">{q.metric}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleCopy(q.query, i)}
                  className="p-1 rounded hover:bg-slate-700/50 transition-colors"
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
                  className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:saturate-0"
                  title="Execute query"
                  aria-label="Execute query"
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
      <h3 className="text-[10px] font-bold font-display text-slate-500 mb-2">Infrastructure Health</h3>
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

// ─── Ghost Topology (placeholder while loading) ─────────────────────────

const GhostTopology: React.FC = () => (
  <svg viewBox="0 0 280 100" className="w-full opacity-20 blur-[1px]" style={{ maxHeight: '120px' }}>
    <line x1="70" y1="50" x2="140" y2="50" stroke="#475569" strokeWidth={1} />
    <line x1="140" y1="50" x2="210" y2="50" stroke="#475569" strokeWidth={1} />
    <circle cx="70" cy="50" r="16" fill="#0f3443" stroke="#d4922e" strokeWidth={1.5} />
    <circle cx="140" cy="50" r="16" fill="#0f3443" stroke="#d4922e" strokeWidth={1.5} />
    <circle cx="210" cy="50" r="16" fill="#0f3443" stroke="#d4922e" strokeWidth={1.5} />
    <text x="70" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-a</text>
    <text x="140" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-b</text>
    <text x="210" y="80" textAnchor="middle" fill="#475569" fontSize="8" fontFamily="monospace">svc-c</text>
  </svg>
);

export default Navigator;
