import React, { useState, useMemo, useEffect } from 'react';
import { SparklineWidget } from '../shared/SparklineWidget';
import type { DeviceStatus, DriftEvent, MetricDataPoint } from './hooks/useMonitorSnapshot';
import { fetchDeviceMetrics } from '../../services/api';

interface Props {
  devices: DeviceStatus[];
  drifts: DriftEvent[];
  onSelectDevice: (deviceId: string) => void;
}

const statusColor: Record<string, string> = { up: '#22c55e', degraded: '#f59e0b', down: '#ef4444' };
const statusOrder: Record<string, number> = { down: 0, degraded: 1, up: 2 };

interface DeviceMetrics {
  cpu_pct: number;
  mem_pct: number;
  latencyHistory: MetricDataPoint[];
}

const CircularGauge: React.FC<{ value: number; label: string; color: string; size?: number }> = ({
  value, label, color, size = 48,
}) => {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(Math.max(value, 0), 100);
  const offset = c - (pct / 100) * c;
  return (
    <div className="flex flex-col items-center gap-0.5">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="#3d3528" strokeWidth={3} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={3}
          strokeDasharray={c} strokeDashoffset={offset}
          strokeLinecap="round" />
      </svg>
      <div className="text-center -mt-8">
        <div className="text-xs font-mono font-bold" style={{ color }}>{pct.toFixed(0)}%</div>
      </div>
      <div className="text-[9px] font-mono mt-3" style={{ color: '#64748b' }}>{label}</div>
    </div>
  );
};

