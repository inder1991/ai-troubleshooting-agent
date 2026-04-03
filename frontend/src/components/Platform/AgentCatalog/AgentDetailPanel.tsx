import React from 'react';
import type { CatalogAgent } from './useAgentCatalog';

interface Props { agent: CatalogAgent; onClose: () => void; }

const AgentDetailPanel: React.FC<Props> = ({ agent, onClose }) => (
  <div className="h-full flex flex-col" style={{ background: '#0c1a1f' }}>
    <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: '#1e2a2e' }}>
      <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>{agent.name}</span>
      <button onClick={onClose}><span className="material-symbols-outlined" style={{ fontSize: 18, color: '#64748b' }}>close</span></button>
    </div>
    <div className="p-5 text-xs font-mono" style={{ color: '#64748b' }}>Detail panel — Task 3</div>
  </div>
);

export default AgentDetailPanel;
