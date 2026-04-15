import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getAgents } from '../../services/api';

const RECENT_THRESHOLD_MS = 60_000;

export const CompactAgentFleet: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['agent-fleet'],
    queryFn: getAgents,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const agents = data?.agents ?? [];

  const { activeCount, totalCount, activeNames } = useMemo(() => {
    const now = Date.now();
    const active = agents.filter(a => {
      if (a.status === 'offline') return false;
      return a.recent_executions.some(ex => now - new Date(ex.timestamp).getTime() < RECENT_THRESHOLD_MS);
    });
    return {
      activeCount: active.length,
      totalCount: agents.length,
      activeNames: active.slice(0, 4).map(a => a.name),
    };
  }, [agents]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-[14px] text-slate-400 animate-spin" aria-hidden="true">progress_activity</span>
        <span className="text-body-xs text-slate-400">Loading agents...</span>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-body-xs font-display font-bold text-slate-400">Agent Fleet</h3>
        <span className="text-body-xs text-slate-400">
          <span className="text-white font-bold">{activeCount}</span>/{totalCount} active
        </span>
      </div>
      {activeCount === 0 ? (
        <div className="flex items-center gap-2 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-500/40" aria-hidden="true" />
          <span className="text-body-xs text-slate-400">{totalCount} agents on standby</span>
        </div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {activeNames.map((name) => (
            <span key={name} className="flex items-center gap-1 text-body-xs px-1.5 py-0.5 rounded bg-duck-accent/10 text-duck-accent border border-duck-accent/20">
              <span className="w-1 h-1 rounded-full bg-duck-accent animate-pulse" aria-hidden="true" />
              {name}
            </span>
          ))}
          {activeCount > 4 && (
            <span className="text-body-xs text-slate-400">+{activeCount - 4} more</span>
          )}
        </div>
      )}
    </div>
  );
};
