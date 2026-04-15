import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCICDStream } from '../../services/api';
import { getActiveProfile } from '../../services/profileApi';
import { DeliveryRow } from './DeliveryRow';
import DeliveryFilters, {
  matchesDeliveryFilter,
  type DeliveryFilterState,
} from './DeliveryFilters';
import { DeliveryDrawer } from './DeliveryDrawer';
import type { DeliveryItem } from '../../types';

export function CICDLiveBoard() {
  const { data: activeProfile } = useQuery({
    queryKey: ['active-profile'],
    queryFn: getActiveProfile,
    staleTime: 60_000,
  });
  const clusterId = activeProfile?.id;

  const since = useMemo(
    () => new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    [],
  );

  const { data, isLoading, isError, error, dataUpdatedAt } = useQuery({
    queryKey: ['cicd-stream', clusterId, since],
    queryFn: () =>
      getCICDStream({ clusterId: clusterId!, since, limit: 200 }),
    enabled: !!clusterId,
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  const [filters, setFilters] = useState<DeliveryFilterState>({
    kinds: new Set(),
    statuses: new Set(),
    search: '',
  });

  const [selected, setSelected] = useState<DeliveryItem | null>(null);

  const filteredItems = useMemo(
    () => (data?.items ?? []).filter((i) => matchesDeliveryFilter(i, filters)),
    [data, filters],
  );

  const handleInvestigate = (item: DeliveryItem) => {
    const params = new URLSearchParams({
      capability: 'troubleshoot_pipeline',
    });
    if (clusterId) params.set('cluster_id', clusterId);
    if (item.git_repo) params.set('git_repo', item.git_repo);
    if (item.target) params.set('target', item.target);
    window.location.assign(`/investigations/new?${params.toString()}`);
  };

  const subtitle =
    activeProfile?.display_name ??
    activeProfile?.name ??
    clusterId ??
    'No active cluster';

  return (
    <div className="flex flex-col h-full bg-zinc-950 text-zinc-100">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Delivery</h1>
          <div className="text-xs text-zinc-500">{subtitle}</div>
        </div>
        <div className="flex items-center gap-2">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-zinc-500">
              Last updated {new Date(dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        </div>
      </div>

      <DeliveryFilters value={filters} onChange={setFilters} />

      {data?.source_errors && data.source_errors.length > 0 && (
        <div className="px-4 py-2 text-xs text-amber-300 bg-wr-severity-medium/10 border-b border-wr-severity-medium/30">
          {data.source_errors
            .map((err) => `${err.source}/${err.name}: ${err.message}`)
            .join(' • ')}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {!clusterId ? (
          <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
            Select an active cluster profile to view delivery events.
          </div>
        ) : isLoading && !data ? (
          <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
            Loading delivery events…
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center h-full text-red-400 text-sm">
            {(error as Error)?.message ?? 'Failed to load'}
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
            No delivery events match the current filters.
          </div>
        ) : (
          <div>
            {filteredItems.map((item) => (
              <DeliveryRow
                key={item.id + item.source + item.source_instance}
                item={item}
                onSelect={setSelected}
                onInvestigate={handleInvestigate}
              />
            ))}
          </div>
        )}
      </div>

      <DeliveryDrawer item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
