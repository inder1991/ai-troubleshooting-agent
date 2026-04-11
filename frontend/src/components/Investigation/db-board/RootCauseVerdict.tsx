import React from 'react';
import { motion } from 'framer-motion';
import { SEVERITY_TEXT, SEVERITY_BADGE, SEV_DOT } from './constants';

interface RootCauseVerdictProps {
  verdict: string | null;
  confidence: number;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  recommendation?: string;
  contributingPanels?: string[];
  causalChain?: string[];
  evidenceWeights?: Record<string, { weight: number; reason: string }>;
}

const RootCauseVerdict: React.FC<RootCauseVerdictProps> = ({
  verdict,
  confidence,
  severity = 'medium',
  recommendation,
  contributingPanels,
  causalChain,
  evidenceWeights,
}) => {
  if (!verdict) return null;

  const badge = SEVERITY_BADGE[severity] || SEVERITY_BADGE.medium;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="bg-duck-accent/5 border border-duck-accent/20 rounded-lg px-4 py-3 mb-4"
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full shrink-0 ${SEV_DOT[severity] || SEV_DOT.medium}`} />
          <span className="material-symbols-outlined text-duck-accent text-lg">target</span>
          <span className="text-xs font-display font-bold text-white">Root Cause Identified</span>
          <span className={`material-symbols-outlined text-sm ${SEVERITY_TEXT[severity] || SEVERITY_TEXT.medium}`} aria-hidden="true">
            {severity === 'critical' ? 'emergency' : severity === 'high' ? 'warning' : severity === 'medium' ? 'info' : 'check_circle'}
          </span>
          <span className={`text-body-xs sm:text-body-xs font-bold px-1.5 py-0.5 rounded border ${badge}`}>
            {severity.toUpperCase()}
          </span>
        </div>
        <span className="text-sm font-display font-bold text-duck-accent">{confidence}%</span>
      </div>

      <p className="text-[12px] text-slate-200 leading-relaxed mb-2">
        {typeof verdict === 'string' ? verdict : JSON.stringify(verdict)}
      </p>

      {causalChain && causalChain.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap mt-2 text-body-xs">
          {causalChain.map((step, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-slate-400">&rarr;</span>}
              <span className="px-1.5 py-0.5 rounded bg-duck-surface/50 text-slate-300">{step}</span>
            </React.Fragment>
          ))}
        </div>
      )}

      {recommendation && (
        <p className="text-body-xs text-slate-300 italic border-t border-duck-border/30 pt-2 mt-2">
          {typeof recommendation === 'string' ? recommendation : JSON.stringify(recommendation)}
        </p>
      )}

      {contributingPanels && contributingPanels.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2">
          <span className="text-body-xs text-slate-400">Evidence:</span>
          {contributingPanels.map((p, i) => (
            <span key={`${p}-${i}`} className="text-body-xs px-1.5 py-0.5 rounded bg-duck-accent/20 text-duck-accent">
              {p}
            </span>
          ))}
        </div>
      )}

      {evidenceWeights && Object.keys(evidenceWeights).length > 0 && (
        <div className="mt-2 space-y-1">
          <span className="text-body-xs text-slate-400">Evidence weights:</span>
          {Object.entries(evidenceWeights).map(([id, { weight, reason }]) => (
            <div key={id} className="flex items-center gap-2">
              <div className="h-1.5 bg-duck-accent/30 rounded-full overflow-hidden" style={{ width: `${weight * 100}%`, minWidth: 8 }}>
                <div className="h-full bg-duck-accent rounded-full" style={{ width: '100%' }} />
              </div>
              <span className="text-body-xs text-slate-400 truncate">{reason}</span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
};

export default React.memo(RootCauseVerdict);
