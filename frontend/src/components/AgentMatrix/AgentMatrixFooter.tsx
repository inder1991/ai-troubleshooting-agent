import React from 'react';
import type { AgentMatrixSummary } from '../../types';

interface AgentMatrixFooterProps {
  summary: AgentMatrixSummary;
}

const AgentMatrixFooter: React.FC<AgentMatrixFooterProps> = ({ summary }) => {
  return (
    <footer
      className="flex items-center justify-between px-8 py-2.5 border-t text-[11px]"
      style={{ borderColor: '#3d3528', backgroundColor: '#13110d' }}
    >
      <div className="flex items-center gap-5">
        <span style={{ color: '#64748b' }}>
          {summary.total} agents
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#e09f3e' }} />
          <span style={{ color: '#e09f3e' }}>{summary.active} active</span>
        </span>
        {summary.degraded > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#f59e0b' }} />
            <span style={{ color: '#f59e0b' }}>{summary.degraded} degraded</span>
          </span>
        )}
        {summary.offline > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#ef4444' }} />
            <span style={{ color: '#ef4444' }}>{summary.offline} offline</span>
          </span>
        )}
      </div>
    </footer>
  );
};

export default AgentMatrixFooter;
