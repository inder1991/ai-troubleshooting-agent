import React, { useState, useMemo } from 'react';
import type { DeviceStatus, DriftEvent } from './hooks/useMonitorSnapshot';

interface Props {
  devices: DeviceStatus[];
  drifts: DriftEvent[];
  onSelectDevice: (deviceId: string) => void;
}

const statusOrder: Record<string, number> = { down: 0, degraded: 1, up: 2 };
const statusColor: Record<string, string> = { up: '#22c55e', degraded: '#f59e0b', down: '#ef4444' };

const NOCWallTab: React.FC<Props> = ({ devices, drifts, onSelectDevice }) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

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
    if (statusFilter !== 'all') {
      list = list.filter((d) => d.status === statusFilter);
    }
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((d) => d.device_id.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      const so = (statusOrder[a.status] ?? 2) - (statusOrder[b.status] ?? 2);
      if (so !== 0) return so;
      return b.latency_ms - a.latency_ms;
    });
    return list;
  }, [devices, search, statusFilter]);

  const downCount = devices.filter((d) => d.status === 'down').length;
  const degradedCount = devices.filter((d) => d.status === 'degraded').length;
  const upCount = devices.filter((d) => d.status === 'up').length;

  const thClass = 'text-left text-[11px] font-semibold uppercase tracking-wider py-2.5 px-3 border-b';
  const tdClass = 'py-2 px-3 text-[13px] font-mono border-b';

  return (
    <div className="flex flex-col h-full">
      {/* Filters */}
      <div className="flex items-center gap-4 px-6 py-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search devices..."
          className="pl-3 pr-3 py-2 rounded-lg border text-sm font-mono outline-none focus:border-[#07b6d5] max-w-xs"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 rounded-lg border text-sm font-mono outline-none"
          style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
        >
          <option value="all">All Status</option>
          <option value="down">Down</option>
          <option value="degraded">Degraded</option>
          <option value="up">Up</option>
        </select>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-6 pb-4">
        <table className="w-full border-collapse">
          <thead>
            <tr style={{ color: '#64748b', borderColor: '#224349' }}>
              <th className={thClass} style={{ width: 60, borderColor: '#224349' }}>Status</th>
              <th className={thClass} style={{ borderColor: '#224349' }}>Device</th>
              <th className={thClass} style={{ borderColor: '#224349' }}>Latency</th>
              <th className={thClass} style={{ borderColor: '#224349' }}>Packet Loss</th>
              <th className={thClass} style={{ borderColor: '#224349' }}>Drift</th>
              <th className={thClass} style={{ borderColor: '#224349' }}>Since</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((d) => (
              <tr
                key={d.device_id}
                className="hover:bg-[#162a2e] transition-colors cursor-pointer"
                onClick={() => onSelectDevice(d.device_id)}
              >
                <td className={tdClass} style={{ borderColor: '#224349' }}>
                  <span
                    className="inline-block w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: statusColor[d.status] }}
                  />
                </td>
                <td className={tdClass} style={{ color: '#e2e8f0', borderColor: '#224349' }}>{d.device_id}</td>
                <td className={tdClass} style={{ color: d.status === 'down' ? '#64748b' : '#07b6d5', borderColor: '#224349' }}>
                  {d.status === 'down' ? '\u2014' : `${d.latency_ms.toFixed(1)}ms`}
                </td>
                <td className={tdClass} style={{ color: d.packet_loss > 0 ? '#f59e0b' : '#94a3b8', borderColor: '#224349' }}>
                  {(d.packet_loss * 100).toFixed(0)}%
                </td>
                <td className={tdClass} style={{ color: '#94a3b8', borderColor: '#224349' }}>
                  {driftCounts[d.device_id] || 0}
                </td>
                <td className={tdClass} style={{ color: '#64748b', borderColor: '#224349' }}>
                  {d.status !== 'up' && d.last_status_change
                    ? new Date(d.last_status_change).toLocaleTimeString()
                    : '\u2014'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer summary */}
      <div className="px-6 py-2 border-t text-xs font-mono" style={{ borderColor: '#224349', color: '#64748b' }}>
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
