import React from 'react';
import type { VerdictEvent } from '../../types';

interface VerdictStackProps {
  events: VerdictEvent[];
}

const severityColor = (severity: VerdictEvent['severity']) => {
  switch (severity) {
    case 'FATAL': return '#ef4444';
    case 'WARN': return '#f59e0b';
    case 'INFO': return '#13b6ec';
  }
};

const VerdictStack: React.FC<VerdictStackProps> = ({ events }) => {
  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      <h3 className="text-[10px] uppercase font-bold tracking-widest text-slate-500 mb-4 px-2">Verdict Stack</h3>

      {events.length === 0 && (
        <p className="text-xs text-slate-600 animate-pulse px-4">Correlating events...</p>
      )}

      <div className="relative flex-1 px-4 border-l border-[#1f3b42] ml-2 space-y-6 pt-2 overflow-y-auto custom-scrollbar">
        {events.map((evt, i) => {
          const color = severityColor(evt.severity);
          return (
            <div key={i} className="relative group">
              <div
                className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full ring-4 ring-[#0f2023] group-hover:ring-opacity-50 transition-all"
                style={{ backgroundColor: color }}
              />
              <div className="text-xs font-mono" style={{ color }}>
                {evt.timestamp} - {evt.severity}
              </div>
              <p className="text-[11px] text-slate-400 mt-1 italic">{evt.message}</p>
            </div>
          );
        })}

        <svg className="absolute left-[-16px] top-0 w-2 h-full pointer-events-none -z-10">
          <line x1="0" y1="0" x2="0" y2="100%" stroke="#1f3b42" strokeDasharray="4 4" />
        </svg>
      </div>
    </div>
  );
};

export default VerdictStack;
