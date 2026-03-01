import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { LayoutGroup, AnimatePresence, motion } from 'framer-motion';
import { useTopologySelection } from '../../contexts/TopologySelectionContext';
import { filterBannerVariants } from '../../styles/topology-animations';
import type {
  V4Findings, V4SessionStatus, TaskEvent, Severity, ErrorPattern,
  CriticVerdict, ChangeCorrelation, BlastRadiusData, SeverityData,
  SpanInfo, ServiceFlowStep, PatientZero, MetricAnomaly, DiagnosticPhase,
  DiffAnalysisItem, SuggestedFixArea, NegativeFinding, HighPriorityFile,
  CrossRepoFinding, PastIncidentMatch, EventMarker, PodHealthStatus,
  EvidencePinV2, ValidationStatus, CausalRole,
} from '../../types';
import AgentFindingCard from './cards/AgentFindingCard';
import CausalRoleBadge from './cards/CausalRoleBadge';
import EvidencePinCard from './cards/EvidencePinCard';
import StackTraceTelescope from './cards/StackTraceTelescope';
import SaturationGauge from './cards/SaturationGauge';
import AnomalySparkline, { findMatchingTimeSeries } from './cards/AnomalySparkline';
import IncidentClosurePanel from './IncidentClosurePanel';
import FixPipelinePanel from './FixPipelinePanel';
import { SkeletonStack } from '../ui/SkeletonCard';
import SkeletonCard from '../ui/SkeletonCard';
import { safeFixed, formatTime, safeDate } from '../../utils/format';
import CausalForestView from './CausalForestView';

// HUD components
import HUDAtmosphere from './hud/HUDAtmosphere';
import BriefingHeader from './hud/BriefingHeader';
import LogicVineContainer from './hud/LogicVineContainer';
import VineCard from './hud/VineCard';
import TargetingBrackets from './hud/TargetingBrackets';
import WorkerSignature from './hud/WorkerSignature';
import WeldSpark from './hud/WeldSpark';
import MermaidChart from '../Agent2/Mermaid';
import SymptomDeck from './hud/SymptomDeck';
import AssemblyWorkbench from './hud/AssemblyWorkbench';
import ResolveCinematic from './hud/ResolveCinematic';

interface EvidenceFindingsProps {
  findings: V4Findings | null;
  status: V4SessionStatus | null;
  events: TaskEvent[];
  sessionId?: string;
  phase?: DiagnosticPhase | null;
  onRefresh?: () => void;
  onNavigateToDossier?: () => void;
  manualPins?: EvidencePinV2[];
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

interface PinnedCard {
  id: string;
  agentType: string;
  title: string;
}

const EvidenceFindings: React.FC<EvidenceFindingsProps> = ({ findings, status: _status, events, sessionId, phase, onRefresh, onNavigateToDossier, manualPins }) => {
  const { selectedService, clearSelection } = useTopologySelection();

  // ── P0-3: Build reactive pin update map from WebSocket events ──────
  // Backend emits event_type: "evidence_pin_updated" (not in TS union, but present at runtime)
  const pinUpdateMap = useMemo(() => {
    const map = new Map<string, { validation_status: ValidationStatus; causal_role: CausalRole | null }>();
    for (const event of events) {
      if ((event.event_type as string) !== 'evidence_pin_updated' || !event.details) continue;
      const d = event.details;
      if (typeof d.pin_id !== 'string') continue;
      map.set(d.pin_id, {
        validation_status: (d.validation_status as ValidationStatus) ?? 'pending_critic',
        causal_role: (d.causal_role as CausalRole) ?? null,
      });
    }
    return map;
  }, [events]);

  // Merge WebSocket updates into manual pins for reactive rendering
  const mergedPins = useMemo<EvidencePinV2[]>(() => {
    if (!manualPins || manualPins.length === 0) return [];
    if (pinUpdateMap.size === 0) return manualPins;
    return manualPins.map((pin) => {
      const update = pinUpdateMap.get(pin.id);
      if (!update) return pin;
      return {
        ...pin,
        validation_status: update.validation_status,
        causal_role: update.causal_role ?? pin.causal_role,
      };
    });
  }, [manualPins, pinUpdateMap]);

  // Service filter: returns true if no service selected OR if text mentions the service
  const matchesService = useCallback(
    (text: string) => !selectedService || text.toLowerCase().includes(selectedService.toLowerCase()),
    [selectedService],
  );

  const allErrorPatterns = findings?.error_patterns || [];

  // Apply topology service filter to error patterns
  const errorPatternMatchesSvc = useCallback(
    (p: ErrorPattern) =>
      !selectedService ||
      p.affected_components.some((c) => matchesService(c)) ||
      matchesService(p.exception_type) ||
      matchesService(p.error_message),
    [selectedService, matchesService],
  );
  const errorPatterns = allErrorPatterns.filter(errorPatternMatchesSvc);
  const rootCausePatterns = errorPatterns.filter((p) => p.causal_role === 'root_cause');
  const cascadingPatterns = errorPatterns.filter((p) => p.causal_role === 'cascading_failure');
  const correlatedPatterns = errorPatterns.filter(
    (p) => p.causal_role === 'correlated_anomaly'
  );
  const ungroupedPatterns = rootCausePatterns.length === 0 ? errorPatterns : [];

  // Filtered sub-collections for other sections
  const filteredFindings = useMemo(
    () => (findings?.findings || []).filter((f) => matchesService(f.title) || matchesService(f.description)),
    [findings?.findings, matchesService],
  );
  const filteredMetrics = useMemo(
    () => (findings?.metric_anomalies || []).filter((ma) => matchesService(ma.metric_name)),
    [findings?.metric_anomalies, matchesService],
  );
  const filteredServiceFlow = useMemo(
    () => (findings?.service_flow || []).filter((step) => matchesService(step.service)),
    [findings?.service_flow, matchesService],
  );
  const filteredTraceSpans = useMemo(
    () => (findings?.trace_spans || []).filter((span) => matchesService(span.service)),
    [findings?.trace_spans, matchesService],
  );
  const filteredChangeCorrelations = useMemo(
    () => (findings?.change_correlations || []).filter((c) => matchesService(c.service_name || '')),
    [findings?.change_correlations, matchesService],
  );
  const filteredPodStatuses = useMemo(
    () => (findings?.pod_statuses || []).filter((p) => matchesService(p.pod_name)),
    [findings?.pod_statuses, matchesService],
  );
  const filteredK8sEvents = useMemo(
    () => (findings?.k8s_events || []).filter((e) => matchesService(e.involved_object)),
    [findings?.k8s_events, matchesService],
  );

  const sev = (findings?.severity_recommendation?.recommended_severity || 'P4') as 'P1' | 'P2' | 'P3' | 'P4';

  const hasContent = errorPatterns.length > 0 ||
    (findings?.findings?.length ?? 0) > 0 ||
    (findings?.metric_anomalies?.length ?? 0) > 0 ||
    (findings?.service_flow?.length ?? 0) > 0 ||
    !!findings?.root_cause_location ||
    (findings?.code_call_chain?.length ?? 0) > 0 ||
    events.length > 0;

  // ── Briefing Header data derivation ──
  const latestEvent = events.filter(e => e.event_type !== 'tool_call').slice(-1)[0];
  const latestEventText = latestEvent?.message || 'Initializing investigation...';
  const agentName = latestEvent?.agent_name || 'System';
  const isProcessing = phase !== 'complete' && phase !== 'diagnosis_complete';

  // ── Pin state for Assembly Workbench ──
  const [pinnedSections, setPinnedSections] = useState<Map<string, PinnedCard>>(new Map());
  const handlePin = useCallback((sectionId: string, title: string, agentCode: string) => {
    setPinnedSections(prev => {
      const next = new Map(prev);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.set(sectionId, { id: sectionId, agentType: agentCode, title });
      }
      return next;
    });
  }, []);
  const handleUnpin = useCallback((id: string) => {
    setPinnedSections(prev => {
      const next = new Map(prev);
      next.delete(id);
      return next;
    });
  }, []);
  const fixReady = phase === 'diagnosis_complete' || phase === 'complete';

