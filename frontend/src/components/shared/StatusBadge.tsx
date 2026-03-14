import React from 'react';

export type SystemStatus = 'healthy' | 'degraded' | 'critical' | 'unknown' | 'in_progress';

interface StatusBadgeProps {
  status: SystemStatus;
  label: string;
  count?: number;
  pulse?: boolean;
}

const statusStyles: Record<SystemStatus, { bg: string; text: string; border: string; dot: string }> = {
  healthy:     { bg: 'bg-green-500/10',    text: 'text-green-500',    border: 'border-green-500/20',    dot: 'bg-green-500' },
  degraded:    { bg: 'bg-[#f59e0b]/10',    text: 'text-[#f59e0b]',    border: 'border-[#f59e0b]/20',    dot: 'bg-[#f59e0b]' },
  critical:    { bg: 'bg-[#ef4444]/10',    text: 'text-[#ef4444]',    border: 'border-[#ef4444]/20',    dot: 'bg-[#ef4444]' },
  unknown:     { bg: 'bg-slate-500/10',    text: 'text-slate-400',    border: 'border-slate-500/20',    dot: 'bg-slate-400' },
  in_progress: { bg: 'bg-[#e09f3e]/10',   text: 'text-[#e09f3e]',   border: 'border-[#e09f3e]/20',   dot: 'bg-[#e09f3e]' },
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, count, pulse = false }) => {
  const s = statusStyles[status] || statusStyles.unknown;

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded border ${s.bg} ${s.text} ${s.border} text-[10px] uppercase tracking-wider`}>
      <span className="relative flex h-1.5 w-1.5">
        {pulse && <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${s.dot}`} />}
        <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${s.dot}`} />
      </span>
      <span>{label}</span>
      {count !== undefined && (
        <span className="ml-1 px-1 bg-black/20 rounded-sm text-[9px]">{count}</span>
      )}
    </div>
  );
};