const NOCWallTab: React.FC<Props> = ({ devices, drifts, onSelectDevice }) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [deviceMetrics, setDeviceMetrics] = useState<Record<string, DeviceMetrics>>({});

  // Fetch metrics for visible devices
  useEffect(() => {
    const loadMetrics = async () => {
      const metrics: Record<string, DeviceMetrics> = {};
      for (const d of devices.slice(0, 20)) {
        try {
          const [cpuRes, memRes, latRes] = await Promise.all([
            fetchDeviceMetrics(d.device_id, 'cpu_pct', '5m', '30s').catch(() => ({ data: [] })),
            fetchDeviceMetrics(d.device_id, 'mem_pct', '5m', '30s').catch(() => ({ data: [] })),
            fetchDeviceMetrics(d.device_id, 'latency_ms', '1h', '1m').catch(() => ({ data: [] })),
          ]);
          const cpuData = cpuRes.data || [];
          const memData = memRes.data || [];
          metrics[d.device_id] = {
            cpu_pct: cpuData.length > 0 ? cpuData[cpuData.length - 1].value : 0,
            mem_pct: memData.length > 0 ? memData[memData.length - 1].value : 0,
            latencyHistory: latRes.data || [],
          };
        } catch {
          metrics[d.device_id] = { cpu_pct: 0, mem_pct: 0, latencyHistory: [] };
        }
      }
      setDeviceMetrics(metrics);
    };
    if (devices.length > 0) loadMetrics();
  }, [devices]);

  const driftCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of drifts) {
      const key = d.entity_id.split('-')[0] || d.entity_id;
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  }, [drifts]);

  const filtered = useMemo(() => {
    let list = [...devices];
    if (statusFilter !== 'all') list = list.filter((d) => d.status === statusFilter);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((d) => d.device_id.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      const so = (statusOrder[a.status] ?? 2) - (statusOrder[b.status] ?? 2);
      return so !== 0 ? so : b.latency_ms - a.latency_ms;
    });
    return list;
  }, [devices, search, statusFilter]);

  const downCount = devices.filter((d) => d.status === 'down').length;
  const degradedCount = devices.filter((d) => d.status === 'degraded').length;
  const upCount = devices.filter((d) => d.status === 'up').length;

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="flex items-center gap-4 px-6 py-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search devices..."
          className="pl-3 pr-3 py-2 rounded-lg border text-sm font-mono outline-none focus:border-[#e09f3e] max-w-xs"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#3d3528', color: '#e8e0d4' }}
        />
        <div className="flex gap-1">
          {['all', 'down', 'degraded', 'up'].map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className="px-2.5 py-1 rounded text-xs font-mono transition-colors"
              style={{
                backgroundColor: statusFilter === s ? 'rgba(224,159,62,0.15)' : 'transparent',
                color: s === 'all' ? (statusFilter === s ? '#e09f3e' : '#64748b') : statusColor[s] || '#64748b',
                border: `1px solid ${statusFilter === s ? '#e09f3e' : '#3d3528'}`,
              }}
            >
              {s.toUpperCase()}
              {s !== 'all' && ` (${s === 'down' ? downCount : s === 'degraded' ? degradedCount : upCount})`}
            </button>
          ))}
        </div>
      </div>

      {/* Device Cards Grid */}
      <div className="flex-1 overflow-auto px-6 pb-4">
        {devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-16 gap-6">
            <span className="material-symbols-outlined text-5xl" style={{ color: '#3d3528' }}>sensors</span>
            <div className="text-center space-y-1">
              <div className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>Device Health Monitoring</div>
              <div className="text-xs font-mono" style={{ color: '#64748b' }}>Connect SNMP or API adapters to enable live device monitoring</div>
            </div>
            <div className="text-xs font-mono space-y-1 text-left" style={{ color: '#7a7060' }}>
              <div>• Cisco IOS-XE — SNMP v2c/v3</div>
              <div>• Palo Alto PAN-OS — REST API via Panorama</div>
              <div>• F5 BIG-IP — iControl REST</div>
              <div>• Checkpoint — HTTPS Management API</div>
              <div>• Any vendor — Ping probes (auto-configured)</div>
            </div>
            <div className="flex gap-3">
              <a href="/network/adapters" className="px-3 py-1.5 rounded text-xs font-mono border" style={{ borderColor: '#07b6d5', color: '#07b6d5' }}>
                Configure Adapters →
              </a>
              <a href="/network/topology" className="px-3 py-1.5 rounded text-xs font-mono border" style={{ borderColor: '#3d3528', color: '#7a7060' }}>
                View Topology →
              </a>
            </div>
          </div>
        ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filtered.map((d) => {
            const m = deviceMetrics[d.device_id];
            const dc = driftCounts[d.device_id] || 0;
            return (
              <div
                key={d.device_id}
                onClick={() => onSelectDevice(d.device_id)}
                className="rounded-lg border p-3 cursor-pointer transition-all hover:border-[#e09f3e]"
                style={{
                  backgroundColor: '#0a1a1e',
                  borderColor: d.status === 'down' ? '#ef444440' : d.status === 'degraded' ? '#f59e0b40' : '#3d3528',
                }}
              >
                {/* Header: status + name */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: statusColor[d.status] }} />
                    <span className="text-sm font-mono font-medium truncate" style={{ color: '#e8e0d4' }}>
                      {d.device_id}
                    </span>
                  </div>
                  {dc > 0 && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: '#f59e0b20', color: '#f59e0b' }}>
                      {dc} drift
                    </span>
                  )}
                </div>

                {/* Gauges + Sparkline */}
                <div className="flex items-center justify-between">
                  <div className="flex gap-3">
                    <CircularGauge
                      value={m?.cpu_pct || 0}
                      label="CPU"
                      color={!m || m.cpu_pct < 70 ? '#22c55e' : m.cpu_pct < 90 ? '#f59e0b' : '#ef4444'}
                    />
                    <CircularGauge
                      value={m?.mem_pct || 0}
                      label="MEM"
                      color={!m || m.mem_pct < 80 ? '#e09f3e' : m.mem_pct < 95 ? '#f59e0b' : '#ef4444'}
                    />
                  </div>
                  {/* Latency sparkline */}
                  <div className="w-24 h-10">
                    {m?.latencyHistory && m.latencyHistory.length > 1 ? (
                      <SparklineWidget
                        data={m.latencyHistory.map(p => p.value)}
                        color={d.status === 'down' ? 'red' : d.status === 'degraded' ? 'amber' : 'gold'}
                        height={40}
                        strokeWidth={1.5}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-[9px] font-mono" style={{ color: '#3d3528' }}>
                        —
                      </div>
                    )}
                  </div>
                </div>

                {/* Footer: latency + packet loss */}
                <div className="flex justify-between mt-2 text-[10px] font-mono" style={{ color: '#64748b' }}>
                  <span>
                    {d.status === 'down' ? '—' : `${d.latency_ms.toFixed(1)}ms`}
                  </span>
                  <span style={{ color: d.packet_loss > 0 ? '#f59e0b' : '#64748b' }}>
                    {(d.packet_loss * 100).toFixed(0)}% loss
                  </span>
                  <span>{d.probe_method}</span>
                </div>
              </div>
            );
          })}
        </div>
        )}
      </div>

      {/* Footer summary */}
      <div className="px-6 py-2 border-t text-xs font-mono" style={{ borderColor: '#3d3528', color: '#64748b' }}>
        {downCount > 0 && <span style={{ color: '#ef4444' }}>{downCount} DOWN</span>}
        {downCount > 0 && (degradedCount > 0 || upCount > 0) && ' \u00b7 '}
        {degradedCount > 0 && <span style={{ color: '#f59e0b' }}>{degradedCount} DEGRADED</span>}
        {degradedCount > 0 && upCount > 0 && ' \u00b7 '}
        <span style={{ color: '#22c55e' }}>{upCount} UP</span>
        {drifts.length > 0 && <span> \u00b7 {drifts.length} active drift events</span>}
      </div>
    </div>
  );
};

export default NOCWallTab;
