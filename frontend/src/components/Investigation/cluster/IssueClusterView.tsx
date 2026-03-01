import React, { useState } from 'react';
import type { IssueCluster } from '../../../types';

interface IssueClusterViewProps {
  clusters: IssueCluster[];
}

const SEVERITY_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high: 'bg-red-400',
  warning: 'bg-amber-500',
  medium: 'bg-amber-400',
  low: 'bg-slate-500',
  info: 'bg-slate-400',
};

const BASIS_STYLE: Record<string, string> = {
  topology: 'text-cyan-400 border-cyan-500/40 bg-cyan-500/10',
  temporal: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  namespace: 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10',
  node_affinity: 'text-blue-400 border-blue-500/40 bg-blue-500/10',
  control_plane_fan_out: 'text-purple-400 border-purple-500/40 bg-purple-500/10',
};

export default function IssueClusterView({ clusters }: IssueClusterViewProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!clusters || clusters.length === 0) return null;

  return (
    <div className="space-y-3 mb-4">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-cyan-400">hub</span>
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Issue Clusters</span>
        <span className="text-[9px] font-mono text-slate-500">{clusters.length}</span>
      </div>

      {clusters.map(cluster => {
        const isExpanded = expandedId === cluster.cluster_id;
        return (
          <div
            key={cluster.cluster_id}
            className="bg-slate-900/40 border border-slate-700/30 rounded-lg overflow-hidden"
          >
            {/* Header */}
            <button
              onClick={() => setExpandedId(isExpanded ? null : cluster.cluster_id)}
              className="w-full px-3 py-2 flex items-center gap-2 hover:bg-slate-800/30 transition-colors"
            >
              <span className="text-[10px] font-mono text-cyan-400">{cluster.cluster_id}</span>

              {/* Confidence bar */}
              <div className="w-12 h-1 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-cyan-500 rounded-full"
                  style={{ width: `${Math.round(cluster.confidence * 100)}%` }}
                />
              </div>
              <span className="text-[9px] font-mono text-slate-500">{Math.round(cluster.confidence * 100)}%</span>

              {/* Correlation basis badges */}
              <div className="flex items-center gap-1 ml-1">
                {cluster.correlation_basis.map(basis => (
                  <span
                    key={basis}
                    className={`px-1.5 py-0.5 text-[8px] font-mono rounded border ${BASIS_STYLE[basis] || 'text-slate-400 border-slate-500/40 bg-slate-500/10'}`}
                  >
                    {basis.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>

              {/* Affected count */}
              <span className="ml-auto text-[9px] font-mono text-slate-500">
                {cluster.affected_resources.length} resources
              </span>
              <span className="material-symbols-outlined text-slate-500 text-sm">
                {isExpanded ? 'expand_less' : 'expand_more'}
              </span>
            </button>

            {isExpanded && (
              <div className="border-t border-slate-700/30 px-3 py-2 space-y-3">
                {/* Root Candidates */}
                {cluster.root_candidates.length > 0 && (
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-red-400 font-semibold">Root Candidates</span>
                    <div className="mt-1 space-y-1.5">
                      {cluster.root_candidates.map((rc, i) => (
                        <div key={i} className="bg-red-500/5 border border-red-500/20 rounded px-2 py-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-mono text-red-300">{rc.resource_key}</span>
                            <span className="text-[9px] font-mono text-slate-500">{Math.round(rc.confidence * 100)}%</span>
                          </div>
                          <p className="text-[10px] text-slate-400 mt-0.5">{rc.hypothesis}</p>
                          {rc.supporting_signals.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {rc.supporting_signals.map((s, j) => (
                                <span key={j} className="text-[8px] font-mono px-1 py-0.5 bg-slate-800/60 text-slate-500 rounded">
                                  {s}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Alerts */}
                {cluster.alerts.length > 0 && (
                  <div>
                    <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Alerts</span>
                    <div className="mt-1 space-y-0.5">
                      {cluster.alerts.map((alert, i) => {
                        const dotClass = SEVERITY_DOT[alert.severity] || SEVERITY_DOT.info;
                        return (
                          <div key={i} className="flex items-center gap-2 text-[11px]">
                            <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
                            <span className="font-mono text-slate-400">{alert.resource_key}</span>
                            <span className="text-slate-500">{alert.alert_type}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
