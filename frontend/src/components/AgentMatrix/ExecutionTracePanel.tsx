import React from 'react';
import type { AgentTraceEntry } from '../../types';

interface ExecutionTracePanelProps {
  trace: AgentTraceEntry[] | undefined;
  isLoading: boolean;
}

const LEVEL_COLORS: Record<AgentTraceEntry['level'], string> = {
  info: '#e09f3e',
  warn: '#f59e0b',
  error: '#ef4444',
};

const ExecutionTracePanel: React.FC<ExecutionTracePanelProps> = ({ trace, isLoading }) => {
  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#3d3528' }}>
      <h3 className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: '#64748b' }}>
        Execution Trace
      </h3>

      <div
        className="rounded-lg p-3 max-h-64 overflow-y-auto"
        style={{ backgroundColor: '#060d0f' }}
      >
        {isLoading && (
          <div className="flex items-center gap-2 py-6 justify-center">
            <div
              className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
              style={{ borderColor: '#e09f3e', borderTopColor: 'transparent' }}
            />
            <span className="text-xs font-mono" style={{ color: '#475569' }}>
              Loading trace...
            </span>
          </div>
        )}

        {!isLoading && (!trace || trace.length === 0) && (
          <div className="flex flex-col items-center gap-2 py-6">
            <span
              className="material-symbols-outlined text-2xl"
              style={{ color: '#1e3a3e' }}
            >
              hourglass_empty
            </span>
            <span className="text-xs font-mono uppercase tracking-widest" style={{ color: '#475569' }}>
              Awaiting Dispatch
            </span>
            <span className="text-[10px] font-mono" style={{ color: '#374151' }}>
              No execution trace available
            </span>
          </div>
        )}

        {!isLoading && trace && trace.length > 0 && (
          <div className="flex flex-col gap-0.5">
            {trace.map((entry, i) => {
              const ts = new Date(entry.timestamp);
              const timeStr = ts.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
              const levelColor = LEVEL_COLORS[entry.level];

              return (
                <div key={i} className="flex gap-2 text-[11px] font-mono leading-relaxed">
                  <span style={{ color: '#475569' }}>{timeStr}</span>
                  <span
                    className="uppercase w-10 text-right flex-shrink-0"
                    style={{ color: levelColor }}
                  >
                    {entry.level}
                  </span>
                  <span style={{ color: '#cbd5e1' }}>{entry.message}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ExecutionTracePanel;
