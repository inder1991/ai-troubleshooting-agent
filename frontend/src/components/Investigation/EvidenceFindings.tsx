import React, { useState, useMemo } from 'react';
import type {
  V4Findings, V4SessionStatus, TaskEvent, Severity, ErrorPattern,
  CriticVerdict, ChangeCorrelation, BlastRadiusData, SeverityData,
  SpanInfo, ServiceFlowStep, PatientZero, MetricAnomaly,
} from '../../types';
import AgentFindingCard from './cards/AgentFindingCard';
import CausalRoleBadge from './cards/CausalRoleBadge';
import StackTraceTelescope from './cards/StackTraceTelescope';
import SaturationGauge from './cards/SaturationGauge';
import AnomalySparkline, { findMatchingTimeSeries } from './cards/AnomalySparkline';

interface EvidenceFindingsProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
}

const severityColor: Record<Severity, string> = {
  critical: 'bg-red-500/20 text-red-300 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  low: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  info: 'bg-slate-500/20 text-slate-300 border-slate-500/30',
};

const verdictColor: Record<CriticVerdict['verdict'], string> = {
  validated: 'bg-green-500/20 text-green-300',
  challenged: 'bg-red-500/20 text-red-300',
  insufficient_data: 'bg-yellow-500/20 text-yellow-300',
};

const severityPriorityColor: Record<string, { border: string; bg: string; text: string }> = {
  P1: { border: 'border-red-500/40', bg: 'bg-red-500/10', text: 'text-red-400' },
  P2: { border: 'border-orange-500/40', bg: 'bg-orange-500/10', text: 'text-orange-400' },
  P3: { border: 'border-yellow-500/40', bg: 'bg-yellow-500/10', text: 'text-yellow-400' },
  P4: { border: 'border-blue-500/40', bg: 'bg-blue-500/10', text: 'text-blue-400' },
};

