import React from 'react';
import type { AgentInfo } from '../../types';

interface AgentCardProps {
  agent: AgentInfo;
  onClick: () => void;
}

const STATUS_COLORS: Record<AgentInfo['status'], string> = {
  active: '#07b6d5',
  degraded: '#f59e0b',
  offline: '#ef4444',
};

const ROLE_LABELS: Record<AgentInfo['role'], string> = {
  orchestrator: 'ORCHESTRATOR',
  analysis: 'ANALYSIS',
  validation: 'VALIDATION',
  fix_generation: 'FIX GENERATION',
  domain_expert: 'DOMAIN EXPERT',
};

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick }) => {
  const statusColor = STATUS_COLORS[agent.status];

  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-lg border p-4 transition-all duration-200 hover:border-[#07b6d5] group"
      style={{
        backgroundColor: '#0a1214',
        borderColor: '#224349',
      }}
    >
      {/* Header: Icon + Name + Status */}
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 border"
          style={{
            backgroundColor: 'rgba(7,182,213,0.1)',
            borderColor: 'rgba(7,182,213,0.2)',
          }}
        >
          <span
            className="material-symbols-outlined text-lg"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
          >
            {agent.icon}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-mono font-semibold text-white truncate">{agent.name}</h3>
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{
                backgroundColor: statusColor,
                boxShadow: agent.status === 'degraded' ? `0 0 6px ${statusColor}` : undefined,
                animation: agent.status === 'degraded' ? 'pulse 2s ease-in-out infinite' : undefined,
              }}
            />
          </div>
          <span
            className="text-[9px] font-mono uppercase tracking-widest"
            style={{ color: '#64748b' }}
          >
            {ROLE_LABELS[agent.role]}
          </span>
        </div>
      </div>

      {/* Description */}
      <p
        className="text-xs leading-relaxed mb-3"
        style={{
          color: '#94a3b8',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {agent.description}
      </p>

      {/* Tools pills */}
      <div className="flex flex-wrap gap-1 mb-2">
        {agent.tools.slice(0, 4).map((tool) => (
          <span
            key={tool}
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: '#162a2e',
              color: '#64748b',
            }}
          >
            {tool}
          </span>
        ))}
        {agent.tools.length > 4 && (
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{ backgroundColor: '#162a2e', color: '#64748b' }}
          >
            +{agent.tools.length - 4}
          </span>
        )}
        {agent.tools.length === 0 && (
          <span className="text-[10px] font-mono italic" style={{ color: '#475569' }}>
            LLM-only
          </span>
        )}
      </div>

      {/* Degraded tools warning */}
      {agent.degraded_tools.length > 0 && (
        <div className="flex items-center gap-1.5 mt-1">
          <span
            className="material-symbols-outlined text-xs"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}
          >
            warning
          </span>
          <span className="text-[10px] font-mono" style={{ color: '#f59e0b' }}>
            {agent.degraded_tools.length} tool{agent.degraded_tools.length > 1 ? 's' : ''} degraded
          </span>
        </div>
      )}
    </button>
  );
};

export default AgentCard;
