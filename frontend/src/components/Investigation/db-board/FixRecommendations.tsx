import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { SEV_BADGE } from './constants';

interface Fix {
  priority: number;
  finding_id: string;
  title: string;
  severity: string;
  category: string;
  recommendation: string;
  sql: string;
  warning?: string;
  verification_sql?: string;
  estimated_impact?: string;
  agent: string;
}

interface FixRecommendationsProps {
  fixes: Fix[];
  onExportReport?: () => void;
}

const FixRecommendations: React.FC<FixRecommendationsProps> = ({ fixes, onExportReport }) => {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  const handleCopy = useCallback((sql: string, idx: number) => {
    navigator.clipboard.writeText(sql).then(() => {
      setCopied(idx);
      setTimeout(() => setCopied(null), 2000);
    });
  }, []);

  if (fixes.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-[10px] font-display font-bold text-slate-400">Recommended Fixes</h2>
        <span className="text-[9px] text-slate-500">{fixes.length}</span>
      </div>

      <div className="space-y-0">
        {fixes.map((fix, i) => {
          const badge = SEV_BADGE[fix.severity] || SEV_BADGE.medium;
          const isExpanded = expanded === i;
          const isCritical = fix.severity === 'critical';

          return (
            <div
              key={fix.finding_id || i}
              className={isCritical ? 'bg-red-500/[0.03]' : ''}
            >
              {/* Fix header — always visible */}
              <button
                onClick={() => setExpanded(isExpanded ? null : i)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-duck-surface/30 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
                aria-expanded={isExpanded}
              >
                <span className="text-[11px] font-bold text-slate-500 w-5 shrink-0">{fix.priority}.</span>
                <span className={`text-[10px] font-bold ${isCritical ? 'text-white' : 'text-slate-300'}`}>
                  {fix.title}
                </span>
                <span className={`text-[8px] font-bold px-1 py-0.5 rounded border shrink-0 ${badge}`}>
                  {fix.severity.toUpperCase()}
                </span>
                {fix.sql && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleCopy(fix.sql, i); }}
                    className="ml-auto shrink-0 text-slate-400 hover:text-duck-accent transition-colors"
                    aria-label={`Copy SQL for ${fix.title}`}
                  >
                    <span className="material-symbols-outlined text-[14px]">
                      {copied === i ? 'check' : 'content_copy'}
                    </span>
                  </button>
                )}
              </button>

              {/* Expanded: SQL + recommendation */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden px-3 pb-2"
                  >
                    <p className="text-[10px] text-slate-400 mb-2">{fix.recommendation}</p>
                    {fix.sql && (
                      <pre className="text-[10px] font-mono text-amber-300/80 bg-duck-bg/80 rounded px-2 py-1.5 overflow-x-auto whitespace-pre-wrap border border-duck-border/30">
                        {fix.sql}
                      </pre>
                    )}
                    {fix.warning && (
                      <p className="text-[9px] text-amber-400/70 mt-1.5 flex items-start gap-1">
                        <span className="material-symbols-outlined text-[12px] shrink-0 mt-px" aria-hidden="true">warning</span>
                        {fix.warning}
                      </p>
                    )}
                    {fix.estimated_impact && (
                      <p className="text-[9px] text-slate-300 mt-1.5">
                        <span className="text-slate-400">Impact:</span> {fix.estimated_impact}
                      </p>
                    )}
                    {fix.verification_sql && (
                      <details className="mt-1.5">
                        <summary className="text-[9px] text-duck-accent cursor-pointer hover:text-amber-300 transition-colors">
                          Verify this fix
                        </summary>
                        <pre className="text-[9px] font-mono text-slate-400 bg-duck-bg/50 rounded px-2 py-1.5 mt-1 whitespace-pre-wrap overflow-x-auto">
                          {fix.verification_sql}
                        </pre>
                      </details>
                    )}
                    <span className="text-[9px] text-slate-600 mt-1 block">{fix.agent}</span>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>

      {/* Export Report button */}
      {onExportReport && (
        <button
          onClick={onExportReport}
          className="mt-3 w-full flex items-center justify-center gap-2 py-2 text-[10px] font-display font-bold text-slate-400 border border-duck-border/30 rounded-lg hover:border-duck-accent/30 hover:text-duck-accent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
        >
          <span className="material-symbols-outlined text-[14px]">description</span>
          Export Report
        </button>
      )}
    </div>
  );
};

export default React.memo(FixRecommendations);
