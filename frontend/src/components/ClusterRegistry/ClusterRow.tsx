import React from 'react';
import type { ClusterRegistryEntry } from '../../types';

interface ClusterRowProps {
  cluster: ClusterRegistryEntry;
  onViewRecommendations: (clusterId: string) => void;
  onRunScan: (clusterId: string) => void;
}

const healthColor: Record<string, string> = {
  critical: '#ef4444',
  warning: '#e09f3e',
  healthy: '#22c55e',
  unknown: '#6b7280',
};

const healthDot: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  healthy: 'bg-green-500',
  unknown: 'bg-gray-500',
};

const providerLabel: Record<string, string> = {
  aws: 'AWS',
  azure: 'Azure',
  gcp: 'GCP',
  oci: 'OCI',
  onprem: 'On-Prem',
};

const providerBg: Record<string, string> = {
  aws: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  azure: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  gcp: 'bg-red-500/15 text-red-400 border-wr-severity-high/30',
  oci: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  onprem: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
};

const ClusterRow: React.FC<ClusterRowProps> = ({ cluster, onViewRecommendations, onRunScan }) => {
  const borderColor = healthColor[cluster.health_status] || healthColor.unknown;
  const costWarning = cluster.idle_pct > 40;

  const timeAgo = (iso: string) => {
    if (!iso) return 'Never';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  return (
    <div
      className="flex items-center gap-4 px-5 py-3.5 bg-[#1e1b15] hover:bg-[#252118] border border-[#3d3528]/50 rounded-lg transition-colors group"
      style={{ borderLeftWidth: 3, borderLeftColor: borderColor }}
    >
      {/* Name + Health */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${healthDot[cluster.health_status] || healthDot.unknown}`} />
          <span className="text-sm font-medium text-slate-100 truncate">{cluster.cluster_name}</span>
        </div>
        <span className="text-body-xs text-slate-400">{timeAgo(cluster.last_scan_at)}</span>
      </div>

      {/* Provider Badge */}
      <span className={`text-body-xs font-bold uppercase px-2 py-0.5 rounded border ${providerBg[cluster.provider] || providerBg.onprem}`}>
        {providerLabel[cluster.provider] || cluster.provider}
      </span>

      {/* Nodes */}
      <div className="w-16 text-center">
        <div className="text-xs text-slate-300">{cluster.node_count}</div>
        <div className="text-body-xs text-slate-400">nodes</div>
      </div>

      {/* Pods */}
      <div className="w-16 text-center">
        <div className="text-xs text-slate-300">{cluster.pod_count}</div>
        <div className="text-body-xs text-slate-400">pods</div>
      </div>

      {/* Cost */}
      <div className="w-24 text-right">
        <div className={`text-xs font-medium ${costWarning ? 'text-[#e09f3e]' : 'text-slate-300'}`}>
          ${cluster.monthly_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}/mo
        </div>
        {costWarning && (
          <div className="text-body-xs text-[#e09f3e]/70">{cluster.idle_pct.toFixed(0)}% idle</div>
        )}
      </div>

      {/* Savings */}
      <div className="w-20 text-right">
        {cluster.total_savings_usd > 0 ? (
          <span className="text-body-xs font-medium text-green-400">
            -${cluster.total_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </span>
        ) : (
          <span className="text-body-xs text-slate-400">--</span>
        )}
      </div>

      {/* Recommendations count */}
      <div className="w-16 text-center">
        {cluster.recommendation_count > 0 ? (
          <div className="flex items-center justify-center gap-1">
            <span className="text-xs text-slate-300">{cluster.recommendation_count}</span>
            {cluster.critical_count > 0 && (
              <span className="text-body-xs bg-wr-severity-high/20 text-red-400 px-1 rounded">{cluster.critical_count}!</span>
            )}
          </div>
        ) : (
          <span className="text-body-xs text-slate-400">--</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 opacity-70 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onViewRecommendations(cluster.cluster_id)}
          className="px-3 py-1.5 text-body-xs font-medium bg-[#e09f3e]/15 text-[#e09f3e] border border-[#e09f3e]/30 rounded hover:bg-[#e09f3e]/25 transition-colors"
        >
          Recommendations
        </button>
        <button
          onClick={() => onRunScan(cluster.cluster_id)}
          className="px-3 py-1.5 text-body-xs font-medium bg-[#252118] text-slate-300 border border-[#3d3528] rounded hover:bg-[#3d3528] transition-colors"
        >
          Run Scan
        </button>
        <button
          onClick={() => onRunScan(cluster.cluster_id)}
          className="p-1.5 text-slate-400 hover:text-slate-300 transition-colors"
          title="Refresh"
        >
          <span className="material-symbols-outlined text-[16px]">refresh</span>
        </button>
      </div>
    </div>
  );
};

export default ClusterRow;
