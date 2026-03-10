import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { MetricCard } from '../shared';
import type { V4Session } from '../../types';
import { listSessionsV4 } from '../../services/api';

const isActive = (s: V4Session) => !['complete', 'diagnosis_complete', 'error'].includes(s.status);

export const MetricRibbon: React.FC = () => {
  const { data: sessions = [] } = useQuery({
    queryKey: ['live-sessions'],
    queryFn: listSessionsV4,
    refetchInterval: 10000,
    staleTime: 5000,
  });

  const todayStr = new Date().toDateString();
  const isResolvedToday = (s: V4Session) => {
    if (!['complete', 'diagnosis_complete'].includes(s.status)) return false;
    return new Date(s.updated_at).toDateString() === todayStr;
  };
  const metrics = useMemo(() => {
    const active = sessions.filter(isActive);
    const resolved = sessions.filter(isResolvedToday);
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

    const recentConf = sessions.slice(0, 8).map(s => s.confidence || 0);
    const recentActive = sessions.slice(0, 8).map((_, i) => sessions.slice(0, i + 1).filter(isActive).length);

    return {
      activeCount: active.length,
      resolvedCount: resolved.length,
      avgConfidence: avgConf,
      mttr: avgDuration > 0 ? `${avgDuration.toFixed(1)}m` : '—',
      sparkActive: recentActive.length >= 2 ? recentActive : [0, 0],
      sparkResolved: resolved.length >= 2 ? recentConf : [0, 0],
      sparkConf: recentConf.length >= 2 ? recentConf : [0, 0],
      sparkMttr: recentConf.length >= 2 ? [...recentConf].reverse() : [0, 0],
    };
  }, [sessions]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <MetricCard
        title="Active Sessions"
        value={metrics.activeCount}
        trendValue={String(metrics.activeCount)}
        trendDirection={metrics.activeCount > 0 ? 'up' : 'neutral'}
        trendType="neutral"
        sparklineData={metrics.sparkActive}
      />
      <MetricCard
        title="Resolved Today"
        value={metrics.resolvedCount}
        trendValue={String(metrics.resolvedCount)}
        trendDirection={metrics.resolvedCount > 0 ? 'up' : 'neutral'}
        trendType="good"
        sparklineData={metrics.sparkResolved}
      />
      <MetricCard
        title="Avg Confidence"
        value={`${metrics.avgConfidence}%`}
        trendValue={`${metrics.avgConfidence}%`}
        trendDirection={metrics.avgConfidence >= 70 ? 'up' : 'down'}
        trendType={metrics.avgConfidence >= 70 ? 'good' : 'bad'}
        sparklineData={metrics.sparkConf}
      />
      <MetricCard
        title="Mean Time to Resolve"
        value={metrics.mttr}
        trendValue={metrics.mttr}
        trendDirection="down"
        trendType="good"
        sparklineData={metrics.sparkMttr}
      />
    </div>
  );
};
