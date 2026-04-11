import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import type { V4Session, TaskEvent, DiagnosticPhase } from '../../types';
import { getSessionEvents, getSessionDossier, API_BASE_URL } from '../../services/api';
import FixRecommendations from './db-board/FixRecommendations';

import PanelZone from './db-board/PanelZone';
import type { PanelState } from './db-board/PanelZone';
import CaseFile from './db-board/CaseFile';
import RootCauseVerdict from './db-board/RootCauseVerdict';
import HealthStrip from './db-board/HealthStrip';
import { DB_AGENT_IDS, getStatusIcon, formatDuration } from './db-board/constants';

import QueryFlamechart from './db-viz/QueryFlamechart';
import ExplainPlanTree from './db-viz/ExplainPlanTree';
import IndexUsageMatrix from './db-viz/IndexUsageMatrix';
import TableBloatHeatmap from './db-viz/TableBloatHeatmap';
import ConnectionPoolGauge from './db-viz/ConnectionPoolGauge';
import SlowQueryTimeline from './db-viz/SlowQueryTimeline';
import ReplicationTopologySVG from './db-viz/ReplicationTopologySVG';

function extractVerdict(synthEvent: TaskEvent | null): string | null {
  if (!synthEvent) return null;
  const msg = synthEvent.message;
  if (typeof msg === 'string') return msg;
  if (msg && typeof msg === 'object') {
    return (msg as any).title || (msg as any).detail || JSON.stringify(msg);
  }
  return null;
}

interface DatabaseWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: DiagnosticPhase | null;
  confidence: number;
}

function derivePanelState(agentEvents: TaskEvent[], dataKey: string): PanelState {
  if (agentEvents.length === 0) return 'dormant';
  const hasFinding = agentEvents.some((e) => e.event_type === 'finding' && e.details?.[dataKey]);
  if (hasFinding) return 'lit';
  const hasError = agentEvents.some((e) => e.event_type === 'error');
  const isComplete = agentEvents.some((e) => e.event_type === 'success');
  if (hasError && !isComplete) return 'error';
  if (isComplete) return 'dormant';
  const hasActivity = agentEvents.some((e) => ['started', 'progress'].includes(e.event_type));
  if (hasActivity) return 'scanning';
  return 'dormant';
}

function extractData<T>(agentEvents: TaskEvent[], key: string): T | null {
  for (let i = agentEvents.length - 1; i >= 0; i--) {
    if (agentEvents[i].details?.[key]) return agentEvents[i].details![key] as T;
  }
  return null;
}

