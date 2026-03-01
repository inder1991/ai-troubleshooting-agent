import React from 'react';
import type { CurrentRisk } from '../../../types';

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  warning: 'border-l-amber-500',
  info: 'border-l-slate-500',
};

interface CurrentRiskCardProps {
  risk: CurrentRisk;
}

export default function CurrentRiskCard({ risk }: CurrentRiskCardProps) {
  const borderClass = SEVERITY_BORDER[risk.severity] || SEVERITY_BORDER.info;

  return (
    <div className={`bg-slate-900/40 border border-slate-700/30 border-l-2 ${borderClass} rounded px-3 py-2`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-slate-300">{risk.category}</span>
        {risk.affected_count > 0 && (
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/30">
            {risk.affected_count} affected
          </span>
        )}
      </div>
      <p className="text-[11px] text-slate-400">{risk.description}</p>
      <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-500">
        <span className="font-mono">{risk.resource}</span>
        {risk.issue_cluster_id && (
          <span className="text-cyan-500/60 font-mono">{risk.issue_cluster_id}</span>
        )}
      </div>
    </div>
  );
}
