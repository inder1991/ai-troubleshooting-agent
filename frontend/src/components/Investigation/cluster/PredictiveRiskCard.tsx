import React from 'react';
import type { PredictiveRisk } from '../../../types';

interface PredictiveRiskCardProps {
  risk: PredictiveRisk;
}

export default function PredictiveRiskCard({ risk }: PredictiveRiskCardProps) {
  return (
    <div className="bg-wr-bg/40 border border-wr-border-strong/30 border-l-2 border-l-amber-500 rounded px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-slate-300">{risk.category}</span>
        <span className="text-body-xs font-mono px-1.5 py-0.5 rounded-full bg-wr-severity-medium/10 text-amber-400 border border-wr-severity-medium/30">
          {risk.time_horizon}
        </span>
      </div>
      <p className="text-body-xs text-slate-400">{risk.description}</p>
      <p className="text-body-xs text-amber-400/70 mt-1">{risk.predicted_impact}</p>
      <div className="text-body-xs text-slate-400 font-mono mt-1">{risk.resource}</div>
    </div>
  );
}
