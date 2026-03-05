import React, { useState, useEffect, useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { LinkMetric, TopTalker, ProtocolBreakdown } from './hooks/useMonitorSnapshot';
import { fetchTopTalkers, fetchProtocolBreakdown } from '../../services/api';

interface Props {
  links: LinkMetric[];
}

const PROTOCOL_NAMES: Record<string, string> = {
  '6': 'TCP', '17': 'UDP', '1': 'ICMP', '47': 'GRE', '50': 'ESP',
};

const PROTOCOL_COLORS = ['#07b6d5', '#22c55e', '#f59e0b', '#a855f7', '#ef4444', '#64748b'];

const TIME_RANGES = ['5m', '15m', '1h', '6h', '24h'] as const;

const formatBytes = (bytes: number) => {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`;
  return `${bytes} B`;
};

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

const TrafficFlowsTab: React.FC<Props> = ({ links }) => {
  const [timeRange, setTimeRange] = useState<string>('5m');
  const [topTalkers, setTopTalkers] = useState<TopTalker[]>([]);
  const [protocols, setProtocols] = useState<ProtocolBreakdown[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const [tt, pb] = await Promise.all([
          fetchTopTalkers(timeRange, 10),
          fetchProtocolBreakdown(timeRange),
        ]);
        setTopTalkers(tt.flows || []);
        setProtocols(pb.protocols || []);
      } catch {
        // API not available yet — use link data as fallback
      }
    };
    load();
  }, [timeRange]);

  const sorted = useMemo(() => {
    return [...links].sort((a, b) => b.bandwidth_bps - a.bandwidth_bps);
  }, [links]);

  const maxBandwidth = Math.max(...links.map((l) => l.bandwidth_bps), 1);

  const protocolChartData = protocols.map((p) => ({
    name: PROTOCOL_NAMES[p.protocol] || `Proto ${p.protocol}`,
    bytes: p.bytes,
  }));

  return (
    <div className="flex flex-col h-full">
      {/* Time range selector */}
      <div className="px-6 pt-4 pb-2 flex items-center gap-2">
        <span className="text-xs font-mono" style={{ color: '#64748b' }}>Time Range:</span>
        <div className="flex gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setTimeRange(r)}
              className="px-2.5 py-1 rounded text-xs font-mono transition-colors"
              style={{
                backgroundColor: timeRange === r ? 'rgba(7,182,213,0.15)' : 'transparent',
                color: timeRange === r ? '#07b6d5' : '#64748b',
                border: `1px solid ${timeRange === r ? '#07b6d5' : '#224349'}`,
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-6 py-2">
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Top Talkers */}
          <div>
            <h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
              Top Talkers
            </h3>
            {topTalkers.length > 0 ? (
              <div className="space-y-1">
                <div className="grid grid-cols-4 text-[10px] font-mono font-bold pb-1 border-b" style={{ color: '#64748b', borderColor: '#224349' }}>
                  <span>Source</span><span>Destination</span><span>Protocol</span><span className="text-right">Bytes</span>
                </div>
                {topTalkers.map((t, i) => (
                  <div key={i} className="grid grid-cols-4 text-xs font-mono py-1 border-b" style={{ borderColor: '#22434920' }}>
                    <span className="truncate" style={{ color: '#e2e8f0' }}>{t.src_ip}</span>
                    <span className="truncate" style={{ color: '#e2e8f0' }}>{t.dst_ip}</span>
                    <span style={{ color: '#07b6d5' }}>{PROTOCOL_NAMES[t.protocol] || t.protocol}</span>
                    <span className="text-right" style={{ color: '#22c55e' }}>{formatBytes(t.bytes)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs font-mono py-4 text-center" style={{ color: '#64748b' }}>
                No flow data yet. Configure devices to export NetFlow/sFlow.
              </div>
            )}
          </div>

          {/* Protocol Breakdown */}
          <div>
            <h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
              Protocol Breakdown
            </h3>
            {protocolChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={protocolChartData} layout="vertical">
                  <XAxis type="number" tickFormatter={formatBytes} tick={{ fill: '#64748b', fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" width={50} tick={{ fill: '#e2e8f0', fontSize: 11 }} />
                  <Tooltip
                    formatter={(value: number) => formatBytes(value)}
                    contentStyle={{ backgroundColor: '#0a1a1e', border: '1px solid #224349', borderRadius: '6px', fontSize: '11px' }}
                    labelStyle={{ color: '#e2e8f0' }}
                  />
                  <Bar dataKey="bytes" radius={[0, 4, 4, 0]}>
                    {protocolChartData.map((_, i) => (
                      <Cell key={i} fill={PROTOCOL_COLORS[i % PROTOCOL_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-xs font-mono py-4 text-center" style={{ color: '#64748b' }}>
                No protocol data available.
              </div>
            )}
          </div>
        </div>

        {/* Link bandwidth bars (existing) */}
        <div className="mt-6">
          <h3 className="text-sm font-mono font-bold mb-3" style={{ color: '#07b6d5' }}>
            Link Bandwidth
          </h3>
          {sorted.length === 0 ? (
            <div className="text-xs font-mono py-4 text-center" style={{ color: '#64748b' }}>
              No link metrics available.
            </div>
          ) : (
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
                        className="absolute inset-y-0 left-0 rounded"
                        style={{ width: `${barWidth}%`, backgroundColor: healthColor(link), opacity: 0.2 }}
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
                    <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: healthColor(link) }} />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Summary */}
      <div className="px-6 py-2 border-t text-xs font-mono" style={{ borderColor: '#224349', color: '#64748b' }}>
        {links.length} active links &middot;{' '}
        {links.filter((l) => l.error_rate > 0.05).length} with errors &middot;{' '}
        {links.filter((l) => l.utilization > 0.8).length} highly utilized
        {topTalkers.length > 0 && ` · ${topTalkers.length} top talkers`}
      </div>
    </div>
  );
};

export default TrafficFlowsTab;
