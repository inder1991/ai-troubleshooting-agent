import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCICDStream } from '../../services/api';
import { getActiveProfile } from '../../services/profileApi';
import { useNavigate } from 'react-router-dom';

export const DeliveryPulse: React.FC = () => {
  const navigate = useNavigate();

  const { data: activeProfile } = useQuery({
    queryKey: ['active-profile'],
    queryFn: getActiveProfile,
    staleTime: 60_000,
  });
  const clusterId = activeProfile?.id;

  const since = useMemo(
    () => new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
    []
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: ['cicd-stream-pulse', clusterId, since],
    queryFn: () => getCICDStream({ clusterId: clusterId!, since, limit: 20 }),
    enabled: !!clusterId,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  const topItems = useMemo(() => (data?.items ?? []).slice(0, 8), [data]);

  return (
    <div className="surface-panel p-2.5 overflow-hidden">
      <header className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px] text-duck-accent" aria-hidden="true">rocket_launch</span>
          <h3 className="text-body-xs font-display font-bold tracking-wider uppercase text-white">Delivery Pulse</h3>
        </div>
        <button
          className="text-body-xs text-slate-400 hover:text-duck-accent transition-colors"
          onClick={() => navigate('/cicd')}
          aria-label="Open delivery board"
        >
          Open →
        </button>
      </header>

      {!clusterId && (
        <div className="text-body-xs text-slate-500 py-2">No active cluster.</div>
      )}
      {clusterId && isLoading && (
        <div className="text-body-xs text-slate-500 py-2">Loading…</div>
      )}
      {clusterId && isError && (
        <div className="text-body-xs text-red-400 py-2">Failed to load delivery events</div>
      )}
      {clusterId && !isLoading && !isError && topItems.length === 0 && (
        <div className="text-body-xs text-slate-500 py-2">No recent activity.</div>
      )}

      <ul className="space-y-1">
        {topItems.map((item) => {
          const statusColor =
            item.status === 'success' || item.status === 'healthy'
              ? 'text-emerald-300'
              : item.status === 'failed'
              ? 'text-red-400'
              : item.status === 'in_progress' || item.status === 'progressing' || item.status === 'degraded'
              ? 'text-amber-300'
              : 'text-slate-400';
          const kindIcon =
            item.kind === 'commit' ? 'commit' : item.kind === 'build' ? 'build_circle' : 'sync';
          return (
            <li
              key={`${item.id}-${item.source}-${item.source_instance}`}
              className="flex items-center gap-2 text-body-xs py-1 px-1 rounded hover:bg-duck-card/30 cursor-pointer"
              onClick={() => navigate('/cicd')}
            >
              <span
                className={`material-symbols-outlined text-[13px] ${statusColor}`}
                aria-hidden="true"
              >
                {kindIcon}
              </span>
              <span className="flex-1 truncate text-slate-200">{item.title}</span>
              <span className={`uppercase text-body-xs tracking-wider ${statusColor}`}>
                {item.status}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default DeliveryPulse;