const DatabaseWarRoom: React.FC<DatabaseWarRoomProps> = ({
  session, events, wsConnected, phase, confidence,
}) => {
  const [elapsedSec, setElapsedSec] = useState(0);
  const [activePlanIdx, setActivePlanIdx] = useState(0);
  const [pollFailCount, setPollFailCount] = useState(0);
  const startRef = useRef(Date.now());
  useEffect(() => {
    const iv = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startRef.current) / 1000));
    }, 5000);
    return () => clearInterval(iv);
  }, []);

  // Poll events REST endpoint every 3s for reliability (catches WS misses)
  const [polledEvents, setPolledEvents] = useState<TaskEvent[]>([]);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const evts = await getSessionEvents(session.session_id);
        if (!cancelled && evts.length > 0) {
          setPolledEvents(evts);
        }
        setPollFailCount(0);
      } catch {
        setPollFailCount(c => c + 1);
      }
    };
    poll(); // immediate first fetch
    const iv = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [session.session_id]);

  // Fetch dossier + fix recommendations when investigation completes
  const [fixes, setFixes] = useState<any[]>([]);
  const [dossier, setDossier] = useState<any>(null);
  useEffect(() => {
    if (phase !== 'complete') return;
    getSessionDossier(session.session_id).then((data) => {
      if (data.fixes) setFixes(data.fixes);
      if (data.dossier) setDossier(data.dossier);
    }).catch(() => {});
  }, [phase, session.session_id]);

  const handleExportReport = useCallback(() => {
    if (!dossier) return;
    const exec = dossier.executive_summary || {};
    const rca = dossier.root_cause_analysis || {};
    const md = [
      `# Database Diagnostic Report`,
      `## ${exec.profile || session.service_name}`,
      `**Status:** ${exec.health_status || 'unknown'} | **Findings:** ${exec.total_findings || 0} | **Critical:** ${exec.critical_count || 0}`,
      ``,
      `## Root Cause`,
      `**${rca.primary_root_cause || 'Unknown'}** (${rca.severity || '?'}, confidence: ${((rca.confidence || 0) * 100).toFixed(0)}%)`,
      rca.detail || '',
      ``,
      `## Evidence Chain`,
      ...(dossier.evidence_chain || []).map((e: any, i: number) => `${i + 1}. **${e.title}** (${e.severity}) — ${e.detail || ''}`),
      ``,
      `## Recommended Fixes`,
      ...fixes.map((f: any, i: number) => [
        `### ${i + 1}. ${f.title} (${f.severity})`,
        f.recommendation || '',
        f.sql ? `\`\`\`sql\n${f.sql}\n\`\`\`` : '',
      ].join('\n')),
      ``,
      `## Impact Assessment`,
      `Blast radius: ${dossier.impact_assessment?.blast_radius || 'unknown'}`,
      `User impact: ${dossier.impact_assessment?.estimated_user_impact || 'unknown'}`,
      ``,
      `---`,
      `*Generated by DebugDuck DB Diagnostics*`,
    ].join('\n');

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.incident_id || session.session_id.slice(0, 8)}-db-report.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [dossier, fixes, session]);

  const handleCancel = useCallback(async () => {
    try {
      await fetch(`${API_BASE_URL}/api/v4/session/${session.session_id}/cancel`, { method: 'POST' });
    } catch { /* silent */ }
  }, [session.session_id]);

  // Merge: deduplicate events from WS and REST poll
  const mergedEvents = useMemo(() => {
    const seen = new Set<string>();
    const result: TaskEvent[] = [];
    for (const ev of [...events, ...polledEvents]) {
      const key = `${ev.agent_name}-${ev.event_type}-${ev.message}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(ev);
      }
    }
    return result;
  }, [events, polledEvents]);

  const agentEventMap = useMemo(() => {
    const map: Record<string, typeof mergedEvents> = {};
    for (const ev of mergedEvents) {
      if (ev.agent_name) {
        (map[ev.agent_name] ??= []).push(ev);
      }
    }
    return map;
  }, [mergedEvents]);

  const ps = useMemo(() => ({
    queries: derivePanelState(agentEventMap['query_analyst'] || [], 'slow_queries'),
    connPool: derivePanelState(agentEventMap['health_analyst'] || [], 'connections'),
    indexes: derivePanelState(agentEventMap['schema_analyst'] || [], 'indexes'),
    bloat: derivePanelState(agentEventMap['schema_analyst'] || [], 'table_bloat'),
    plan: derivePanelState(agentEventMap['query_analyst'] || [], 'explain_plans') === 'lit'
      ? 'lit' as PanelState
      : derivePanelState(agentEventMap['query_analyst'] || [], 'explain_plan'),
  }), [agentEventMap]);

  // Track which agents have completed (for notApplicable prop)
  const agentDone = useMemo(() => ({
    query: (agentEventMap['query_analyst'] || []).some(e => e.event_type === 'success' || e.event_type === 'error'),
    health: (agentEventMap['health_analyst'] || []).some(e => e.event_type === 'success' || e.event_type === 'error'),
    schema: (agentEventMap['schema_analyst'] || []).some(e => e.event_type === 'success' || e.event_type === 'error'),
  }), [agentEventMap]);

  const slowQueries = extractData<any[]>(agentEventMap['query_analyst'] || [], 'slow_queries');
  const planSteps = extractData<any[]>(agentEventMap['query_analyst'] || [], 'plan_steps');
  const explainPlan = extractData<any>(agentEventMap['query_analyst'] || [], 'explain_plan');
  const explainPlans = extractData<any[]>(agentEventMap['query_analyst'] || [], 'explain_plans');
  const allPlans = explainPlans || (explainPlan ? [explainPlan] : []);
  const connections = extractData<any>(agentEventMap['health_analyst'] || [], 'connections');
  const indexes = extractData<any[]>(agentEventMap['schema_analyst'] || [], 'indexes');
  const tableBloat = extractData<any[]>(agentEventMap['schema_analyst'] || [], 'table_bloat');
  const replication = extractData<any>(agentEventMap['health_analyst'] || [], 'replication');
  const performance = extractData<any>(agentEventMap['health_analyst'] || [], 'performance');

  const synthEvent = useMemo(() => {
    const synthEvents = agentEventMap['synthesizer'] || [];
    for (let i = synthEvents.length - 1; i >= 0; i--) {
      if (synthEvents[i].event_type === 'success') return synthEvents[i];
    }
    return null;
  }, [agentEventMap]);

  const litPanels = useMemo(() => {
    const out: string[] = [];
    if (ps.queries === 'lit') out.push('Queries');
    if (ps.connPool === 'lit') out.push('Connections');
    if (ps.indexes === 'lit') out.push('Indexes');
    if (ps.bloat === 'lit') out.push('Bloat');
    if (ps.plan === 'lit') out.push('Plan');
    return out;
  }, [ps]);

  return (
    <div className={`flex flex-col h-full overflow-hidden bg-duck-bg ${phase === 'complete' ? 'ring-1 ring-duck-accent/20' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-duck-border bg-duck-panel/50 shrink-0">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-violet-400 text-xl">database</span>
          <div>
            <h1 className="text-sm font-display font-bold text-white">{session.service_name}</h1>
            <p className="text-body-xs text-slate-400">{phase || 'initializing'}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs font-mono text-amber-400">
            {formatDuration(elapsedSec)}
          </span>
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-red-400'}`} />
            <span className={`text-body-xs font-bold uppercase ${wsConnected ? 'text-emerald-400' : 'text-red-300'}`}>
              {wsConnected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
          {phase && !['complete', 'error', 'cancelled'].includes(phase) && (
            <button
              onClick={handleCancel}
              className="text-body-xs text-slate-400 hover:text-red-400 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              aria-label="Cancel investigation"
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {pollFailCount >= 3 && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2 shrink-0">
          <span className="material-symbols-outlined text-red-400 text-sm" aria-hidden="true">wifi_off</span>
          <span className="text-body-xs text-red-400">Connection lost — retrying automatically</span>
        </div>
      )}

      {/* 3-column board */}
      <div className="grid grid-cols-1 md:grid-cols-12 lg:grid-cols-12 flex-1 overflow-hidden">

        {/* LEFT: Case File */}
        <div className="md:col-span-3 lg:col-span-3 border-r border-duck-border overflow-hidden">
          <CaseFile
            serviceName={session.service_name}
            sessionId={session.session_id}
            incidentId={session.incident_id}
            events={mergedEvents}
            elapsedSec={elapsedSec}
          />
        </div>

        {/* CENTER: The Board — asymmetric grid */}
        <div className="md:col-span-5 lg:col-span-5 overflow-y-auto p-4 custom-scrollbar">
          {/* Root Cause Verdict — takes top when present */}
          <RootCauseVerdict
            verdict={extractVerdict(synthEvent)}
            confidence={confidence}
            severity={(synthEvent?.details?.severity as any) || 'medium'}
            recommendation={synthEvent?.details?.recommendation as string | undefined}
            contributingPanels={litPanels}
            causalChain={dossier?.root_cause_analysis?.causal_chain}
            evidenceWeights={dossier?.root_cause_analysis?.evidence_weight_map}
          />

          {/* Asymmetric grid: Query Performance (2fr) | Connection Pool (1fr) etc. */}
          <div className={`grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-x-4 gap-y-5 ${phase === 'complete' ? 'opacity-70 transition-opacity duration-300' : ''}`}>
            {/* Query Performance — LARGE */}
            <PanelZone
              title="Query Performance"
              icon="query_stats"
              agentName="query_analyst"
              state={ps.queries}
              className="min-h-[180px]"
            >
              <div className="space-y-3">
                {slowQueries ? <SlowQueryTimeline queries={slowQueries} /> : null}
                {planSteps ? <QueryFlamechart planSteps={planSteps} /> : null}
                {!slowQueries && !planSteps && (
                  <p className="text-body-xs text-slate-500 italic text-center py-4">Awaiting query data...</p>
                )}
              </div>
            </PanelZone>

            {/* Connection Pool — standard */}
            <PanelZone
              title="Connections"
              icon="hub"
              agentName="health_analyst"
              state={ps.connPool}
              className="min-h-[180px]"
            >
              {connections && (
                <ConnectionPoolGauge
                  active={connections.active ?? 0}
                  idle={connections.idle ?? 0}
                  waiting={connections.waiting ?? 0}
                  max={connections.max_connections ?? connections.max ?? 100}
                />
              )}
            </PanelZone>

            {/* Index Health */}
            <PanelZone
              title="Index Health"
              icon="format_list_numbered"
              agentName="schema_analyst"
              state={ps.indexes}
            >
              {indexes && <IndexUsageMatrix indexes={indexes} />}
            </PanelZone>

            {/* Table Bloat */}
            <PanelZone
              title="Table Bloat"
              icon="grid_view"
              agentName="schema_analyst"
              state={ps.bloat}
            >
              {tableBloat && <TableBloatHeatmap tables={tableBloat} />}
            </PanelZone>

            {/* Query Plan — takes left column */}
            <PanelZone
              title="Query Plan"
              icon="account_tree"
              agentName="query_analyst"
              state={ps.plan}
              notApplicable={ps.plan === 'dormant' && agentDone.query}
            >
              {allPlans.length > 1 && (
                <div className="flex gap-1 mb-2">
                  {allPlans.map((p: any, i: number) => (
                    <button
                      key={i}
                      onClick={() => setActivePlanIdx(i)}
                      className={`text-body-xs px-1.5 py-0.5 rounded transition-colors ${
                        i === activePlanIdx
                          ? 'bg-duck-accent/20 text-duck-accent'
                          : 'text-slate-400 hover:text-slate-300'
                      }`}
                    >
                      pid:{p.pid || i}
                    </button>
                  ))}
                </div>
              )}
              {allPlans[activePlanIdx] && <ExplainPlanTree plan={allPlans[activePlanIdx]} />}
            </PanelZone>

            {/* Intentional empty right cell — asymmetry */}
            <div className="hidden md:block" />
          </div>

          {/* Schema Drift removed — needs baseline infrastructure (future work) */}
        </div>

        {/* RIGHT: The Map */}
        <div className="md:col-span-4 lg:col-span-4 border-l border-duck-border overflow-y-auto p-4 custom-scrollbar">
          {/* Fix Recommendations + Export (after completion) — shown FIRST when complete */}
          {phase === 'complete' && (
            <div className="mb-5 border-b border-duck-border/50 pb-4">
              {fixes.length > 0 ? (
                <FixRecommendations fixes={fixes} onExportReport={dossier ? handleExportReport : undefined} />
              ) : (
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
                  <span className="text-body-xs font-display font-bold text-emerald-400">Complete — no fixes needed</span>
                </div>
              )}
            </div>
          )}

          {/* Agent Status — compact when complete, full list otherwise */}
          {phase === 'complete' ? (
            <div className="flex items-center gap-2 py-1 mb-4">
              <span className="material-symbols-outlined text-emerald-400 text-sm">check_circle</span>
              <span className="text-body-xs font-display font-bold text-emerald-400">All agents complete</span>
            </div>
          ) : (
            <div className="mb-5">
              <h2 className="text-body-xs font-display font-bold text-slate-400 mb-2">Agents</h2>
              <div className="space-y-1">
                {DB_AGENT_IDS.map((agent) => {
                  const agentEvents = agentEventMap[agent] || [];
                  const last = agentEvents[agentEvents.length - 1];
                  const status: string = last?.event_type || 'pending';
                  const si = getStatusIcon(status);
                  return (
                    <div key={agent} className="flex items-center justify-between py-2 px-2 md:py-1">
                      <span className="text-body-xs text-slate-400">{agent.replace(/_/g, ' ')}</span>
                      <span className={`material-symbols-outlined text-[14px] ${si.cls}`}>
                        {si.icon}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Replication Topology */}
          <div className="mb-5">
            <h2 className="text-body-xs font-display font-bold text-slate-400 mb-2">Replication</h2>
            {replication ? (
              replication.replicas && replication.replicas.length > 0 ? (
                <ReplicationTopologySVG
                  primary={replication.primary || { host: session.service_name, lag_ms: 0 }}
                  replicas={replication.replicas || []}
                />
              ) : (
                <div className="flex items-center gap-2 py-3 px-3 bg-duck-surface/20 rounded-lg">
                  <span className="material-symbols-outlined text-slate-400 text-sm" aria-hidden="true">dns</span>
                  <span className="text-body-xs text-slate-400">Single node — no replication configured</span>
                </div>
              )
            ) : (
              <div className="flex items-center justify-center h-20 border border-dashed border-duck-border/30 rounded-lg">
                <span className="text-body-xs text-slate-400 italic">Awaiting replication data</span>
              </div>
            )}
          </div>

          {/* Health Strip */}
          <div className="mb-5">
            <h2 className="text-body-xs font-display font-bold text-slate-400 mb-2">Health</h2>
            <HealthStrip
              cacheHitRatio={performance?.cache_hit_ratio}
              tps={performance?.transactions_per_sec}
              deadlocks={performance?.deadlocks}
              uptimeSeconds={performance?.uptime_seconds}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default React.memo(DatabaseWarRoom);
