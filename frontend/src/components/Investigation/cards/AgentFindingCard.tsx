import React from 'react';

type AgentCode = 'L' | 'M' | 'K' | 'C';

const agentStyles: Record<AgentCode, { border: string; bg: string; label: string }> = {
  L: { border: 'card-border-L', bg: 'bg-red-500/10', label: 'Log Analyzer' },
  M: { border: 'card-border-M', bg: 'bg-cyan-500/10', label: 'Metric Scanner' },
  K: { border: 'card-border-K', bg: 'bg-orange-500/10', label: 'K8s Probe' },
  C: { border: 'card-border-C', bg: 'bg-emerald-500/10', label: 'Change Intel' },
};

const badgeColor: Record<AgentCode, string> = {
  L: 'bg-red-500 text-white',
  M: 'bg-cyan-500 text-white',
  K: 'bg-orange-500 text-white',
  C: 'bg-emerald-500 text-white',
};

interface AgentFindingCardProps {
  agent: AgentCode;
  title: string;
  children: React.ReactNode;
}

const AgentFindingCard: React.FC<AgentFindingCardProps> = ({ agent, title, children }) => {
  const style = agentStyles[agent];
  return (
    <div className={`${style.border} ${style.bg} rounded-lg overflow-hidden`}>
      <div className="px-4 py-2.5 flex items-center gap-2">
        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${badgeColor[agent]}`}>
          {agent}
        </span>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">{style.label}</span>
        <span className="text-xs font-medium text-slate-200 ml-1">{title}</span>
      </div>
      <div className="px-4 pb-3">
        {children}
      </div>
    </div>
  );
};

export default AgentFindingCard;
