import React, { useState, useMemo } from 'react';
import type { DeviceStatus, LinkMetric, DriftEvent, DiscoveryCandidate } from './hooks/useMonitorSnapshot';
import DeviceStatusSidebar from './DeviceStatusSidebar';

interface Props {
  devices: DeviceStatus[];
  links: LinkMetric[];
  drifts: DriftEvent[];
  candidates: DiscoveryCandidate[];
  onOpenEditor?: () => void;
}

const statusColor: Record<string, string> = { up: '#22c55e', degraded: '#f59e0b', down: '#ef4444' };

function linkColor(utilization: number): string {
  if (utilization > 0.8) return '#ef4444';
  if (utilization > 0.5) return '#f59e0b';
  return '#22c55e';
}

function linkWidth(bandwidthBps: number): number {
  if (bandwidthBps > 1_000_000_000) return 4;
  if (bandwidthBps > 100_000_000) return 3;
  if (bandwidthBps > 1_000_000) return 2;
  return 1;
}

function formatBw(bps: number): string {
  if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(1)}G`;
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(0)}M`;
  if (bps >= 1_000) return `${(bps / 1_000).toFixed(0)}K`;
  return `${bps}`;
}

const LiveTopologyTab: React.FC<Props> = ({ devices, links, drifts, candidates, onOpenEditor }) => {
  const [selectedDevice, setSelectedDevice] = useState<DeviceStatus | null>(null);

  // Simple grid layout for devices
  const positions = useMemo(() => {
    const cols = Math.max(Math.ceil(Math.sqrt(devices.length)), 1);
    const spacing = 120;
    const offsetX = 80;
    const offsetY = 60;
    return devices.map((d, i) => ({
      device: d,
      x: offsetX + (i % cols) * spacing,
      y: offsetY + Math.floor(i / cols) * spacing,
    }));
  }, [devices]);

  const posMap = useMemo(() => {
    const map: Record<string, { x: number; y: number }> = {};
    for (const p of positions) {
      map[p.device.device_id] = { x: p.x, y: p.y };
    }
    return map;
  }, [positions]);

  const svgWidth = Math.max(600, positions.length > 0 ? Math.max(...positions.map((p) => p.x)) + 120 : 600);
  const svgHeight = Math.max(400, positions.length > 0 ? Math.max(...positions.map((p) => p.y)) + 100 : 400);

  return (
    <div className="flex h-full">
      {/* Main canvas */}
      <div className="flex-1 overflow-auto p-4">
        <div className="flex justify-end mb-2">
          {onOpenEditor && (
            <button
              onClick={onOpenEditor}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
              style={{ background: 'rgba(224,159,62,0.12)', color: '#e09f3e', border: '1px solid rgba(224,159,62,0.2)' }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>edit</span>
              Open in Editor
            </button>
          )}
        </div>
        {devices.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            No devices being monitored. Add devices to the topology to see them here.
          </div>
        ) : (
          <svg width={svgWidth} height={svgHeight} className="mx-auto">
            {/* Links */}
            {links.map((link, i) => {
              const src = posMap[link.src_device_id];
              const dst = posMap[link.dst_device_id];
              if (!src || !dst) return null;
              const color = linkColor(link.utilization);
              const width = linkWidth(link.bandwidth_bps);
              return (
                <g key={`link-${i}`}>
                  {/* Invisible fat hit area for hover */}
                  <line
                    x1={src.x} y1={src.y} x2={dst.x} y2={dst.y}
                    stroke="transparent" strokeWidth="12"
                  >
                    <title>
                      {`${link.src_device_id} → ${link.dst_device_id}\n` +
                       `Bandwidth: ${formatBw(link.bandwidth_bps)}bps\n` +
                       `Latency: ${link.latency_ms.toFixed(1)}ms\n` +
                       `Utilization: ${(link.utilization * 100).toFixed(0)}%\n` +
                       `Error Rate: ${(link.error_rate * 100).toFixed(2)}%`}
                    </title>
                  </line>
                  <line
                    x1={src.x} y1={src.y} x2={dst.x} y2={dst.y}
                    stroke={color} strokeWidth={width} opacity={0.7}
                  />
                  <text
                    x={(src.x + dst.x) / 2}
                    y={(src.y + dst.y) / 2 - 6}
                    fill={color}
                    fontSize="10"
                    textAnchor="middle"
                    fontFamily="monospace"
                  >
                    {link.latency_ms.toFixed(1)}ms · {(link.utilization * 100).toFixed(0)}%
                  </text>
                </g>
              );
            })}

            {/* Device nodes */}
            {positions.map(({ device, x, y }) => (
              <g
                key={device.device_id}
                onClick={() => setSelectedDevice(device)}
                className="cursor-pointer"
              >
                <circle
                  cx={x} cy={y} r="24"
                  fill="#0a1a1e"
                  stroke={statusColor[device.status] || '#64748b'}
                  strokeWidth="3"
                />
                {device.status === 'down' && (
                  <circle cx={x} cy={y} r="24" fill="none" stroke="#ef4444" strokeWidth="3" opacity="0.4">
                    <animate attributeName="r" from="24" to="32" dur="1.5s" repeatCount="indefinite" />
                    <animate attributeName="opacity" from="0.4" to="0" dur="1.5s" repeatCount="indefinite" />
                  </circle>
                )}
                <text
                  x={x} y={y + 3}
                  fill="#e8e0d4"
                  fontSize="10"
                  textAnchor="middle"
                  fontFamily="monospace"
                >
                  {device.device_id.length > 8
                    ? device.device_id.substring(0, 8) + '...'
                    : device.device_id}
                </text>
                <text
                  x={x} y={y + 40}
                  fill={statusColor[device.status]}
                  fontSize="9"
                  textAnchor="middle"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  {device.status.toUpperCase()}
                </text>
                {device.status !== 'down' && (
                  <text
                    x={x} y={y + 50}
                    fill="#e09f3e"
                    fontSize="9"
                    textAnchor="middle"
                    fontFamily="monospace"
                  >
                    {device.latency_ms.toFixed(0)}ms
                  </text>
                )}
              </g>
            ))}
          </svg>
        )}

        {/* Summary bar */}
        <div className="flex items-center gap-6 px-4 py-2 mt-2 rounded-lg text-xs font-mono" style={{ backgroundColor: '#0a1a1e' }}>
          {drifts.length > 0 && (
            <span style={{ color: '#f59e0b' }}>
              {drifts.filter((d) => d.severity === 'critical').length} critical /
              {' '}{drifts.length} total drifts
            </span>
          )}
          {candidates.length > 0 && (
            <span style={{ color: '#e09f3e' }}>
              {candidates.length} discovered device{candidates.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Sidebar */}
      {selectedDevice && (
        <DeviceStatusSidebar
          device={selectedDevice}
          onClose={() => setSelectedDevice(null)}
        />
      )}
    </div>
  );
};

export default LiveTopologyTab;
