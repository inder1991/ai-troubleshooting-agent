import React, { useState } from 'react';
import type { DiagHypothesis, DiagHypothesisResult } from '../../types';

interface HypothesisEvidenceMapProps {
  hypotheses: DiagHypothesis[];
  result: DiagHypothesisResult | null;
}

const agentCodeMap: Record<string, string> = {
  log_agent: 'L',
  metrics_agent: 'M',
  k8s_agent: 'K',
  tracing_agent: 'T',
  code_agent: 'D',
  change_agent: 'C',
};

const agentBadgeColor: Record<string, string> = {
  L: 'bg-wr-severity-high/20 text-red-400',
  M: 'bg-wr-severity-medium/20 text-amber-400',
  K: 'bg-orange-500/20 text-orange-400',
  T: 'bg-violet-500/20 text-violet-400',
  D: 'bg-blue-500/20 text-blue-400',
  C: 'bg-emerald-500/20 text-emerald-400',
};

const categoryLabel: Record<string, string> = {
  memory: 'Memory (OOM)',
  connection: 'Connection',
  database: 'Database',
  cpu: 'CPU',
  disk: 'Disk I/O',
  network: 'Network',
  config: 'Config',
};

const HypothesisEvidenceMap: React.FC<HypothesisEvidenceMapProps> = ({
  hypotheses,
  result,
}) => {
  const [expanded, setExpanded] = useState(hypotheses.length >= 2);

  if (hypotheses.length === 0) return null;

  const sorted = [...hypotheses].sort((a, b) => {
    if (a.status === 'winner') return -1;
    if (b.status === 'winner') return 1;
    if (a.status === 'active' && b.status !== 'active') return -1;
    if (b.status === 'active' && a.status !== 'active') return 1;
    return b.confidence - a.confidence;
  });

  return (
    <div className="mb-4 border border-wr-border rounded-lg overflow-hidden bg-wr-bg/40">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2.5 flex items-center gap-2 text-left hover:bg-wr-surface/20 transition-colors"
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} hypothesis evidence map`}
      >
        <span
          className={`material-symbols-outlined text-xs text-slate-400 transition-transform duration-200 ${
            expanded ? 'rotate-90' : ''
          }`}
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          chevron_right
        </span>
        <span
          className="material-symbols-outlined text-amber-400 text-sm"
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          science
        </span>
        <span className="text-body-xs font-bold uppercase tracking-widest text-slate-400">
          Hypothesis Evidence Map
        </span>
        <span className="text-body-xs text-slate-500 ml-auto">
          {hypotheses.filter((h) => h.status === 'active').length} active
          {hypotheses.some((h) => h.status === 'eliminated') &&
            ` · ${hypotheses.filter((h) => h.status === 'eliminated').length} eliminated`}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-3 space-y-3 border-t border-wr-border/50">
          {sorted.map((h) => (
            <div
              key={h.hypothesis_id}
              className={`pt-3 ${h.status === 'eliminated' ? 'opacity-40' : ''}`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    h.status === 'winner'
                      ? 'bg-emerald-500'
                      : h.status === 'eliminated'
                        ? 'bg-slate-600'
                        : 'bg-amber-500'
                  }`}
                />
                <span
                  className={`text-body-xs font-bold ${
                    h.status === 'eliminated'
                      ? 'line-through text-slate-500'
                      : 'text-slate-200'
                  }`}
                >
                  {categoryLabel[h.category] || h.category}
                </span>
                <span
                  className={`text-body-xs font-mono font-bold ${
                    h.confidence >= 70
                      ? 'text-emerald-400'
                      : h.confidence >= 40
                        ? 'text-amber-400'
                        : 'text-red-400'
                  }`}
                >
                  {Math.round(h.confidence)}%
                </span>
                {h.status === 'winner' && (
                  <span className="text-body-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded">
                    WINNER
                  </span>
                )}
              </div>

              {h.evidence_for.length > 0 && (
                <div className="ml-4 mb-1">
                  <span className="text-body-xs font-bold text-green-400 uppercase tracking-wider">
                    For
                  </span>
                  <div className="mt-0.5 space-y-0.5">
                    {h.evidence_for.map((s, i) => {
                      const code = agentCodeMap[s.source_agent] || '?';
                      const badgeClass = agentBadgeColor[code] || 'bg-slate-500/20 text-slate-400';
                      return (
                        <div key={i} className="flex items-center gap-2 text-body-xs">
                          <span
                            className={`w-4 h-4 rounded-full flex items-center justify-center text-body-xs font-bold shrink-0 ${badgeClass}`}
                          >
                            {code}
                          </span>
                          <span className="text-slate-300">
                            {s.signal_name.replace(/_/g, ' ')}
                          </span>
                          <span className="text-slate-500 ml-auto">
                            {(s.strength * 100).toFixed(0)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {h.evidence_against.length > 0 && (
                <div className="ml-4 mb-1">
                  <span className="text-body-xs font-bold text-red-400 uppercase tracking-wider">
                    Against
                  </span>
                  <div className="mt-0.5 space-y-0.5">
                    {h.evidence_against.map((s, i) => {
                      const code = agentCodeMap[s.source_agent] || '?';
                      const badgeClass = agentBadgeColor[code] || 'bg-slate-500/20 text-slate-400';
                      return (
                        <div key={i} className="flex items-center gap-2 text-body-xs">
                          <span
                            className={`w-4 h-4 rounded-full flex items-center justify-center text-body-xs font-bold shrink-0 ${badgeClass}`}
                          >
                            {code}
                          </span>
                          <span className="text-slate-300">
                            {s.signal_name.replace(/_/g, ' ')}
                          </span>
                          <span className="text-slate-500 ml-auto">contradicts</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {h.evidence_for.length === 0 && h.evidence_against.length === 0 && h.status !== 'eliminated' && (
                <div className="ml-4 text-body-xs text-slate-500 italic">
                  No evidence mapped yet
                </div>
              )}

              {h.status === 'eliminated' && h.elimination_reason && (
                <div className="ml-4 text-body-xs text-slate-500">
                  Eliminated: {h.elimination_reason}
                </div>
              )}

              {h.downstream_effects.length > 0 && h.status !== 'eliminated' && (
                <div className="ml-4 mt-1">
                  <span className="text-body-xs text-slate-500">
                    Downstream: {h.downstream_effects.join(' → ')}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default HypothesisEvidenceMap;
