import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import type { V4Findings } from '../../types';
import { getFindings } from '../../services/api';

interface DatabaseDossierViewProps {
  sessionId: string;
  onBack: () => void;
}

const DB_SECTIONS = [
  { id: 'executive-summary', title: 'Executive Summary', icon: 'summarize' },
  { id: 'root-cause', title: 'Root Cause Analysis', icon: 'search' },
  { id: 'findings-by-agent', title: 'Findings by Agent', icon: 'psychology' },
  { id: 'performance', title: 'Performance Recommendations', icon: 'speed' },
  { id: 'remediation', title: 'Remediation Plans', icon: 'build' },
  { id: 'health-scorecard', title: 'Health Scorecard', icon: 'monitoring' },
] as const;

function severityBadge(severity: string) {
  const colors: Record<string, string> = {
    critical: 'text-red-400 bg-red-500/10',
    high: 'text-orange-400 bg-orange-500/10',
    medium: 'text-yellow-400 bg-yellow-500/10',
    low: 'text-emerald-400 bg-emerald-500/10',
    info: 'text-slate-400 bg-slate-500/10',
  };
  return colors[severity] || colors.info;
}

const DossierSection: React.FC<{
  id: string;
  title: string;
  icon: string;
  index: number;
  children: React.ReactNode;
}> = ({ id, title, icon, index, children }) => (
  <motion.section
    id={id}
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ delay: 0.1 + index * 0.08 }}
    className="mb-10"
  >
    <div className="flex items-center gap-3 mb-4 border-b border-slate-800 pb-2">
      <div className="w-1 h-6 bg-violet-500 shadow-[0_0_10px_rgba(139,92,246,0.5)]" />
      <span className="material-symbols-outlined text-violet-400">
        {icon}
      </span>
      <h2 className="text-lg font-bold text-white">{title}</h2>
    </div>
    {children}
  </motion.section>
);

