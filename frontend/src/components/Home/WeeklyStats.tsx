import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';

const COMPLETED = ['complete', 'diagnosis_complete'];
const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

export const WeeklyStats: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 15000,
    staleTime: 8000,
  });

  const stats = useMemo(() => {
    const now = Date.now();
    const thisWeek = sessions.filter(s => now - new Date(s.created_at).getTime() < WEEK_MS);
    const completed = thisWeek.filter(s => COMPLETED.includes(s.status));
    const errored = thisWeek.filter(s => s.status === 'error');
    const totalResolved = completed.length;
    const total = thisWeek.length;
    const resolutionRate = total > 0 ? Math.round((totalResolved / total) * 100) : 0;

    const avgTime = completed.length > 0
      ? completed.reduce((sum, s) => {
          return sum + (new Date(s.updated_at).getTime() - new Date(s.created_at).getTime());
        }, 0) / completed.length / 60000
      : 0;

    return { total, totalResolved, errored: errored.length, resolutionRate, avgTime };
  }, [sessions]);

  const items = [
    { label: 'This Week', value: String(stats.total), color: 'text-white' },
    { label: 'Resolved', value: String(stats.totalResolved), color: 'text-emerald-400' },
    { label: 'Failed', value: String(stats.errored), color: stats.errored > 0 ? 'text-red-400' : 'text-slate-400' },
    { label: 'Resolution', value: `${stats.resolutionRate}%`, color: stats.resolutionRate >= 80 ? 'text-emerald-400' : 'text-amber-400' },
    { label: 'Avg Time', value: stats.avgTime > 0 ? `${stats.avgTime.toFixed(1)}m` : '—', color: 'text-slate-300' },
  ];

  return (
    <div>
      <h3 className="text-[10px] font-display font-bold text-slate-400 mb-1.5">Weekly Stats</h3>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        {items.map((item) => (
          <div key={item.label} className="flex items-center justify-between">
            <span className="text-[9px] text-slate-500">{item.label}</span>
            <span className={`text-[10px] font-mono font-bold ${item.color}`} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
