import React, { useState, useEffect, useCallback } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, Severity, CriticVerdict } from '../../types';
import { getFindings, getSessionStatus } from '../../services/api';

interface EvidenceStackProps {
  sessionId: string;
  events: TaskEvent[];
}

type TabId = 'evidence' | 'timeline' | 'findings' | 'metrics';

const severityColor: Record<Severity, string> = {
  critical: 'bg-red-500/20 text-red-300 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  low: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  info: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
};

const verdictColor: Record<CriticVerdict['verdict'], string> = {
  confirmed: 'bg-green-500/20 text-green-300',
  plausible: 'bg-blue-500/20 text-blue-300',
  weak: 'bg-yellow-500/20 text-yellow-300',
  rejected: 'bg-red-500/20 text-red-300',
};

const tabs: { id: TabId; label: string; icon: string }[] = [
  { id: 'evidence', label: 'Evidence', icon: 'inventory_2' },
  { id: 'timeline', label: 'Timeline', icon: 'timeline' },
  { id: 'findings', label: 'Findings', icon: 'target' },
  { id: 'metrics', label: 'Metrics', icon: 'bar_chart' },
];

const EvidenceStack: React.FC<EvidenceStackProps> = ({ sessionId, events }) => {
  const [activeTab, setActiveTab] = useState<TabId>('evidence');
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [status, setStatus] = useState<V4SessionStatus | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([getFindings(sessionId), getSessionStatus(sessionId)]);
      setFindings(f);
      setStatus(s);
    } catch {
      // silent
    }
  }, [sessionId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="flex flex-col h-full bg-[#0f2023]">
      {/* Header bar */}
      <div className="h-12 border-b border-[#07b6d5]/5 flex items-center justify-between px-6 bg-slate-900/10">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-slate-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>inventory_2</span>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Dynamic Evidence Stack</h2>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            <span className="text-[10px] text-slate-500 font-medium">Real-time Feed</span>
          </div>
          <button className="text-xs text-primary font-bold hover:underline">Clear Filter</button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-slate-800/50 bg-slate-900/20 px-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-3 text-xs font-medium transition-colors border-b-2 ${
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        {activeTab === 'evidence' && <EvidenceTab findings={findings} events={events} />}
        {activeTab === 'timeline' && <TimelineTab events={events} breadcrumbs={status?.breadcrumbs || []} />}
        {activeTab === 'findings' && <FindingsTab findings={findings} />}
        {activeTab === 'metrics' && <MetricsTab findings={findings} />}
      </div>
    </div>
  );
};