const DatabaseDossierView: React.FC<DatabaseDossierViewProps> = ({ sessionId, onBack }) => {
  const [findings, setFindings] = useState<V4Findings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getFindings(sessionId)
      .then(setFindings)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [sessionId]);

  const allFindings = findings?.findings || [];
  const rawData = findings as any;
  const summary: string = rawData?.summary || 'No summary available.';
  const rootCause: string = rawData?.root_cause || 'Undetermined';

  const queryFindings = allFindings.filter((f: any) => f.agent === 'query_analyst');
  const healthFindings = allFindings.filter((f: any) => f.agent === 'health_analyst');
  const schemaFindings = allFindings.filter((f: any) => f.agent === 'schema_analyst');

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-outlined text-4xl text-violet-400 animate-pulse block mb-2">database</span>
          <p className="text-sm text-slate-400">Loading database dossier...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto bg-duck-bg">
      <div className="max-w-4xl mx-auto px-8 py-10">
        {/* Back button */}
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white mb-6 transition-colors"
        >
          <span className="material-symbols-outlined text-base">arrow_back</span>
          <span>Back to Investigation</span>
        </button>

        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-violet-500/10 border border-violet-500/20">
            <span className="material-symbols-outlined text-violet-400 text-2xl">description</span>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Database Diagnostic Report</h1>
            <p className="text-xs text-slate-500">Session: {sessionId.slice(0, 8)} — {new Date().toLocaleDateString()}</p>
          </div>
        </div>

        {/* Section Navigation */}
        <div className="flex flex-wrap gap-2 mb-8">
          {DB_SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] text-slate-400 hover:text-white bg-duck-card/30 border border-duck-border hover:border-violet-500/30 transition-colors"
            >
              <span className="material-symbols-outlined text-xs">{s.icon}</span>
              {s.title}
            </a>
          ))}
        </div>

        {/* Executive Summary */}
        <DossierSection id="executive-summary" title="Executive Summary" icon="summarize" index={0}>
          <div className="bg-duck-card/30 border border-duck-border rounded-lg p-4">
            <p className="text-sm text-slate-300 leading-relaxed">{summary}</p>
          </div>
        </DossierSection>

        {/* Root Cause */}
        <DossierSection id="root-cause" title="Root Cause Analysis" icon="search" index={1}>
          <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-red-400 text-sm">error</span>
              <span className="text-xs font-bold text-red-400 uppercase tracking-wider">Root Cause</span>
            </div>
            <p className="text-sm text-white font-medium">{rootCause}</p>
          </div>
        </DossierSection>

        {/* Findings by Agent */}
        <DossierSection id="findings-by-agent" title="Findings by Agent" icon="psychology" index={2}>
          {[
            { label: 'Query Analyst', items: queryFindings, color: 'gold' },
            { label: 'Health Analyst', items: healthFindings, color: 'emerald' },
            { label: 'Schema Analyst', items: schemaFindings, color: 'amber' },
          ].map(({ label, items, color }) => (
            <div key={label} className="mb-4">
              <h3 className={`text-xs font-bold text-${color}-400 uppercase tracking-wider mb-2`}>{label} ({items.length})</h3>
              {items.length === 0 ? (
                <p className="text-[11px] text-slate-600 italic">No findings from this agent.</p>
              ) : (
                <div className="space-y-2">
                  {items.map((f: any, i: number) => (
                    <div key={i} className="bg-duck-card/30 border border-duck-border rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-bold text-white">{f.title}</span>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${severityBadge(f.severity)}`}>
                          {f.severity?.toUpperCase()}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400">{f.detail}</p>
                      {f.recommendation && (
                        <p className="text-[10px] text-slate-500 mt-1">Recommendation: {f.recommendation}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </DossierSection>

        {/* Performance Recommendations */}
        <DossierSection id="performance" title="Performance Recommendations" icon="speed" index={3}>
          <div className="space-y-2">
            {allFindings.filter((f: any) => f.recommendation).map((f: any, i: number) => (
              <div key={i} className="flex items-start gap-3 bg-duck-card/20 rounded-lg p-3">
                <span className="material-symbols-outlined text-violet-400 text-sm mt-0.5">lightbulb</span>
                <div>
                  <p className="text-xs text-white font-medium">{f.title}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">{f.recommendation}</p>
                </div>
              </div>
            ))}
            {allFindings.filter((f: any) => f.recommendation).length === 0 && (
              <p className="text-[11px] text-slate-600 italic">No recommendations generated.</p>
            )}
          </div>
        </DossierSection>

        {/* Remediation Plans */}
        <DossierSection id="remediation" title="Remediation Plans" icon="build" index={4}>
          <div className="bg-duck-card/30 border border-duck-border rounded-lg p-4">
            <p className="text-[11px] text-slate-500 italic">
              Remediation plans will be generated when agents identify actionable fixes. Use the Plan → Verify → Approve → Execute workflow.
            </p>
          </div>
        </DossierSection>

        {/* Health Scorecard */}
        <DossierSection id="health-scorecard" title="Health Scorecard" icon="monitoring" index={5}>
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Total Findings', value: allFindings.length, color: 'text-white' },
              { label: 'Critical', value: allFindings.filter((f: any) => f.severity === 'critical').length, color: 'text-red-400' },
              { label: 'High', value: allFindings.filter((f: any) => f.severity === 'high').length, color: 'text-orange-400' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-duck-card/30 border border-duck-border rounded-lg p-3 text-center">
                <p className={`text-2xl font-bold ${color}`}>{value}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider">{label}</p>
              </div>
            ))}
          </div>
        </DossierSection>

        {/* Export */}
        <div className="flex justify-end mt-8 pb-8">
          <button className="flex items-center gap-2 px-4 py-2 bg-violet-500/10 border border-violet-500/20 text-violet-400 rounded-lg text-xs font-bold hover:bg-violet-500/20 transition-colors">
            <span className="material-symbols-outlined text-sm">download</span>
            Export PDF (coming soon)
          </button>
        </div>
      </div>
    </div>
  );
};

export default DatabaseDossierView;
