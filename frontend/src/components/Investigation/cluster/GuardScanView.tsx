import React, { useState } from 'react';
import type { GuardScanResult } from '../../../types';
import CurrentRiskCard from './CurrentRiskCard';
import PredictiveRiskCard from './PredictiveRiskCard';
import DeltaSection from './DeltaSection';

interface GuardScanViewProps {
  scanResult: GuardScanResult;
}

const HEALTH_BADGE: Record<string, string> = {
  HEALTHY: 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10',
  DEGRADED: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  CRITICAL: 'text-red-400 border-red-500/40 bg-red-500/10',
  UNKNOWN: 'text-slate-400 border-slate-500/40 bg-slate-500/10',
};

export default function GuardScanView({ scanResult }: GuardScanViewProps) {
  const [sections, setSections] = useState({ current: true, predictive: true, delta: true });

  const toggleSection = (key: keyof typeof sections) => {
    setSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const healthClass = HEALTH_BADGE[scanResult.overall_health] || HEALTH_BADGE.UNKNOWN;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span className="material-symbols-outlined text-cyan-400">health_and_safety</span>
        <span className="text-sm font-semibold text-slate-200">Guard Scan</span>
        <span className={`px-2 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded-full border ${healthClass}`}>
          {scanResult.overall_health}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                scanResult.risk_score > 0.7 ? 'bg-red-500' : scanResult.risk_score > 0.4 ? 'bg-amber-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.min(scanResult.risk_score * 100, 100)}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-slate-500">{Math.round(scanResult.risk_score * 100)}%</span>
        </div>
      </div>

      {/* Current Risks */}
      <div className="border border-slate-700/30 rounded-lg overflow-hidden">
        <button
          onClick={() => toggleSection('current')}
          className="w-full px-3 py-2 flex items-center gap-2 bg-red-500/5 hover:bg-red-500/10 transition-colors"
        >
          <span className="material-symbols-outlined text-red-400 text-sm">warning</span>
          <span className="text-xs font-semibold text-red-300">Current Risks</span>
          <span className="text-[9px] font-mono text-slate-500 ml-auto">{scanResult.current_risks.length}</span>
          <span className="material-symbols-outlined text-slate-500 text-sm">
            {sections.current ? 'expand_less' : 'expand_more'}
          </span>
        </button>
        {sections.current && (
          <div className="p-2 space-y-1.5">
            {scanResult.current_risks.length === 0 ? (
              <p className="text-xs text-slate-500 italic px-1">No current risks detected</p>
            ) : (
              scanResult.current_risks.map((risk, i) => <CurrentRiskCard key={i} risk={risk} />)
            )}
          </div>
        )}
      </div>

      {/* Predictive Risks */}
      <div className="border border-slate-700/30 rounded-lg overflow-hidden">
        <button
          onClick={() => toggleSection('predictive')}
          className="w-full px-3 py-2 flex items-center gap-2 bg-amber-500/5 hover:bg-amber-500/10 transition-colors"
        >
          <span className="material-symbols-outlined text-amber-400 text-sm">trending_up</span>
          <span className="text-xs font-semibold text-amber-300">Predictive Risks</span>
          <span className="text-[9px] font-mono text-slate-500 ml-auto">{scanResult.predictive_risks.length}</span>
          <span className="material-symbols-outlined text-slate-500 text-sm">
            {sections.predictive ? 'expand_less' : 'expand_more'}
          </span>
        </button>
        {sections.predictive && (
          <div className="p-2 space-y-1.5">
            {scanResult.predictive_risks.length === 0 ? (
              <p className="text-xs text-slate-500 italic px-1">No predictive risks detected</p>
            ) : (
              scanResult.predictive_risks.map((risk, i) => <PredictiveRiskCard key={i} risk={risk} />)
            )}
          </div>
        )}
      </div>

      {/* Delta */}
      <div className="border border-slate-700/30 rounded-lg overflow-hidden">
        <button
          onClick={() => toggleSection('delta')}
          className="w-full px-3 py-2 flex items-center gap-2 bg-cyan-500/5 hover:bg-cyan-500/10 transition-colors"
        >
          <span className="material-symbols-outlined text-cyan-400 text-sm">compare_arrows</span>
          <span className="text-xs font-semibold text-cyan-300">Delta Since Last Scan</span>
          <span className="material-symbols-outlined text-slate-500 text-sm">
            {sections.delta ? 'expand_less' : 'expand_more'}
          </span>
        </button>
        {sections.delta && <DeltaSection delta={scanResult.delta} />}
      </div>
    </div>
  );
}
