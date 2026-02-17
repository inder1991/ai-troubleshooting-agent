import React, { useEffect, useState, useCallback } from 'react';
import type { V4Session, V4SessionStatus, DiagnosticPhase, TaskEvent, PastIncidentMatch } from '../../types';
import { getSessionStatus, getFindings } from '../../services/api';

interface ContextScopeProps {
  session: V4Session;
  events?: TaskEvent[];
}

const phaseLabel = (phase: DiagnosticPhase): string =>
  phase.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const ContextScope: React.FC<ContextScopeProps> = ({ session, events = [] }) => {
  const [status, setStatus] = useState<V4SessionStatus | null>(null);
  const [pastIncidents, setPastIncidents] = useState<PastIncidentMatch[]>([]);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getSessionStatus(session.session_id);
      setStatus(data);
    } catch {
      // silent
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Reactive: refetch on summary/phase_change events
  const relevantEventCount = events.filter(
    (e) => e.event_type === 'summary' || e.event_type === 'phase_change'
  ).length;

  useEffect(() => {
    if (relevantEventCount > 0) {
      fetchStatus();
      getFindings(session.session_id)
        .then((f) => setPastIncidents(f.past_incidents || []))
        .catch(() => {});
    }
  }, [relevantEventCount, session.session_id, fetchStatus]);

  const confidence = status?.confidence ?? session.confidence;
  const confidencePercent = Math.round(confidence * 100);
  const phase = status?.phase ?? session.status;
  const totalTokens = status?.token_usage?.reduce((sum, t) => sum + t.total_tokens, 0) ?? 0;

  // Extract namespace and cluster info from events or session data
  const namespace = extractFromEvents(events, 'namespace') || 'default';
  const clusterUrl = extractFromEvents(events, 'cluster_url') || null;

  // Build agents status from token usage data
  const agentStatuses = buildAgentStatuses(status, events);

  return (
    <div className="flex flex-col h-full bg-slate-900/20 border-l border-[#07b6d5]/10">
      {/* Header */}
      <div className="p-4 border-b border-[#07b6d5]/10 flex items-center gap-2">
        <span className="material-symbols-outlined text-slate-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>info</span>
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Context & Scope</h2>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-8 custom-scrollbar">
        {/* System Info */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">System Info</h3>
          <div className="space-y-3">
            <InfoRow label="Service" value={session.service_name} />
            <InfoRow label="Namespace" value={namespace} />
            {clusterUrl && <InfoRow label="Cluster" value={shortenUrl(clusterUrl)} title={clusterUrl} />}
            <InfoRow label="Session ID" value={session.session_id.substring(0, 8).toUpperCase()} valueColor="text-[#07b6d5]" />
            <InfoRow label="Phase" value={phaseLabel(phase)} />
            <InfoRow
              label="Confidence"
              value={`${confidencePercent}%`}
              valueColor={confidencePercent >= 70 ? 'text-green-400' : confidencePercent >= 40 ? 'text-amber-400' : 'text-red-400'}
              bold
            />
            <InfoRow
              label="Created"
              value={new Date(session.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            />
          </div>
        </section>

        {/* Agent Status */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Agent Status</h3>
          <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-800 space-y-3">
            {agentStatuses.map((agent, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className={`w-1.5 h-1.5 rounded-full ${
                  agent.status === 'active' ? 'bg-primary animate-pulse' :
                  agent.status === 'complete' ? 'bg-green-500' :
                  agent.status === 'error' ? 'bg-red-500' : 'bg-slate-600'
                }`} />
                <span className={`text-[11px] ${
                  agent.status === 'active' ? 'text-primary font-medium' : 'text-slate-300'
                }`}>
                  {agent.name}
                </span>
                <span className={`ml-auto text-[10px] ${
                  agent.status === 'active' ? 'text-primary' :
                  agent.status === 'complete' ? 'text-green-500' :
                  agent.status === 'error' ? 'text-red-400' : 'text-slate-500'
                }`}>
                  {agent.status === 'complete' && agent.tokens ? `${agent.tokens.toLocaleString()} tokens` :
                   agent.status === 'active' ? 'Active' :
                   agent.status === 'error' ? 'Failed' : 'Pending'}
                </span>
              </div>
            ))}
            {totalTokens > 0 && (
              <div className="border-t border-slate-700 pt-2 flex justify-between">
                <span className="text-[10px] text-slate-500">Total tokens</span>
                <span className="text-[10px] font-mono text-slate-400">{totalTokens.toLocaleString()}</span>
              </div>
            )}
          </div>
        </section>

        {/* Known Playbooks */}
        <KnownPlaybooksSection incidents={pastIncidents} />

        {/* Labels */}
        <section>
          <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Labels</h3>
          <div className="flex flex-wrap gap-2">
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              svc:{session.service_name}
            </span>
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              ns:{namespace}
            </span>
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              phase:{phase}
            </span>
            <span className="bg-slate-800 px-2 py-1 rounded text-[10px] text-slate-400 border border-slate-700">
              confidence:{confidencePercent}%
            </span>
          </div>
        </section>
      </div>

      {/* Footer action */}
      <div className="p-4 border-t border-[#07b6d5]/10">
        <button className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs font-bold transition-colors border border-slate-700 flex items-center justify-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>history</span>
          View Previous Incidents
        </button>
      </div>
    </div>
  );
};

// ─── Helpers ───────────────────────────────────────────────────────────────

const InfoRow: React.FC<{
  label: string;
  value: string;
  valueColor?: string;
  bold?: boolean;
  title?: string;
}> = ({ label, value, valueColor = 'text-slate-200', bold, title }) => (
  <div className="flex justify-between items-center border-b border-slate-800/50 pb-2">
    <span className="text-[11px] text-slate-400">{label}</span>
    <span className={`text-[11px] font-mono ${valueColor} ${bold ? 'font-bold' : ''}`} title={title}>
      {value}
    </span>
  </div>
);

function shortenUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname;
  } catch {
    return url.length > 30 ? url.slice(0, 30) + '...' : url;
  }
}

function extractFromEvents(events: TaskEvent[], key: string): string | null {
  // Look through phase_change or summary event details for context info
  for (let i = events.length - 1; i >= 0; i--) {
    const val = events[i].details?.[key];
    if (val && typeof val === 'string') return val;
  }
  return null;
}

interface AgentStatus {
  name: string;
  status: 'pending' | 'active' | 'complete' | 'error';
  tokens?: number;
}

function buildAgentStatuses(status: V4SessionStatus | null, events: TaskEvent[]): AgentStatus[] {
  const agents = ['log_agent', 'metrics_agent', 'k8s_agent', 'tracing_agent', 'code_agent', 'change_agent'];
  const agentLabels: Record<string, string> = {
    log_agent: 'Log Analyzer',
    metrics_agent: 'Metric Scanner',
    k8s_agent: 'K8s Probe',
    tracing_agent: 'Trace Walker',
    code_agent: 'Code Navigator',
    change_agent: 'Change Intel',
  };

  // Determine status from events
  const started = new Set<string>();
  const completed = new Set<string>();
  const errored = new Set<string>();

  events.forEach((e) => {
    if (e.event_type === 'started') started.add(e.agent_name);
    if (e.event_type === 'summary' || e.event_type === 'success') completed.add(e.agent_name);
    if (e.event_type === 'error') errored.add(e.agent_name);
  });

  // Token usage map
  const tokenMap: Record<string, number> = {};
  status?.token_usage?.forEach((t) => {
    tokenMap[t.agent_name] = t.total_tokens;
  });

  return agents.map((a) => ({
    name: agentLabels[a] || a,
    status: errored.has(a) ? 'error' :
            completed.has(a) ? 'complete' :
            started.has(a) ? 'active' : 'pending',
    tokens: tokenMap[a],
  }));
}

// ─── Known Playbooks ──────────────────────────────────────────────────────

const KnownPlaybooksSection: React.FC<{ incidents: PastIncidentMatch[] }> = ({ incidents }) => {
  const [expanded, setExpanded] = useState(false);
  const topMatch = incidents[0];
  const autoExpand = topMatch && topMatch.similarity_score > 0.85;

  // Auto-expand if top match has high similarity
  useEffect(() => {
    if (autoExpand) setExpanded(true);
  }, [autoExpand]);

  return (
    <section>
      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Known Playbooks</h3>
      <div className="bg-slate-800/30 rounded-lg border border-slate-800">
        <button
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          className="w-full px-3 py-2.5 flex items-center gap-2 text-left hover:bg-slate-800/50 transition-colors rounded-lg"
        >
          <span
            className="material-symbols-outlined text-xs text-slate-400 transition-transform"
            style={{ fontFamily: 'Material Symbols Outlined', transform: expanded ? 'rotate(90deg)' : 'none' }}
          >
            chevron_right
          </span>
          <span className="material-symbols-outlined text-sm text-slate-400" style={{ fontFamily: 'Material Symbols Outlined' }}>
            library_books
          </span>
          <span className="text-[11px] text-slate-300 flex-1">
            {incidents.length > 0
              ? `${incidents.length} similar incident${incidents.length > 1 ? 's' : ''} found`
              : 'No matches'}
          </span>
          {incidents.length > 0 && (
            <span className="text-[10px] font-mono text-amber-400">
              {Math.round(topMatch.similarity_score * 100)}%
            </span>
          )}
        </button>

        {expanded && incidents.length > 0 && (
          <div className="px-3 pb-3 space-y-2">
            {incidents.map((inc, i) => (
              <PlaybookRow key={inc.fingerprint_id || i} incident={inc} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

const PlaybookRow: React.FC<{ incident: PastIncidentMatch }> = ({ incident }) => {
  const [expanded, setExpanded] = useState(false);
  const score = Math.round(incident.similarity_score * 100);

  return (
    <div className="bg-slate-900/50 rounded border border-slate-700/50">
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="w-full px-2.5 py-2 flex items-center gap-2 text-left hover:bg-slate-800/30 transition-colors rounded"
      >
        <span
          className="material-symbols-outlined text-xs text-slate-500 transition-transform"
          style={{ fontFamily: 'Material Symbols Outlined', transform: expanded ? 'rotate(90deg)' : 'none' }}
        >
          chevron_right
        </span>
        <span className="text-[11px] text-slate-200 flex-1 truncate">
          {incident.root_cause || 'Unknown root cause'}
        </span>
        <span className={`text-[10px] font-mono ${score >= 80 ? 'text-green-400' : score >= 60 ? 'text-amber-400' : 'text-slate-400'}`}>
          {score}%
        </span>
      </button>

      {expanded && (
        <div className="px-2.5 pb-2.5 space-y-2 border-t border-slate-700/30 pt-2">
          {incident.resolution_steps.length > 0 && (
            <div>
              <span className="text-[10px] text-slate-500 uppercase tracking-wide">Resolution</span>
              <ul className="mt-1 space-y-1">
                {incident.resolution_steps.map((step, i) => (
                  <li key={i} className="text-[11px] text-slate-300 flex gap-1.5">
                    <span className="text-slate-500 shrink-0">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {incident.affected_services.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {incident.affected_services.map((svc) => (
                <span key={svc} className="text-[10px] bg-slate-800 px-1.5 py-0.5 rounded text-slate-400 border border-slate-700">
                  {svc}
                </span>
              ))}
            </div>
          )}
          {incident.time_to_resolve > 0 && (
            <div className="text-[10px] text-slate-500">
              Resolved in {incident.time_to_resolve < 60
                ? `${incident.time_to_resolve}m`
                : `${Math.round(incident.time_to_resolve / 60)}h ${incident.time_to_resolve % 60}m`}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ContextScope;
