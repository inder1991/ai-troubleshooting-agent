import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type {
  V4Findings,
  PostmortemDossierData,
  ErrorPattern,
  Finding,
} from '../../types';
import { previewPostMortem, publishPostMortem, getFindings } from '../../services/api';
import AgentFindingCard from './cards/AgentFindingCard';
import CausalRoleBadge from './cards/CausalRoleBadge';
import MermaidChart from '../Agent2/Mermaid';
import CopyButton from '../ui/CopyButton';

// ── Types ──────────────────────────────────────────────────────────────────

interface PostMortemDossierViewProps {
  sessionId: string;
  onBack: () => void;
}

type AgentCode = 'L' | 'M' | 'K' | 'C' | 'D';

const SECTIONS = [
  { id: 'incident-card', title: 'Incident Card', icon: 'badge' },
  { id: 'executive-summary', title: 'Executive Summary', icon: 'summarize' },
  { id: 'impact-statement', title: 'Impact Statement', icon: 'crisis_alert' },
  { id: 'visual-topology', title: 'Visual Topology', icon: 'hub' },
  { id: 'timeline', title: 'Timeline of Truth', icon: 'timeline' },
  { id: 'evidence-table', title: 'Evidence Table', icon: 'table_chart' },
  { id: 'agent-reasoning', title: 'Agent Reasoning', icon: 'psychology' },
  { id: 'remediation', title: 'Remediation', icon: 'build' },
  { id: 'action-items', title: 'Action Items', icon: 'checklist' },
  { id: 'publish', title: 'Publish', icon: 'publish' },
] as const;

// ── Helpers ────────────────────────────────────────────────────────────────

function agentCodeFromName(name: string): AgentCode {
  const n = name.toLowerCase();
  if (n.includes('log')) return 'L';
  if (n.includes('metric')) return 'M';
  if (n.includes('k8s') || n.includes('kube')) return 'K';
  if (n.includes('change') || n.includes('intel')) return 'C';
  return 'D';
}

function severityColor(sev?: string): string {
  switch (sev) {
    case 'P1': return 'text-red-400 bg-red-500/20 border-red-500/30';
    case 'P2': return 'text-orange-400 bg-orange-500/20 border-orange-500/30';
    case 'P3': return 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30';
    case 'P4': return 'text-green-400 bg-green-500/20 border-green-500/30';
    default: return 'text-slate-400 bg-slate-500/20 border-slate-500/30';
  }
}

// ── DossierSection wrapper ─────────────────────────────────────────────────

const DossierSection: React.FC<{
  id: string;
  title: string;
  icon: string;
  index: number;
  sectionRef: (el: HTMLElement | null) => void;
  children: React.ReactNode;
}> = ({ id, title, icon, index, sectionRef, children }) => (
  <motion.section
    id={id}
    ref={sectionRef}
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: 0.1 + index * 0.08 }}
    className="mb-12 group dossier-section"
  >
    <div className="flex items-center gap-3 mb-4 border-b border-slate-800 pb-2">
      <div className="w-1 h-6 bg-[#07b6d5] shadow-[0_0_10px_rgba(7,182,213,0.5)]" />
      <span className="material-symbols-outlined text-cyan-500" style={{ fontFamily: 'Material Symbols Outlined' }}>
        {icon}
      </span>
      <h2 className="text-lg font-bold uppercase tracking-widest text-white">{title}</h2>
    </div>
    <div className="pl-4">{children}</div>
  </motion.section>
);

// ── AttestationBadge ───────────────────────────────────────────────────────

