import React from 'react';

interface HealthStripProps {
  cacheHitRatio?: number;
  tps?: number;
  deadlocks?: number;
  uptimeSeconds?: number;
}

function formatUptime(sec: number): string {
  if (sec >= 86400) return `${Math.floor(sec / 86400)}d`;
  if (sec >= 3600) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 60)}m`;
}

const STATUS_DOT = { ok: 'bg-emerald-400', warn: 'bg-amber-400', bad: 'bg-red-400' } as const;

function statusDot(ok: boolean): string {
  return ok ? STATUS_DOT.ok : STATUS_DOT.bad;
}

const HealthStrip: React.FC<HealthStripProps> = ({
  cacheHitRatio,
  tps,
  deadlocks,
  uptimeSeconds,
}) => {
  const items = [
    {
      label: 'Cache',
      fullLabel: 'Cache hit ratio',
      value: cacheHitRatio != null ? `${(cacheHitRatio * 100).toFixed(1)}%` : '—',
      ok: (cacheHitRatio ?? 1) >= 0.9,
    },
    {
      label: 'TPS',
      fullLabel: 'Transactions per second',
      value: tps != null ? (tps >= 1000 ? `${(tps / 1000).toFixed(1)}K` : String(Math.round(tps))) : '—',
      ok: (tps ?? 0) > 10,
    },
    {
      label: 'Deadlocks',
      fullLabel: 'Active deadlocks',
      value: deadlocks != null ? String(deadlocks) : '—',
      ok: (deadlocks ?? 0) <= 2,
    },
    {
      label: 'Uptime',
      fullLabel: 'Database uptime',
      value: uptimeSeconds != null ? formatUptime(uptimeSeconds) : '—',
      ok: (uptimeSeconds ?? 0) > 300,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:flex md:items-center md:gap-4 gap-2 px-3 py-2 bg-duck-surface/30 rounded-lg">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5" title={item.fullLabel}>
          <span className={`w-1.5 h-1.5 rounded-full ${statusDot(item.ok)}`} aria-hidden="true" />
          <span className="text-body-xs text-slate-400">{item.label}</span>
          <span className="text-body-xs font-bold text-slate-300">{item.value}</span>
        </div>
      ))}
    </div>
  );
};

export default React.memo(HealthStrip);
