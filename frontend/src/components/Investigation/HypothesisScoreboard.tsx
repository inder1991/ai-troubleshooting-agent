import React from 'react';
import { motion } from 'framer-motion';
import type { DiagHypothesis, DiagHypothesisResult } from '../../types';

interface HypothesisScoreboardProps {
  hypotheses: DiagHypothesis[];
  result: DiagHypothesisResult | null;
  /** Fallback for legacy single-hypothesis mode */
  legacyGuess: { text: string; confidence: number } | null;
}

const categoryLabel: Record<string, string> = {
  memory: 'Memory (OOM)',
  connection: 'Connection',
  database: 'Database',
  cpu: 'CPU',
  disk: 'Disk I/O',
  network: 'Network',
  config: 'Config',
};

const statusColor: Record<string, string> = {
  active: 'bg-amber-500',
  winner: 'bg-emerald-500',
  eliminated: 'bg-slate-600',
};

const confidenceColor = (c: number) =>
  c >= 70 ? 'bg-emerald-500' : c >= 40 ? 'bg-amber-500' : 'bg-red-500';

const HypothesisScoreboard: React.FC<HypothesisScoreboardProps> = ({
  hypotheses,
  result,
  legacyGuess,
}) => {
  if (hypotheses.length === 0 && legacyGuess) {
    return (
      <div className="flex-shrink-0 border-t border-wr-border/50 bg-wr-bg/60 px-4 py-3">
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className="material-symbols-outlined text-amber-400 text-sm"
            style={{ fontFamily: 'Material Symbols Outlined' }}
          >
            neurology
          </span>
          <span className="text-body-xs font-bold uppercase tracking-widest text-slate-400">
            Current Best Guess
          </span>
          <span
            className={`ml-auto text-sm font-mono font-bold ${
              legacyGuess.confidence >= 70
                ? 'text-emerald-400'
                : legacyGuess.confidence >= 40
                  ? 'text-amber-400'
                  : 'text-red-400'
            }`}
          >
            {legacyGuess.confidence}%
          </span>
        </div>
        <p className="text-body-xs text-slate-300 leading-relaxed line-clamp-2">
          {legacyGuess.text}
        </p>
        <div className="mt-2 h-1.5 bg-wr-surface rounded-full overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${confidenceColor(legacyGuess.confidence)}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(legacyGuess.confidence, 100)}%` }}
            transition={{ type: 'spring', bounce: 0, duration: 0.8 }}
          />
        </div>
      </div>
    );
  }

  if (hypotheses.length === 0) return null;

  const sorted = [...hypotheses].sort((a, b) => {
    if (a.status === 'winner') return -1;
    if (b.status === 'winner') return 1;
    if (a.status === 'active' && b.status !== 'active') return -1;
    if (b.status === 'active' && a.status !== 'active') return 1;
    return b.confidence - a.confidence;
  });

  // Task 4.14: cap to top-3. The supervisor's reducer already keeps 3,
  // but the board can receive more when live-updates race the reducer.
  const topThree = sorted.slice(0, 3);
  const remaining = sorted.length - topThree.length;

  const isInconclusive = result?.status === 'inconclusive';
  const isResolved = result?.status === 'resolved';

  return (
    <div className="flex-shrink-0 border-t border-wr-border/50 bg-wr-bg/60 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <span
          className="material-symbols-outlined text-amber-400 text-sm"
          style={{ fontFamily: 'Material Symbols Outlined' }}
        >
          science
        </span>
        <span className="text-body-xs font-bold uppercase tracking-widest text-slate-400">
          Hypothesis Scoreboard
        </span>
        {isResolved && (
          <span className="ml-auto text-body-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
            RESOLVED
          </span>
        )}
        {isInconclusive && (
          <span className="ml-auto text-body-xs font-bold text-amber-400 bg-wr-severity-medium/10 border border-amber-500/20 px-2 py-0.5 rounded-full">
            INCONCLUSIVE
          </span>
        )}
      </div>

      <div className="space-y-1.5" data-testid="hypothesis-scoreboard-rows">
        {topThree.map((h) => (
          <div
            key={h.hypothesis_id}
            className={`flex items-center gap-2 ${
              h.status === 'eliminated' ? 'opacity-40' : ''
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${statusColor[h.status]}`}
            />

            <span
              className={`text-body-xs font-bold flex-1 min-w-0 truncate ${
                h.status === 'eliminated'
                  ? 'line-through text-slate-500'
                  : 'text-slate-300'
              }`}
            >
              {categoryLabel[h.category] || h.category}
              {h.status === 'winner' && (
                <span className="ml-1.5 text-emerald-400 text-body-xs font-bold no-underline">
                  WINNER
                </span>
              )}
            </span>

            {h.status === 'eliminated' ? (
              <span
                className="text-body-xs text-slate-500 truncate max-w-[120px]"
                title={h.elimination_reason || ''}
              >
                {h.elimination_reason || 'eliminated'}
              </span>
            ) : (
              <>
                <div className="w-16 h-1.5 bg-wr-surface rounded-full overflow-hidden shrink-0">
                  <motion.div
                    className={`h-full rounded-full ${confidenceColor(h.confidence)}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(h.confidence, 100)}%` }}
                    transition={{ type: 'spring', bounce: 0, duration: 0.6 }}
                  />
                </div>
                <span
                  className={`text-body-xs font-mono font-bold w-8 text-right shrink-0 ${
                    h.confidence >= 70
                      ? 'text-emerald-400'
                      : h.confidence >= 40
                        ? 'text-amber-400'
                        : 'text-red-400'
                  }`}
                >
                  {Math.round(h.confidence)}%
                </span>
              </>
            )}
          </div>
        ))}
      </div>

      {remaining > 0 && (
        <div className="mt-1 text-body-xs text-slate-500 italic">
          +{remaining} more {remaining === 1 ? 'hypothesis' : 'hypotheses'} with
          lower confidence hidden
        </div>
      )}

      {isInconclusive && result?.recommendations && result.recommendations.length > 0 && (
        <div className="mt-2 pt-2 border-t border-wr-border/30">
          <span className="text-body-xs text-amber-400 font-bold">Next steps:</span>
          <ul className="mt-0.5 space-y-0.5">
            {result.recommendations.map((r, i) => (
              <li key={i} className="text-body-xs text-slate-400">
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default HypothesisScoreboard;
