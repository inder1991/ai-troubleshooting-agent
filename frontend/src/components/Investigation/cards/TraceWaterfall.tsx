import React, { useState } from 'react';
import type { SpanInfo } from '../../../types';

interface TraceWaterfallProps {
  spans: SpanInfo[];
}

const TraceWaterfall: React.FC<TraceWaterfallProps> = ({ spans }) => {
  const [expandedSpan, setExpandedSpan] = useState<number | null>(null);
  const totalDuration = Math.max(...spans.map((s) => s.duration_ms), 1);
  const errorCount = spans.filter((s) => s.status === 'error' || s.error).length;

  const depthMap = new Map<string, number>();
  const visiting = new Set<string>();
  const computeDepth = (span: SpanInfo): number => {
    if (depthMap.has(span.span_id)) return depthMap.get(span.span_id)!;
    if (!span.parent_span_id) { depthMap.set(span.span_id, 0); return 0; }
    if (visiting.has(span.span_id)) { depthMap.set(span.span_id, 0); return 0; }
    visiting.add(span.span_id);
    const parent = spans.find((s) => s.span_id === span.parent_span_id);
    const depth = parent ? computeDepth(parent) + 1 : 0;
    visiting.delete(span.span_id);
    depthMap.set(span.span_id, depth);
    return depth;
  };
  spans.forEach(computeDepth);

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-cyan-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>stacked_bar_chart</span>
        <span className="text-[11px] font-bold uppercase tracking-wider">Trace Waterfall</span>
        <span className="text-[10px] text-slate-500 ml-auto">{spans.length} spans, {totalDuration.toFixed(0)}ms</span>
        {errorCount > 0 && <span className="text-red-400 text-[10px] font-bold">{errorCount} errors</span>}
      </div>
      <div className="space-y-1">
        {spans.map((span, i) => {
          const widthPct = Math.max((span.duration_ms / totalDuration) * 100, 2);
          const isError = span.status === 'error' || span.error;
          const barColor = isError ? 'bg-red-500' : span.critical_path ? 'bg-amber-500' : 'bg-green-500';
          const depth = depthMap.get(span.span_id) || 0;
          const isExpanded = expandedSpan === i;
          const hasDetail = (isError && span.error_message) || (span.tags && Object.keys(span.tags).length > 0);
          return (
            <div key={i}>
              <button
                onClick={() => hasDetail ? setExpandedSpan(isExpanded ? null : i) : undefined}
                className={`flex items-center gap-2 py-0.5 w-full text-left ${hasDetail ? 'cursor-pointer hover:bg-slate-800/30 rounded' : 'cursor-default'}`}
                style={{ paddingLeft: `${depth * 16}px` }}
              >
                <span className="text-[10px] font-mono text-[#07b6d5] w-20 shrink-0 truncate">{span.service}</span>
                <span className="text-[10px] text-slate-400 w-28 shrink-0 truncate">{span.operation}</span>
                <div className="flex-1 h-3 bg-slate-800/50 rounded overflow-hidden">
                  <div className={`h-full rounded ${barColor}`} style={{ width: `${widthPct}%` }} />
                </div>
                <span className={`text-[10px] font-mono w-14 text-right shrink-0 ${isError ? 'text-red-400' : 'text-slate-400'}`}>
                  {span.duration_ms.toFixed(0)}ms
                </span>
              </button>
              {isExpanded && (
                <div className="ml-6 mt-1 mb-2 bg-slate-800/30 rounded-lg border border-slate-700/30 p-2 space-y-1" style={{ marginLeft: `${depth * 16 + 24}px` }}>
                  {span.error_message && (
                    <p className="text-[10px] text-red-400 font-mono break-all">{span.error_message}</p>
                  )}
                  {span.tags && Object.keys(span.tags).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(span.tags).map(([k, v]) => (
                        <span key={k} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-700/50 text-slate-400">
                          {k}={v}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TraceWaterfall;