  // ── Resolve Cinematic trigger ──
  const [showResolve, setShowResolve] = useState(false);
  const prevPhaseRef = useRef<DiagnosticPhase | null>(null);
  useEffect(() => {
    if (phase === 'complete' && prevPhaseRef.current !== 'complete') {
      setShowResolve(true);
    }
    prevPhaseRef.current = phase || null;
  }, [phase]);

  // ── New card detection ──
  const seenSectionsRef = useRef<Set<string>>(new Set());
  const [newSections, setNewSections] = useState<Set<string>>(new Set());

  const currentSectionIds = useMemo(() => {
    const ids: string[] = [];
    if (rootCausePatterns.length > 0) ids.push('root-cause');
    if (cascadingPatterns.length > 0) ids.push('cascading');
    if (ungroupedPatterns.length > 0) ids.push('ungrouped');
    if ((findings?.findings?.length ?? 0) > 0) ids.push('findings');
    if ((findings?.metric_anomalies?.length ?? 0) > 0) ids.push('metrics');
    if ((findings?.k8s_events?.length ?? 0) > 0 || (findings?.pod_statuses?.length ?? 0) > 0) ids.push('k8s');
    if (findings?.blast_radius) ids.push('blast-radius');
    if ((findings?.service_flow?.length ?? 0) > 0) ids.push('service-flow');
    if ((findings?.change_correlations?.length ?? 0) > 0) ids.push('causality');
    if ((findings?.code_overall_confidence ?? 0) > 0 || findings?.root_cause_location) ids.push('code-nav');
    if (correlatedPatterns.length > 0) ids.push('correlated');
    if ((findings?.trace_spans?.length ?? 0) > 0) ids.push('traces');
    if ((findings?.event_markers?.length ?? 0) > 0) ids.push('event-markers');
    if ((findings?.past_incidents?.length ?? 0) > 0) ids.push('past-incidents');
    return ids;
  }, [findings, rootCausePatterns, cascadingPatterns, ungroupedPatterns, correlatedPatterns]);

  useEffect(() => {
    const newIds = currentSectionIds.filter(id => !seenSectionsRef.current.has(id));
    if (newIds.length > 0) {
      setNewSections(new Set(newIds));
      newIds.forEach(id => seenSectionsRef.current.add(id));
      const timer = setTimeout(() => setNewSections(new Set()), 1500);
      return () => clearTimeout(timer);
    }
  }, [currentSectionIds]);

  // ── Track vine card index for stagger ──
  let vineIndex = 0;

