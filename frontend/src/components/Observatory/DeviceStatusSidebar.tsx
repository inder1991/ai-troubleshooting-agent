import React, { useState, useEffect } from 'react';
import type { DeviceStatus } from './hooks/useMonitorSnapshot';
import { fetchDeviceHistory } from '../../services/api';

interface Props {
  device: DeviceStatus;
  onClose: () => void;
}

const statusColor: Record<string, string> = { up: '#22c55e', degraded: '#f59e0b', down: '#ef4444' };

const DeviceStatusSidebar: React.FC<Props> = ({ device, onClose }) => {
  const [history, setHistory] = useState<{ value: number; recorded_at: string }[]>([]);
  const [period, setPeriod] = useState('24h');

  useEffect(() => {
    fetchDeviceHistory(device.device_id, period)
      .then((data) => setHistory(data.history || []))
      .catch(() => setHistory([]));
  }, [device.device_id, period]);

  const maxLatency = Math.max(...history.map((h) => h.value), 1);

  return (
    <div
      className="w-80 flex flex-col border-l overflow-y-auto"
      style={{ backgroundColor: '#0a1a1e', borderColor: '#3d3528' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: '#3d3528' }}>
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-full"
            style={{ backgroundColor: statusColor[device.status] }}
          />
          <span className="text-white font-bold text-sm">{device.device_id}</span>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-sm">&times;</button>
      </div>

      {/* Status details */}
      <div className="px-4 py-3 space-y-3">
        <div className="flex justify-between text-xs">
          <span style={{ color: '#64748b' }}>Status</span>
          <span className="uppercase font-bold" style={{ color: statusColor[device.status] }}>
            {device.status}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: '#64748b' }}>Latency</span>
          <span style={{ color: '#e09f3e' }} className="font-mono">
            {device.status === 'down' ? '\u2014' : `${device.latency_ms.toFixed(1)}ms`}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: '#64748b' }}>Packet Loss</span>
          <span style={{ color: device.packet_loss > 0 ? '#f59e0b' : '#8a7e6b' }} className="font-mono">
            {(device.packet_loss * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: '#64748b' }}>Probe</span>
          <span style={{ color: '#8a7e6b' }} className="font-mono">{device.probe_method}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span style={{ color: '#64748b' }}>Last Seen</span>
          <span style={{ color: '#8a7e6b' }} className="font-mono">
            {device.last_seen ? new Date(device.last_seen).toLocaleTimeString() : '\u2014'}
          </span>
        </div>
      </div>

      {/* Latency sparkline */}
      <div className="px-4 py-3 border-t" style={{ borderColor: '#3d3528' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs" style={{ color: '#64748b' }}>Latency History</span>
          <div className="flex gap-1">
            {['1h', '24h', '7d'].map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className="px-2 py-0.5 rounded text-body-xs font-mono"
                style={period === p
                  ? { backgroundColor: 'rgba(224,159,62,0.15)', color: '#e09f3e' }
                  : { color: '#64748b' }
                }
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        {history.length > 0 ? (
          <svg viewBox={`0 0 ${history.length} 40`} className="w-full h-10" preserveAspectRatio="none">
            <polyline
              fill="none"
              stroke="#e09f3e"
              strokeWidth="1.5"
              points={history.map((h, i) => `${i},${40 - (h.value / maxLatency) * 36}`).join(' ')}
            />
          </svg>
        ) : (
          <div className="text-body-xs text-center py-4" style={{ color: '#64748b' }}>No data</div>
        )}
      </div>
    </div>
  );
};

export default DeviceStatusSidebar;
