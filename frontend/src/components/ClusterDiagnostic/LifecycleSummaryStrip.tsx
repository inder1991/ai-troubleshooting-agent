import React, { useMemo } from 'react';
import type { DiagnosticIssue, ClusterDomainReport, IssueLifecycleState } from '../../types';

interface LifecycleSummaryStripProps {
  diagnosticIssues?: DiagnosticIssue[];
  domainReports: ClusterDomainReport[];
  dataCompleteness?: number;
  phase: string;
}

const DOT_COLORS: Partial<Record<IssueLifecycleState, string>> = {
  ACTIVE_DISRUPTION: '#ef4444',
  WORSENING: '#f59e0b',
  NEW: '#e09f3e',
  EXISTING: '#64748b',
  LONG_STANDING: '#475569',
  INTERMITTENT: '#6366f1',
  SYMPTOM: '#94a3b8',
};

const STATE_ORDER: IssueLifecycleState[] = [
  'ACTIVE_DISRUPTION', 'WORSENING', 'NEW', 'EXISTING', 'LONG_STANDING', 'INTERMITTENT', 'SYMPTOM',
];

const LifecycleSummaryStrip: React.FC<LifecycleSummaryStripProps> = ({
  diagnosticIssues,
  domainReports,
  dataCompleteness,
  phase,
}) => {
  const stateCounts = useMemo(() => {
    const counts: Partial<Record<IssueLifecycleState, number>> = {};
    if (diagnosticIssues && diagnosticIssues.length > 0) {
      diagnosticIssues.forEach(i => {
        counts[i.state] = (counts[i.state] || 0) + 1;
      });
    } else {
      // Derive from domain anomalies
      let total = 0;
      domainReports.forEach(r => { total += r.anomalies.length; });
      if (total > 0) counts.EXISTING = total;
    }
    return counts;
  }, [diagnosticIssues, domainReports]);

  const domainCount = domainReports.filter(r => r.status !== 'SKIPPED').length;
  const completePct = dataCompleteness != null ? Math.round(dataCompleteness * 100) : null;
  const isScanning = phase !== 'complete';

  return (
    <div className="h-9 flex items-center gap-3 px-3 border-b border-[#2a2520] select-none overflow-x-auto">
      {/* State dots */}
      {STATE_ORDER.map(state => {
        const count = stateCounts[state];
        if (!count) return null;
        const color = DOT_COLORS[state] || '#94a3b8';
        return (
          <span key={state} className="flex items-center gap-1 shrink-0">
            <span
              className={`inline-block w-[6px] h-[6px] rounded-full ${isScanning ? 'animate-pulse' : ''}`}
              style={{ backgroundColor: color }}
            />
            <span className="text-[10px] font-mono text-slate-400">{count}</span>
          </span>
        );
      })}

      {/* Separator */}
      {Object.keys(stateCounts).length > 0 && (
        <span className="w-px h-3 bg-[#2a2520] shrink-0" />
      )}

      {/* Domain count */}
      <span className="text-[10px] text-slate-500 shrink-0">{domainCount} domains scanned</span>

      {/* Completeness */}
      {completePct !== null && (
        <>
          <span className="w-px h-3 bg-[#2a2520] shrink-0" />
          <span className="text-[10px] text-slate-500 font-mono shrink-0">{completePct}% complete</span>
        </>
      )}
    </div>
  );
};

export default LifecycleSummaryStrip;
