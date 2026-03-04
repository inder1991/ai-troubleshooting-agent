import React, { useMemo } from 'react';
import type { LinkMetric } from './hooks/useMonitorSnapshot';

interface Props {
  links: LinkMetric[];
}

const TrafficFlowsTab: React.FC<Props> = ({ links }) => {
  const sorted = useMemo(() => {
    return [...links].sort((a, b) => b.bandwidth_bps - a.bandwidth_bps);
  }, [links]);

  const maxBandwidth = Math.max(...links.map((l) => l.bandwidth_bps), 1);

  const formatBandwidth = (bps: number) => {
    if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(1)} Gbps`;
    if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`;
    if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} Kbps`;
    return `${bps} bps`;
  };

  const healthColor = (link: LinkMetric) => {
    if (link.error_rate > 0.05) return '#ef4444';
    if (link.utilization > 0.8 || link.latency_ms > 100) return '#f59e0b';
    return '#22c55e';
  };

  if (links.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        No link metrics available. Traffic data will appear once the monitor collects link statistics.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Flow visualization */}
      <div className="flex-1 overflow-auto px-6 py-4">
        <div className="space-y-2">
          {sorted.map((link, i) => {
            const barWidth = Math.max((link.bandwidth_bps / maxBandwidth) * 100, 5);
            return (
              <div key={`${link.src_device_id}-${link.dst_device_id}-${i}`} className="flex items-center gap-3">
                <div className="w-28 text-right text-xs font-mono truncate" style={{ color: '#e2e8f0' }}>
                  {link.src_device_id}
                </div>
                <div className="flex-1 relative h-6 rounded" style={{ backgroundColor: '#0a1a1e' }}>
                  <div
                    className="absolute inset-y-0 left-0 rounded flex items-center px-2"
                    style={{
                      width: `${barWidth}%`,
                      backgroundColor: healthColor(link),
                      opacity: 0.2,
                    }}
                  />
                  <div className="absolute inset-0 flex items-center justify-between px-2 text-[11px] font-mono">
                    <span style={{ color: '#07b6d5' }}>{formatBandwidth(link.bandwidth_bps)}</span>
                    <span style={{ color: '#64748b' }}>
                      {link.latency_ms.toFixed(1)}ms &middot; {(link.utilization * 100).toFixed(0)}% util
                    </span>
                  </div>
                </div>
                <div className="w-28 text-xs font-mono truncate" style={{ color: '#e2e8f0' }}>
                  {link.dst_device_id}
                </div>
                <span
                  className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: healthColor(link) }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary */}
      <div className="px-6 py-2 border-t text-xs font-mono" style={{ borderColor: '#224349', color: '#64748b' }}>
        {links.length} active links &middot;{' '}
        {links.filter((l) => l.error_rate > 0.05).length} with errors &middot;{' '}
        {links.filter((l) => l.utilization > 0.8).length} highly utilized
      </div>
    </div>
  );
};

export default TrafficFlowsTab;