const AttestationBadge: React.FC<{ humanVerified: boolean }> = ({ humanVerified }) => (
  <span
    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-wider border ${
      humanVerified
        ? 'bg-cyan-500/10 border-cyan-500/20 text-cyan-400'
        : 'bg-violet-500/10 border-violet-500/20 text-violet-400'
    }`}
  >
    <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>
      {humanVerified ? 'verified' : 'smart_toy'}
    </span>
    {humanVerified ? 'HUMAN-VERIFIED' : 'AI-GENERATED'}
  </span>
);

// ── ResolvedStamp ─────────────────────────────────────────────────────────

const ResolvedStamp: React.FC = () => {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 3, rotate: -15 }}
      animate={{ opacity: 0.8, scale: 1, rotate: -15 }}
      transition={{ type: "spring", stiffness: 300, damping: 15, delay: 0.8 }}
      className="absolute top-12 right-12 z-50 pointer-events-none select-none"
    >
      <div className="border-4 border-emerald-500 rounded-lg px-6 py-2 bg-emerald-500/10 backdrop-blur-sm shadow-[0_0_40px_rgba(16,185,129,0.3)]">
        <h2
          className="text-5xl font-black text-emerald-400 tracking-[0.2em] uppercase mix-blend-screen"
          style={{ textShadow: '0 0 15px rgba(16,185,129,0.6)' }}
        >
          Resolved
        </h2>
      </div>
    </motion.div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────

const PostMortemDossierView: React.FC<PostMortemDossierViewProps> = ({
  sessionId,
  onBack,
}) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [dossierData, setDossierData] = useState<PostmortemDossierData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editable narrative fields
  const [execSummary, setExecSummary] = useState('');
  const [impactStmt, setImpactStmt] = useState('');
  const [editingExec, setEditingExec] = useState(false);
  const [editingImpact, setEditingImpact] = useState(false);
  const [humanVerified, setHumanVerified] = useState<Record<'exec' | 'impact', boolean>>({
    exec: false,
    impact: false,
  });

  // Publish
  const [spaceKey, setSpaceKey] = useState('ENG');
  const [publishTitle, setPublishTitle] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [showPublishSuccess, setShowPublishSuccess] = useState(false);

  // ToC tracking
  const [activeSection, setActiveSection] = useState<string>(SECTIONS[0].id);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Fetch findings + dossier data fresh on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const [data, freshFindings] = await Promise.all([
          previewPostMortem(sessionId),
          getFindings(sessionId),
        ]);
        if (cancelled) return;
        setDossierData(data);
        setFindings(freshFindings);
        setExecSummary(data.executive_summary || '');
        setImpactStmt(data.impact_statement || '');
        setPublishTitle(data.title || '');
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load dossier');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  // IntersectionObserver for ToC active tracking
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        }
      },
      { root: container, rootMargin: '-20% 0px -70% 0px', threshold: 0 }
    );

    for (const ref of Object.values(sectionRefs.current)) {
      if (ref) observer.observe(ref);
    }

    return () => observer.disconnect();
  }, [dossierData]);

  const handleSectionClick = useCallback((sectionId: string) => {
    const el = sectionRefs.current[sectionId];
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const handleSaveExec = useCallback(() => {
    setEditingExec(false);
    setHumanVerified((prev) => ({ ...prev, exec: true }));
  }, []);

  const handleSaveImpact = useCallback(() => {
    setEditingImpact(false);
    setHumanVerified((prev) => ({ ...prev, impact: true }));
  }, []);

  const handlePublish = useCallback(async () => {
    if (publishing) return;
    setPublishing(true);
    try {
      // Build final markdown with narrative sections
      let markdown = dossierData?.body_markdown || '';
      if (execSummary) {
        const marker = humanVerified.exec ? '<!-- human-verified -->\n' : '';
        markdown = `## Executive Summary\n\n${execSummary}\n${marker}\n` + markdown;
      }
      if (impactStmt) {
        const marker = humanVerified.impact ? '<!-- human-verified -->\n' : '';
        markdown = `## Impact Statement\n\n${impactStmt}\n${marker}\n` + markdown;
      }

      await publishPostMortem(sessionId, {
        space_key: spaceKey,
        title: publishTitle,
        body_markdown: markdown,
      });
      setShowPublishSuccess(true);
      setTimeout(() => setShowPublishSuccess(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Publish failed');
    } finally {
      setPublishing(false);
    }
  }, [publishing, dossierData, execSummary, impactStmt, humanVerified, sessionId, spaceKey, publishTitle]);

  // Build full markdown for copy
  const fullMarkdown = useMemo(() => {
    let md = dossierData?.body_markdown || '';
    if (execSummary) md = `## Executive Summary\n\n${execSummary}\n\n` + md;
    if (impactStmt) md = `## Impact Statement\n\n${impactStmt}\n\n` + md;
    return md;
  }, [dossierData, execSummary, impactStmt]);

  // Group findings by agent
  const findingsByAgent = useMemo(() => {
    const groups: Record<string, Finding[]> = {};
    if (findings?.findings) {
      for (const f of findings.findings) {
        const agent = f.agent_name || 'unknown';
        if (!groups[agent]) groups[agent] = [];
        groups[agent].push(f);
      }
    }
    return groups;
  }, [findings]);

  // Sorted error patterns
  const sortedPatterns = useMemo(() => {
    if (!findings?.error_patterns) return [];
    return [...findings.error_patterns].sort(
      (a, b) => (a.priority_rank || 999) - (b.priority_rank || 999)
    );
  }, [findings]);

  const setSectionRef = useCallback((id: string) => (el: HTMLElement | null) => {
    sectionRefs.current[id] = el;
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0f2023]">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center"
        >
          <span className="material-symbols-outlined text-4xl text-cyan-500 animate-spin" style={{ fontFamily: 'Material Symbols Outlined' }}>
            sync
          </span>
          <div className="text-sm text-slate-400 mt-3">Compiling incident dossier...</div>
        </motion.div>
      </div>
    );
  }

  if (error && !dossierData) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#0f2023]">
        <div className="text-center">
          <span className="material-symbols-outlined text-4xl text-red-400" style={{ fontFamily: 'Material Symbols Outlined' }}>error</span>
          <div className="text-sm text-red-400 mt-3">{error}</div>
          <button onClick={onBack} className="mt-4 text-sm text-cyan-400 hover:underline">Back to War Room</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-[#0f2023] overflow-hidden h-full">
      {/* Header bar */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-900/60 shrink-0">
        <button
          onClick={onBack}
          className="dossier-back-button flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          <span className="material-symbols-outlined text-base" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
          Back to War Room
        </button>
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-cyan-500" style={{ fontFamily: 'Material Symbols Outlined' }}>description</span>
          <span className="text-sm font-bold uppercase tracking-[0.2em] text-white">Incident Dossier</span>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sticky sidebar ToC */}
        <nav className="dossier-nav-sidebar w-56 shrink-0 border-r border-slate-800 bg-slate-900/40 overflow-y-auto py-6 px-4">
          <div className="text-[9px] font-bold uppercase tracking-[0.2em] text-slate-600 mb-4 px-2">
            Contents
          </div>
          {SECTIONS.map((section, i) => {
            const isActive = activeSection === section.id;
            return (
              <button
                key={section.id}
                onClick={() => handleSectionClick(section.id)}
                className={`w-full text-left px-3 py-2 rounded-r text-[11px] transition-all flex items-center gap-2 mb-0.5 ${
                  isActive
                    ? 'border-l-2 border-[#07b6d5] text-white bg-cyan-500/5'
                    : 'border-l-2 border-transparent text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
                }`}
              >
                <span className="text-[10px] text-slate-600 font-mono w-4">{i + 1}</span>
                {section.title}
              </button>
            );
          })}
        </nav>

        {/* Scrollable content */}
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-8 py-8">
          <div className="max-w-4xl mx-auto relative">
            <ResolvedStamp />
            {error && (
              <div className="mb-4 text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
                {error}
              </div>
            )}

            {/* Section 1: Incident Card */}
            <DossierSection id="incident-card" title="Incident Card" icon="badge" index={0} sectionRef={setSectionRef('incident-card')}>
              <div className="grid grid-cols-2 gap-4 text-[12px]">
                <InfoRow label="Incident ID" value={findings?.incident_id || findings?.session_id || '—'} />
                <InfoRow label="Service" value={findings?.target_service || '—'} />
                <div>
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider">Severity</span>
                  <div className="mt-1">
                    {findings?.severity_recommendation ? (
                      <span className={`inline-flex px-2 py-0.5 rounded border text-[11px] font-bold ${severityColor(findings.severity_recommendation.recommended_severity)}`}>
                        {findings.severity_recommendation.recommended_severity}
                      </span>
                    ) : <span className="text-slate-400">—</span>}
                  </div>
                </div>
                <InfoRow label="Blast Radius" value={findings?.blast_radius?.scope?.replace(/_/g, ' ') || '—'} />
                <InfoRow label="Patient Zero" value={findings?.patient_zero?.service || '—'} />
                <InfoRow
                  label="Root Cause"
                  value={findings?.root_cause_location?.relationship || findings?.error_patterns?.[0]?.exception_type || '—'}
                />
                <InfoRow
                  label="Confidence"
                  value={findings?.code_overall_confidence ? `${findings.code_overall_confidence}%` : '—'}
                />
                <InfoRow
                  label="Jira"
                  value={findings?.closure_state?.jira_result?.issue_key || '—'}
                />
                <InfoRow
                  label="Remedy"
                  value={findings?.closure_state?.remedy_result?.incident_number || '—'}
                />
              </div>
            </DossierSection>

            {/* Section 2: Executive Summary */}
            <DossierSection id="executive-summary" title="Executive Summary" icon="summarize" index={1} sectionRef={setSectionRef('executive-summary')}>
              <div className="flex items-center gap-3 mb-3">
                <AttestationBadge humanVerified={humanVerified.exec} />
                {!editingExec && (
                  <button
                    onClick={() => setEditingExec(true)}
                    className="dossier-edit-toggle text-[10px] text-slate-500 hover:text-slate-300 flex items-center gap-1"
                  >
                    <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>edit</span>
                    Edit
                  </button>
                )}
              </div>
              {editingExec ? (
                <div className="space-y-2">
                  <textarea
                    value={execSummary}
                    onChange={(e) => setExecSummary(e.target.value)}
                    rows={4}
                    className="w-full bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 text-[12px] text-slate-200 focus:outline-none focus:border-cyan-500/50 resize-none"
                  />
                  <button
                    onClick={handleSaveExec}
                    className="text-[10px] font-bold px-3 py-1.5 rounded bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <p className="text-[13px] text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {execSummary || 'No executive summary available. Click Edit to write one.'}
                </p>
              )}
            </DossierSection>

            {/* Section 3: Impact Statement */}
            <DossierSection id="impact-statement" title="Impact Statement" icon="crisis_alert" index={2} sectionRef={setSectionRef('impact-statement')}>
              <div className="flex items-center gap-3 mb-3">
                <AttestationBadge humanVerified={humanVerified.impact} />
                {!editingImpact && (
                  <button
                    onClick={() => setEditingImpact(true)}
                    className="dossier-edit-toggle text-[10px] text-slate-500 hover:text-slate-300 flex items-center gap-1"
                  >
                    <span className="material-symbols-outlined text-[12px]" style={{ fontFamily: 'Material Symbols Outlined' }}>edit</span>
                    Edit
                  </button>
                )}
              </div>
              {editingImpact ? (
                <div className="space-y-2">
                  <textarea
                    value={impactStmt}
                    onChange={(e) => setImpactStmt(e.target.value)}
                    rows={4}
                    className="w-full bg-slate-800/60 border border-slate-700/50 rounded-lg p-3 text-[12px] text-slate-200 focus:outline-none focus:border-cyan-500/50 resize-none"
                  />
                  <button
                    onClick={handleSaveImpact}
                    className="text-[10px] font-bold px-3 py-1.5 rounded bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <p className="text-[13px] text-slate-300 leading-relaxed whitespace-pre-wrap">
                  {impactStmt || 'No impact statement available. Click Edit to write one.'}
                </p>
              )}
            </DossierSection>

            {/* Section 4: Visual Topology */}
            <DossierSection id="visual-topology" title="Visual Topology" icon="hub" index={3} sectionRef={setSectionRef('visual-topology')}>
              <div className="dossier-mermaid-section bg-slate-900/60 border border-slate-800 rounded-lg p-4 min-h-[200px]">
                {findings?.code_mermaid_diagram ? (
                  <MermaidChart chart={findings.code_mermaid_diagram} />
                ) : (
                  <div className="flex flex-col items-center justify-center h-40 text-slate-500 text-[12px] gap-2">
                    <span className="material-symbols-outlined text-[20px] text-slate-600" style={{ fontFamily: 'Material Symbols Outlined' }}>account_tree</span>
                    <span>No topology diagram available.</span>
                    <span className="text-[10px] text-slate-600">Attach a repository to enable code-level topology mapping.</span>
                  </div>
                )}
              </div>
            </DossierSection>

            {/* Section 5: Timeline of Truth */}
            <DossierSection id="timeline" title="Timeline of Truth" icon="timeline" index={4} sectionRef={setSectionRef('timeline')}>
              {!findings?.patient_zero && !findings?.service_flow?.length && !findings?.reasoning_chain?.length ? (
                <div className="text-[12px] text-slate-500 py-4 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[14px] text-slate-600" style={{ fontFamily: 'Material Symbols Outlined' }}>hourglass_empty</span>
                  No timeline events available yet. Events populate as the investigation progresses.
                </div>
              ) : (
                <div className="relative pl-6">
                  <div className="absolute left-2 top-0 bottom-0 w-px bg-slate-700" />

                  {/* Patient zero event */}
                  {findings?.patient_zero && (
                    <TimelineEvent
                      timestamp={findings.patient_zero.first_error_time || ''}
                      description={`Patient Zero: ${findings.patient_zero.service} — ${findings.patient_zero.evidence}`}
                      source="Patient Zero"
                      isFirst
                    />
                  )}

                  {/* Service flow events */}
                  {findings?.service_flow?.slice(0, 15).map((step, i) => (
                    <TimelineEvent
                      key={i}
                      timestamp={step.timestamp}
                      description={`${step.service} → ${step.operation} [${step.status}]${step.message ? ` — ${step.message}` : ''}`}
                      source={step.is_new_service ? 'New Service' : 'Trace'}
                      isError={step.status === 'error' || step.status === 'timeout'}
                    />
                  ))}

                  {/* Reasoning chain events */}
                  {findings?.reasoning_chain?.slice(0, 5).map((step, i) => (
                    <TimelineEvent
                      key={`rc-${i}`}
                      timestamp=""
                      description={step.inference}
                      source={step.tool || `Step ${step.step}`}
                    />
                  ))}
                </div>
              )}
            </DossierSection>

            {/* Section 6: Evidence Table */}
            <DossierSection id="evidence-table" title="Evidence Table" icon="table_chart" index={5} sectionRef={setSectionRef('evidence-table')}>
              <div className="dossier-evidence-table overflow-x-auto">
                {sortedPatterns.length > 0 ? (
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-left text-[9px] text-slate-500 uppercase tracking-wider border-b border-slate-800">
                        <th className="py-2 pr-3">Pattern</th>
                        <th className="py-2 pr-3">Freq</th>
                        <th className="py-2 pr-3">Severity</th>
                        <th className="py-2 pr-3">Causal Role</th>
                        <th className="py-2">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPatterns.map((p: ErrorPattern, i: number) => (
                        <tr key={p.pattern_id || i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                          <td className="py-2 pr-3 text-slate-200 font-mono max-w-[300px] truncate">
                            {p.exception_type}
                          </td>
                          <td className="py-2 pr-3 text-slate-400">{p.frequency}</td>
                          <td className="py-2 pr-3">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                              p.severity === 'critical' ? 'text-red-400 bg-red-500/20' :
                              p.severity === 'high' ? 'text-orange-400 bg-orange-500/20' :
                              p.severity === 'medium' ? 'text-yellow-400 bg-yellow-500/20' :
                              'text-slate-400 bg-slate-500/20'
                            }`}>
                              {p.severity}
                            </span>
                          </td>
                          <td className="py-2 pr-3">
                            {p.causal_role && <CausalRoleBadge role={p.causal_role} />}
                          </td>
                          <td className="py-2 text-slate-400">{p.confidence_score}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="text-[12px] text-slate-500 py-4">No error patterns available</div>
                )}
              </div>
            </DossierSection>

            {/* Section 7: Agent Reasoning Log */}
            <DossierSection id="agent-reasoning" title="Agent Reasoning Log" icon="psychology" index={6} sectionRef={setSectionRef('agent-reasoning')}>
              <div className="space-y-3">
                {Object.keys(findingsByAgent).length > 0 ? (
                  Object.entries(findingsByAgent).map(([agentName, agentFindings]) => (
                    <AgentFindingCard
                      key={agentName}
                      agent={agentCodeFromName(agentName)}
                      title={`${agentFindings.length} finding${agentFindings.length !== 1 ? 's' : ''}`}
                    >
                      <div className="space-y-1.5">
                        {agentFindings.slice(0, 3).map((f) => (
                          <div key={f.finding_id} className="text-[11px] text-slate-300">
                            <span className={`inline-block w-1.5 h-1.5 rounded-full mr-2 ${
                              f.severity === 'critical' ? 'bg-red-500' :
                              f.severity === 'high' ? 'bg-orange-500' :
                              f.severity === 'medium' ? 'bg-yellow-500' :
                              'bg-slate-500'
                            }`} />
                            {f.summary}
                            <span className="text-slate-500 ml-2">({f.confidence_score}%)</span>
                          </div>
                        ))}
                        {agentFindings.length > 3 && (
                          <div className="text-[10px] text-slate-500 mt-1">
                            +{agentFindings.length - 3} more
                          </div>
                        )}
                      </div>
                    </AgentFindingCard>
                  ))
                ) : (
                  <div className="text-[12px] text-slate-500">No agent findings available</div>
                )}
              </div>
            </DossierSection>

            {/* Section 8: Remediation */}
            <DossierSection id="remediation" title="Remediation" icon="build" index={7} sectionRef={setSectionRef('remediation')}>
              {findings?.fix_data ? (
                <div className="space-y-3">
                  {findings.fix_data.fix_explanation && (
                    <div className="text-[12px] text-slate-300">
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Fix Explanation</span>
                      {findings.fix_data.fix_explanation}
                    </div>
                  )}
                  {findings.fix_data.pr_url && (
                    <div className="text-[12px]">
                      <span className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">Pull Request</span>
                      <a
                        href={findings.fix_data.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-cyan-400 hover:underline font-mono"
                      >
                        {findings.fix_data.pr_url}
                      </a>
                    </div>
                  )}
                  {findings.fix_data.pr_data?.branch_name && (
                    <InfoRow label="Branch" value={findings.fix_data.pr_data.branch_name} />
                  )}
                  {findings.fix_data.pr_data?.commit_sha && (
                    <InfoRow label="Commit" value={findings.fix_data.pr_data.commit_sha.slice(0, 8)} />
                  )}
                  {findings.fix_data.diff && (
                    <details className="mt-2">
                      <summary className="text-[10px] text-cyan-500 cursor-pointer hover:text-cyan-300">
                        View Diff
                      </summary>
                      <pre className="mt-2 text-[10px] text-slate-300 bg-slate-900/80 border border-slate-800 rounded-lg p-3 overflow-x-auto max-h-[400px] overflow-y-auto font-mono whitespace-pre">
                        {findings.fix_data.diff.slice(0, 3000)}
                      </pre>
                    </details>
                  )}
                </div>
              ) : (
                <div className="text-[12px] text-slate-500 flex flex-col gap-1">
                  <span>No automated fix was generated.</span>
                  <span className="text-[10px] text-slate-600">Attach a repository during session setup to enable automated fix generation.</span>
                </div>
              )}
            </DossierSection>

            {/* Section 9: Action Items */}
            <DossierSection id="action-items" title="Action Items" icon="checklist" index={8} sectionRef={setSectionRef('action-items')}>
              <div className="space-y-4">
                {/* PromQL alerting recommendations */}
                {findings?.suggested_promql_queries && findings.suggested_promql_queries.length > 0 && (
                  <div>
                    <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">Alerting Recommendations</h3>
                    <div className="space-y-2">
                      {findings.suggested_promql_queries.map((q, i) => (
                        <div key={i} className="bg-slate-800/40 border border-slate-700/50 rounded-lg p-3">
                          <div className="text-[11px] text-slate-300 font-medium">{q.metric}</div>
                          <code className="block text-[10px] text-cyan-400 font-mono mt-1">{q.query}</code>
                          <div className="text-[10px] text-slate-500 mt-1">{q.rationale}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Inferred dependencies / circuit breaker recs */}
                {findings?.inferred_dependencies && findings.inferred_dependencies.length > 0 && (
                  <div>
                    <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">Circuit Breaker Recommendations</h3>
                    <div className="space-y-1">
                      {findings.inferred_dependencies.map((dep, i) => (
                        <div key={i} className="text-[11px] text-slate-400">
                          <span className="text-slate-300">{dep.source}</span>
                          {dep.target && <span> → {dep.target}</span>}
                          {dep.evidence && <span className="text-slate-500 ml-2">({dep.evidence})</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ITSM links */}
                <div>
                  <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">ITSM Links</h3>
                  <div className="space-y-1 text-[11px]">
                    {findings?.closure_state?.jira_result?.status === 'success' ? (
                      <div className="flex items-center gap-2">
                        <span className="text-green-400">Jira:</span>
                        <a href={findings.closure_state.jira_result.issue_url} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
                          {findings.closure_state.jira_result.issue_key}
                        </a>
                      </div>
                    ) : (
                      <div className="text-slate-500">Jira: Not created</div>
                    )}
                    {findings?.closure_state?.remedy_result?.status === 'success' ? (
                      <div className="flex items-center gap-2">
                        <span className="text-green-400">Remedy:</span>
                        <a href={findings.closure_state.remedy_result.incident_url} target="_blank" rel="noopener noreferrer" className="text-cyan-400 hover:underline">
                          {findings.closure_state.remedy_result.incident_number}
                        </a>
                      </div>
                    ) : (
                      <div className="text-slate-500">Remedy: Not created</div>
                    )}
                  </div>
                </div>

                {/* Verification checklist */}
                <div>
                  <h3 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-2">Verification Checklist</h3>
                  <div className="space-y-1 text-[11px] text-slate-400">
                    <div>&#9744; Verify fix in production</div>
                    <div>&#9744; Update runbook if applicable</div>
                    <div>&#9744; Schedule follow-up review</div>
                    <div>&#9744; Confirm alerting rules deployed</div>
                  </div>
                </div>
              </div>
            </DossierSection>

            {/* Section 10: Publish Footer */}
            <DossierSection id="publish" title="Publish" icon="publish" index={9} sectionRef={setSectionRef('publish')}>
              <div className="dossier-publish-footer space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">
                      Confluence Space Key
                    </label>
                    <input
                      type="text"
                      value={spaceKey}
                      onChange={(e) => setSpaceKey(e.target.value)}
                      className="text-[12px] bg-slate-800/60 border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-600 w-full font-mono focus:outline-none focus:border-cyan-500/50"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">
                      Page Title
                    </label>
                    <input
                      type="text"
                      value={publishTitle}
                      onChange={(e) => setPublishTitle(e.target.value)}
                      className="text-[12px] bg-slate-800/60 border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-600 w-full focus:outline-none focus:border-cyan-500/50"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    onClick={handlePublish}
                    disabled={publishing || !spaceKey.trim()}
                    className="text-[11px] font-bold px-4 py-2 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
                  >
                    <span className="material-symbols-outlined text-[14px]" style={{ fontFamily: 'Material Symbols Outlined' }}>
                      {publishing ? 'sync' : 'cloud_upload'}
                    </span>
                    {publishing ? 'Publishing...' : 'Publish to Confluence'}
                  </button>

                  <CopyButton text={fullMarkdown} className="!p-2" size={14} />
                  <span className="text-[10px] text-slate-600">Copy Markdown</span>
                </div>

                <div className="text-[10px] text-slate-600 mt-2">
                  Generated at {new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC
                </div>
              </div>
            </DossierSection>
          </div>
        </div>
      </div>

      {/* Publish Success Cinematic */}
      <AnimatePresence>
        {showPublishSuccess && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none"
          >
            <motion.div
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
              className="absolute inset-0 bg-emerald-500/10 origin-bottom"
            />
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: 0.3, type: 'spring' }}
              className="relative text-center"
            >
              <span className="material-symbols-outlined text-6xl text-emerald-400 drop-shadow-[0_0_20px_rgba(16,185,129,0.6)]" style={{ fontFamily: 'Material Symbols Outlined' }}>
                task_alt
              </span>
              <div className="text-lg font-bold uppercase tracking-[0.3em] text-emerald-300 mt-4">
                Transmission Complete
              </div>
              <div className="text-sm text-emerald-400/60 mt-1">Post-mortem published to Confluence</div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Small sub-components ───────────────────────────────────────────────────

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <span className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</span>
    <div className="text-[12px] text-slate-200 mt-0.5 font-mono truncate">{value}</div>
  </div>
);

const TimelineEvent: React.FC<{
  timestamp: string;
  description: string;
  source: string;
  isFirst?: boolean;
  isError?: boolean;
}> = ({ timestamp, description, source, isFirst, isError }) => (
  <div className="relative mb-4 pl-4">
    <div className={`absolute -left-[5px] top-1.5 w-3 h-3 rounded-full border-2 ${
      isFirst ? 'bg-red-500 border-red-400' :
      isError ? 'bg-orange-500 border-orange-400' :
      'bg-slate-600 border-slate-500'
    }`} />
    <div className="flex items-start gap-3">
      {timestamp && (
        <span className="text-[10px] text-slate-500 font-mono whitespace-nowrap mt-0.5">
          {timestamp}
        </span>
      )}
      <div className="flex-1">
        <span className="text-[11px] text-slate-300">{description}</span>
        <span className="text-[9px] ml-2 px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 border border-slate-700/50">
          {source}
        </span>
      </div>
    </div>
  </div>
);

export default PostMortemDossierView;
