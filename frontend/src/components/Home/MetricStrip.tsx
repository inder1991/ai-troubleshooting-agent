import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { V4Session } from '../../types';
import { listSessionsV4, fetchEnvironmentHealth } from '../../services/api';

const isActive = (s: V4Session) => !['complete', 'diagnosis_complete', 'error'].includes(s.status);

export const MetricStrip: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 15000,
    staleTime: 8000,
  });

  const { data: nodes = [] } = useQuery({
    queryKey: ['env-health-snapshot'],
    queryFn: fetchEnvironmentHealth,
    refetchInterval: 15000,
  });

  const metrics = useMemo(() => {
    const active = sessions.filter(isActive).length;
    const todayStr = new Date().toDateString();
    const resolved = sessions.filter(s =>
      ['complete', 'diagnosis_complete'].includes(s.status) &&
      new Date(s.updated_at).toDateString() === todayStr
    ).length;
    const avgConf = sessions.length > 0
      ? Math.round(sessions.reduce((sum, s) => sum + (s.confidence || 0), 0) / sessions.length)
      : 0;
    const resolvedSessions = sessions.filter(s => ['complete', 'diagnosis_complete'].includes(s.status));
    const avgDuration = resolvedSessions.length > 0
      ? resolvedSessions.reduce((sum, s) => {
          const ms = new Date(s.updated_at).getTime() - new Date(s.created_at).getTime();
          return sum + ms;
        }, 0) / resolvedSessions.length / 60000
      : 0;
    const issueCount = nodes.filter(n => n.status !== 'healthy').length;
    return { active, resolved, avgConf, mttr: avgDuration, issueCount, totalNodes: nodes.length };
  }, [sessions, nodes]);

  const healthColor = metrics.issueCount === 0 ? 'text-emerald-400' : metrics.issueCount <= 2 ? 'text-amber-400' : 'text-red-400';
  const healthIcon = metrics.issueCount === 0 ? 'check_circle' : 'warning';
  const healthLabel = metrics.issueCount === 0
    ? `${metrics.totalNodes} Systems Nominal`
    : `${metrics.issueCount} Issue${metrics.issueCount > 1 ? 's' : ''} Detected`;

  return (
    <div className="flex items-center gap-5 px-8 py-1.5 border-b border-duck-border/50 bg-duck-panel/50 shrink-0 overflow-x-auto">
      {/* Health status (replaces "All Systems Nominal") */}
      <div className={`flex items-center gap-1.5 ${healthColor}`}>
        <span className="material-symbols-outlined text-[14px]" aria-hidden="true">{healthIcon}</span>
        <span className="text-[11px] font-display font-bold whitespace-nowrap">
          <span className={`font-mono font-bold ${metrics.issueCount > 0 ? 'text-red-400 animate-pulse' : 'text-white'}`}>
            {metrics.issueCount > 0 ? metrics.issueCount : metrics.totalNodes}
          </span>{' '}
          {metrics.issueCount === 0 ? 'Systems Nominal' : `Issue${metrics.issueCount > 1 ? 's' : ''} Detected`}
        </span>
      </div>

      <div className="w-px h-4 bg-duck-border/30" />

      {/* Metrics */}
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-duck-accent" aria-hidden="true" />
        <span className="text-[11px] text-slate-300 whitespace-nowrap">
          <span className={`font-mono font-bold ${metrics.active > 0 ? 'text-duck-accent' : 'text-white'}`} style={{ fontVariantNumeric: 'tabular-nums' }}>{metrics.active}</span> Active
        </span>
      </div>

      <div className="w-px h-4 bg-duck-border/20" />

      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
        <span className="text-[11px] text-slate-300 whitespace-nowrap">
          <span className="font-mono font-bold text-emerald-400" style={{ fontVariantNumeric: 'tabular-nums' }}>{sessions.length > 0 ? metrics.resolved : '—'}</span> Resolved
        </span>
      </div>

      <div className="w-px h-4 bg-duck-border/20" />

      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-slate-300 whitespace-nowrap">
          Conf <span className={`font-mono font-bold ${metrics.avgConf === 0 ? 'text-white' : metrics.avgConf >= 70 ? 'text-white' : metrics.avgConf >= 40 ? 'text-amber-400' : 'text-red-400'}`} style={{ fontVariantNumeric: 'tabular-nums' }}>{sessions.length > 0 ? `${metrics.avgConf}%` : '—'}</span>
        </span>
      </div>

      <div className="w-px h-4 bg-duck-border/20" />

      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-slate-300 whitespace-nowrap">
          MTTR <span className={`font-mono font-bold ${metrics.mttr === 0 ? 'text-white' : metrics.mttr < 5 ? 'text-white' : metrics.mttr < 15 ? 'text-amber-400' : 'text-red-400'}`} style={{ fontVariantNumeric: 'tabular-nums' }}>{metrics.mttr > 0 ? `${metrics.mttr.toFixed(1)}m` : '—'}</span>
        </span>
      </div>
    </div>
  );
};
