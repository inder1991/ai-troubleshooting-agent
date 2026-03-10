import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import * as Tooltip from '@radix-ui/react-tooltip';
import { fetchEnvironmentHealth } from '../../services/api';
import type { HealthNode } from '../../types';

const getNodeStyles = (status: HealthNode['status']) => {
  switch (status) {
    case 'critical':
      return 'bg-red-500/20 border-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)] animate-pulse';
    case 'degraded':
      return 'bg-amber-500/20 border-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)] animate-pulse';
    case 'offline':
      return 'bg-slate-800 border-slate-700 opacity-50';
    case 'healthy':
    default:
      return 'bg-duck-surface border-duck-border/40 hover:border-duck-accent/50 transition-colors';
  }
};

const statusTextColor = (status: HealthNode['status']) =>
  status === 'healthy' ? 'text-emerald-400' : status === 'degraded' ? 'text-amber-400' : 'text-red-400';

export const EnvironmentHealth: React.FC = () => {
  const { data: nodes = [], isLoading } = useQuery({
    queryKey: ['env-health-snapshot'],
    queryFn: fetchEnvironmentHealth,
    refetchInterval: 10000,
  });

  const { healthyCount, issueCount } = useMemo(() => {
    const issues = nodes.filter(n => n.status !== 'healthy');
    return {
      healthyCount: nodes.length - issues.length,
      issueCount: issues.length,
    };
  }, [nodes]);

  return (
    <div className="bg-duck-panel border border-duck-border rounded-lg h-full p-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3 shrink-0">
        <div>
          <h3 className="text-xs font-bold text-duck-muted uppercase tracking-wider">
            Environment Health
          </h3>
          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
            {isLoading ? 'Scanning...' : `${healthyCount}/${nodes.length} Systems Nominal`}
          </div>
        </div>

        {!isLoading && issueCount > 0 && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-red-500/10 border border-red-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" aria-hidden="true" />
            <span className="text-[9px] leading-none font-bold text-red-400 uppercase tracking-wider">
              {issueCount} {issueCount === 1 ? 'Issue' : 'Issues'}
            </span>
          </div>
        )}
      </div>

      {/* NOC Matrix */}
      <div className="flex-1 overflow-y-auto custom-scrollbar pr-1">
        <Tooltip.Provider delayDuration={0}>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(20px,1fr))] gap-1.5">
            {isLoading ? (
              Array.from({ length: 48 }).map((_, i) => (
                <div key={i} className="aspect-square rounded-[3px] bg-duck-surface animate-pulse" />
              ))
            ) : (
              nodes.map((node) => (
                <Tooltip.Root key={node.id}>
                  <Tooltip.Trigger asChild>
                    <button
                      className={`aspect-square rounded-[3px] border ${getNodeStyles(node.status)}`}
                      aria-label={`${node.name} status: ${node.status}`}
                    />
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      className="z-50 bg-duck-flyout border border-duck-border rounded px-2.5 py-1.5 shadow-xl"
                      sideOffset={5}
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="text-[10px] font-bold text-white uppercase tracking-wider">
                          {node.name}
                        </span>
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                          <span className={statusTextColor(node.status)}>
                            {node.status.toUpperCase()}
                          </span>
                          {node.latencyMs != null && (
                            <span className="text-slate-500">{node.latencyMs}ms</span>
                          )}
                        </div>
                      </div>
                      <Tooltip.Arrow className="fill-duck-border" />
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
              ))
            )}
          </div>
        </Tooltip.Provider>
      </div>
    </div>
  );
};
