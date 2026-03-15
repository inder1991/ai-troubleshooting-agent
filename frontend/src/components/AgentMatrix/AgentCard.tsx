import React, { useRef, useEffect } from 'react';
import type { AgentInfo } from '../../types';
import { ROLE_COLORS } from '../../constants/colors';

interface AgentCardProps {
  agent: AgentInfo;
  onClick: () => void;
  isSelected?: boolean;
  enterDelay?: number;
}

const STATUS_COLORS: Record<AgentInfo['status'], string> = {
  active: '#e09f3e',
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

function formatAgentName(name: string): string {
  return name.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
}

function formatTimeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  if (isNaN(diff) || diff < 0) return '—';
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onClick, isSelected, enterDelay = 0 }) => {
  const cardRef = useRef<HTMLButtonElement>(null);
  const statusColor = STATUS_COLORS[agent.status];

  // Scroll selected card into view after grid reflow completes (300ms transition)
  useEffect(() => {
    if (isSelected && cardRef.current) {
      const timer = setTimeout(() => {
        cardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [isSelected]);

  const cardStyle: React.CSSProperties = {
    backgroundColor: agent.status === 'degraded'
      ? 'rgba(245,158,11,0.05)'
      : isSelected ? '#1a1814' : '#0a1214',
    borderColor: isSelected ? '#e09f3e' : '#3d3528',
    borderLeftWidth: agent.status !== 'active' ? '3px' : undefined,
    borderLeftColor: agent.status === 'degraded' ? '#f59e0b' : agent.status === 'offline' ? '#ef4444' : undefined,
    opacity: agent.status === 'offline' ? 0.6 : 1,
    animation: `fadeSlideUp 300ms cubic-bezier(0.25, 1, 0.5, 1) ${enterDelay}ms both`,
    transition: 'border-color 200ms cubic-bezier(0.25, 1, 0.5, 1), transform 200ms cubic-bezier(0.25, 1, 0.5, 1), box-shadow 200ms cubic-bezier(0.25, 1, 0.5, 1)',
  };

  return (
    <button
      ref={cardRef}
      onClick={onClick}
      className="text-left w-full rounded-lg border p-4 group"
      style={cardStyle}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
        e.currentTarget.style.borderColor = '#e09f3e';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
        e.currentTarget.style.borderColor = isSelected ? '#e09f3e' : '#3d3528';
      }}
    >
      {/* Header: Icon + Name + Status */}
      <div className="flex items-center gap-3 mb-2">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 border"
          style={{
            backgroundColor: `${ROLE_COLORS[agent.role] || '#e09f3e'}15`,
            borderColor: `${ROLE_COLORS[agent.role] || '#e09f3e'}30`,
          }}
        >
          <span
            className="material-symbols-outlined text-lg"
            style={{ color: ROLE_COLORS[agent.role] || '#e09f3e' }}
          >
            {agent.icon}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white truncate">{formatAgentName(agent.name)}</h3>
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{
                backgroundColor: statusColor,
                boxShadow: agent.status === 'degraded' ? `0 0 6px ${statusColor}` : undefined,
                animation: agent.status === 'degraded' ? 'pulse 2s ease-in-out infinite' : undefined,
              }}
              title={agent.status}
              aria-label={`Status: ${agent.status}`}
            />
          </div>
          <span
            className="text-[10px] uppercase tracking-widest"
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
          color: '#8a7e6b',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {agent.description}
      </p>

      {/* Operational metrics instead of tool pills */}
      <div className="flex items-center gap-4 text-[10px]" style={{ color: '#64748b' }}>
        <span className="flex items-center gap-1">
          <span className="material-symbols-outlined text-[12px]">schedule</span>
          {agent.recent_executions.length > 0
            ? formatTimeAgo(agent.recent_executions[0].timestamp)
            : '—'}
        </span>
        <span className="flex items-center gap-1">
          <span className="material-symbols-outlined text-[12px]">check_circle</span>
          {agent.recent_executions.length > 0
            ? `${Math.round((agent.recent_executions.filter(e => e.status === 'SUCCESS').length / agent.recent_executions.length) * 100)}%`
            : '—'}
        </span>
        <span className="flex items-center gap-1">
          <span className="material-symbols-outlined text-[12px]">build</span>
          {agent.tools.length} tools
        </span>
      </div>
    </button>
  );
};

export default AgentCard;
