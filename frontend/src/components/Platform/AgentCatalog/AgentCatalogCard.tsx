import React from 'react';
import type { CatalogAgent } from './useAgentCatalog';

const STATUS_COLOR: Record<string, string> = {
  active: '#22c55e',
  degraded: '#f59e0b',
  offline: '#ef4444',
};

const ROLE_COLOR: Record<string, string> = {
  orchestrator: '#07b6d5',
  analysis: '#a855f7',
  validation: '#22c55e',
  'fix-generation': '#e09f3e',
};

interface Props {
  agent: CatalogAgent;
  selected: boolean;
  onClick: () => void;
}

const AgentCatalogCard: React.FC<Props> = ({ agent, selected, onClick }) => (
  <div
    onClick={onClick}
    style={{
      background: selected ? 'rgba(7,182,213,0.08)' : 'rgba(255,255,255,0.02)',
      border: `1px solid ${selected ? '#07b6d5' : '#1e2a2e'}`,
      borderRadius: 8, padding: '12px 14px', cursor: 'pointer',
      transition: 'border-color 0.15s',
    }}
  >
    <div className="flex items-start justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="material-symbols-outlined flex-shrink-0"
          style={{ fontSize: 16, color: ROLE_COLOR[agent.role] || '#64748b' }}
        >
          smart_toy
        </span>
        <span className="text-xs font-mono font-semibold truncate" style={{ color: '#e8e0d4' }}>
          {agent.name}
        </span>
      </div>
      <span
        className="w-2 h-2 rounded-full flex-shrink-0 mt-1"
        style={{ background: STATUS_COLOR[agent.status] }}
        title={agent.status}
      />
    </div>

    <div className="mt-1 text-body-xs font-mono truncate" style={{ color: '#64748b' }}>
      {agent.id}
    </div>

    <div className="mt-2 flex items-center gap-2 flex-wrap">
      <span
        className="text-body-xs font-mono px-1.5 py-0.5 rounded"
        style={{
          background: `${ROLE_COLOR[agent.role] || '#64748b'}20`,
          color: ROLE_COLOR[agent.role] || '#64748b',
          border: `1px solid ${ROLE_COLOR[agent.role] || '#64748b'}40`,
        }}
      >
        {agent.role}
      </span>
      <span className="text-body-xs font-mono" style={{ color: '#3d4a50' }}>
        {agent.workflow}
      </span>
    </div>

    {agent.tools.length > 0 && (
      <div className="mt-2 text-body-xs font-mono" style={{ color: '#4a5568' }}>
        {agent.tools.length} tool{agent.tools.length !== 1 ? 's' : ''}
        {agent.timeout_s && ` · ${agent.timeout_s}s timeout`}
      </div>
    )}
  </div>
);

export default AgentCatalogCard;
