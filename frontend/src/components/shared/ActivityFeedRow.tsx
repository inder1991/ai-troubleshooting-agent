import React from 'react';
import { StatusBadge, type SystemStatus } from './StatusBadge';

interface ActivityFeedRowProps {
  targetService: string;
  targetNamespace: string;
  timestamp: string;
  status: SystemStatus;
  phase: string;
  confidenceScore: number;
  durationStr: string;
  activeAgents: string[];
  onClick?: () => void;
}

export const ActivityFeedRow: React.FC<ActivityFeedRowProps> = ({
  targetService,
  targetNamespace,
  timestamp,
  status,
  phase,
  confidenceScore,
  durationStr,
  activeAgents,
  onClick,
}) => {
  const barColor = confidenceScore >= 80 ? 'bg-green-500' : confidenceScore >= 50 ? 'bg-[#f59e0b]' : 'bg-[#ef4444]';

  return (
    <div
      onClick={onClick}
      className="flex items-center justify-between p-3 border-b border-[#224349] hover:bg-[#0f2023] transition-colors group cursor-pointer"
    >
      <div className="flex items-center gap-4 w-1/3">
        <div className="w-8 h-8 rounded bg-[#162a2e] flex items-center justify-center border border-[#3a5a60] shrink-0 text-[#07b6d5]">
          <span className="material-symbols-outlined text-[16px]" style={{ fontFamily: 'Material Symbols Outlined' }}>memory</span>
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[#e2e8f0] font-mono font-bold text-sm">{targetService}</span>
            {targetNamespace && (
              <span className="text-[#64748b] font-mono text-[10px] bg-black/20 px-1 rounded">ns:{targetNamespace}</span>
            )}
          </div>
          <span className="text-[#64748b] text-[11px] block mt-0.5">{timestamp}</span>
        </div>
      </div>

      <div className="flex flex-col gap-2 w-1/3 px-4">
        <div className="flex items-center gap-3">
          <StatusBadge status={status} label={phase} pulse={status === 'in_progress'} />
          <span className="text-[#94a3b8] font-mono text-[10px]">Conf: {confidenceScore}%</span>
        </div>
        <div className="w-full h-1 bg-[#162a2e] rounded-full overflow-hidden">
          <div className={`h-full ${barColor} transition-all duration-1000`} style={{ width: `${confidenceScore}%` }} />
        </div>
      </div>

      <div className="flex items-center justify-end gap-6 w-1/3">
        <div className="flex flex-col items-end">
          <span className="text-[#64748b] font-mono text-[10px] uppercase">Duration</span>
          <span className="text-[#e2e8f0] font-mono text-xs">{durationStr}</span>
        </div>
        <div className="flex -space-x-2">
          {activeAgents.slice(0, 4).map((agent, i) => (
            <div
              key={i}
              className="w-6 h-6 rounded-full bg-[#1a3a40] border border-[#224349] flex items-center justify-center text-[10px] font-mono text-[#07b6d5] z-10 hover:z-20 hover:-translate-y-1 transition-transform"
              title={`${agent} Agent`}
            >
              {agent.charAt(0)}
            </div>
          ))}
        </div>
        <span className="material-symbols-outlined text-[#64748b] group-hover:text-[#07b6d5] transition-colors text-[18px] opacity-0 group-hover:opacity-100" style={{ fontFamily: 'Material Symbols Outlined' }}>
          chevron_right
        </span>
      </div>
    </div>
  );
};
