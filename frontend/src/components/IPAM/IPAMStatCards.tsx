import React from 'react';
import type { IPAMStats } from '../../types';

interface Props {
  stats: IPAMStats;
}

const cards = [
  { key: 'total_ips' as const, label: 'Total IPs', icon: 'lan', color: 'text-slate-300' },
  { key: 'assigned_ips' as const, label: 'Assigned', icon: 'check_circle', color: 'text-cyan-400' },
  { key: 'available_ips' as const, label: 'Available', icon: 'radio_button_unchecked', color: 'text-emerald-400' },
  { key: 'reserved_ips' as const, label: 'Reserved', icon: 'lock', color: 'text-blue-400' },
  { key: 'deprecated_ips' as const, label: 'Deprecated', icon: 'do_not_disturb', color: 'text-slate-500' },
  { key: 'total_subnets' as const, label: 'Subnets', icon: 'hub', color: 'text-amber-400' },
];

export default function IPAMStatCards({ stats }: Props) {
  return (
    <div className="grid grid-cols-6 gap-3">
      {cards.map((c) => {
        const value = stats[c.key];
        const isTotal = c.key === 'total_ips';
        const isSubnets = c.key === 'total_subnets';
        const pct = !isTotal && !isSubnets && stats.total_ips > 0
          ? Math.round((value / stats.total_ips) * 100)
          : 0;
        return (
          <div
            key={c.key}
            className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3"
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`material-symbols-outlined text-lg ${c.color}`}>
                {c.icon}
              </span>
              <span className="text-[11px] text-slate-400 uppercase tracking-wider">
                {c.label}
              </span>
            </div>
            <div className="text-xl font-mono font-bold text-slate-100">
              {value.toLocaleString()}
            </div>
            {isTotal && (
              <div className="text-xs text-slate-500 mt-0.5">
                {stats.overall_utilization_pct}% utilized
              </div>
            )}
            {!isTotal && !isSubnets && (
              <div className="text-xs text-slate-500 mt-0.5">{pct}% of total</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
