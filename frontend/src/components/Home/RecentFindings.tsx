import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';

const COMPLETED = ['complete', 'diagnosis_complete'];

function timeAgo(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime();
  if (ms < 60000) return 'now';
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m`;
  if (ms < 86400000) return `${Math.floor(ms / 3600000)}h`;
  return `${Math.floor(ms / 86400000)}d`;
}

export const RecentFindings: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 15000,
    staleTime: 8000,
  });

  const recentCompleted = useMemo(() =>
    sessions
      .filter(s => COMPLETED.includes(s.status))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 5),
    [sessions]
  );

  return (
    <div>
      <h3 className="text-body-xs font-display font-bold text-slate-400 mb-1.5">Recent Findings</h3>
      {recentCompleted.length === 0 ? (
        <div className="flex items-center gap-2 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500/40" aria-hidden="true" />
          <span className="text-body-xs text-slate-400">No completed investigations</span>
        </div>
      ) : (
        <div className="space-y-1.5">
          {recentCompleted.map((s) => {
            const critCount = s.critical_count ?? 0;
            const findCount = s.findings_count ?? 0;
            const sevColor = critCount > 0 ? 'text-red-400' : findCount > 0 ? 'text-amber-400' : 'text-emerald-400';
            const sevDot = critCount > 0 ? 'bg-red-400' : findCount > 0 ? 'bg-amber-400' : 'bg-emerald-400';
            return (
              <div key={s.session_id} className="flex items-start gap-2">
                <span className={`w-1.5 h-1.5 rounded-full mt-1 shrink-0 ${sevDot}`} aria-hidden="true" />
                <div className="flex-1 min-w-0">
                  <span className="text-body-xs text-slate-300 block truncate">{s.service_name}</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-body-xs font-bold ${sevColor}`}>
                      {critCount > 0 ? `${critCount} crit` : findCount > 0 ? `${findCount} issues` : 'Clean'}
                    </span>
                    <span className="text-body-xs text-slate-500">{timeAgo(s.updated_at)}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
