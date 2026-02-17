import React from 'react';
import type { V4Session } from '../../types';

interface SessionStatsProps {
  sessions: V4Session[];
}

const SessionStats: React.FC<SessionStatsProps> = ({ sessions }) => {
  const total = sessions.length;
  const active = sessions.filter(
    (s) => s.status !== 'complete' && s.status !== 'diagnosis_complete'
  ).length;
  const completed = sessions.filter(
    (s) => s.status === 'complete' || s.status === 'diagnosis_complete'
  ).length;
  const failed = sessions.filter((s) => (s.status as string) === 'error').length;

  const stats = [
    { label: 'Total Sessions', value: total, icon: 'database', color: '#94a3b8', bg: 'rgba(100,116,139,0.2)' },
    { label: 'Active', value: active, icon: 'monitoring', color: '#4ade80', bg: 'rgba(34,197,94,0.2)' },
    { label: 'Completed', value: completed, icon: 'check_circle', color: '#07b6d5', bg: 'rgba(7,182,213,0.2)' },
    { label: 'Failed', value: failed, icon: 'cancel', color: '#f87171', bg: 'rgba(239,68,68,0.2)' },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-xl p-4 flex items-center gap-3 border"
          style={{ backgroundColor: 'rgba(30,47,51,0.5)', borderColor: '#224349' }}
        >
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: stat.bg }}
          >
            <span
              className="material-symbols-outlined text-xl"
              style={{ fontFamily: 'Material Symbols Outlined', color: stat.color }}
            >
              {stat.icon}
            </span>
          </div>
          <div>
            <div className="text-2xl font-bold" style={{ color: stat.color }}>{stat.value}</div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">{stat.label}</div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default SessionStats;
