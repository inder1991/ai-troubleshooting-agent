/**
 * DBOverview — Fleet health dashboard showing all connection profiles
 * with health gauges, connection stats, and quick actions.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchDBProfiles,
  fetchDBProfileHealth,
} from '../../services/api';

interface ProfileHealth {
  profile_id: string;
  name: string;
  engine: string;
  host: string;
  port: number;
  database: string;
  status: string;
  latency_ms?: number;
  version?: string;
  performance?: {
    connections_active: number;
    connections_idle: number;
    connections_max: number;
    cache_hit_ratio: number;
    transactions_per_sec: number;
    deadlocks: number;
    uptime_seconds: number;
  };
  connections?: {
    active: number;
    idle: number;
    waiting: number;
    max_connections: number;
  };
  error?: string;
}

const DBOverview: React.FC = () => {
  const [profiles, setProfiles] = useState<ProfileHealth[]>([]);
  const [loading, setLoading] = useState(true);

  const loadProfiles = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchDBProfiles();
      // Fetch health for each profile in parallel
      const healthPromises = list.map(async (p: Record<string, unknown>) => {
        try {
          const h = await fetchDBProfileHealth(p.id as string);
          return { ...p, ...h } as ProfileHealth;
        } catch {
          return { ...p, status: 'error', error: 'Health check failed' } as ProfileHealth;
        }
      });
      setProfiles(await Promise.all(healthPromises));
    } catch {
      setProfiles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadProfiles(); }, [loadProfiles]);

  const severityColor = (status: string) => {
    if (status === 'healthy') return 'text-emerald-400';
    if (status === 'degraded') return 'text-amber-400';
    if (status === 'error' || status === 'unreachable') return 'text-red-400';
    return 'text-slate-400';
  };

  const statusIcon = (status: string) => {
    if (status === 'healthy') return 'check_circle';
    if (status === 'degraded') return 'warning';
    return 'error';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-slate-400">
        <span className="material-symbols-outlined animate-spin mr-2">progress_activity</span>
        Loading fleet health...
      </div>
    );
  }

  if (profiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
        <span className="material-symbols-outlined text-4xl">database</span>
        <p className="text-lg">No database connections configured</p>
        <p className="text-sm">Go to <strong>Connections</strong> to add your first database profile.</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">Fleet Health</h2>
        <button
          onClick={loadProfiles}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
        >
          <span className="material-symbols-outlined text-[16px]">refresh</span>
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {profiles.map((p) => (
          <div key={p.profile_id} className="rounded-xl border border-slate-700/50 bg-[#0d2328] p-4 space-y-3">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`material-symbols-outlined text-lg ${severityColor(p.status)}`}>
                  {statusIcon(p.status)}
                </span>
                <div>
                  <p className="text-sm font-medium text-slate-100">{p.name}</p>
                  <p className="text-xs text-slate-500">{p.engine} • {p.host}:{p.port}/{p.database}</p>
                </div>
              </div>
              {p.latency_ms !== undefined && (
                <span className="text-xs text-slate-500">{p.latency_ms}ms</span>
              )}
            </div>

            {/* Error state */}
            {p.error && (
              <p className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">{p.error}</p>
            )}

            {/* Stats */}
            {p.performance && p.connections && (
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-slate-800/50 p-2">
                  <p className="text-xs text-slate-500">Active</p>
                  <p className="text-lg font-semibold text-cyan-400">{p.connections.active}</p>
                </div>
                <div className="rounded-lg bg-slate-800/50 p-2">
                  <p className="text-xs text-slate-500">Cache Hit</p>
                  <p className="text-lg font-semibold text-emerald-400">
                    {(p.performance.cache_hit_ratio * 100).toFixed(1)}%
                  </p>
                </div>
                <div className="rounded-lg bg-slate-800/50 p-2">
                  <p className="text-xs text-slate-500">TPS</p>
                  <p className="text-lg font-semibold text-amber-400">
                    {p.performance.transactions_per_sec.toFixed(0)}
                  </p>
                </div>
              </div>
            )}

            {/* Connection gauge */}
            {p.connections && p.connections.max_connections > 0 && (
              <div>
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Connections</span>
                  <span>{p.connections.active + p.connections.idle}/{p.connections.max_connections}</span>
                </div>
                <div className="h-1.5 rounded-full bg-slate-700 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      ((p.connections.active + p.connections.idle) / p.connections.max_connections) > 0.8
                        ? 'bg-red-500' : 'bg-cyan-500'
                    }`}
                    style={{
                      width: `${Math.min(100, ((p.connections.active + p.connections.idle) / p.connections.max_connections) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            )}

            {p.version && (
              <p className="text-xs text-slate-600">v{p.version}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DBOverview;
