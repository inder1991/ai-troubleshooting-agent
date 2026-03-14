import React, { useState } from 'react';
import { SEV_DOT, SEV_BADGE } from '../db-board/constants';

interface SlowQuery {
  pid: number;
  duration_ms: number;
  query: string;
  timestamp?: string;
}

interface SlowQueryTimelineProps {
  queries: SlowQuery[];
  maxDuration?: number;
}

type SeverityLevel = 'critical' | 'high' | 'medium' | 'low';

function getSeverity(ms: number): SeverityLevel {
  if (ms > 30000) return 'critical';
  if (ms > 10000) return 'high';
  if (ms > 5000) return 'medium';
  return 'low';
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

const SlowQueryTimeline: React.FC<SlowQueryTimelineProps> = ({ queries }) => {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (queries.length === 0) {
    return (
      <div className="flex items-center justify-center py-4">
        <p className="text-[10px] text-slate-400 italic">No slow queries detected</p>
      </div>
    );
  }

  const sorted = [...queries].sort((a, b) => b.duration_ms - a.duration_ms);
  const worst = sorted[0].duration_ms;

  return (
    <div>
      {/* Query list */}
      <div className="space-y-0">
        {sorted.map((q, i) => {
          const sev = getSeverity(q.duration_ms);
          const dot = SEV_DOT[sev] || SEV_DOT.medium;
          const badge = SEV_BADGE[sev] || SEV_BADGE.medium;
          const isExpanded = expanded === i;
          const barWidth = Math.max((q.duration_ms / worst) * 100, 8);

          return (
            <button
              key={q.pid || i}
              onClick={() => setExpanded(isExpanded ? null : i)}
              className="w-full text-left py-2 px-2 border-b border-duck-border/20 last:border-0 hover:bg-duck-surface/30 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-duck-accent"
              aria-expanded={isExpanded}
              aria-label={`Query pid ${q.pid}, duration ${formatDuration(q.duration_ms)}`}
            >
              {/* Row 1: Duration + severity + pid */}
              <div className="flex items-center gap-2 mb-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} aria-hidden="true" />
                <span className="text-xs font-display font-bold text-white">{formatDuration(q.duration_ms)}</span>
                <span className={`text-[8px] font-bold px-1 py-0.5 rounded border ${badge}`}>{sev.toUpperCase()}</span>
                <span className="ml-auto text-[9px] text-slate-400 font-mono">pid:{q.pid}</span>
              </div>

              {/* Row 2: Duration bar (proportional) */}
              <div className="h-1 bg-duck-border/20 rounded-full mb-1.5 overflow-hidden">
                <div className={`h-full rounded-full ${dot}`} style={{ width: `${barWidth}%` }} />
              </div>

              {/* Row 3: SQL preview (2 lines, expandable) */}
              <p className={`text-[10px] sm:text-[11px] font-mono text-slate-400 leading-relaxed ${isExpanded ? 'whitespace-pre-wrap break-all' : 'line-clamp-2'}`}>
                {q.query}
              </p>

              {/* Expanded: full details */}
              {isExpanded && q.timestamp && (
                <p className="text-[9px] text-slate-400 mt-1.5 font-mono">
                  Timestamp: {q.timestamp}
                </p>
              )}
            </button>
          );
        })}
      </div>

      {/* Summary */}
      <p className="text-[10px] text-slate-400 mt-2 px-2">
        {queries.length} slow {queries.length === 1 ? 'query' : 'queries'} — worst: {formatDuration(worst)}
      </p>
    </div>
  );
};

export default SlowQueryTimeline;
