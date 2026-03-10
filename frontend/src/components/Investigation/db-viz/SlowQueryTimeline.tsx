import React from 'react';

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

function severityColor(duration_ms: number): string {
  if (duration_ms > 30000) return '#ef4444'; // critical
  if (duration_ms > 10000) return '#f97316'; // high
  if (duration_ms > 5000) return '#f59e0b'; // medium
  return '#10b981'; // low
}

function dotSize(duration_ms: number, maxDuration: number): number {
  const minSize = 6;
  const maxSize = 18;
  const ratio = Math.min(duration_ms / maxDuration, 1);
  return minSize + ratio * (maxSize - minSize);
}

const SlowQueryTimeline: React.FC<SlowQueryTimelineProps> = ({
  queries,
  maxDuration: maxDurationProp,
}) => {
  if (queries.length === 0) {
    return (
      <div className="text-center py-4">
        <span className="material-symbols-outlined text-2xl text-slate-700 block mb-1">query_stats</span>
        <p className="text-[10px] text-slate-600">No slow queries detected</p>
      </div>
    );
  }

  const maxDuration = maxDurationProp || Math.max(...queries.map((q) => q.duration_ms));

  return (
    <div className="space-y-1">
      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {[
          { label: '>30s', color: '#ef4444' },
          { label: '>10s', color: '#f97316' },
          { label: '>5s', color: '#f59e0b' },
          { label: '<5s', color: '#10b981' },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[9px] text-slate-500">{label}</span>
          </div>
        ))}
      </div>

      {/* Timeline */}
      <div className="relative bg-duck-card/30 border border-duck-border rounded-lg p-3 overflow-x-auto">
        <div className="flex items-end gap-1 h-16 min-w-0">
          {queries.map((q, i) => {
            const color = severityColor(q.duration_ms);
            const size = dotSize(q.duration_ms, maxDuration);
            return (
              <div
                key={q.pid || i}
                className="group relative flex flex-col items-center"
                style={{ minWidth: `${size + 2}px` }}
              >
                {/* Tooltip */}
                <div className="absolute bottom-full mb-1 hidden group-hover:block z-10">
                  <div className="bg-slate-900 border border-slate-700 rounded px-2 py-1 shadow-lg whitespace-nowrap">
                    <p className="text-[10px] text-white font-mono">{q.duration_ms}ms</p>
                    <p className="text-[9px] text-slate-400 max-w-[200px] truncate">{q.query}</p>
                  </div>
                </div>
                {/* Dot */}
                <div
                  className="rounded-full transition-transform hover:scale-125 cursor-pointer"
                  style={{
                    width: `${size}px`,
                    height: `${size}px`,
                    backgroundColor: color,
                    opacity: 0.85,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary */}
      <p className="text-[10px] text-slate-500">
        {queries.length} slow {queries.length === 1 ? 'query' : 'queries'} — max {(maxDuration / 1000).toFixed(1)}s
      </p>
    </div>
  );
};

export default SlowQueryTimeline;
