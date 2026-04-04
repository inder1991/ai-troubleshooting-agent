import React, { useState } from 'react';
import type { ClusterDomainAnomaly } from '../../types';

interface UncorrelatedFindingsProps {
  findings: ClusterDomainAnomaly[];
}

const severityColor = (s?: string) =>
  s === 'high' ? 'border-red-500/40 text-red-400'
  : s === 'medium' ? 'border-amber-500/40 text-amber-400'
  : 'border-slate-500/40 text-slate-400';

const UncorrelatedFindings: React.FC<UncorrelatedFindingsProps> = ({ findings }) => {
  const [expanded, setExpanded] = useState(false);

  if (findings.length === 0) return null;

  return (
    <div className="bg-wr-inset rounded border border-wr-border-subtle p-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left"
        aria-expanded={expanded}
        aria-label={`${findings.length} uncorrelated findings`}
      >
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Uncorrelated Findings ({findings.length})
        </span>
        <span className="material-symbols-outlined text-sm text-slate-600">
          {expanded ? 'expand_less' : 'expand_more'}
        </span>
      </button>
      {expanded && (
        <div className="mt-2 space-y-1.5">
          {findings.map((f, i) => (
            <div key={f.anomaly_id || i} className={`text-[11px] pl-3 border-l-2 ${severityColor(f.severity)}`}>
              <span className="font-mono text-slate-600 mr-1.5">[{f.domain}]</span>
              {f.description}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default UncorrelatedFindings;
