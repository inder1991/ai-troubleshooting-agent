import React from 'react';
import type { ClusterCausalChain } from '../../types';

interface RootCauseCardProps {
  chain?: ClusterCausalChain;
  confidence: number;
}

const RootCauseCard: React.FC<RootCauseCardProps> = ({ chain, confidence }) => {
  if (!chain) {
    return (
      <div className="border border-[#1f3b42] rounded-lg bg-[#152a2f]/40 p-5">
        <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>search</span>
          Root Cause Analysis
        </h3>
        <p className="text-sm text-slate-500 animate-pulse">Correlating events...</p>
      </div>
    );
  }

  const isConfident = confidence >= 50;
  const badgeText = isConfident ? 'Identified Root Cause' : 'Suspected Root Cause';
  const badgeColor = isConfident ? '#ef4444' : '#f59e0b';

  return (
    <div
      className="border-2 rounded-lg p-5 relative overflow-hidden"
      style={{
        borderColor: badgeColor,
        backgroundColor: `${badgeColor}08`,
        boxShadow: `0 0 20px ${badgeColor}15`,
      }}
    >
      <div className="absolute inset-0 blur-3xl -z-10" style={{ backgroundColor: `${badgeColor}08` }} />
      <h3 className="text-[10px] uppercase font-bold tracking-widest mb-1 flex items-center gap-2" style={{ color: badgeColor }}>
        <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>warning</span>
        {badgeText}
      </h3>
      <h2 className="text-xl font-bold text-white mb-4 leading-tight">
        {chain.root_cause.description}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        <div className="p-2 bg-[#0f2023]/40 border border-[#1f3b42] rounded flex flex-col justify-between">
          <div className="text-[8px] uppercase text-slate-500">Confidence</div>
          <div className="text-lg font-mono" style={{ color: badgeColor }}>
            {Math.round(chain.confidence * 100)}%
          </div>
        </div>
        <div className="p-2 bg-[#0f2023]/40 border border-[#1f3b42] rounded flex flex-col justify-between">
          <div className="text-[8px] uppercase text-slate-500">Cascading Effects</div>
          <div className="text-lg font-mono text-amber-500">
            {chain.cascading_effects.length}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RootCauseCard;
