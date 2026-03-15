import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listClusters } from '../../services/api';
import type { ClusterRegistryEntry } from '../../types';
import ClusterRow from './ClusterRow';

interface ClusterRegistryPageProps {
  onViewRecommendations: (clusterId: string) => void;
  onRunScan: (clusterId: string) => void;
}

const ClusterRegistryPage: React.FC<ClusterRegistryPageProps> = ({ onViewRecommendations, onRunScan }) => {
  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState<string>('all');
  const [healthFilter, setHealthFilter] = useState<string>('all');

  const { data: clusters = [], isLoading, error } = useQuery({
    queryKey: ['clusters'],
    queryFn: listClusters,
    refetchInterval: 30_000,
  });

  const providers = useMemo(() => {
    const set = new Set(clusters.map((c) => c.provider));
    return Array.from(set).sort();
  }, [clusters]);

  const filtered = useMemo(() => {
    let list = clusters;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.cluster_name.toLowerCase().includes(q) ||
          c.provider.toLowerCase().includes(q) ||
          c.cluster_id.toLowerCase().includes(q)
      );
    }
    if (providerFilter !== 'all') {
      list = list.filter((c) => c.provider === providerFilter);
    }
    if (healthFilter !== 'all') {
      list = list.filter((c) => c.health_status === healthFilter);
    }
    return list;
  }, [clusters, search, providerFilter, healthFilter]);

  // Aggregates
  const totals = useMemo(() => {
    return filtered.reduce(
      (acc, c) => ({
        clusters: acc.clusters + 1,
        nodes: acc.nodes + c.node_count,
        pods: acc.pods + c.pod_count,
        cost: acc.cost + c.monthly_cost,
        savings: acc.savings + c.total_savings_usd,
      }),
      { clusters: 0, nodes: 0, pods: 0, cost: 0, savings: 0 }
    );
  }, [filtered]);

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar" style={{ background: '#1a1814' }}>
      <div className="max-w-[1400px] mx-auto px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-display font-bold text-slate-100 flex items-center gap-2">
              <span className="material-symbols-outlined text-[#e09f3e]" style={{ fontSize: 24 }}>cloud_circle</span>
              Cluster Fleet
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              {clusters.length} cluster{clusters.length !== 1 ? 's' : ''} registered
              {totals.cost > 0 && (
                <> &middot; <span className="text-[#e09f3e]">${totals.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo</span> total</>
              )}
            </p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 text-[16px]">search</span>
            <input
              type="text"
              placeholder="Search clusters..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-xs bg-[#13110d] border border-[#3d3528] rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-[#e09f3e]/50"
            />
          </div>

          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            className="px-3 py-2 text-xs bg-[#13110d] border border-[#3d3528] rounded-lg text-slate-300 focus:outline-none focus:border-[#e09f3e]/50"
          >
            <option value="all">All Providers</option>
            {providers.map((p) => (
              <option key={p} value={p}>{p.toUpperCase()}</option>
            ))}
          </select>

          <select
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value)}
            className="px-3 py-2 text-xs bg-[#13110d] border border-[#3d3528] rounded-lg text-slate-300 focus:outline-none focus:border-[#e09f3e]/50"
          >
            <option value="all">All Health</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="healthy">Healthy</option>
          </select>
        </div>

        {/* Column Headers */}
        <div className="flex items-center gap-4 px-5 py-2 text-[10px] uppercase tracking-wider text-slate-500 font-medium">
          <div className="flex-1">Cluster</div>
          <div className="w-16 text-center">Provider</div>
          <div className="w-16 text-center">Nodes</div>
          <div className="w-16 text-center">Pods</div>
          <div className="w-24 text-right">Cost</div>
          <div className="w-20 text-right">Savings</div>
          <div className="w-16 text-center">Recs</div>
          <div className="w-[220px]"></div>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-20">
            <span className="material-symbols-outlined text-[#e09f3e] animate-spin text-2xl">progress_activity</span>
            <span className="ml-3 text-sm text-slate-400">Loading clusters...</span>
          </div>
        )}

        {/* Error */}
        {error && !isLoading && (
          <div className="flex items-center justify-center py-20">
            <span className="material-symbols-outlined text-red-400 text-xl mr-2">error</span>
            <span className="text-sm text-red-400">Failed to load clusters</span>
          </div>
        )}

        {/* Empty */}
        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <span className="material-symbols-outlined text-slate-600 mb-3" style={{ fontSize: 48 }}>cloud_off</span>
            <p className="text-sm text-slate-400 mb-1">No clusters connected.</p>
            <p className="text-xs text-slate-500">Add a cluster in Integrations to get started.</p>
          </div>
        )}

        {/* Rows */}
        {!isLoading && !error && filtered.length > 0 && (
          <div className="flex flex-col gap-2">
            {filtered.map((cluster) => (
              <ClusterRow
                key={cluster.cluster_id}
                cluster={cluster}
                onViewRecommendations={onViewRecommendations}
                onRunScan={onRunScan}
              />
            ))}
          </div>
        )}

        {/* Footer Totals */}
        {!isLoading && filtered.length > 0 && (
          <div className="flex items-center gap-6 mt-4 px-5 py-3 bg-[#13110d] border border-[#3d3528]/30 rounded-lg text-[11px] text-slate-400">
            <span>{totals.clusters} cluster{totals.clusters !== 1 ? 's' : ''}</span>
            <span>{totals.nodes} nodes</span>
            <span>{totals.pods} pods</span>
            <span className="text-[#e09f3e]">${totals.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo total</span>
            {totals.savings > 0 && (
              <span className="text-green-400">-${totals.savings.toLocaleString(undefined, { maximumFractionDigits: 0 })} potential savings</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ClusterRegistryPage;