  return (
    <div className="flex flex-col h-full bg-[#0f2023]">
      <HUDAtmosphere>
        {/* Briefing Header */}
        <BriefingHeader
          latestEventText={latestEventText}
          agentName={agentName}
          severity={sev}
          isProcessing={isProcessing}
        />

        {/* Scrollable evidence stack */}
        <LayoutGroup>
          <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
            {/* Topology service filter banner */}
            <AnimatePresence>
              {selectedService && (
                <motion.div
                  variants={filterBannerVariants}
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                  className="mb-4 flex items-center justify-between px-3 py-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span className="text-[11px] text-cyan-300">
                      Showing evidence for: <span className="font-mono font-bold">{selectedService}</span>
                    </span>
                  </div>
                  <button
                    onClick={clearSelection}
                    className="text-[10px] text-slate-400 hover:text-white px-2 py-0.5 rounded bg-slate-700/50 hover:bg-slate-600/50 transition-colors"
                  >
                    Clear filter
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
            {/* Causal Forest — multi-root-cause view */}
            {findings?.causal_forest && findings.causal_forest.length > 0 && (
              <div className="mb-4">
                <CausalForestView forest={findings.causal_forest} sessionId={sessionId || ''} />
              </div>
            )}
            {/* Evidence Anchor Bar - prevents infinite scroll doom */}
            {findings && hasContent && (
              <div className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur border-b border-slate-800 flex gap-1.5 p-2 mb-4 rounded-lg overflow-x-auto scrollbar-hide">
                {rootCausePatterns.length > 0 && (
                  <a href="#section-root-cause" className="text-[10px] uppercase font-bold text-red-400 bg-red-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-red-500/20 transition-colors">
                    Root Cause ({rootCausePatterns.length})
                  </a>
                )}
                {cascadingPatterns.length > 0 && (
                  <a href="#section-cascading" className="text-[10px] uppercase font-bold text-orange-400 bg-orange-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-orange-500/20 transition-colors">
                    Cascading ({cascadingPatterns.length})
                  </a>
                )}
                {filteredFindings.length > 0 && (
                  <a href="#section-findings" className="text-[10px] uppercase font-bold text-cyan-400 bg-cyan-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-cyan-500/20 transition-colors">
                    Findings ({filteredFindings.length})
                  </a>
                )}
                {filteredMetrics.length > 0 && (
                  <a href="#section-metrics" className="text-[10px] uppercase font-bold text-cyan-400 bg-cyan-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-cyan-500/20 transition-colors">
                    Metrics ({filteredMetrics.length})
                  </a>
                )}
                {(filteredK8sEvents.length > 0 || filteredPodStatuses.length > 0) && (
                  <a href="#section-k8s" className="text-[10px] uppercase font-bold text-orange-400 bg-orange-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-orange-500/20 transition-colors">
                    K8s ({filteredK8sEvents.length + filteredPodStatuses.length})
                  </a>
                )}
                {(findings?.trace_spans?.length ?? 0) > 0 && (
                  <a href="#section-traces" className="text-[10px] uppercase font-bold text-violet-400 bg-violet-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-violet-500/20 transition-colors">
                    Traces ({findings?.trace_spans?.length})
                  </a>
                )}
                {correlatedPatterns.length > 0 && (
                  <a href="#section-correlated" className="text-[10px] uppercase font-bold text-blue-400 bg-blue-500/10 px-2 py-1 rounded whitespace-nowrap hover:bg-blue-500/20 transition-colors">
                    Correlated ({correlatedPatterns.length})
                  </a>
                )}
              </div>
            )}
            {findings === null ? (
              <SkeletonStack count={3} />
            ) : !hasContent ? (
              <PhaseAwareEmptyState phase={phase || null} />
            ) : (
              <LogicVineContainer>
                {/* 1. Root Cause patterns */}
                <div id="section-root-cause" className="scroll-mt-16" />
                {rootCausePatterns.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    isRootCause
                    sectionId="root-cause"
                    isNew={newSections.has('root-cause')}
                    onPin={() => handlePin('root-cause', rootCausePatterns[0]?.exception_type || 'Root Cause', 'L')}
                    isPinned={pinnedSections.has('root-cause')}
                  >
                    {newSections.has('root-cause') && <WeldSpark />}
                    <TargetingBrackets>
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
                    </TargetingBrackets>
                    <WorkerSignature confidence={rootCausePatterns.length > 0 ? Math.round(rootCausePatterns.reduce((s, p) => s + p.confidence_score, 0) / rootCausePatterns.length) : 0} agentCode="L" />
                  </VineCard>
                )}

                {/* 2. Cascading patterns */}
                <div id="section-cascading" className="scroll-mt-16" />
                {cascadingPatterns.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="cascading"
                    isNew={newSections.has('cascading')}
                    onPin={() => handlePin('cascading', 'Cascading Failures', 'L')}
                    isPinned={pinnedSections.has('cascading')}
                  >
                    {cascadingPatterns.length > 5 ? (
                      <SymptomDeck
                        symptoms={cascadingPatterns}
                        renderSymptom={(ep, i) => (
                          <AgentFindingCard key={ep.pattern_id || `cas-${i}`} agent="L" title="Cascading Error">
                            <CausalRoleBadge role="cascading_failure" />
                            <ErrorPatternContent pattern={ep} rank={i + 1} />
                          </AgentFindingCard>
                        )}
                      />
                    ) : (
                      <section className="space-y-2">
                        {cascadingPatterns.map((ep, i) => (
                          <AgentFindingCard key={ep.pattern_id || `cas-${i}`} agent="L" title="Cascading Error">
                            <CausalRoleBadge role="cascading_failure" />
                            <ErrorPatternContent pattern={ep} rank={i + 1} />
                          </AgentFindingCard>
                        ))}
                      </section>
                    )}
                    <WorkerSignature confidence={cascadingPatterns.length > 0 ? Math.round(cascadingPatterns.reduce((s, p) => s + p.confidence_score, 0) / cascadingPatterns.length) : 0} agentCode="L" />
                  </VineCard>
                )}

                {/* Ungrouped error patterns */}
                {ungroupedPatterns.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="ungrouped"
                    isNew={newSections.has('ungrouped')}
                    onPin={() => handlePin('ungrouped', 'Error Clusters', 'L')}
                    isPinned={pinnedSections.has('ungrouped')}
                  >
                    {ungroupedPatterns.length > 5 ? (
                      <SymptomDeck
                        symptoms={ungroupedPatterns}
                        renderSymptom={(ep, i) => (
                          <ErrorPatternCluster key={ep.pattern_id || `ug-${i}`} pattern={ep} rank={i + 1} />
                        )}
                      />
                    ) : (
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
                  </VineCard>
                )}

                {/* 3. High-severity findings */}
                <div id="section-findings" className="scroll-mt-16" />
                {filteredFindings.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="findings"
                    isNew={newSections.has('findings')}
                    onPin={() => handlePin('findings', 'Investigation Findings', 'C')}
                    isPinned={pinnedSections.has('findings')}
                  >
                    <section className="space-y-2">
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Findings</div>
                      {[...filteredFindings]
                        .sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
                        .map((finding, i) => {
                          const verdict = findings?.critic_verdicts?.find((v) => v.finding_id === finding.finding_id);
                          const agentCode = getAgentCode(finding.agent_name);
                          return (
                            <AgentFindingCard key={finding.finding_id || i} agent={agentCode} title={finding.title}>
                              <p className="text-xs text-slate-400 mb-2">{finding.description}</p>
                              <div className="flex items-center gap-3 text-[10px] text-slate-500">
                                <span className={`px-1.5 py-0.5 rounded ${severityColor[finding.severity]}`}>{finding.severity}</span>
                                <span>Confidence: {Math.round(finding.confidence)}%</span>
                                {verdict && (
                                  <span className={`px-1.5 py-0.5 rounded ${verdictColor[verdict.verdict]}`}>
                                    {verdict.verdict}
                                  </span>
                                )}
                              </div>
                              {verdict && (verdict.reasoning || verdict.recommendation) && (
                                <div className="mt-2 bg-slate-800/30 rounded-lg border border-slate-700/30 p-2 space-y-1">
                                  {verdict.reasoning && (
                                    <p className="text-[10px] text-slate-400">{verdict.reasoning}</p>
                                  )}
                                  {verdict.recommendation && (
                                    <p className="text-[10px] text-cyan-400 italic">{verdict.recommendation}</p>
                                  )}
                                  {verdict.confidence_in_verdict > 0 && (
                                    <span className="text-[9px] text-slate-500 font-mono">Verdict confidence: {verdict.confidence_in_verdict}%</span>
                                  )}
                                  {verdict.verdict === 'challenged' && verdict.contradicting_evidence && verdict.contradicting_evidence.length > 0 && (
                                    <div className="mt-1.5 pt-1.5 border-t border-red-500/20">
                                      <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">Contradicting Evidence</span>
                                      <div className="mt-1 space-y-1">
                                        {verdict.contradicting_evidence.map((b, bi) => (
                                          <div key={bi} className="text-[10px] text-slate-400 flex items-start gap-1.5">
                                            <span className="text-red-500 shrink-0 mt-0.5">
                                              <span className="material-symbols-outlined" style={{ fontSize: 10 }}>error</span>
                                            </span>
                                            <span>{b.action}: {b.raw_evidence || b.detail}</span>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                              {finding.suggested_fix && (
                                <p className="text-[10px] text-cyan-400 mt-2">Fix: {finding.suggested_fix}</p>
                              )}
                            </AgentFindingCard>
                          );
                        })}
                    </section>
                    <WorkerSignature confidence={filteredFindings.length > 0 ? Math.round(filteredFindings.reduce((s, f) => s + f.confidence, 0) / filteredFindings.length) : 0} agentCode="C" />
                  </VineCard>
                )}

                {/* 4. Metric anomalies */}
                <div id="section-metrics" className="scroll-mt-16" />
                {filteredMetrics.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="metrics"
                    isNew={newSections.has('metrics')}
                    onPin={() => handlePin('metrics', 'Metric Anomalies', 'M')}
                    isPinned={pinnedSections.has('metrics')}
                  >
                    <section>
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Metric Anomalies</div>
                      <div className="grid grid-cols-2 gap-3">
                        {filteredMetrics.map((ma, i) => {
                          const tsData = findMatchingTimeSeries(findings?.time_series_data || {}, ma.metric_name);
                          return (
                            <AgentFindingCard key={i} agent="M" title={ma.metric_name}>
                              <div className="flex items-baseline gap-3 mb-2">
                                <div className="text-xl font-bold font-mono text-white">{safeFixed(ma.current_value, 1)}</div>
                                <div className="text-xs font-mono text-slate-500">baseline {safeFixed(ma.baseline_value, 1)}</div>
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
                    <WorkerSignature confidence={filteredMetrics.length > 0 ? Math.round(filteredMetrics.reduce((s, ma) => s + ma.confidence_score, 0) / filteredMetrics.length) : 0} agentCode="M" />
                  </VineCard>
                )}

                {/* 5. K8s health + events */}
                <div id="section-k8s" className="scroll-mt-16" />
                {(filteredK8sEvents.length > 0 || filteredPodStatuses.length > 0) && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="k8s"
                    isNew={newSections.has('k8s')}
                    onPin={() => handlePin('k8s', 'Kubernetes Health', 'K')}
                    isPinned={pinnedSections.has('k8s')}
                  >
                    <section>
                      <AgentFindingCard agent="K" title="Kubernetes Health">
                        {filteredPodStatuses.length > 0 && (() => {
                          const pods = filteredPodStatuses;
                          return (
                          <>
                            <div className="grid grid-cols-4 gap-3 mb-3">
                              <StatBox label="Pods" value={pods.length} />
                              <StatBox label="Restarts" value={pods.reduce((s, p) => s + (p.restart_count || 0), 0)} color="text-amber-500" />
                              <StatBox label="Healthy" value={pods.filter((p) => p.ready).length} color="text-green-500" />
                              <StatBox label="Unhealthy" value={pods.filter((p) => !p.ready).length} color="text-red-500" />
                            </div>
                            <PodDetailsList pods={pods} />
                          </>
                          );
                        })()}
                        {filteredK8sEvents.length > 0 && (
                          <div className="space-y-1.5">
                            {filteredK8sEvents.map((ke, i) => (
                              <div key={i} className="flex items-center gap-2 text-[11px]">
                                <span className={`w-2 h-2 rounded-full ${ke.type === 'Warning' ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
                                <span className="font-mono text-slate-300">{ke.involved_object}</span>
                                <span className="text-slate-400 truncate">{ke.reason}: {ke.message}</span>
                                <span className="text-[10px] text-slate-400 ml-auto shrink-0">{ke.count}x</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </AgentFindingCard>
                    </section>
                    <WorkerSignature confidence={filteredPodStatuses.length > 0 ? Math.round((filteredPodStatuses.filter(p => !p.ready).length / filteredPodStatuses.length) * 100) : (filteredK8sEvents.length > 0 ? 70 : 0)} agentCode="K" />
                  </VineCard>
                )}

                {/* 6. Blast Radius */}
                {findings?.blast_radius && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="blast-radius"
                    isNew={newSections.has('blast-radius')}
                    onPin={() => handlePin('blast-radius', 'Blast Radius', 'C')}
                    isPinned={pinnedSections.has('blast-radius')}
                  >
                    <BlastRadiusCard blast={findings?.blast_radius || null} severity={findings?.severity_recommendation || null} />
                  </VineCard>
                )}

                {/* 7. Temporal Flow Timeline */}
                {filteredServiceFlow.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="service-flow"
                    isNew={newSections.has('service-flow')}
                    onPin={() => handlePin('service-flow', 'Temporal Flow', 'L')}
                    isPinned={pinnedSections.has('service-flow')}
                  >
                    <TemporalFlowTimeline
                      steps={filteredServiceFlow}
                      source={findings?.flow_source || 'elasticsearch'}
                      confidence={findings?.flow_confidence || 0}
                      patientZero={findings?.patient_zero}
                    />
                  </VineCard>
                )}

                {/* 8. Unified Causality Chain */}
                {(filteredChangeCorrelations.length > 0 || (findings?.diff_analysis?.length ?? 0) > 0 || (findings?.suggested_fix_areas?.length ?? 0) > 0 || findings?.change_summary) && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="causality"
                    isNew={newSections.has('causality')}
                    onPin={() => handlePin('causality', 'Causality Chain', 'C')}
                    isPinned={pinnedSections.has('causality')}
                  >
                    <CausalityChainCard findings={findings} />
                    <WorkerSignature confidence={filteredChangeCorrelations.length > 0 ? Math.round(filteredChangeCorrelations.reduce((s, c) => s + c.risk_score * 100, 0) / filteredChangeCorrelations.length) : 0} agentCode="C" />
                  </VineCard>
                )}

                {/* 8b. Code Navigator Section */}
                {((findings?.code_overall_confidence ?? 0) > 0 || findings?.root_cause_location || (findings?.code_call_chain?.length ?? 0) > 0) && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="code-nav"
                    isNew={newSections.has('code-nav')}
                    onPin={() => handlePin('code-nav', 'Code Navigator', 'D')}
                    isPinned={pinnedSections.has('code-nav')}
                  >
                    <section className="space-y-3">
                      {(findings?.code_overall_confidence ?? 0) > 0 && (() => {
                        const conf = findings?.code_overall_confidence ?? 0;
                        return (
                        <div className="flex items-center gap-2 mb-1">
                          <span className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold bg-blue-500 text-white">D</span>
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Code Navigator</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                            conf >= 80 ? 'text-green-400 bg-green-500/10 border border-green-500/20' :
                            conf >= 50 ? 'text-amber-400 bg-amber-500/10 border border-amber-500/20' :
                            'text-blue-400 bg-blue-500/10 border border-blue-500/20'
                          }`}>
                            {conf}% confidence
                          </span>
                        </div>
                        );
                      })()}

                      {findings?.root_cause_location && (
                        <AgentFindingCard agent="D" title="Root Cause Location">
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                                findings.root_cause_location.fix_relevance === 'must_fix'
                                  ? 'text-red-300 bg-red-500/20 border-red-500/30'
                                  : 'text-amber-300 bg-amber-500/20 border-amber-500/30'
                              }`}>{findings.root_cause_location.fix_relevance.replace(/_/g, ' ').toUpperCase()}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-300 font-mono">
                                {findings.root_cause_location.impact_type.replace(/_/g, ' ')}
                              </span>
                            </div>
                            <div className="font-mono text-[11px] text-blue-400">{findings.root_cause_location.file_path}</div>
                            {findings.root_cause_location.relevant_lines?.length > 0 && (
                              <div className="text-[10px] text-slate-500">
                                Lines: {findings.root_cause_location.relevant_lines.map(r => `${r.start}-${r.end}`).join(', ')}
                              </div>
                            )}
                            <p className="text-[10px] text-slate-400">{findings.root_cause_location.relationship}</p>
                            {findings.root_cause_location.code_snippet && (
                              <pre className="text-[10px] font-mono bg-slate-900/60 rounded p-2 text-green-400 overflow-x-auto whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                                {findings.root_cause_location.code_snippet}
                              </pre>
                            )}
                          </div>
                        </AgentFindingCard>
                      )}

                      {(findings?.code_call_chain?.length ?? 0) > 0 && (
                        <AgentFindingCard agent="D" title="Code Call Chain">
                          <div className="space-y-1">
                            {(findings?.code_call_chain || []).map((step, i) => (
                              <div key={i} className="flex items-center gap-2">
                                <div className="flex flex-col items-center w-4">
                                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                                  {i < (findings?.code_call_chain?.length ?? 0) - 1 && (
                                    <div className="w-px h-4 bg-slate-700" />
                                  )}
                                </div>
                                <span className="text-[11px] font-mono text-slate-300">{step}</span>
                              </div>
                            ))}
                          </div>
                        </AgentFindingCard>
                      )}

                      {(findings?.impacted_files?.length ?? 0) > 0 && (
                        <AgentFindingCard agent="D" title={`Impacted Files (${findings?.impacted_files?.length ?? 0})`}>
                          <div className="space-y-1.5">
                            {(findings?.impacted_files || []).map((file, i) => (
                              <div key={i} className="flex items-center gap-2 text-[10px]">
                                <span className={`px-1 py-0.5 rounded border text-[9px] font-bold ${
                                  file.fix_relevance === 'must_fix' ? 'text-red-300 bg-red-500/20 border-red-500/30' :
                                  file.fix_relevance === 'should_review' ? 'text-amber-300 bg-amber-500/20 border-amber-500/30' :
                                  'text-slate-400 bg-slate-500/20 border-slate-500/30'
                                }`}>{file.fix_relevance.replace(/_/g, ' ').toUpperCase()}</span>
                                <span className="font-mono text-blue-400 truncate" title={file.file_path}>{file.file_path}</span>
                                <span className="text-slate-500 ml-auto shrink-0">{file.impact_type.replace(/_/g, ' ')}</span>
                              </div>
                            ))}
                          </div>
                        </AgentFindingCard>
                      )}

                      {(findings?.code_shared_resource_conflicts?.length ?? 0) > 0 && (
                        <AgentFindingCard agent="D" title="Shared Resource Conflicts">
                          <div className="flex flex-wrap gap-2">
                            {(findings?.code_shared_resource_conflicts || []).map((conflict, i) => (
                              <span key={i} className="text-[10px] font-mono px-2.5 py-1 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">
                                {conflict}
                              </span>
                            ))}
                          </div>
                        </AgentFindingCard>
                      )}

                      {(findings?.code_cross_repo_findings?.length ?? 0) > 0 && (
                        <AgentFindingCard agent="D" title="Cross-Repo Findings">
                          <div className="space-y-2">
                            {(findings?.code_cross_repo_findings || []).map((crf: CrossRepoFinding, i: number) => (
                              <div key={i} className="bg-slate-800/30 rounded-lg border border-slate-700/50 px-3 py-2">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="text-[11px] font-mono text-violet-400">{crf.repo}</span>
                                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400 border border-violet-500/20 font-bold uppercase">
                                    {(crf.role || '').replace(/_/g, ' ')}
                                  </span>
                                </div>
                                <p className="text-[10px] text-slate-400">{crf.evidence}</p>
                              </div>
                            ))}
                          </div>
                        </AgentFindingCard>
                      )}

                      {findings?.code_mermaid_diagram && (
                        <AgentFindingCard agent="D" title="Service Flow Diagram">
                          {/* h-80 = strict 320px height for pan/zoom engine to anchor against */}
                          <div className="rounded-xl overflow-hidden w-full h-80 border border-slate-700/50 relative">
                            <MermaidChart chart={findings.code_mermaid_diagram} />
                          </div>
                        </AgentFindingCard>
                      )}
                    </section>
                    <WorkerSignature confidence={findings?.code_overall_confidence ?? 65} agentCode="D" />
                  </VineCard>
                )}

                {/* 8c. Fix Pipeline */}
                {sessionId && (
                  phase === 'diagnosis_complete' ||
                  phase === 'fix_in_progress' ||
                  phase === 'complete' ||
                  (findings?.fix_data && findings.fix_data.fix_status !== 'not_started')
                ) && (
                  <VineCard index={vineIndex++} sectionId="fix-pipeline">
                    <FixPipelinePanel
                      sessionId={sessionId}
                      findings={findings}
                      phase={phase || null}
                      onRefresh={onRefresh || (() => {})}
                    />
                  </VineCard>
                )}

                {/* 9. Correlated anomalies */}
                <div id="section-correlated" className="scroll-mt-16" />
                {correlatedPatterns.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="correlated"
                    isNew={newSections.has('correlated')}
                    onPin={() => handlePin('correlated', 'Correlated Anomalies', 'L')}
                    isPinned={pinnedSections.has('correlated')}
                  >
                    <section className="space-y-2">
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Correlated Anomalies</div>
                      {correlatedPatterns.map((ep, i) => (
                        <AgentFindingCard key={ep.pattern_id || `cor-${i}`} agent="L" title="Correlated Pattern">
                          <CausalRoleBadge role="correlated_anomaly" />
                          <ErrorPatternContent pattern={ep} rank={i + 1} />
                        </AgentFindingCard>
                      ))}
                    </section>
                  </VineCard>
                )}

                {/* 10. Trace waterfall */}
                <div id="section-traces" className="scroll-mt-16" />
                {filteredTraceSpans.length > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="traces"
                    isNew={newSections.has('traces')}
                    onPin={() => handlePin('traces', 'Trace Waterfall', 'L')}
                    isPinned={pinnedSections.has('traces')}
                  >
                    <TraceWaterfall spans={filteredTraceSpans} />
                  </VineCard>
                )}

                {/* 10b. Event Markers */}
                {(findings?.event_markers?.length ?? 0) > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="event-markers"
                    isNew={newSections.has('event-markers')}
                  >
                    <EventMarkerTimeline markers={findings?.event_markers || []} />
                  </VineCard>
                )}

                {/* 10c. Past Incidents */}
                {(findings?.past_incidents?.length ?? 0) > 0 && (
                  <VineCard
                    index={vineIndex++}
                    sectionId="past-incidents"
                    isNew={newSections.has('past-incidents')}
                  >
                    <PastIncidentsSection incidents={findings?.past_incidents || []} />
                  </VineCard>
                )}

                {/* 11. Incident Closure Panel */}
                {sessionId && (phase === 'diagnosis_complete' || phase === 'fix_in_progress' || phase === 'complete') && (
                  <VineCard index={vineIndex++} sectionId="closure">
                    <IncidentClosurePanel
                      sessionId={sessionId}
                      findings={findings}
                      phase={phase}
                      onNavigateToDossier={onNavigateToDossier}
                    />
                  </VineCard>
                )}

                {/* Activity Feed fallback */}
                {errorPatterns.length === 0 && (findings?.findings?.length ?? 0) === 0 && events.length > 0 && (
                  <VineCard index={vineIndex++} sectionId="activity-feed">
                    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60">
                        <span className="text-[11px] font-bold uppercase tracking-wider">Agent Activity Feed</span>
                      </div>
                      <div className="p-4 font-mono text-[11px] space-y-1 text-slate-400 max-h-[300px] overflow-y-auto custom-scrollbar">
                        {events.slice(-20).map((ev, i) => (
                          <div key={i} className="flex gap-3">
                            <span className="text-slate-400 shrink-0">
                              {formatTime(ev.timestamp)}
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
                  </VineCard>
                )}
              </LogicVineContainer>
            )}

            {/* Manual Evidence Pins (merged with WebSocket validation updates) */}
            {mergedPins.length > 0 && (
              <div className="mt-6">
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="material-symbols-outlined text-amber-400"
                    style={{ fontFamily: 'Material Symbols Outlined', fontSize: '16px' }}
                  >
                    push_pin
                  </span>
                  <span className="text-[11px] font-bold text-amber-400 uppercase tracking-wider">
                    Manual Evidence ({mergedPins.length})
                  </span>
                </div>
                <div className="space-y-3">
                  {mergedPins.map((pin) => (
                    <EvidencePinCard key={pin.id} pin={pin} />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Assembly Workbench */}
          <AssemblyWorkbench
            pinnedItems={Array.from(pinnedSections.values())}
            onUnpin={handleUnpin}
            fixReady={fixReady}
          />
        </LayoutGroup>

        {/* Resolve Cinematic */}
        <AnimatePresence>
          {showResolve && (
            <ResolveCinematic
              findings={findings}
              onDismiss={() => setShowResolve(false)}
            />
          )}
        </AnimatePresence>
      </HUDAtmosphere>
    </div>
  );
};

// ─── Helpers ──────────────────────────────────────────────────────────────

function severityRank(s: Severity): number {
  const ranks: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return ranks[s] ?? 4;
}

function getAgentCode(name: string): 'L' | 'M' | 'K' | 'C' | 'D' {
  if (name.includes('log')) return 'L';
  if (name.includes('metric')) return 'M';
  if (name.includes('k8s')) return 'K';
  if (name.includes('code')) return 'D';
  if (name.includes('change')) return 'C';
  if (name.includes('trac')) return 'L';
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
      <div className="flex gap-4 text-[10px] text-slate-400">
        <span>First: {safeDate(pattern.first_seen)}</span>
        {pattern.last_seen && <span>Last: {safeDate(pattern.last_seen)}</span>}
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
      <button onClick={() => setExpanded(!expanded)} className="w-full px-3 py-2.5 text-left flex items-center gap-2" aria-expanded={expanded} aria-label={`${expanded ? 'Collapse' : 'Expand'} error pattern: ${pattern.exception_type}`}>
        <span className={`material-symbols-outlined text-xs text-slate-400 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className={`text-[10px] font-bold uppercase ${
          pattern.severity === 'critical' || pattern.severity === 'high' ? 'text-red-400' :
          pattern.severity === 'medium' ? 'text-amber-400' : 'text-blue-400'
        }`}>{pattern.severity}</span>
        {pattern.causal_role && <CausalRoleBadge role={pattern.causal_role} />}
        <span className="text-xs font-mono text-slate-200 truncate flex-1" title={pattern.exception_type}>{pattern.exception_type}</span>
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
          {severity?.factors && Object.keys(severity.factors).length > 0 && (
            <div className="space-y-1 pt-1 border-t border-slate-800">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Severity Factors</span>
              {Object.entries(severity.factors).map(([key, value]) => (
                <div key={key} className="flex items-start gap-2 text-[10px]">
                  <span className="text-slate-500 shrink-0">{key.replace(/_/g, ' ')}:</span>
                  <span className="text-slate-400">{value}</span>
                </div>
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
                      {step.timestamp && <div className="text-[10px] text-slate-400 font-mono">{safeDate(step.timestamp)}</div>}
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

// ─── Causality Chain Card (unified) ───────────────────────────────────────

interface CausalityLink {
  correlation: ChangeCorrelation;
  diffs: DiffAnalysisItem[];
  fixes: SuggestedFixArea[];
}

const CausalityChainCard: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const correlations = findings?.change_correlations || [];
  const diffs = findings?.diff_analysis || [];
  const fixes = findings?.suggested_fix_areas || [];
  const changeSummary = findings?.change_summary || null;
  const highPriorityFiles = findings?.change_high_priority_files || [];
  const negativeFindings = findings?.negative_findings || [];
  const [ruledOutOpen, setRuledOutOpen] = useState(false);

  // Filter negative findings to change/infra-related ones
  const changeNegatives = useMemo(() =>
    negativeFindings.filter(nf =>
      nf.agent === 'change_agent' ||
      /config|deploy|change|rollout|scaling|hpa/i.test(nf.category + ' ' + nf.description)
    ),
  [negativeFindings]);

  const links: CausalityLink[] = useMemo(() => {
    return correlations
      .filter(c => c.risk_score > 0)
      .sort((a, b) => b.risk_score - a.risk_score)
      .map(corr => {
        const changedFiles = new Set((corr.files_changed || []).map(f => f.toLowerCase()));
        const matchedDiffs = diffs.filter(d =>
          changedFiles.has(d.file.toLowerCase()) ||
          d.commit_sha?.startsWith(corr.change_id?.slice(0, 7) || '---')
        );
        const matchedFixes = fixes.filter(f =>
          changedFiles.has(f.file_path.toLowerCase()) ||
          matchedDiffs.some(d => d.file.toLowerCase() === f.file_path.toLowerCase())
        );
        return { correlation: corr, diffs: matchedDiffs, fixes: matchedFixes };
      });
  }, [correlations, diffs, fixes]);

  // Orphaned diffs/fixes not linked to any correlation
  const linkedDiffFiles = new Set(links.flatMap(l => l.diffs.map(d => d.file)));
  const linkedFixFiles = new Set(links.flatMap(l => l.fixes.map(f => f.file_path)));
  const orphanDiffs = diffs.filter(d => !linkedDiffFiles.has(d.file));
  const orphanFixes = fixes.filter(f => !linkedFixFiles.has(f.file_path));

  // Early return AFTER all hooks
  if (correlations.length === 0 && diffs.length === 0 && fixes.length === 0 && !changeSummary && changeNegatives.length === 0) return null;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="material-symbols-outlined text-violet-400 text-sm"
              style={{ fontFamily: 'Material Symbols Outlined' }}>account_tree</span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Causality Chain</span>
        <span className="text-[10px] text-slate-500">
          {links.length} correlation{links.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Gap 3: System Insight — Executive Brief */}
      {changeSummary && (
        <div className="rounded-lg bg-blue-500/5 border border-blue-500/20 px-4 py-2.5 flex items-start gap-2.5">
          <span className="material-symbols-outlined text-blue-400 text-sm mt-0.5 shrink-0"
                style={{ fontFamily: 'Material Symbols Outlined' }}>lightbulb</span>
          <p className="text-[11px] text-slate-300 leading-relaxed">{changeSummary}</p>
        </div>
      )}

      {/* Gap 2: Top Suspects — High Priority Files */}
      {highPriorityFiles.length > 0 && (
        <div className="rounded-lg bg-slate-900/40 border border-slate-700/50 px-4 py-2.5">
          <div className="flex items-center gap-1.5 mb-2">
            <span className="material-symbols-outlined text-amber-400 text-xs"
                  style={{ fontFamily: 'Material Symbols Outlined' }}>target</span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">Top Suspects</span>
            <span className="text-[9px] text-slate-600 ml-1">Files the AI is investigating</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {highPriorityFiles.map((hpf, i) => (
              <span key={i}
                    className="group relative text-[10px] font-mono px-2 py-1 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/25 cursor-default"
                    title={`Risk: ${Math.round(hpf.risk_score * 100)}% | ${hpf.description}`}>
                {hpf.file_path.split('/').pop()}
                <span className="ml-1.5 text-[9px] text-amber-500 font-bold">{Math.round(hpf.risk_score * 100)}%</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {links.map((link, i) => (
        <CausalityLinkCard key={i} link={link} />
      ))}

      {/* Orphaned diffs from code_agent */}
      {orphanDiffs.length > 0 && (
        <AgentFindingCard agent="D" title="Additional Diff Analysis">
          <div className="space-y-2">
            {orphanDiffs.map((item, i) => <DiffRow key={i} item={item} />)}
          </div>
        </AgentFindingCard>
      )}

      {/* Orphaned fixes */}
      {orphanFixes.length > 0 && (
        <AgentFindingCard agent="D" title="Additional Fix Suggestions">
          <div className="space-y-2">
            {orphanFixes.map((fix, i) => <FixRow key={i} fix={fix} />)}
          </div>
        </AgentFindingCard>
      )}

      {/* Gap 4: Ruled Out — Dead Ends */}
      {changeNegatives.length > 0 && (
        <div className="rounded-lg bg-slate-900/20 border border-slate-800/50">
          <button onClick={() => setRuledOutOpen(!ruledOutOpen)}
                  className="w-full text-left px-4 py-2 flex items-center gap-2"
                  aria-expanded={ruledOutOpen}
                  aria-label={`${ruledOutOpen ? 'Collapse' : 'Expand'} ruled out findings`}>
            <span className={`material-symbols-outlined text-xs text-slate-400 transition-transform duration-200 ${ruledOutOpen ? 'rotate-90' : ''}`}
                  style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
            <span className="material-symbols-outlined text-slate-400 text-xs"
                  style={{ fontFamily: 'Material Symbols Outlined' }}>scan_delete</span>
            <span className="text-[10px] text-slate-400 uppercase tracking-wider font-bold">Ruled Out</span>
            <span className="text-[9px] text-slate-500">{changeNegatives.length} checked</span>
          </button>
          {ruledOutOpen && (
            <div className="px-4 pb-3 space-y-1.5">
              {changeNegatives.map((nf, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] text-slate-500">
                  <span className="text-green-600 shrink-0">&#10003;</span>
                  <span className="text-slate-600 font-medium">{nf.category}:</span>
                  <span className="text-slate-500">{nf.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
};

const CausalityLinkCard: React.FC<{ link: CausalityLink }> = ({ link }) => {
  const [expanded, setExpanded] = useState(link.correlation.risk_score > 0.7);
  const riskPct = Math.round(link.correlation.risk_score * 100);
  const riskColor = riskPct >= 80 ? 'text-red-400' : riskPct >= 50 ? 'text-amber-400' : 'text-blue-400';
  const hasLikelyCause = link.diffs.some(d => d.verdict === 'likely_cause');
  const temporalPct = Math.round((link.correlation.temporal_correlation ?? 0) * 100);
  const temporalColor = temporalPct >= 80 ? 'text-red-400 bg-red-500/10 border-red-500/20'
    : temporalPct >= 50 ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
    : 'text-blue-400 bg-blue-500/10 border-blue-500/20';

  return (
    <div className="rounded-lg overflow-hidden bg-slate-900/40 border border-slate-700/50"
         style={{ borderLeft: '3px solid', borderImage: 'linear-gradient(to bottom, #10b981, #3b82f6, #8b5cf6) 1' }}>

      {/* Top: Change Agent - Who/When */}
      <button onClick={() => setExpanded(!expanded)}
              className="w-full text-left px-4 py-2.5 flex items-center gap-2">
        <span className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold bg-emerald-500 text-white shrink-0">C</span>
        <span className="text-[11px] font-mono text-violet-400">{link.correlation.change_id?.slice(0, 8) || '--'}</span>
        <span className="text-[11px] text-slate-300 truncate flex-1">{link.correlation.description}</span>
        {/* Gap 1: Temporal Correlation — Time Proximity Badge */}
        {temporalPct > 0 && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono flex items-center gap-1 shrink-0 ${temporalColor}`}
                title="Time proximity to incident start">
            <span className="material-symbols-outlined text-[10px]" style={{ fontFamily: 'Material Symbols Outlined' }}>schedule</span>
            {temporalPct}% match
          </span>
        )}
        <span className={`text-[10px] font-bold ${riskColor}`}>{riskPct}%</span>
        {hasLikelyCause && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">LIKELY CAUSE</span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-slate-800/50">
          {/* Meta row */}
          <div className="px-4 py-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-slate-500 bg-slate-800/20">
            <span>Author: {link.correlation.author}</span>
            <span>Type: {(link.correlation.change_type || 'code_deploy').replace(/_/g, ' ')}</span>
            {link.correlation.timestamp && <span>{safeDate(link.correlation.timestamp)}</span>}
            {link.correlation.service_name && <span className="text-cyan-400">{link.correlation.service_name}</span>}
            {temporalPct > 0 && (
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined text-[10px] text-slate-400" style={{ fontFamily: 'Material Symbols Outlined' }}>schedule</span>
                Time proximity: {temporalPct}%
              </span>
            )}
          </div>

          {/* Middle: Diff Analysis */}
          {link.diffs.length > 0 && (
            <div className="px-4 py-2 border-t border-slate-800/30">
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold bg-blue-500 text-white">D</span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Diff Analysis</span>
              </div>
              <div className="space-y-1.5">
                {link.diffs.map((d, i) => {
                  const style = verdictStyle[d.verdict];
                  return (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      <span className={`px-1 py-0.5 rounded border ${style.text} ${style.bg} ${style.border} text-[9px] font-bold`}>
                        {d.verdict.replace(/_/g, ' ').toUpperCase()}
                      </span>
                      <span className="font-mono text-blue-400 truncate" title={d.file}>{d.file}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Files changed fallback */}
          {link.diffs.length === 0 && (link.correlation.files_changed?.length ?? 0) > 0 && (
            <div className="px-4 py-2 border-t border-slate-800/30 text-[10px] text-slate-400">
              Files: {link.correlation.files_changed.join(', ')}
            </div>
          )}

          {/* Bottom: Suggested Fix */}
          {link.fixes.length > 0 && (
            <div className="px-4 py-2 border-t border-slate-800/30">
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="material-symbols-outlined text-green-400 text-xs" style={{ fontFamily: 'Material Symbols Outlined' }}>build</span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">Suggested Fix</span>
              </div>
              {link.fixes.map((fix, i) => (
                <div key={i} className="text-[10px]">
                  <span className="font-mono text-blue-400">{fix.file_path}</span>
                  <span className="text-slate-400 ml-2">{fix.description}</span>
                </div>
              ))}
            </div>
          )}

          {/* Reasoning */}
          {link.correlation.reasoning && (
            <div className="px-4 py-2 border-t border-slate-800/30 text-[10px] text-slate-500 italic">
              {link.correlation.reasoning}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Legacy: Change Correlations Section (kept for reference) ─────────────

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
          {correlation.timestamp && <div>Time: {safeDate(correlation.timestamp)}</div>}
          {correlation.files_changed.length > 0 && <div>Files: {correlation.files_changed.length} changed</div>}
        </div>
      )}
    </div>
  );
};

// ─── Legacy: Diff Analysis Section (kept for reference + DiffRow reused) ──

const verdictStyle: Record<DiffAnalysisItem['verdict'], { text: string; bg: string; border: string }> = {
  likely_cause: { text: 'text-red-300', bg: 'bg-red-500/20', border: 'border-red-500/30' },
  contributing: { text: 'text-amber-300', bg: 'bg-amber-500/20', border: 'border-amber-500/30' },
  unrelated: { text: 'text-slate-400', bg: 'bg-slate-500/20', border: 'border-slate-500/30' },
};

const DiffAnalysisSection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const items = findings?.diff_analysis || [];
  if (items.length === 0) return null;
  const causeCount = items.filter(d => d.verdict === 'likely_cause').length;

  return (
    <AgentFindingCard agent="D" title="Diff Intelligence">
      <div className="space-y-2">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-slate-500">{items.length} files analyzed</span>
          {causeCount > 0 && (
            <span className="text-[10px] font-bold text-red-400">{causeCount} likely cause{causeCount > 1 ? 's' : ''}</span>
          )}
        </div>
        {items.map((item, i) => (
          <DiffRow key={i} item={item} />
        ))}
      </div>
    </AgentFindingCard>
  );
};

const DiffRow: React.FC<{ item: DiffAnalysisItem }> = ({ item }) => {
  const [expanded, setExpanded] = useState(item.verdict === 'likely_cause');
  const style = verdictStyle[item.verdict];

  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700/50">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-3 py-2 flex items-center gap-2" aria-expanded={expanded}>
        <span className={`material-symbols-outlined text-xs text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${style.text} ${style.bg} ${style.border}`}>
          {item.verdict.replace(/_/g, ' ').toUpperCase()}
        </span>
        <span className="text-[11px] font-mono text-blue-400 truncate flex-1" title={item.file}>{item.file}</span>
        {item.commit_sha && (
          <span className="text-[10px] font-mono text-violet-400">{item.commit_sha.slice(0, 8)}</span>
        )}
      </button>
      {expanded && item.reasoning && (
        <div className="px-3 pb-2.5 text-[10px] text-slate-400 font-mono break-words">
          {item.reasoning}
        </div>
      )}
    </div>
  );
};

// ─── Legacy: Suggested Fix Areas Section (kept for reference + FixRow reused)

const SuggestedFixSection: React.FC<{ findings: V4Findings | null }> = ({ findings }) => {
  const fixes = findings?.suggested_fix_areas || [];
  if (fixes.length === 0) return null;

  return (
    <AgentFindingCard agent="D" title="Suggested Fixes">
      <div className="space-y-2">
        {fixes.map((fix, i) => (
          <FixRow key={i} fix={fix} />
        ))}
      </div>
    </AgentFindingCard>
  );
};

const FixRow: React.FC<{ fix: SuggestedFixArea }> = ({ fix }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700/50">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-3 py-2 flex items-center gap-2" aria-expanded={expanded}>
        <span className={`material-symbols-outlined text-xs text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`} style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
        <span className="text-[11px] font-mono text-blue-400 truncate" title={fix.file_path}>{fix.file_path}</span>
        <span className="text-[10px] text-slate-400 truncate flex-1 ml-1">{fix.description}</span>
      </button>
      {expanded && fix.suggested_change && (
        <div className="px-3 pb-2.5">
          <pre className="text-[10px] text-green-400 font-mono bg-slate-900/60 rounded p-2 overflow-x-auto whitespace-pre-wrap">{fix.suggested_change}</pre>
        </div>
      )}
    </div>
  );
};

// ─── Trace Waterfall ──────────────────────────────────────────────────────

const TraceWaterfall: React.FC<{ spans: SpanInfo[] }> = ({ spans }) => {
  const [expandedSpan, setExpandedSpan] = useState<number | null>(null);
  const totalDuration = Math.max(...spans.map((s) => s.duration_ms), 1);
  const errorCount = spans.filter((s) => s.status === 'error' || s.error).length;

  const depthMap = new Map<string, number>();
  const visiting = new Set<string>();
  const computeDepth = (span: SpanInfo): number => {
    if (depthMap.has(span.span_id)) return depthMap.get(span.span_id)!;
    if (!span.parent_span_id) { depthMap.set(span.span_id, 0); return 0; }
    if (visiting.has(span.span_id)) { depthMap.set(span.span_id, 0); return 0; }
    visiting.add(span.span_id);
    const parent = spans.find((s) => s.span_id === span.parent_span_id);
    const depth = parent ? computeDepth(parent) + 1 : 0;
    visiting.delete(span.span_id);
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
          const isExpanded = expandedSpan === i;
          const hasDetail = (isError && span.error_message) || (span.tags && Object.keys(span.tags).length > 0);
          return (
            <div key={i}>
              <button
                onClick={() => hasDetail ? setExpandedSpan(isExpanded ? null : i) : undefined}
                className={`flex items-center gap-2 py-0.5 w-full text-left ${hasDetail ? 'cursor-pointer hover:bg-slate-800/30 rounded' : 'cursor-default'}`}
                style={{ paddingLeft: `${depth * 16}px` }}
              >
                <span className="text-[10px] font-mono text-[#07b6d5] w-20 shrink-0 truncate">{span.service}</span>
                <span className="text-[10px] text-slate-400 w-28 shrink-0 truncate">{span.operation}</span>
                <div className="flex-1 h-3 bg-slate-800/50 rounded overflow-hidden">
                  <div className={`h-full rounded ${barColor}`} style={{ width: `${widthPct}%` }} />
                </div>
                <span className={`text-[10px] font-mono w-14 text-right shrink-0 ${isError ? 'text-red-400' : 'text-slate-400'}`}>
                  {span.duration_ms.toFixed(0)}ms
                </span>
              </button>
              {isExpanded && (
                <div className="ml-6 mt-1 mb-2 bg-slate-800/30 rounded-lg border border-slate-700/30 p-2 space-y-1" style={{ marginLeft: `${depth * 16 + 24}px` }}>
                  {span.error_message && (
                    <p className="text-[10px] text-red-400 font-mono break-all">{span.error_message}</p>
                  )}
                  {span.tags && Object.keys(span.tags).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(span.tags).map(([k, v]) => (
                        <span key={k} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400">
                          {k}={v}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── Pod Details List (expandable per-pod view) ──────────────────────────

const PodDetailsList: React.FC<{ pods: PodHealthStatus[] }> = ({ pods }) => {
  const [expandedPod, setExpandedPod] = useState<string | null>(null);
  const unhealthyPods = pods.filter((p) => !p.ready || p.oom_killed || p.crash_loop || p.restart_count > 0);
  const displayPods = unhealthyPods.length > 0 ? unhealthyPods : pods.slice(0, 3);

  if (displayPods.length === 0) return null;

  return (
    <div className="space-y-1 mb-2">
      <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">
        {unhealthyPods.length > 0 ? 'Unhealthy Pods' : 'Pod Details'}
      </span>
      {displayPods.map((pod) => {
        const isExpanded = expandedPod === pod.pod_name;
        return (
          <div key={pod.pod_name} className="bg-slate-800/30 rounded-lg border border-slate-700/30 overflow-hidden">
            <button
              onClick={() => setExpandedPod(isExpanded ? null : pod.pod_name)}
              className="w-full text-left px-2.5 py-1.5 flex items-center gap-2 hover:bg-slate-800/50 transition-colors"
            >
              <span className={`w-2 h-2 rounded-full shrink-0 ${pod.ready ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
              <span className="text-[10px] font-mono text-slate-300 truncate flex-1">{pod.pod_name}</span>
              {pod.oom_killed && <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">OOM</span>}
              {pod.crash_loop && <span className="text-[9px] px-1 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30">CRASH</span>}
              {pod.restart_count > 0 && <span className="text-[9px] text-amber-400 font-mono">{pod.restart_count}x</span>}
              <span className={`material-symbols-outlined text-xs text-slate-600 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                    style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
            </button>
            {isExpanded && (
              <div className="px-2.5 pb-2 pt-1 border-t border-slate-700/30 space-y-1 text-[10px]">
                <div className="flex gap-4 text-slate-500">
                  <span>Status: <span className="text-slate-300">{pod.status}</span></span>
                  {pod.namespace && <span>NS: <span className="text-slate-300">{pod.namespace}</span></span>}
                  {pod.container_count !== undefined && (
                    <span>Containers: <span className="text-slate-300">{pod.ready_containers ?? 0}/{pod.container_count}</span></span>
                  )}
                </div>
                {pod.conditions && pod.conditions.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {pod.conditions.map((c, i) => (
                      <span key={i} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400">{c}</span>
                    ))}
                  </div>
                )}
                {pod.resource_requests && Object.keys(pod.resource_requests).length > 0 && (
                  <div className="text-slate-500">
                    Requests: {Object.entries(pod.resource_requests).map(([k, v]) => `${k}=${v}`).join(', ')}
                  </div>
                )}
                {pod.resource_limits && Object.keys(pod.resource_limits).length > 0 && (
                  <div className="text-slate-500">
                    Limits: {Object.entries(pod.resource_limits).map(([k, v]) => `${k}=${v}`).join(', ')}
                  </div>
                )}
                {(pod.init_container_failures?.length ?? 0) > 0 && (
                  <div className="text-red-400">
                    Init failures: {pod.init_container_failures!.join(', ')}
                  </div>
                )}
                {(pod.image_pull_errors?.length ?? 0) > 0 && (
                  <div className="text-red-400">
                    Image errors: {pod.image_pull_errors!.join(', ')}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

// ─── Event Marker Timeline ────────────────────────────────────────────────

const severityMarkerColor: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-red-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-500',
  info: 'bg-slate-500',
};

const EventMarkerTimeline: React.FC<{ markers: EventMarker[] }> = ({ markers }) => {
  if (markers.length === 0) return null;

  const sorted = [...markers].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center gap-2">
        <span className="material-symbols-outlined text-amber-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>flag</span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Event Markers</span>
        <span className="text-[10px] text-slate-500 ml-auto">{markers.length} events</span>
      </div>
      <div className="p-4 space-y-1.5">
        {sorted.map((marker, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <span className={`w-2 h-2 rounded-full shrink-0 ${severityMarkerColor[marker.severity] || 'bg-slate-500'}`} />
            <span className="text-[10px] font-mono text-slate-400 shrink-0">
              {formatTime(marker.timestamp)}
            </span>
            <span className="text-slate-300">{marker.label}</span>
            <span className="text-[9px] text-slate-400 ml-auto shrink-0">{marker.source}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ─── Past Incidents Section ───────────────────────────────────────────────

const PastIncidentsSection: React.FC<{ incidents: PastIncidentMatch[] }> = ({ incidents }) => {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl overflow-hidden">
      <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center gap-2">
        <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>history</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-violet-400">Similar Past Incidents</span>
        <span className="text-[10px] text-slate-500 ml-auto">{incidents.length} match{incidents.length !== 1 ? 'es' : ''}</span>
      </div>
      <div className="p-4 space-y-2">
        {incidents.map((inc, i) => {
          const isExpanded = expandedIdx === i;
          const similarity = typeof inc.similarity_score === 'number'
            ? Math.round(inc.similarity_score * 100)
            : 0;
          const simColor = similarity >= 80 ? 'text-red-400' : similarity >= 50 ? 'text-amber-400' : 'text-blue-400';

          return (
            <div key={inc.fingerprint_id || i} className="bg-slate-800/30 rounded-lg border border-slate-700/50 overflow-hidden">
              <button
                onClick={() => setExpandedIdx(isExpanded ? null : i)}
                className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-slate-800/50 transition-colors"
              >
                <span className={`material-symbols-outlined text-xs text-slate-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                      style={{ fontFamily: 'Material Symbols Outlined' }}>chevron_right</span>
                <span className={`text-[10px] font-bold font-mono ${simColor}`}>{similarity}%</span>
                <span className="text-[11px] text-slate-300 truncate flex-1">{inc.root_cause || 'Unknown root cause'}</span>
                {inc.time_to_resolve > 0 && (
                  <span className="text-[9px] text-slate-500 font-mono shrink-0">
                    {inc.time_to_resolve < 3600
                      ? `${Math.round(inc.time_to_resolve / 60)}m`
                      : `${(inc.time_to_resolve / 3600).toFixed(1)}h`} to resolve
                  </span>
                )}
              </button>
              {isExpanded && (
                <div className="px-3 pb-3 border-t border-slate-700/30 pt-2 space-y-2">
                  {(inc.error_patterns?.length ?? 0) > 0 && (
                    <div>
                      <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Error Patterns</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {inc.error_patterns?.map((ep, j) => (
                          <span key={j} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">{ep}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {(inc.affected_services?.length ?? 0) > 0 && (
                    <div>
                      <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Affected Services</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {inc.affected_services?.map((svc, j) => (
                          <span key={j} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-300">{svc}</span>
                        ))}
                      </div>
                    </div>
                  )}
                  {(inc.resolution_steps?.length ?? 0) > 0 && (
                    <div>
                      <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Resolution Steps</span>
                      <ol className="mt-1 space-y-0.5">
                        {inc.resolution_steps?.map((step, j) => (
                          <li key={j} className="text-[10px] text-slate-400 flex items-start gap-1.5">
                            <span className="text-slate-600 shrink-0">{j + 1}.</span>
                            <span>{step}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ─── Phase-Aware Empty State ───────────────────────────────────────────────

const phaseEmptyMessages: Record<string, { icon: string; message: string }> = {
  initial: { icon: 'radar', message: 'Agents are gathering data...' },
  collecting_context: { icon: 'radar', message: 'Agents are gathering data...' },
  logs_analyzed: { icon: 'analytics', message: 'Log analysis complete. Waiting for metrics...' },
  metrics_analyzed: { icon: 'analytics', message: 'Metrics analyzed. Continuing investigation...' },
  k8s_analyzed: { icon: 'analytics', message: 'K8s analysis done. Continuing investigation...' },
  diagnosis_complete: { icon: 'check_circle', message: 'Investigation complete. Review findings above.' },
  complete: { icon: 'check_circle', message: 'Investigation complete.' },
};

const PhaseAwareEmptyState: React.FC<{ phase: DiagnosticPhase | null }> = ({ phase }) => {
  const info = phaseEmptyMessages[phase || 'initial'] || phaseEmptyMessages.initial;
  const isComplete = phase === 'diagnosis_complete' || phase === 'complete';

  return (
    <div className="flex items-center justify-center h-full min-h-[200px] text-slate-400">
      <div className="text-center">
        {!isComplete && (
          <div className="w-8 h-8 border-2 border-slate-800 border-t-[#07b6d5] rounded-full animate-spin mx-auto mb-3" />
        )}
        <span
          className="material-symbols-outlined text-2xl text-slate-500 mb-2 block"
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          {info.icon}
        </span>
        <p className="text-sm">{info.message}</p>
      </div>
    </div>
  );
};

export default EvidenceFindings;