const EvidenceFindings: React.FC<EvidenceFindingsProps> = ({ findings, status: _status, events }) => {

  const errorPatterns = findings?.error_patterns || [];
  const rootCausePatterns = errorPatterns.filter((p) => p.causal_role === 'root_cause');
  const cascadingPatterns = errorPatterns.filter((p) => p.causal_role === 'cascading_failure');
  const correlatedPatterns = errorPatterns.filter(
    (p) => p.causal_role === 'correlated_anomaly' || (!p.causal_role && rootCausePatterns.length > 0)
  );
  const ungroupedPatterns = rootCausePatterns.length === 0 ? errorPatterns : [];

  const sev = findings?.severity_recommendation?.recommended_severity || 'P4';
  const sevStyle = severityPriorityColor[sev] || severityPriorityColor.P4;

  const hasContent = errorPatterns.length > 0 ||
    (findings?.findings?.length ?? 0) > 0 ||
    (findings?.metric_anomalies?.length ?? 0) > 0 ||
    (findings?.service_flow?.length ?? 0) > 0 ||
    events.length > 0;

  return (
    <div className="flex flex-col h-full bg-[#0f2023]">
      {/* Header */}
      <div className="h-12 border-b border-slate-800/50 flex items-center justify-between px-6 bg-slate-900/10 sticky top-0 z-10 backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-slate-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>radar</span>
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">Evidence and Findings</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${sevStyle.text} ${sevStyle.bg} border ${sevStyle.border}`}>
            {sev}
          </span>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            <span className="text-[10px] text-slate-500 font-medium">Live</span>
          </div>
        </div>
      </div>

      {/* Single scrollable stack */}
      <div className="flex-1 overflow-y-auto p-6 space-y-5 custom-scrollbar">
        {!hasContent ? (
          <EmptyState message="Collecting evidence... Agents are scanning logs, metrics, and traces." />
        ) : (
          <>
            {/* 1. Root Cause patterns */}
            {rootCausePatterns.length > 0 && (
              <section className="space-y-2">
                {rootCausePatterns.map((ep, i) => {
                  const saturationMetrics = getSaturationMetrics(findings?.metric_anomalies || []);
                  return (
                    <AgentFindingCard key={ep.pattern_id || `rc-${i}`} agent="L" title="Error Pattern">
                      <CausalRoleBadge role="root_cause" />
                      {saturationMetrics.length > 0 && (
                        <div className="flex gap-3 my-2">
                          {saturationMetrics.map((sm, si) => (
                            <SaturationGauge key={si} metricName={sm.metric_name} currentValue={sm.current_value} />
                          ))}
                        </div>
                      )}
                      <ErrorPatternContent pattern={ep} rank={i + 1} />
                    </AgentFindingCard>
                  );
                })}
              </section>
            )}

            {/* 2. Cascading patterns */}
            {cascadingPatterns.length > 0 && (
              <section className="space-y-2">
                {cascadingPatterns.map((ep, i) => (
                  <AgentFindingCard key={ep.pattern_id || `cas-${i}`} agent="L" title="Cascading Error">
                    <CausalRoleBadge role="cascading_failure" />
                    <ErrorPatternContent pattern={ep} rank={i + 1} />
                  </AgentFindingCard>
                ))}
              </section>
            )}

            {/* Ungrouped error patterns (when no causal_role data) */}
            {ungroupedPatterns.length > 0 && (
              <section className="space-y-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="material-symbols-outlined text-amber-500 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>receipt_long</span>
                  <span className="text-[11px] font-bold uppercase tracking-wider">Error Clusters</span>
                  <span className="text-[10px] font-mono text-slate-500">{ungroupedPatterns.length}</span>
                </div>
                {ungroupedPatterns.map((ep, i) => (
                  <ErrorPatternCluster key={ep.pattern_id || `ug-${i}`} pattern={ep} rank={i + 1} />
                ))}
              </section>
            )}

            {/* 3. High-severity findings */}
            {(findings?.findings?.length ?? 0) > 0 && (
              <section className="space-y-2">
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Findings</div>
                {findings!.findings
                  .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
                  .map((finding, i) => {
                    const verdict = findings!.critic_verdicts?.find((v) => v.finding_index === i);
                    const agentCode = getAgentCode(finding.agent_name);
                    return (
                      <AgentFindingCard key={finding.finding_id || i} agent={agentCode} title={finding.title}>
                        <p className="text-xs text-slate-400 mb-2">{finding.description}</p>
                        <div className="flex items-center gap-3 text-[10px] text-slate-500">
                          <span className={`px-1.5 py-0.5 rounded ${severityColor[finding.severity]}`}>{finding.severity}</span>
                          <span>Confidence: {Math.round(finding.confidence * 100)}%</span>
                          {verdict && (
                            <span className={`px-1.5 py-0.5 rounded ${verdictColor[verdict.verdict]}`}>
                              {verdict.verdict}
                            </span>
                          )}
                        </div>
                        {finding.suggested_fix && (
                          <p className="text-[10px] text-cyan-400 mt-2">Fix: {finding.suggested_fix}</p>
                        )}
                      </AgentFindingCard>
                    );
                  })}
              </section>
            )}

            {/* 4. Metric anomalies */}
            {(findings?.metric_anomalies?.length ?? 0) > 0 && (
              <section>
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Metric Anomalies</div>
                <div className="grid grid-cols-2 gap-3">
                  {findings!.metric_anomalies.map((ma, i) => {
                    const tsData = findMatchingTimeSeries(findings!.time_series_data || {}, ma.metric_name);
                    return (
                      <AgentFindingCard key={i} agent="M" title={ma.metric_name}>
                        <div className="flex items-baseline gap-3 mb-2">
                          <div className="text-xl font-bold font-mono text-white">{ma.current_value.toFixed(1)}</div>
                          <div className="text-xs font-mono text-slate-500">baseline {ma.baseline_value.toFixed(1)}</div>
                          <div className={`text-sm font-mono font-bold ml-auto ${
                            ma.severity === 'critical' || ma.severity === 'high' ? 'text-red-400' : 'text-cyan-400'
                          }`}>
                            {ma.direction === 'above' ? '\u25B2' : '\u25BC'}{Math.round(ma.deviation_percent)}%
                          </div>
                        </div>
                        <AnomalySparkline
                          dataPoints={tsData || []}
                          baselineValue={ma.baseline_value}
                          peakValue={ma.peak_value}
                          spikeStart={ma.spike_start}
                          spikeEnd={ma.spike_end}
                          severity={ma.severity}
                        />
                        {ma.correlation_to_incident && (
                          <p className="text-[10px] text-slate-400 italic mt-1.5">{ma.correlation_to_incident}</p>
                        )}
                      </AgentFindingCard>
                    );
                  })}
                </div>
              </section>
            )}

            {/* 5. K8s health + events */}
            {((findings?.k8s_events?.length ?? 0) > 0 || (findings?.pod_statuses?.length ?? 0) > 0) && (
              <section>
                <AgentFindingCard agent="K" title="Kubernetes Health">
                  {(findings?.pod_statuses?.length ?? 0) > 0 && (
                    <div className="grid grid-cols-4 gap-3 mb-3">
                      <StatBox label="Pods" value={findings!.pod_statuses.length} />
                      <StatBox label="Restarts" value={findings!.pod_statuses.reduce((s, p) => s + p.restart_count, 0)} color="text-amber-500" />
                      <StatBox label="Healthy" value={findings!.pod_statuses.filter((p) => p.ready).length} color="text-green-500" />
                      <StatBox label="Unhealthy" value={findings!.pod_statuses.filter((p) => !p.ready).length} color="text-red-500" />
                    </div>
                  )}
                  {(findings?.k8s_events?.length ?? 0) > 0 && (
                    <div className="space-y-1.5">
                      {findings!.k8s_events.map((ke, i) => (
                        <div key={i} className="flex items-center gap-2 text-[11px]">
                          <span className={`w-2 h-2 rounded-full ${ke.type === 'Warning' ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
                          <span className="font-mono text-slate-300">{ke.involved_object}</span>
                          <span className="text-slate-400 truncate">{ke.reason}: {ke.message}</span>
                          <span className="text-[10px] text-slate-600 ml-auto shrink-0">{ke.count}x</span>
                        </div>
                      ))}
                    </div>
                  )}
                </AgentFindingCard>
              </section>
            )}

            {/* 6. Blast Radius */}
            <BlastRadiusCard blast={findings?.blast_radius || null} severity={findings?.severity_recommendation || null} />

            {/* 7. Temporal Flow Timeline */}
            {(findings?.service_flow?.length ?? 0) > 0 && (
              <TemporalFlowTimeline
                steps={findings!.service_flow}
                source={findings?.flow_source || 'elasticsearch'}
                confidence={findings?.flow_confidence || 0}
                patientZero={findings?.patient_zero}
              />
            )}

            {/* 8. Change correlations */}
            <ChangeCorrelationsSection findings={findings} />

            {/* 9. Correlated anomalies */}
            {correlatedPatterns.length > 0 && (
              <section className="space-y-2">
                <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Correlated Anomalies</div>
                {correlatedPatterns.map((ep, i) => (
                  <AgentFindingCard key={ep.pattern_id || `cor-${i}`} agent="L" title="Correlated Pattern">
                    <CausalRoleBadge role="correlated_anomaly" />
                    <ErrorPatternContent pattern={ep} rank={i + 1} />
                  </AgentFindingCard>
                ))}
              </section>
            )}

            {/* 10. Trace waterfall */}
            {(findings?.trace_spans?.length ?? 0) > 0 && (
              <TraceWaterfall spans={findings!.trace_spans} />
            )}

            {/* Activity Feed fallback */}
            {errorPatterns.length === 0 && (findings?.findings?.length ?? 0) === 0 && events.length > 0 && (
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
          </>
        )}
      </div>
    </div>
  );
};

// ─── Helpers ──────────────────────────────────────────────────────────────

function severityRank(s: Severity): number {
  const ranks: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return ranks[s] ?? 4;
}

function getAgentCode(name: string): 'L' | 'M' | 'K' | 'C' {
  if (name.includes('log')) return 'L';
  if (name.includes('metric')) return 'M';
  if (name.includes('k8s')) return 'K';
  return 'C';
}

function getSaturationMetrics(anomalies: MetricAnomaly[]): MetricAnomaly[] {
  const saturationPattern = /saturation|pool|throttl/i;
  return anomalies.filter(
    (ma) => saturationPattern.test(ma.metric_name) && ma.current_value <= 1.5
  );
}

const StatBox: React.FC<{ label: string; value: number; color?: string }> = ({ label, value, color = 'text-white' }) => (
  <div className="bg-slate-800/50 p-2 rounded border border-slate-700/50">
    <div className="text-[9px] text-slate-500">{label}</div>
    <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
  </div>
);

// ─── Error Pattern Content (inside AgentFindingCard) ──────────────────────

const ErrorPatternContent: React.FC<{ pattern: ErrorPattern; rank: number }> = ({ pattern }) => (
  <div className="mt-2 space-y-2">
    <div className="flex items-center gap-2">
      <span className={`text-[10px] font-bold uppercase ${
        pattern.severity === 'critical' || pattern.severity === 'high' ? 'text-red-400' :
        pattern.severity === 'medium' ? 'text-amber-400' : 'text-blue-400'
      }`}>{pattern.severity}</span>
      <span className="text-xs font-mono text-slate-200 truncate flex-1">{pattern.exception_type}</span>
      <span className="text-xs font-bold text-red-400">{pattern.count}x</span>
    </div>
    <p className="text-[11px] font-mono text-slate-300">{pattern.sample_message}</p>
    {pattern.first_seen && (
      <div className="flex gap-4 text-[10px] text-slate-500">
        <span>First: {new Date(pattern.first_seen).toLocaleString()}</span>
        {pattern.last_seen && <span>Last: {new Date(pattern.last_seen).toLocaleString()}</span>}
      </div>
    )}
    {pattern.affected_components?.length > 0 && (
      <div className="flex flex-wrap gap-1">
        {pattern.affected_components.map((svc, i) => (
          <span key={i} className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/50">{svc}</span>
        ))}
      </div>
    )}
    {(pattern.stack_traces?.length ?? 0) > 0 && (
      <StackTraceTelescope traces={pattern.stack_traces!} />
    )}
    {pattern.priority_reasoning && (
      <p className="text-[10px] text-slate-400 italic">{pattern.priority_reasoning}</p>
    )}
  </div>
);

// ─── Error Pattern Cluster (legacy fallback) ──────────────────────────────

const ErrorPatternCluster: React.FC<{ pattern: ErrorPattern; rank: number }> = ({ pattern, rank }) => {
  const [expanded, setExpanded] = useState(rank === 1);
  const sevColor = pattern.severity === 'critical' || pattern.severity === 'high'
    ? 'border-red-500/30 bg-red-500/10'
    : pattern.severity === 'medium'
    ? 'border-amber-500/30 bg-amber-500/10'
    : 'border-blue-500/30 bg-blue-500/10';

  return (
    <div className={`border rounded-lg overflow-hidden ${sevColor}`}>
      <button onClick={() => setExpanded(!expanded)} className="w-full px-3 py-2.5 text-left flex items-center gap-2">
        <span className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className={`text-[10px] font-bold uppercase ${
          pattern.severity === 'critical' || pattern.severity === 'high' ? 'text-red-400' :
          pattern.severity === 'medium' ? 'text-amber-400' : 'text-blue-400'
        }`}>{pattern.severity}</span>
        {pattern.causal_role && <CausalRoleBadge role={pattern.causal_role} />}
        <span className="text-xs font-mono text-slate-200 truncate flex-1">{pattern.exception_type}</span>
        <span className="text-xs font-bold text-red-400">{pattern.count}x</span>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-black/10 pt-2">
          <ErrorPatternContent pattern={pattern} rank={rank} />
        </div>
      )}
    </div>
  );
};

// ─── Blast Radius Card ────────────────────────────────────────────────────

const BlastRadiusCard: React.FC<{ blast: BlastRadiusData | null; severity: SeverityData | null }> = ({ blast, severity }) => {
  if (!blast) return null;
  const sev = severity?.recommended_severity || 'P4';
  const style = severityPriorityColor[sev] || severityPriorityColor.P4;
  const totalAffected = (blast.upstream_affected?.length || 0) + (blast.downstream_affected?.length || 0);
  const [expanded, setExpanded] = useState(sev === 'P1' || sev === 'P2');

  return (
    <div className={`border rounded-xl overflow-hidden ${style.border} ${style.bg}`}>
      <button onClick={() => setExpanded(!expanded)} className="w-full px-4 py-3 text-left flex items-center gap-3" aria-expanded={expanded}>
        <span className={`material-symbols-outlined text-xs text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className="material-symbols-outlined text-sm text-slate-400" style={{ fontFamily: 'Material Symbols Outlined' }}>hub</span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Blast Radius</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${style.text} bg-black/20`}>{sev}</span>
        <span className="text-[11px] text-slate-400">{blast.scope.replace(/_/g, ' ')} — {totalAffected} affected</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 border-t border-black/10 pt-3 space-y-3">
          {severity?.reasoning && <p className="text-xs text-slate-400">{severity.reasoning}</p>}
          {/* Visual service bubbles */}
          <div className="flex flex-wrap gap-2">
            {blast.upstream_affected?.map((svc) => (
              <span key={`up-${svc}`} className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">{svc} ↑</span>
            ))}
            <span className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 font-bold">{blast.primary_service}</span>
            {blast.downstream_affected?.map((svc) => (
              <span key={`dn-${svc}`} className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30">{svc} ↓</span>
            ))}
          </div>
          {blast.shared_resources?.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {blast.shared_resources.map((res) => (
                <span key={res} className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30">{res}</span>
              ))}
            </div>
          )}
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

// ─── Temporal Flow Timeline ───────────────────────────────────────────────

const TemporalFlowTimeline: React.FC<{
  steps: ServiceFlowStep[];
  source: string;
  confidence: number;
  patientZero?: PatientZero | null;
}> = ({ steps, source, confidence, patientZero }) => {
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

  const lastErrorIdx = (() => {
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].status === 'error') return i;
    }
    return -1;
  })();

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>timeline</span>
          <span className="text-[11px] font-bold uppercase tracking-wider">Temporal Flow</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-500">{serviceCount} services, {steps.length} steps</span>
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20 font-mono">{source} {confidence}%</span>
        </div>
      </div>
      <div className="p-4 relative">
        <div className="absolute left-[31px] top-4 bottom-4 border-l border-dashed border-slate-700" />
        <div className="space-y-3">
          {steps.map((step, i) => {
            const isPatientZero = patientZero?.service?.toLowerCase() === step.service.toLowerCase();
            return (
              <div key={i} className="relative flex items-start gap-3 pl-2">
                <div className="relative z-10 flex-shrink-0 mt-1">
                  <div className={`w-4 h-4 rounded-full border-2 border-slate-900 ${
                    isPatientZero
                      ? 'bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.6)] ring-2 ring-red-500/30'
                      : nodeColor(step.status, i === lastErrorIdx)
                  }`} />
                </div>
                <button onClick={() => setExpandedIdx(expandedIdx === i ? null : i)} className="flex-1 bg-slate-800/30 p-2 rounded-lg border border-slate-700/50 text-left hover:border-slate-600/50 transition-colors">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tight shrink-0">{step.service}</span>
                      {isPatientZero && <span className="text-[8px] px-1 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">ORIGIN</span>}
                      <span className="text-[11px] font-mono text-slate-300 truncate">{step.operation}</span>
                    </div>
                    <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border ${
                      step.status === 'ok' ? 'text-green-400 border-green-500/30 bg-green-500/10' :
                      step.status === 'error' ? 'text-red-400 border-red-500/30 bg-red-500/10' :
                      'text-orange-400 border-orange-500/30 bg-orange-500/10'
                    }`}>
                      {step.status_detail || step.status.toUpperCase()}
                    </span>
                  </div>
                  {expandedIdx === i && (
                    <div className="mt-2 pt-2 border-t border-slate-700/50 space-y-1">
                      {step.timestamp && <div className="text-[10px] text-slate-500 font-mono">{new Date(step.timestamp).toLocaleString()}</div>}
                      {step.message && <div className="text-[10px] text-slate-400 font-mono break-all">{step.message}</div>}
                    </div>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ─── Change Correlations Section ──────────────────────────────────────────

const ChangeCorrelationsSection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const correlations = findings?.change_correlations || [];
  const [expanded, setExpanded] = useState(correlations.some((c) => c.risk_score > 0.8));

  if (correlations.length === 0) return null;

  return (
    <AgentFindingCard agent="C" title="Source of Change">
      <div className="space-y-2">
        {correlations.map((corr, i) => (
          <ChangeRow key={i} correlation={corr} />
        ))}
      </div>
    </AgentFindingCard>
  );
};

const ChangeRow: React.FC<{ correlation: ChangeCorrelation }> = ({ correlation }) => {
  const [expanded, setExpanded] = useState(correlation.risk_score > 0.8);
  const riskPct = Math.round(correlation.risk_score * 100);
  const riskColor = riskPct >= 80 ? 'text-red-400' : riskPct >= 50 ? 'text-amber-400' : 'text-blue-400';

  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700/50">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-3 py-2 flex items-center gap-2" aria-expanded={expanded}>
        <span className={`material-symbols-outlined text-xs text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className="text-[11px] font-mono text-violet-400">{correlation.change_id?.slice(0, 8) || '—'}</span>
        <span className="text-[11px] text-slate-300 truncate flex-1">{correlation.description}</span>
        <span className={`text-[10px] font-bold ${riskColor}`}>{riskPct}%</span>
      </button>
      {expanded && (
        <div className="px-3 pb-2.5 space-y-1 text-[10px] text-slate-400">
          <div>Author: {correlation.author}</div>
          <div>Type: {correlation.change_type.replace(/_/g, ' ')}</div>
          {correlation.timestamp && <div>Time: {new Date(correlation.timestamp).toLocaleString()}</div>}
          {correlation.files_changed.length > 0 && <div>Files: {correlation.files_changed.length} changed</div>}
        </div>
      )}
    </div>
  );
};

// ─── Trace Waterfall ──────────────────────────────────────────────────────

const TraceWaterfall: React.FC<{ spans: SpanInfo[] }> = ({ spans }) => {
  const totalDuration = Math.max(...spans.map((s) => s.duration_ms), 1);
  const errorCount = spans.filter((s) => s.status === 'error' || s.error).length;

  const depthMap = new Map<string, number>();
  const computeDepth = (span: SpanInfo): number => {
    if (depthMap.has(span.span_id)) return depthMap.get(span.span_id)!;
    if (!span.parent_span_id) { depthMap.set(span.span_id, 0); return 0; }
    const parent = spans.find((s) => s.span_id === span.parent_span_id);
    const depth = parent ? computeDepth(parent) + 1 : 0;
    depthMap.set(span.span_id, depth);
    return depth;
  };
  spans.forEach(computeDepth);

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-cyan-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>stacked_bar_chart</span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Trace Waterfall</span>
        <span className="text-[10px] text-slate-500 ml-auto">{spans.length} spans, {totalDuration.toFixed(0)}ms</span>
        {errorCount > 0 && <span className="text-red-400 text-[10px] font-bold">{errorCount} errors</span>}
      </div>
      <div className="space-y-1">
        {spans.map((span, i) => {
          const widthPct = Math.max((span.duration_ms / totalDuration) * 100, 2);
          const isError = span.status === 'error' || span.error;
          const barColor = isError ? 'bg-red-500' : 'bg-green-500';
          const depth = depthMap.get(span.span_id) || 0;
          return (
            <div key={i} className="flex items-center gap-2 py-0.5" style={{ paddingLeft: `${depth * 16}px` }}>
              <span className="text-[10px] font-mono text-[#07b6d5] w-20 shrink-0 truncate">{span.service}</span>
              <span className="text-[10px] text-slate-400 w-28 shrink-0 truncate">{span.operation}</span>
              <div className="flex-1 h-3 bg-slate-800/50 rounded overflow-hidden">
                <div className={`h-full rounded ${barColor}`} style={{ width: `${widthPct}%` }} />
              </div>
              <span className={`text-[10px] font-mono w-14 text-right shrink-0 ${isError ? 'text-red-400' : 'text-slate-400'}`}>
                {span.duration_ms.toFixed(0)}ms
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── Empty State ──────────────────────────────────────────────────────────

const EmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="flex items-center justify-center h-full min-h-[200px] text-slate-500">
    <div className="text-center">
      <div className="w-8 h-8 border-2 border-slate-800 border-t-[#07b6d5] rounded-full animate-spin mx-auto mb-3" />
      <p className="text-sm">{message}</p>
    </div>
  </div>
);

export default EvidenceFindings;
