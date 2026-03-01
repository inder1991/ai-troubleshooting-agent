import React from 'react';
import type { PredictiveRisk } from '../../../types';

interface PredictiveRiskCardProps {
  risk: PredictiveRisk;
}

export default function PredictiveRiskCard({ risk }: PredictiveRiskCardProps) {
  return (
    <div className="bg-slate-900/40 border border-slate-700/30 border-l-2 border-l-amber-500 rounded px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-slate-300">{risk.category}</span>
        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
          {risk.time_horizon}
        </span>
      </div>
      <p className="text-[11px] text-slate-400">{risk.description}</p>
      <p className="text-[10px] text-amber-400/70 mt-1">{risk.predicted_impact}</p>
      <div className="text-[10px] text-slate-500 font-mono mt-1">{risk.resource}</div>
    </div>
  );
}
