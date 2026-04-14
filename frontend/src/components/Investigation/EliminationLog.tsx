import React from 'react';
import type { DiagHypothesisResult } from '../../types';

interface EliminationLogProps {
  result: DiagHypothesisResult | null;
}

const categoryLabel: Record<string, string> = {
  memory: 'memory',
  connection: 'connection',
  database: 'database',
  cpu: 'cpu',
  disk: 'disk',
  network: 'network',
  config: 'config',
};

const EliminationLog: React.FC<EliminationLogProps> = ({ result }) => {
  if (!result || result.elimination_log.length === 0) return null;

  return (
    <section>
      <h3 className="text-body-xs font-bold text-slate-400 uppercase tracking-widest mb-2">
        Elimination Log
      </h3>
      <div className="bg-wr-bg/40 border border-wr-border rounded-lg p-3">
        <div className="space-y-1.5">
          {result.elimination_log.map((entry, i) => (
            <div key={i} className="flex items-start gap-2 text-body-xs">
              <span className="w-2 h-2 mt-1 rounded-full bg-red-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <span className="font-bold text-slate-300">
                  {categoryLabel[entry.hypothesis_id] || entry.hypothesis_id}
                </span>
                <span className="text-slate-500 ml-1">
                  eliminated
                </span>
                {entry.phase && (
                  <span className="text-slate-500 ml-1">
                    at {entry.phase.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
              <span className="text-slate-500 font-mono shrink-0">
                {Math.round(entry.confidence)}%
              </span>
            </div>
          ))}

          {result.winner_id && (
            <div className="flex items-start gap-2 text-body-xs pt-1 border-t border-wr-border/30">
              <span className="w-2 h-2 mt-1 rounded-full bg-emerald-500 shrink-0" />
              <span className="font-bold text-emerald-400">
                WINNER: {categoryLabel[result.winner_id] || result.winner_id}
              </span>
            </div>
          )}

          {result.status === 'inconclusive' && (
            <div className="flex items-start gap-2 text-body-xs pt-1 border-t border-wr-border/30">
              <span className="w-2 h-2 mt-1 rounded-full bg-amber-500 shrink-0" />
              <span className="font-bold text-amber-400">INCONCLUSIVE</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default EliminationLog;
