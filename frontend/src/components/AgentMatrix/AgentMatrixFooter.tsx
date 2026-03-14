import React from 'react';
import type { AgentMatrixSummary } from '../../types';

interface AgentMatrixFooterProps {
  summary: AgentMatrixSummary;
}

const AgentMatrixFooter: React.FC<AgentMatrixFooterProps> = ({ summary }) => {
  const syncPct = summary.total > 0
    ? Math.round((summary.active / summary.total) * 100)
    : 0;

  return (
    <footer
      className="flex items-center justify-between px-8 py-3 border-t text-[11px] font-mono"
      style={{ borderColor: '#3d3528', backgroundColor: '#0a1214' }}
    >
      <div className="flex items-center gap-6">
        <span style={{ color: '#64748b' }}>
          TOTAL <span className="text-white font-semibold">{summary.total}</span>
        </span>
        <span style={{ color: '#64748b' }}>
          ACTIVE <span style={{ color: '#e09f3e' }} className="font-semibold">{summary.active}</span>
        </span>
        {summary.degraded > 0 && (
          <span style={{ color: '#64748b' }}>
            DEGRADED <span style={{ color: '#f59e0b' }} className="font-semibold">{summary.degraded}</span>
          </span>
        )}
        {summary.offline > 0 && (
          <span style={{ color: '#64748b' }}>
            OFFLINE <span style={{ color: '#ef4444' }} className="font-semibold">{summary.offline}</span>
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span style={{ color: '#64748b' }}>Fleet Health</span>
        <div className="w-20 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: '#1e1b15' }}>
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${syncPct}%`,
              backgroundColor: syncPct === 100 ? '#e09f3e' : syncPct >= 80 ? '#f59e0b' : '#ef4444',
            }}
          />
        </div>
        <span style={{ color: syncPct === 100 ? '#e09f3e' : '#f59e0b' }} className="font-semibold">
          {syncPct}%
        </span>
      </div>
    </footer>
  );
};

export default AgentMatrixFooter;
