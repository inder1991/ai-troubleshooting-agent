import React from 'react';
import type { AgentInfo } from '../../types';
import AgentCard from './AgentCard';

interface AgentGridProps {
  agents: AgentInfo[];
  onSelectAgent: (agent: AgentInfo) => void;
  compact?: boolean;
  selectedAgentId?: string;
}

const ROLE_ORDER: AgentInfo['role'][] = [
  'orchestrator',
  'analysis',
  'domain_expert',
  'validation',
  'fix_generation',
];

const ROLE_DISPLAY: Record<AgentInfo['role'], { label: string; icon: string }> = {
  orchestrator: { label: 'Orchestrators', icon: 'account_tree' },
  analysis: { label: 'Analysis Agents', icon: 'analytics' },
  domain_expert: { label: 'Domain Experts', icon: 'school' },
  validation: { label: 'Validation Agents', icon: 'verified' },
  fix_generation: { label: 'Fix Generation Pipeline', icon: 'build' },
};

const AgentGrid: React.FC<AgentGridProps> = ({ agents, onSelectAgent, compact, selectedAgentId }) => {
  // Group agents by role, preserving ROLE_ORDER
  const grouped = ROLE_ORDER.map((role) => ({
    role,
    agents: agents.filter((a) => a.role === role),
  })).filter((g) => g.agents.length > 0);

  return (
    <div className={`flex flex-col gap-6 ${compact ? 'px-4' : 'px-8'} py-4`}>
      {grouped.map(({ role, agents: roleAgents }) => {
        const display = ROLE_DISPLAY[role];
        return (
          <div key={role}>
            {/* Role group header */}
            <div className="flex items-center gap-3 mb-3">
              <span
                className="material-symbols-outlined text-base"
                style={{ color: '#e09f3e' }}
              >
                {display.icon}
              </span>
              <h2 className="text-xs font-mono font-semibold uppercase tracking-widest" style={{ color: '#8a7e6b' }}>
                {display.label}
              </h2>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: '#1e1b15', color: '#64748b' }}>
                {roleAgents.length}
              </span>
              <div className="flex-1 h-px" style={{ backgroundColor: '#3d3528' }} />
            </div>

            {/* Cards grid */}
            <div className={`grid gap-3 ${compact ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5'}`}>
              {roleAgents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  onClick={() => onSelectAgent(agent)}
                  isSelected={agent.id === selectedAgentId}
                />
              ))}
            </div>
          </div>
        );
      })}

      {grouped.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <span className="material-symbols-outlined text-3xl mb-3" style={{ color: '#3d3528' }}>smart_toy</span>
          <p className="text-sm" style={{ color: '#64748b' }}>No agents found in this workflow</p>
          <p className="text-xs mt-1" style={{ color: '#475569' }}>Try a different tab or clear your search</p>
        </div>
      )}
    </div>
  );
};

export default AgentGrid;
