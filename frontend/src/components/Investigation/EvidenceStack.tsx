import React, { useState, useEffect, useCallback } from 'react';
import type { V4Findings, V4SessionStatus, TaskEvent, Severity, CriticVerdict, ChangeCorrelation, BlastRadiusData, SeverityData, SpanInfo, Breadcrumb, ServiceFlowStep, CorrelatedSignalGroup, EventMarker } from '../../types';
import { getFindings, getSessionStatus } from '../../services/api';

interface EvidenceStackProps {
  sessionId: string;
  events: TaskEvent[];
}

type TabId = 'evidence' | 'timeline' | 'findings' | 'metrics' | 'changes' | 'traces';

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

const severityPriorityColor: Record<string, { border: string; bg: string; text: string }> = {
  P1: { border: 'border-red-500/40', bg: 'bg-red-500/10', text: 'text-red-400' },
  P2: { border: 'border-orange-500/40', bg: 'bg-orange-500/10', text: 'text-orange-400' },
  P3: { border: 'border-yellow-500/40', bg: 'bg-yellow-500/10', text: 'text-yellow-400' },
  P4: { border: 'border-blue-500/40', bg: 'bg-blue-500/10', text: 'text-blue-400' },
};

const tabs: { id: TabId; label: string; icon: string }[] = [
  { id: 'evidence', label: 'Evidence', icon: 'inventory_2' },
  { id: 'timeline', label: 'Timeline', icon: 'timeline' },
  { id: 'findings', label: 'Findings', icon: 'target' },
  { id: 'metrics', label: 'Metrics', icon: 'bar_chart' },
  { id: 'changes', label: 'Changes', icon: 'difference' },
  { id: 'traces', label: 'Traces', icon: 'stacked_bar_chart' },
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

  // Reactive: refetch when summary/finding/phase_change events arrive
  const relevantEventCount = events.filter(
    (e) => e.event_type === 'summary' || e.event_type === 'finding' || e.event_type === 'phase_change'
  ).length;

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Instant update on relevant events
  useEffect(() => {
    if (relevantEventCount > 0) {
      fetchData();
    }
  }, [relevantEventCount, fetchData]);

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
        {activeTab === 'changes' && <ChangesTab findings={findings} />}
        {activeTab === 'traces' && <TracesTab findings={findings} events={events} />}
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

      {/* Pod Health */}
      <PodHealthSection findings={findings} />

      {/* Topology — data-driven from trace spans and impacted files */}
      <TopologySection findings={findings} />

      {/* Blast Radius */}
      <BlastRadiusCard findings={findings} />

      {/* Source of Change */}
      <ChangeCorrelationsSection findings={findings} />

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

// Metrics Tab — anomaly cards with deviation indicators
const MetricsTab: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  if (!findings || (findings.metric_anomalies?.length ?? 0) === 0) {
    return <EmptyState message="No metric anomalies detected yet..." />;
  }

  const anomalySeverityColor: Record<string, { border: string; bg: string; text: string }> = {
    critical: { border: 'border-red-500/30', bg: 'bg-red-500/10', text: 'text-red-400' },
    high: { border: 'border-orange-500/30', bg: 'bg-orange-500/10', text: 'text-orange-400' },
    medium: { border: 'border-yellow-500/30', bg: 'bg-yellow-500/10', text: 'text-yellow-400' },
    low: { border: 'border-blue-500/30', bg: 'bg-blue-500/10', text: 'text-blue-400' },
    info: { border: 'border-slate-700', bg: 'bg-slate-900/40', text: 'text-slate-400' },
  };

  const signalTypeStyle: Record<string, string> = {
    RED: 'bg-red-500/20 text-red-400 border-red-500/30',
    USE: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  };

  // Compute event marker positions as percentage of the incident window
  const computePositionPercent = (timestamp: string): number => {
    const markers = findings?.event_markers || [];
    const anomalies = findings?.metric_anomalies || [];
    const allTimes = [
      ...markers.map((m) => new Date(m.timestamp).getTime()),
      ...anomalies.map((a) => new Date(a.spike_start || a.timestamp).getTime()),
      ...anomalies.map((a) => new Date(a.spike_end || a.timestamp).getTime()),
    ].filter((t) => !isNaN(t));
    if (allTimes.length < 2) return 50;
    const minT = Math.min(...allTimes);
    const maxT = Math.max(...allTimes);
    const range = maxT - minT || 1;
    const t = new Date(timestamp).getTime();
    return Math.max(2, Math.min(98, ((t - minT) / range) * 100));
  };

  return (
    <div className="space-y-4">
      {/* Correlated Signal Groups */}
      {(findings?.correlated_signals?.length ?? 0) > 0 && (
        <div className="space-y-3">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Golden Signal Correlations</div>
          {findings!.correlated_signals.map((cs, i) => (
            <div key={i} className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold border ${signalTypeStyle[cs.signal_type] || signalTypeStyle.RED}`}>
                  {cs.signal_type}
                </span>
                <span className="text-[11px] font-bold text-slate-200">{cs.group_name}</span>
              </div>
              <p className="text-xs text-slate-400 mb-2">{cs.narrative}</p>
              <div className="flex flex-wrap gap-1.5">
                {cs.metrics.map((m, j) => (
                  <span key={j} className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/50">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Event Markers Timeline */}
      {(findings?.event_markers?.length ?? 0) > 0 && (
        <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-3">
            Log Events on Timeline
          </div>
          <div className="relative h-8 bg-slate-800/50 rounded-lg overflow-visible">
            {findings!.event_markers.map((marker, i) => (
              <div
                key={i}
                className={`absolute top-0 h-full w-0.5 ${
                  marker.severity === 'critical' || marker.severity === 'high' ? 'bg-red-500' :
                  marker.severity === 'medium' ? 'bg-amber-500' : 'bg-blue-500'
                }`}
                style={{ left: `${computePositionPercent(marker.timestamp)}%` }}
                title={`${marker.label} (${marker.source})`}
              >
                <div className="absolute -top-5 left-1 text-[9px] text-red-400 whitespace-nowrap">
                  {marker.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Anomaly Cards Grid */}
      <div className="grid grid-cols-2 gap-4">
        {findings.metric_anomalies.map((ma, i) => {
          const style = anomalySeverityColor[ma.severity] || anomalySeverityColor.info;
          return (
            <div key={i} className={`border rounded-xl p-4 ${style.border} ${style.bg}`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300">{ma.metric_name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${style.text} bg-black/20`}>
                  {ma.severity}
                </span>
              </div>
              <div className="flex items-baseline gap-3 mb-3">
                <div>
                  <div className="text-[10px] text-slate-500 mb-0.5">Current</div>
                  <div className="text-lg font-bold font-mono text-white">{ma.current_value.toFixed(1)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-slate-500 mb-0.5">Baseline</div>
                  <div className="text-sm font-mono text-slate-400">{ma.baseline_value.toFixed(1)}</div>
                </div>
                <div className="ml-auto text-right">
                  <div className="text-[10px] text-slate-500 mb-0.5">Deviation</div>
                  <div className={`text-sm font-mono font-bold ${style.text}`}>
                    {ma.direction === 'above' ? '\u25B2' : '\u25BC'} {ma.deviation_percent > 0 ? '+' : ''}{Math.round(ma.deviation_percent)}%
                  </div>
                </div>
              </div>
              {ma.correlation_to_incident && (
                <p className="text-[10px] text-slate-400 mb-2 italic">{ma.correlation_to_incident}</p>
              )}
              {/* Deviation bar */}
              <div className="h-2 bg-black/20 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${style.text.replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min(Math.abs(ma.deviation_percent), 100)}%` }}
                />
              </div>
              {ma.confidence_score != null && (
                <div className="text-[9px] text-slate-500 mt-1.5 text-right">
                  Confidence: {ma.confidence_score}%
                </div>
              )}
            </div>
          );
        })}
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

// Pod Health Section (for evidence tab)
const PodHealthSection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const pods = findings?.pod_statuses || [];
  if (pods.length === 0) return null;

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-blue-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>dns</span>
          <span className="text-[11px] font-bold uppercase tracking-wider">Pod Health</span>
        </div>
        <span className="text-[10px] font-mono text-slate-500">{pods.length} pods</span>
      </div>
      <div className="p-4 space-y-2">
        {pods.map((pod, i) => (
          <div key={i} className="flex items-center gap-3 text-[11px]">
            <span className={`w-2 h-2 rounded-full ${pod.ready ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
            <span className="font-mono text-slate-300">{pod.pod_name}</span>
            <span className="text-slate-500">{pod.status}</span>
            {pod.restart_count > 0 && (
              <span className="text-amber-400 font-bold">{pod.restart_count} restarts</span>
            )}
            {pod.oom_killed && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">OOM</span>
            )}
            {pod.crash_loop && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">CrashLoop</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// Data-driven topology section
const TopologySection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const traceSpans = findings?.trace_spans || [];
  const impactedFiles = findings?.impacted_files || [];

  // Extract service dependencies from trace spans
  const services = new Set<string>();
  const edges: { from: string; to: string }[] = [];
  traceSpans.forEach((span) => {
    services.add(span.service);
    if (span.parent_span_id) {
      const parent = traceSpans.find((s) => s.span_id === span.parent_span_id);
      if (parent && parent.service !== span.service) {
        edges.push({ from: parent.service, to: span.service });
      }
    }
  });

  const hasData = services.size > 0 || impactedFiles.length > 0;

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[11px] font-bold uppercase tracking-wider">Topology</span>
        {hasData && (
          <span className="text-[10px] text-primary bg-primary/10 px-2 py-0.5 rounded">Live Data</span>
        )}
      </div>
      {hasData ? (
        <div className="space-y-3">
          {/* Service nodes from traces */}
          {services.size > 0 && (
            <div className="flex flex-wrap gap-2">
              {[...services].map((svc) => {
                const hasError = traceSpans.some((s) => s.service === svc && s.error);
                return (
                  <div
                    key={svc}
                    className={`px-3 py-1.5 rounded-lg border text-[11px] font-mono ${
                      hasError
                        ? 'bg-red-500/10 border-red-500/30 text-red-400'
                        : 'bg-[#07b6d5]/10 border-[#07b6d5]/30 text-[#07b6d5]'
                    }`}
                  >
                    {svc}
                  </div>
                );
              })}
            </div>
          )}
          {/* Dependency arrows */}
          {edges.length > 0 && (
            <div className="space-y-1">
              {[...new Set(edges.map((e) => `${e.from}→${e.to}`))].map((edge) => {
                const [from, to] = edge.split('→');
                return (
                  <div key={edge} className="text-[10px] text-slate-500 font-mono">
                    {from} → {to}
                  </div>
                );
              })}
            </div>
          )}
          {/* Impacted files */}
          {impactedFiles.length > 0 && (
            <div className="border-t border-slate-800 pt-3">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider">Impacted Files</span>
              <div className="mt-2 space-y-1">
                {impactedFiles.map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px]">
                    <span className={`w-1.5 h-1.5 rounded-full ${
                      f.impact_type === 'root_cause' ? 'bg-red-500' : 'bg-[#07b6d5]'
                    }`} />
                    <span className="font-mono text-slate-300">{f.file_path}</span>
                    <span className="text-[10px] text-slate-500">{f.impact_type}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="h-24 flex items-center justify-center text-[11px] text-slate-600">
          Topology will populate as agents discover dependencies
        </div>
      )}
    </div>
  );
};

// ─── Blast Radius Card ────────────────────────────────────────────────────

const BlastRadiusCard: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const blast = findings?.blast_radius;
  const severity = findings?.severity_recommendation;
  if (!blast) return null;

  const sev = severity?.recommended_severity || 'P4';
  const style = severityPriorityColor[sev] || severityPriorityColor.P4;
  const totalAffected = (blast.upstream_affected?.length || 0) + (blast.downstream_affected?.length || 0);
  const defaultExpanded = sev === 'P1' || sev === 'P2';
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`border rounded-xl overflow-hidden ${style.border} ${style.bg}`}>
      {/* L1: Severity badge + scope */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 text-left flex items-center gap-3"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined', color: style.text.includes('red') ? '#f87171' : style.text.includes('orange') ? '#fb923c' : style.text.includes('yellow') ? '#facc15' : '#60a5fa' }}>
          hub
        </span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Blast Radius</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${style.text} bg-black/20`}>
          {sev}
        </span>
        <span className="text-[11px] text-slate-400">
          {blast.scope.replace(/_/g, ' ')} — {totalAffected} affected
        </span>
      </button>
      {/* L2: Service list */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-black/10 pt-3 space-y-3">
          {severity?.reasoning && (
            <p className="text-xs text-slate-400">{severity.reasoning}</p>
          )}
          <div className="space-y-1.5">
            {blast.upstream_affected?.map((svc, i) => (
              <div key={`up-${i}`} className="flex items-center gap-2 text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                <span className="font-mono text-slate-300">{svc}</span>
                <span className="text-[10px] text-slate-500">upstream</span>
              </div>
            ))}
            {blast.downstream_affected?.map((svc, i) => (
              <div key={`dn-${i}`} className="flex items-center gap-2 text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                <span className="font-mono text-slate-300">{svc}</span>
                <span className="text-[10px] text-slate-500">downstream</span>
              </div>
            ))}
            {blast.shared_resources?.map((res, i) => (
              <div key={`sh-${i}`} className="flex items-center gap-2 text-[11px]">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
                <span className="font-mono text-slate-300">{res}</span>
                <span className="text-[10px] text-slate-500">shared</span>
              </div>
            ))}
          </div>
          {blast.estimated_user_impact && (
            <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800">
              Est. User Impact: {blast.estimated_user_impact}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Change Correlations Section ──────────────────────────────────────────

const ChangeCorrelationsSection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const correlations = findings?.change_correlations || [];
  const [expanded, setExpanded] = useState(correlations.some((c) => c.risk_score > 0.8));

  if (correlations.length === 0) return null;

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 text-left flex items-center gap-3"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
          difference
        </span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Source of Change</span>
        <span className="text-[10px] text-slate-500 ml-auto">{correlations.length} changes</span>
      </button>
      {expanded && (
        <div className="border-t border-slate-800 divide-y divide-slate-800/50">
          {correlations.map((corr, i) => (
            <ChangeCorrelationRow key={i} correlation={corr} />
          ))}
        </div>
      )}
    </div>
  );
};

const ChangeCorrelationRow: React.FC<{ correlation: ChangeCorrelation }> = ({ correlation }) => {
  const [expanded, setExpanded] = useState(correlation.risk_score > 0.8);
  const riskPct = Math.round(correlation.risk_score * 100);
  const riskColor = riskPct >= 80 ? 'text-red-400' : riskPct >= 50 ? 'text-amber-400' : 'text-blue-400';

  return (
    <div className="px-4 py-2.5">
      {/* L1: One-line summary */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left flex items-center gap-2"
        aria-expanded={expanded}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="text-[11px] font-mono text-violet-400">
          {correlation.change_id?.slice(0, 8) || '—'}
        </span>
        <span className="text-[11px] text-slate-300 truncate flex-1">{correlation.description}</span>
        <span className={`text-[10px] font-bold ${riskColor}`}>{riskPct}%</span>
      </button>
      {/* L2: Details */}
      {expanded && (
        <div className="pl-6 mt-2 space-y-1 text-[10px] text-slate-400">
          <div>Author: {correlation.author}</div>
          <div>Type: {correlation.change_type.replace(/_/g, ' ')}</div>
          {correlation.timestamp && (
            <div>Time: {new Date(correlation.timestamp).toLocaleString()}</div>
          )}
          {correlation.files_changed.length > 0 && (
            <div>Files: {correlation.files_changed.length} changed</div>
          )}
          <div>Temporal correlation: {Math.round(correlation.temporal_correlation * 100)}%</div>
        </div>
      )}
    </div>
  );
};

// ─── Changes Tab ──────────────────────────────────────────────────────────

const ChangesTab: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const correlations = findings?.change_correlations || [];

  if (correlations.length === 0) {
    return <EmptyState message="No correlated changes detected. The Change Agent will populate data when a repository URL is provided." />;
  }

  return (
    <div className="space-y-4">
      <ChangeCorrelationsSection findings={findings} />
    </div>
  );
};

// ─── Temporal Flow Timeline ────────────────────────────────────────────────

const TemporalFlowTimeline: React.FC<{
  steps: ServiceFlowStep[];
  source: string;
  confidence: number;
}> = ({ steps, source, confidence }) => {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const serviceCount = new Set(steps.map((s) => s.service)).size;

  const nodeColor = (status: ServiceFlowStep['status'], isLast: boolean) => {
    if (status === 'error') {
      return isLast
        ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)] animate-pulse'
        : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]';
    }
    if (status === 'timeout') return 'bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.4)]';
    return 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]';
  };

  const statusBadge = (status: ServiceFlowStep['status'], detail: string) => {
    const colors: Record<string, string> = {
      ok: 'text-green-400 border-green-500/30 bg-green-500/10',
      error: 'text-red-400 border-red-500/30 bg-red-500/10',
      timeout: 'text-orange-400 border-orange-500/30 bg-orange-500/10',
    };
    return (
      <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border ${colors[status] || colors.ok}`}>
        {detail || status.toUpperCase()}
      </span>
    );
  };

  // Find the last error index for the pulse effect
  const lastErrorIdx = (() => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].status === 'error') return i;
    }
    return -1;
  })();

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
            timeline
          </span>
          <span className="text-[11px] font-bold uppercase tracking-wider">Temporal Flow</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500">
            {serviceCount} services, {steps.length} steps
          </span>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20 font-mono">
            {source} {confidence}%
          </span>
        </div>
      </div>

      {/* Timeline */}
      <div className="p-4 relative">
        {/* Vertical dashed line */}
        <div className="absolute left-[31px] top-4 bottom-4 border-l border-dashed border-slate-700" />

        <div className="space-y-3">
          {steps.map((step, i) => (
            <div key={i} className="relative flex items-start gap-3 pl-2">
              {/* Node circle */}
              <div className="relative z-10 flex-shrink-0 mt-1">
                <div
                  className={`w-4 h-4 rounded-full border-2 border-slate-900 ${nodeColor(step.status, i === lastErrorIdx)}`}
                />
              </div>

              {/* Service card */}
              <button
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                className="flex-1 bg-slate-800/30 p-2 rounded-lg border border-slate-700/50 text-left hover:border-slate-600/50 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tight shrink-0">
                      {step.service}
                    </span>
                    <span className="text-[11px] font-mono text-slate-300 truncate">
                      {step.operation}
                    </span>
                  </div>
                  {statusBadge(step.status, step.status_detail)}
                </div>

                {/* L3: Expanded details */}
                {expandedIdx === i && (
                  <div className="mt-2 pt-2 border-t border-slate-700/50 space-y-1">
                    {step.timestamp && (
                      <div className="text-[10px] text-slate-500 font-mono">
                        {new Date(step.timestamp).toLocaleString()}
                      </div>
                    )}
                    {step.message && (
                      <div className="text-[10px] text-slate-400 font-mono break-all">
                        {step.message}
                      </div>
                    )}
                  </div>
                )}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ─── Traces Tab — Waterfall Visualization ─────────────────────────────────

const TracesTab: React.FC<{ findings: V4Findings | null; events: TaskEvent[] }> = ({ findings, events }) => {
  const serviceFlow = findings?.service_flow || [];
  const spans = findings?.trace_spans || [];

  return (
    <div className="space-y-6">
      {/* Temporal Flow from log agent */}
      {serviceFlow.length > 0 && (
        <TemporalFlowTimeline
          steps={serviceFlow}
          source={findings?.flow_source || 'elasticsearch'}
          confidence={findings?.flow_confidence || 0}
        />
      )}

      {/* Existing trace waterfall from tracing agent */}
      {spans.length > 0 && (
        <TraceWaterfall spans={spans} />
      )}

      {/* Fallback: pseudo-spans from events */}
      {serviceFlow.length === 0 && spans.length === 0 && (
        <TraceFallback events={events} />
      )}
    </div>
  );
};

const TraceFallback: React.FC<{ events: TaskEvent[] }> = ({ events }) => {
  const pseudoSpans = events
    .filter((e) => e.event_type === 'tool_call' || e.event_type === 'finding')
    .slice(0, 20);

  if (pseudoSpans.length === 0) {
    return <EmptyState message="No trace data available. Traces will populate when the Trace Walker agent completes analysis." />;
  }

  return (
    <div className="space-y-4">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider">Reconstructed from Agent Activity</div>
      <div className="space-y-1">
        {pseudoSpans.map((ev, i) => (
          <div key={i} className="flex items-center gap-3 text-[11px]">
            <span className="text-slate-600 w-16 shrink-0 font-mono">
              {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            <span className={`w-2 h-2 rounded-full ${ev.event_type === 'finding' ? 'bg-amber-400' : 'bg-slate-500'}`} />
            <span className="text-[#07b6d5] shrink-0">{ev.agent_name}</span>
            <span className="text-slate-400 truncate">{ev.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const TraceWaterfall: React.FC<{ spans: SpanInfo[] }> = ({ spans }) => {
  const totalDuration = Math.max(...spans.map((s) => s.duration_ms), 1);
  const errorCount = spans.filter((s) => s.status === 'error' || s.error).length;

  // Build depth map from parent_span_id
  const depthMap = new Map<string, number>();
  const computeDepth = (span: SpanInfo): number => {
    if (depthMap.has(span.span_id)) return depthMap.get(span.span_id)!;
    if (!span.parent_span_id) {
      depthMap.set(span.span_id, 0);
      return 0;
    }
    const parent = spans.find((s) => s.span_id === span.parent_span_id);
    const depth = parent ? computeDepth(parent) + 1 : 0;
    depthMap.set(span.span_id, depth);
    return depth;
  };
  spans.forEach(computeDepth);

  return (
    <div className="space-y-4">
      {/* L1: Summary bar */}
      <div className="flex items-center gap-4 text-[11px]">
        <span className="text-slate-400">{spans.length} spans</span>
        <span className="text-slate-400">Total: {totalDuration.toFixed(0)}ms</span>
        {errorCount > 0 && (
          <span className="text-red-400 font-bold">{errorCount} errors</span>
        )}
      </div>

      {/* L2: Waterfall */}
      <div className="space-y-1">
        {spans.map((span, i) => (
          <TraceSpanRow key={i} span={span} totalDuration={totalDuration} depth={depthMap.get(span.span_id) || 0} />
        ))}
      </div>
    </div>
  );
};

const TraceSpanRow: React.FC<{ span: SpanInfo; totalDuration: number; depth: number }> = ({ span, totalDuration, depth }) => {
  const [expanded, setExpanded] = useState(false);
  const widthPct = Math.max((span.duration_ms / totalDuration) * 100, 2);
  const isError = span.status === 'error' || span.error;
  const barColor = isError ? 'bg-red-500' : span.status === 'timeout' ? 'bg-orange-500' : 'bg-green-500';

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left flex items-center gap-2 py-1 hover:bg-slate-800/30 rounded transition-colors"
        aria-expanded={expanded}
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        <span
          className={`material-symbols-outlined text-[10px] text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span className="text-[10px] font-mono text-[#07b6d5] w-20 shrink-0 truncate">{span.service}</span>
        <span className="text-[10px] text-slate-400 w-28 shrink-0 truncate">{span.operation}</span>
        <div className="flex-1 h-4 bg-slate-800/50 rounded overflow-hidden relative">
          <div
            className={`h-full rounded ${barColor}`}
            style={{ width: `${widthPct}%` }}
          />
        </div>
        <span className={`text-[10px] font-mono w-14 text-right shrink-0 ${isError ? 'text-red-400' : 'text-slate-400'}`}>
          {span.duration_ms.toFixed(0)}ms
        </span>
        {isError && (
          <span className="text-red-400 text-[10px]">&#10005;</span>
        )}
      </button>
      {/* L3: Expanded span details */}
      {expanded && (
        <div className="ml-8 pl-4 border-l border-slate-800 py-2 space-y-1 text-[10px] text-slate-400" style={{ marginLeft: `${depth * 16 + 24}px` }}>
          <div>Span ID: <span className="font-mono">{span.span_id}</span></div>
          {span.parent_span_id && <div>Parent: <span className="font-mono">{span.parent_span_id}</span></div>}
          <div>Status: <span className={isError ? 'text-red-400 font-bold' : 'text-green-400'}>{span.status}</span></div>
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
