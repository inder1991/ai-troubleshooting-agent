import React from 'react';
import type { ClusterDomainReport } from '../../types';

interface AgentTimelineProps {
  domainReports: ClusterDomainReport[];
  phase: string;
}

const DOMAIN_COLORS: Record<string, string> = {
  ctrl_plane: '#f59e0b',
  node: '#e09f3e',
  network: '#10b981',
  storage: '#8b5cf6',
  rbac: '#ef4444',
};

const AgentTimeline: React.FC<AgentTimelineProps> = ({ domainReports, phase }) => {
  const maxDuration = Math.max(...domainReports.map(r => r.duration_ms || 0), 1);

  return (
    <div className="bg-[#141210] rounded border border-[#2a2520] p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Agent Timeline</span>
        <span className="text-[10px] text-slate-400">{phase === 'complete' ? 'Complete' : 'Running...'}</span>
      </div>
      <div className="space-y-1.5">
        {domainReports.filter(r => r.status !== 'SKIPPED').map(report => {
          const pct = maxDuration > 0 ? ((report.duration_ms || 0) / maxDuration) * 100 : 0;
          const color = DOMAIN_COLORS[report.domain] || '#94a3b8';
          const isRunning = report.status === 'RUNNING' || report.status === 'PENDING';
          return (
            <div key={report.domain} className="flex items-center gap-2">
              <span className="text-[10px] text-slate-500 w-16 text-right font-mono truncate">
                {report.domain.replace('_', ' ')}
              </span>
              <div className="flex-1 h-3 bg-[#1a1814] rounded-sm overflow-hidden relative">
                <div
                  className={`h-full rounded-sm transition-all duration-500 ${isRunning ? 'animate-pulse' : ''}`}
                  style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: color, opacity: report.status === 'FAILED' ? 0.4 : 0.8 }}
                />
              </div>
              <span className="text-[10px] text-slate-400 w-12 text-right font-mono">
                {report.duration_ms ? `${(report.duration_ms / 1000).toFixed(1)}s` : '—'}
              </span>
              <span className="text-[10px] w-4">
                {report.status === 'SUCCESS' ? '✓' : report.status === 'FAILED' ? '✗' : report.status === 'PARTIAL' ? '◐' : '·'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AgentTimeline;
