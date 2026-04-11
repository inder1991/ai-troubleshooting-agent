import React, { useState } from 'react';
import type { RankedHypothesis, ClusterCausalChain } from '../../types';

interface HypothesisCardProps {
  hypotheses?: RankedHypothesis[];
  primaryChain?: ClusterCausalChain;
  confidence: number;
}

const ConfidenceBar: React.FC<{ value: number }> = ({ value }) => {
  const pct = Math.round(value * 100);
  const blocks = Math.round(value * 10);
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-body-xs">
      <span className="inline-flex">
        {Array.from({ length: 10 }).map((_, i) => (
          <span
            key={i}
            className="inline-block w-[5px] h-[10px] mr-px rounded-[1px]"
            style={{ backgroundColor: i < blocks ? 'var(--wr-accent)' : 'var(--wr-bg-primary)' }}
          />
        ))}
      </span>
      <span className="text-slate-400 w-8 text-right">{(pct / 100).toFixed(2)}</span>
    </span>
  );
};

const HypothesisCard: React.FC<HypothesisCardProps> = ({ hypotheses, primaryChain, confidence }) => {
  const [expanded, setExpanded] = useState(false);
  const hasHypotheses = hypotheses && hypotheses.length > 0;

  // Fallback: no hypotheses and no chain
  if (!hasHypotheses && !primaryChain) {
    return (
      <div className="border border-wr-border-subtle rounded bg-wr-inset p-4">
        <h3 className="text-body-xs uppercase font-bold tracking-widest text-slate-500 mb-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">search</span>
          Root Cause Analysis
        </h3>
        <p className="text-body-xs text-slate-600 animate-pulse">Correlating events...</p>
      </div>
    );
  }

  // Ranked hypotheses mode
  if (hasHypotheses) {
    const topHypothesis = hypotheses[0];
    const effects = topHypothesis.causal_chain.slice(1);

    return (
      <div className="border border-wr-border-subtle rounded bg-wr-inset">
        <div className="px-4 pt-4 pb-2">
          <h3 className="text-body-xs uppercase font-bold tracking-widest text-slate-500 mb-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-sm">psychology</span>
            Root Cause Analysis
          </h3>

          <div className="space-y-1">
            {hypotheses.map((h, idx) => {
              const isTop = idx === 0;
              return (
                <div
                  key={h.hypothesis_id}
                  className={`py-2 px-3 rounded ${isTop ? 'border-l-2 border-l-wr-accent bg-wr-bg' : ''}`}
                >
                  <div className="flex items-start gap-2">
                    <span className="text-body-xs font-mono text-slate-600 mt-0.5 shrink-0">#{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`leading-snug ${isTop ? 'text-[13px] font-semibold text-slate-200' : 'text-[12px] text-slate-400'}`}>
                        {h.cause}
                      </p>
                      <div className="flex items-center flex-wrap gap-x-3 gap-y-0.5 mt-1">
                        <ConfidenceBar value={h.confidence} />
                        <span className="text-body-xs text-slate-600">
                          Evidence: {h.supporting_evidence.length} supporting, {h.contradicting_evidence.length} contradicting
                        </span>
                        <span className="text-body-xs text-slate-600">
                          Chain depth: {h.depth}
                        </span>
                        <span className="text-body-xs text-slate-600 capitalize">
                          Source: {h.source}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Cascading Effects (expandable) */}
        {effects.length > 0 && (
          <div className="border-t border-wr-border-subtle">
            <button
              onClick={() => setExpanded(!expanded)}
              aria-label={expanded ? 'Collapse effects' : 'Show cascading effects'}
              aria-expanded={expanded}
              className="w-full px-4 py-2 flex items-center gap-2 text-body-xs text-slate-500 hover:text-slate-400 transition-colors"
            >
              <span className="material-symbols-outlined text-xs" style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }}>
                chevron_right
              </span>
              Cascading Effects ({effects.length})
            </button>
            {expanded && (
              <div className="px-4 pb-3 space-y-1">
                {effects.map((eff, i) => (
                  <div key={i} className="flex items-start gap-2 pl-4">
                    <span className="text-body-xs text-slate-600 font-mono mt-px shrink-0">{i + 1}.</span>
                    <span className="text-body-xs text-slate-500">{eff}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Fallback: show primaryChain (legacy RootCauseCard style)
  const chain = primaryChain!;
  const isConfident = confidence >= 50;
  const badgeColor = isConfident ? 'var(--wr-severity-high)' : 'var(--wr-severity-medium)';
  const badgeText = isConfident ? 'Identified Root Cause' : 'Suspected Root Cause';

  return (
    <div
      className="border-2 rounded p-4 relative overflow-hidden"
      style={{ borderColor: badgeColor, backgroundColor: `${badgeColor}08` }}
    >
      <h3
        className="text-body-xs uppercase font-bold tracking-widest mb-1 flex items-center gap-2"
        style={{ color: badgeColor }}
      >
        <span className="material-symbols-outlined text-sm">warning</span>
        {badgeText}
      </h3>
      <p className="text-lg font-bold text-white mb-3 leading-tight">{chain.root_cause.description}</p>
      <div className="flex gap-4">
        <div className="p-2 bg-wr-bg/60 border border-wr-border-subtle rounded">
          <div className="text-chrome uppercase text-slate-500">Confidence</div>
          <div className="text-base font-mono" style={{ color: badgeColor }}>{Math.round(chain.confidence * 100)}%</div>
        </div>
        <div className="p-2 bg-wr-bg/60 border border-wr-border-subtle rounded">
          <div className="text-chrome uppercase text-slate-500">Cascading Effects</div>
          <div className="text-base font-mono text-amber-500">{chain.cascading_effects.length}</div>
        </div>
      </div>

      {chain.cascading_effects.length > 0 && (
        <div className="border-t border-wr-border-subtle mt-3 pt-2">
          <button
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? 'Collapse effects' : 'Show cascading effects'}
            aria-expanded={expanded}
            className="flex items-center gap-1 text-body-xs text-slate-500 hover:text-slate-400 transition-colors"
          >
            <span className="material-symbols-outlined text-xs" style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }}>
              chevron_right
            </span>
            Cascading Effects ({chain.cascading_effects.length})
          </button>
          {expanded && (
            <div className="mt-2 space-y-1">
              {chain.cascading_effects.map((eff, i) => (
                <div key={i} className="flex items-start gap-2 pl-4">
                  <span className="text-body-xs text-slate-600 font-mono mt-px shrink-0">{eff.order}.</span>
                  <span className="text-body-xs text-slate-500">{eff.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default HypothesisCard;