// Evidence Tab - Log patterns and evidence cards matching reference
const EvidenceTab: React.FC<{ findings: V4Findings | null; events: TaskEvent[] }> = ({ findings, events }) => {
  // Show log patterns if we have error_patterns
  const errorPatterns = findings?.error_patterns || [];
  const k8sEvents = findings?.k8s_events || [];
  const evidenceItems: { severity: Severity; source: string; claim: string }[] = [];

  findings?.findings?.forEach((f) => {
    f.evidence?.forEach((ev) => {
      evidenceItems.push({ severity: f.severity, source: f.agent_name, claim: ev });
    });
  });

  const hasContent = errorPatterns.length > 0 || k8sEvents.length > 0 || evidenceItems.length > 0 || events.length > 0;

  if (!hasContent) {
    return <EmptyState message="Collecting evidence... Agents are scanning logs, metrics, and traces." />;
  }

  return (
    <div className="space-y-6">
      {/* Log Pattern Card - matches reference */}
      {errorPatterns.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-amber-500 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>receipt_long</span>
              <span className="text-[11px] font-bold uppercase tracking-wider">Log Patterns</span>
            </div>
            <span className="text-[10px] font-mono text-slate-500">{errorPatterns.length} patterns</span>
          </div>
          <div className="p-4 font-mono text-[11px] space-y-1 text-slate-400">
            {errorPatterns.map((ep, i) => (
              <div key={i} className="flex gap-4">
                <span className="text-slate-600 w-24 shrink-0">
                  {ep.last_seen ? new Date(ep.last_seen).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                </span>
                <span className={`font-bold w-12 shrink-0 ${
                  ep.severity === 'critical' || ep.severity === 'high' ? 'text-red-400' :
                  ep.severity === 'medium' ? 'text-amber-400' : 'text-blue-400'
                }`}>
                  [{ep.severity === 'critical' || ep.severity === 'high' ? 'ERROR' :
                    ep.severity === 'medium' ? 'WARN' : 'INFO'}]
                </span>
                <span className="truncate">{ep.sample_message || ep.pattern}</span>
                <span className="text-red-400 ml-auto shrink-0">{ep.count}x</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Metric Cards Grid - matches reference */}
      {(findings?.metric_anomalies?.length ?? 0) > 0 && (
        <div className="grid grid-cols-2 gap-4">
          {findings!.metric_anomalies.slice(0, 4).map((ma, i) => (
            <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{ma.metric_name}</span>
                <span className={`text-xs font-bold ${
                  ma.severity === 'critical' || ma.severity === 'high' ? 'text-red-500' : 'text-[#07b6d5]'
                }`}>
                  {ma.current_value.toFixed(1)}{ma.metric_name.includes('%') || ma.metric_name.includes('percent') ? '%' : ''}
                </span>
              </div>
              <div className="h-16 flex items-end gap-1">
                {/* Mini bar chart visualization */}
                {Array.from({ length: 8 }, (_, j) => {
                  const progress = (j + 1) / 8;
                  const height = Math.min(progress * (ma.deviation_percent / 100) * 100, 100);
                  const isHot = j >= 5;
                  return (
                    <div
                      key={j}
                      className={`w-full rounded-t-sm ${
                        isHot
                          ? ma.severity === 'critical' || ma.severity === 'high'
                            ? 'bg-red-500'
                            : 'bg-[#07b6d5]'
                          : `bg-[#07b6d5]/${20 + j * 10}`
                      }`}
                      style={{ height: `${Math.max(height, 10)}%` }}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* K8s Health Grid - matches reference */}
      {k8sEvents.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60">
            <span className="text-[11px] font-bold uppercase tracking-wider">K8s Events</span>
          </div>
          <div className="p-4 space-y-2">
            {k8sEvents.map((ke, i) => (
              <div key={i} className="flex items-center gap-3">
                <span className={`w-2 h-2 rounded-full ${ke.type === 'Warning' ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
                <span className="text-[11px] font-mono text-slate-300">{ke.involved_object}</span>
                <span className="text-[11px] text-slate-400">{ke.reason}: {ke.message}</span>
                <span className="text-[10px] text-slate-600 ml-auto">{ke.count}x</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Topology Hotspots - matches reference */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <span className="text-[11px] font-bold uppercase tracking-wider">Topology Hotspots</span>
          <span className="text-[10px] text-primary bg-primary/10 px-2 py-0.5 rounded">Heatmap Active</span>
        </div>
        <div className="h-48 relative bg-slate-950/40 rounded-lg border border-slate-800/50 flex items-center justify-center overflow-hidden">
          <svg className="w-full h-full" viewBox="0 0 400 200">
            <path d="M100,100 L200,60 M100,100 L200,140 M200,60 L300,100 M200,140 L300,100" stroke="#1e293b" strokeWidth="2" />
            <circle cx="100" cy="100" fill="#07b6d5" r="10" />
            <circle cx="200" cy="60" fill="#07b6d5" r="10" />
            <circle cx="200" cy="140" fill="#ef4444" r="12" className="animate-pulse" />
            <circle cx="300" cy="100" fill="#07b6d5" r="10" />
            <text fill="#64748b" fontFamily="monospace" fontSize="10" x="80" y="80">Ingress</text>
            <text fill="#64748b" fontFamily="monospace" fontSize="10" x="180" y="40">Auth-Svc</text>
            <text fill="#ef4444" fontFamily="monospace" fontSize="10" fontWeight="bold" x="160" y="170">Redis-C (CRITICAL)</text>
            <text fill="#64748b" fontFamily="monospace" fontSize="10" x="280" y="80">Postgres</text>
          </svg>
        </div>
      </div>

      {/* Evidence items */}
      {evidenceItems.length > 0 && (
        <div className="space-y-2">
          {evidenceItems.map((item, i) => (
            <div key={i} className={`border rounded-lg px-3 py-2.5 ${severityColor[item.severity]}`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-bold uppercase tracking-wider opacity-70">{item.source}</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/20">{item.severity}</span>
              </div>
              <p className="text-sm">{item.claim}</p>
            </div>
          ))}
        </div>
      )}

      {/* Recent events feed if no other data yet */}
      {errorPatterns.length === 0 && evidenceItems.length === 0 && events.length > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60">
            <span className="text-[11px] font-bold uppercase tracking-wider">Agent Activity Feed</span>
          </div>
          <div className="p-4 font-mono text-[11px] space-y-1 text-slate-400 max-h-[300px] overflow-y-auto custom-scrollbar">
            {events.slice(-20).map((ev, i) => (
              <div key={i} className="flex gap-3">
                <span className="text-slate-600 shrink-0">
                  {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                <span className={`font-bold shrink-0 ${
                  ev.event_type === 'error' ? 'text-red-400' :
                  ev.event_type === 'warning' ? 'text-amber-400' :
                  ev.event_type === 'success' ? 'text-green-400' : 'text-slate-500'
                }`}>
                  [{ev.event_type.toUpperCase()}]
                </span>
                <span className="text-[#07b6d5]">{ev.agent_name}</span>
                <span className="truncate">{ev.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Timeline Tab
const TimelineTab: React.FC<{
  events: TaskEvent[];
  breadcrumbs: V4SessionStatus['breadcrumbs'];
}> = ({ events, breadcrumbs }) => {
  const timelineItems = [
    ...events.map((e) => ({
      time: e.timestamp,
      agent: e.agent_name,
      action: e.message,
      type: e.event_type as string,
    })),
    ...(breadcrumbs || []).map((b) => ({
      time: b.timestamp,
      agent: b.agent_name,
      action: `${b.action}: ${b.detail}`,
      type: 'breadcrumb',
    })),
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

  if (timelineItems.length === 0) {
    return <EmptyState message="Timeline will populate as agents work..." />;
  }

  const dotColor: Record<string, string> = {
    started: 'bg-blue-400',
    progress: 'bg-slate-400',
    success: 'bg-green-400',
    warning: 'bg-orange-400',
    error: 'bg-red-400',
    breadcrumb: 'bg-[#07b6d5]',
  };

  return (
    <div className="relative pl-6">
      <div className="absolute left-2 top-0 bottom-0 w-px bg-slate-800" />
      <div className="space-y-3">
        {timelineItems.map((item, i) => (
          <div key={i} className="relative">
            <div
              className={`absolute left-[-18px] top-1.5 w-2.5 h-2.5 rounded-full border-2 border-[#0f2023] ${
                dotColor[item.type] || 'bg-slate-400'
              }`}
            />
            <div className="bg-slate-900/40 border border-slate-800 rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 text-xs mb-1">
                <span className="text-slate-500 font-mono">
                  {new Date(item.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
                <span className="text-[#07b6d5] font-medium">{item.agent}</span>
              </div>
              <p className="text-sm text-slate-300">{item.action}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Findings Tab
const FindingsTab: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  if (!findings || (findings.findings?.length ?? 0) === 0) {
    return <EmptyState message="No findings yet. Analysis in progress..." />;
  }

  return (
    <div className="space-y-3">
      {findings.findings.map((finding, i) => {
        const verdict = findings.critic_verdicts?.find((v) => v.finding_index === i);
        return (
          <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <h4 className="text-sm font-medium text-white flex-1">{finding.title}</h4>
              <span className={`text-[10px] px-2 py-0.5 rounded-full ${severityColor[finding.severity]}`}>
                {finding.severity}
              </span>
              {verdict && (
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${verdictColor[verdict.verdict]}`}>
                  {verdict.verdict}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mb-2">{finding.description}</p>
            <div className="flex items-center gap-3 text-[10px] text-slate-500">
              <span>Agent: {finding.agent_name}</span>
              <span>Confidence: {Math.round(finding.confidence * 100)}%</span>
              {finding.suggested_fix && (
                <span className="text-[#07b6d5]">Has fix suggestion</span>
              )}
            </div>
            {verdict && (
              <p className="text-xs text-slate-500 mt-2 italic border-t border-slate-800 pt-2">
                Critic: {verdict.reasoning}
              </p>
            )}
          </div>
        );
      })}

      {(findings.negative_findings?.length ?? 0) > 0 && (
        <div className="mt-4">
          <h4 className="text-xs text-slate-500 uppercase tracking-wider mb-2">Ruled Out</h4>
          {findings.negative_findings.map((nf, i) => (
            <div key={i} className="bg-slate-800/30 border border-slate-800/50 rounded-lg px-3 py-2 mb-1">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">{nf.agent}</span>
                <span className="text-xs text-slate-400">{nf.description}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Metrics Tab
const MetricsTab: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  if (!findings || (findings.metric_anomalies?.length ?? 0) === 0) {
    return <EmptyState message="No metric anomalies detected yet..." />;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {findings.metric_anomalies.map((ma, i) => (
          <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{ma.metric_name}</span>
              <span className={`text-xs font-bold font-mono ${
                ma.severity === 'critical' || ma.severity === 'high' ? 'text-red-500' : 'text-[#07b6d5]'
              }`}>
                {ma.direction === 'above' ? '+' : '-'}{Math.round(ma.deviation_percent)}%
              </span>
            </div>
            <div className="flex items-center gap-4 text-[10px] text-slate-500 mb-3">
              <span>Current: {ma.current_value.toFixed(2)}</span>
              <span>Baseline: {ma.baseline_value.toFixed(2)}</span>
            </div>
            <div className="h-12 flex items-end gap-1">
              {Array.from({ length: 8 }, (_, j) => {
                const height = 10 + (j * 12);
                const isHot = j >= 5;
                return (
                  <div
                    key={j}
                    className={`w-full rounded-t-sm ${
                      isHot && (ma.severity === 'critical' || ma.severity === 'high')
                        ? 'bg-red-500'
                        : `bg-[#07b6d5]`
                    }`}
                    style={{ height: `${Math.min(height, 100)}%`, opacity: isHot ? 1 : 0.2 + j * 0.1 }}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Pod statuses */}
      {(findings.pod_statuses?.length ?? 0) > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60">
            <span className="text-[11px] font-bold uppercase tracking-wider">K8s Pod Status</span>
          </div>
          <div className="p-4 grid grid-cols-4 gap-4">
            <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
              <div className="text-[10px] text-slate-500 mb-1">Total Pods</div>
              <div className="text-lg font-bold font-mono">{findings.pod_statuses.length}</div>
            </div>
            <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
              <div className="text-[10px] text-slate-500 mb-1">Restarts</div>
              <div className="text-lg font-bold font-mono text-amber-500">
                {findings.pod_statuses.reduce((s, p) => s + p.restart_count, 0)}
              </div>
            </div>
            <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
              <div className="text-[10px] text-slate-500 mb-1">Healthy</div>
              <div className="text-lg font-bold font-mono text-green-500">
                {findings.pod_statuses.filter((p) => p.ready).length}
              </div>
            </div>
            <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
              <div className="text-[10px] text-slate-500 mb-1">Unhealthy</div>
              <div className="text-lg font-bold font-mono text-red-500">
                {findings.pod_statuses.filter((p) => !p.ready).length}
              </div>
            </div>
          </div>
          <div className="px-4 py-3 bg-slate-800/20 border-t border-slate-800">
            <div className="flex items-center gap-4 overflow-x-auto pb-1 custom-scrollbar">
              {findings.pod_statuses.map((pod, i) => (
                <div key={i} className="flex items-center gap-2 shrink-0">
                  <span className={`w-2 h-2 rounded-full ${pod.ready ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
                  <span className="text-[11px] font-mono">{pod.pod_name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="flex items-center justify-center h-full min-h-[200px] text-slate-500">
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-slate-800 border-t-[#07b6d5] rounded-full animate-spin mx-auto mb-3" />
      <p className="text-sm">{message}</p>
    </div>
  </div>
);

export default EvidenceStack;
