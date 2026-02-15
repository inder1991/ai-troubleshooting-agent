import React from 'react';
import type { SpanInfo } from '../../types';

interface TraceCardProps {
  spans: SpanInfo[];
}

const TraceCard: React.FC<TraceCardProps> = ({ spans }) => {
  if (spans.length === 0) return null;

  const maxDuration = Math.max(...spans.map((s) => s.duration_ms));
  const sortedSpans = [...spans].sort((a, b) => a.duration_ms - b.duration_ms);
  const failureSpans = spans.filter((s) => s.error);
  const slowestSpan = sortedSpans[sortedSpans.length - 1];

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-purple-500" />
        Trace Analysis
      </h3>

      {/* Summary */}
      <div className="flex gap-4 mb-4">
        <div className="bg-gray-900/50 rounded px-3 py-2 flex-1">
          <div className="text-xs text-gray-400">Total Spans</div>
          <div className="text-lg font-semibold text-white">{spans.length}</div>
        </div>
        <div className="bg-gray-900/50 rounded px-3 py-2 flex-1">
          <div className="text-xs text-gray-400">Failures</div>
          <div className={`text-lg font-semibold ${failureSpans.length > 0 ? 'text-red-400' : 'text-green-400'}`}>
            {failureSpans.length}
          </div>
        </div>
        {slowestSpan && (
          <div className="bg-gray-900/50 rounded px-3 py-2 flex-1">
            <div className="text-xs text-gray-400">Slowest</div>
            <div className="text-lg font-semibold text-yellow-400">{slowestSpan.duration_ms}ms</div>
          </div>
        )}
      </div>

      {/* Call chain visualization */}
      <div className="space-y-1">
        {spans.map((span, i) => {
          const barWidth = maxDuration > 0 ? (span.duration_ms / maxDuration) * 100 : 0;
          const depth = span.parent_span_id ? 1 : 0;

          return (
            <div
              key={span.span_id || i}
              className={`flex items-center gap-2 ${depth > 0 ? 'ml-4' : ''}`}
            >
              <div className="w-32 text-xs text-gray-400 truncate font-mono" title={span.service}>
                {span.service}
              </div>
              <div className="flex-1 h-5 bg-gray-900/50 rounded relative">
                <div
                  className={`h-full rounded ${
                    span.error ? 'bg-red-600/70' : 'bg-blue-600/70'
                  }`}
                  style={{ width: `${Math.max(barWidth, 2)}%` }}
                />
                <span className="absolute right-1 top-0 text-xs text-gray-300 leading-5">
                  {span.duration_ms}ms
                </span>
              </div>
              <div className="w-24 text-xs text-gray-400 truncate" title={span.operation}>
                {span.operation}
              </div>
              {span.error && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-red-900 text-red-300">
                  ERR
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Failure points */}
      {failureSpans.length > 0 && (
        <div className="mt-4 border-t border-gray-700 pt-3">
          <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Failure Points</h4>
          {failureSpans.map((span, i) => (
            <div key={i} className="text-xs text-red-300 bg-red-900/20 rounded px-3 py-1.5 mb-1">
              {span.service} / {span.operation} - {span.duration_ms}ms
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TraceCard;
