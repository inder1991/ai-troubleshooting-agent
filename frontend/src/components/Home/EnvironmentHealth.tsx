import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchEnvironmentHealth } from '../../services/api';
import type { HealthNode } from '../../types';

const statusIcon: Record<string, { icon: string; cls: string }> = {
  critical: { icon: 'error', cls: 'text-red-400' },
  degraded: { icon: 'warning', cls: 'text-amber-400' },
  offline: { icon: 'cancel', cls: 'text-slate-400' },
};

export const EnvironmentHealth: React.FC = () => {
  const { data: nodes = [], isLoading } = useQuery({
    queryKey: ['env-health-snapshot'],
    queryFn: fetchEnvironmentHealth,
    refetchInterval: 10000,
  });

  const { healthyCount, issues } = useMemo(() => {
    const problemNodes = nodes.filter(n => n.status !== 'healthy');
    return {
      healthyCount: nodes.length - problemNodes.length,
      issues: problemNodes.sort((a, b) => {
        const order: Record<string, number> = { critical: 0, degraded: 1, offline: 2 };
        return (order[a.status] ?? 3) - (order[b.status] ?? 3);
      }),
    };
  }, [nodes]);

  // Determine left border color by worst status
  const borderColor = isLoading ? '#64748b'
    : issues.some(n => n.status === 'critical') ? '#ef4444'
    : issues.some(n => n.status === 'degraded') ? '#f59e0b'
    : '#10b981';

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-duck-panel border border-duck-border rounded-lg"
        style={{ borderLeft: `3px solid ${borderColor}` }}>
        <span className="material-symbols-outlined text-sm text-slate-400 animate-spin" aria-hidden="true">progress_activity</span>
        <span className="text-body-xs text-slate-400">Scanning systems...</span>
      </div>
    );
  }

  // All healthy — compact with mini grid
  if (issues.length === 0) {
    return (
      <div className="bg-duck-panel border border-duck-border rounded-lg px-3 py-2"
        style={{ borderLeft: `3px solid ${borderColor}` }}>
        <div className="flex items-center gap-[2px] mb-2">
          {nodes.slice(0, 24).map((node) => (
            <span key={node.id} className="w-1.5 h-1.5 rounded-[1px] bg-emerald-500/30" aria-hidden="true" />
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-sm text-emerald-400" aria-hidden="true">check_circle</span>
          <span className="text-body-xs font-display font-bold text-emerald-400">
            {nodes.length}/{nodes.length} Systems Nominal
          </span>
        </div>
      </div>
    );
  }

  // Has issues — show problems only, summarize healthy
  return (
    <div className="bg-duck-panel border border-duck-border rounded-lg px-3 py-2"
      style={{ borderLeft: `3px solid ${borderColor}` }}>
      {/* Mini NOC strip */}
      <div className="flex items-center gap-[2px] mb-2 pb-2 border-b border-duck-border/30">
        {nodes.slice(0, 24).map((node) => (
          <span
            key={node.id}
            className={`w-1.5 h-1.5 rounded-[1px] ${
              node.status === 'critical' ? 'bg-red-400 animate-pulse' :
              node.status === 'degraded' ? 'bg-amber-400' :
              node.status === 'offline' ? 'bg-slate-600' :
              'bg-emerald-500/30'
            }`}
            aria-hidden="true"
          />
        ))}
      </div>

      {/* Issue list */}
      <div className="space-y-1.5">
        {issues.map((node) => {
          const si = statusIcon[node.status] || statusIcon.degraded;
          return (
            <div key={node.id} className="flex items-center gap-2">
              <span className={`material-symbols-outlined text-[14px] ${si.cls}`} aria-hidden="true">
                {si.icon}
              </span>
              <span className="text-body-xs text-slate-200 font-display font-bold flex-1 truncate">
                {node.name}
              </span>
              <span className={`text-body-xs ${si.cls}`}>
                {node.status}
              </span>
              {node.latencyMs != null && (
                <span className="text-body-xs text-slate-400 font-mono">{node.latencyMs}ms</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Healthy summary */}
      <div className="flex items-center gap-1.5 mt-2 pt-1.5 border-t border-duck-border/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
        <span className="text-body-xs text-slate-400">
          {healthyCount} system{healthyCount !== 1 ? 's' : ''} healthy
        </span>
      </div>
    </div>
  );
};
