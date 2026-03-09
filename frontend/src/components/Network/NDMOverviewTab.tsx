import React, { useMemo, useState, useEffect } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { MonitoredDevice, DiscoveryConfig, DeviceProfileSummary, CollectorHealthStatus } from '../../types';

interface NDMOverviewTabProps {
  devices: MonitoredDevice[];
  configs: DiscoveryConfig[];
  profiles: DeviceProfileSummary[];
  health: CollectorHealthStatus | null;
  onSelectDevice: (id: string) => void;
}

const CHART_COLORS = ['#07b6d5', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16'];

const STATUS_COLOR: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#94a3b8',
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(7,182,213,0.04)', border: '1px solid rgba(7,182,213,0.12)',
  borderRadius: 10, padding: 20,
};

const CircularGauge = ({ value, label, color, max = 100 }: { value: number; label: string; color: string; max?: number }) => {
  const pct = Math.min(value / max, 1);
  const r = 36, cx = 44, cy = 44, circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - pct);
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={88} height={88}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth={6} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={6}
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform={`rotate(-90 ${cx} ${cy})`} />
        <text x={cx} y={cy - 4} textAnchor="middle" fill="#e2e8f0" fontSize={16} fontWeight={700}>
          {value.toFixed(0)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#64748b" fontSize={9}>{label}</text>
      </svg>
    </div>
  );
};

const NDMOverviewTab: React.FC<NDMOverviewTabProps> = ({ devices, configs, profiles, health, onSelectDevice }) => {
  const upCount = devices.filter(d => d.status === 'up').length;
  const downCount = devices.filter(d => d.status === 'down').length;
  const unreachableCount = devices.filter(d => d.status === 'unreachable').length;
  const newCount = devices.filter(d => d.status === 'new').length;

  // Golden signals: real CPU/mem from backend, latency/loss from ping data
  const [aggregateMetrics, setAggregateMetrics] = useState({ avg_cpu: 0, avg_mem: 0, avg_temp: 0, device_count: 0 });

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('/api/collector/devices/aggregate-metrics');
        if (res.ok) {
          setAggregateMetrics(await res.json());
        }
      } catch {
        // Silently fail — gauges show 0
      }
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 30000);
    return () => clearInterval(interval);
  }, []);

  const goldenSignals = useMemo(() => {
    const devicesWithPing = devices.filter(d => d.last_ping);
    const avgLatency = devicesWithPing.length > 0
      ? devicesWithPing.reduce((sum, d) => sum + (d.last_ping?.rtt_avg || 0), 0) / devicesWithPing.length
      : 0;
    const avgLoss = devicesWithPing.length > 0
      ? devicesWithPing.reduce((sum, d) => sum + (d.last_ping?.packet_loss_pct || 0), 0) / devicesWithPing.length
      : 0;
    return {
      avgCpu: aggregateMetrics.avg_cpu,
      avgMem: aggregateMetrics.avg_mem,
      avgLatency,
      avgLoss,
    };
  }, [devices, aggregateMetrics]);

  // Vendor distribution for donut chart
  const vendorData = useMemo(() => {
    const counts: Record<string, number> = {};
    devices.forEach(d => {
      const vendor = d.vendor || 'Unknown';
      counts[vendor] = (counts[vendor] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [devices]);

  // Profile distribution for bar chart
  const profileData = useMemo(() => {
    const counts: Record<string, number> = {};
    devices.forEach(d => {
      const profile = d.matched_profile || 'Unmatched';
      counts[profile] = (counts[profile] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [devices]);

  const summaryCards = [
    { label: 'Total Devices', value: devices.length, color: '#e2e8f0', icon: 'devices' },
    { label: 'Up', value: upCount, color: '#22c55e', icon: 'check_circle' },
    { label: 'Down', value: downCount, color: '#ef4444', icon: 'cancel' },
    { label: 'Unreachable', value: unreachableCount, color: '#f59e0b', icon: 'warning' },
    { label: 'Discovery Configs', value: configs.length, color: '#07b6d5', icon: 'radar' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Cards Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        {summaryCards.map(card => (
          <div key={card.label} style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 20, color: card.color }}>{card.icon}</span>
              <span style={{ fontSize: 12, color: '#64748b' }}>{card.label}</span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color: card.color }}>{card.value}</div>
          </div>
        ))}
      </div>

      {/* Device Health Grid */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>grid_view</span>
          Device Health Grid
        </h3>
        {devices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#64748b', fontSize: 13 }}>
            No devices to display. Add devices to see the health grid.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
            {devices.map(device => {
              const color = STATUS_COLOR[device.status] || '#94a3b8';
              return (
                <div
                  key={device.device_id}
                  onClick={() => onSelectDevice(device.device_id)}
                  title={`${device.hostname || device.management_ip} — ${device.status}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 10px', borderRadius: 6, cursor: 'pointer',
                    background: 'rgba(15,32,35,0.5)',
                    border: '1px solid rgba(148,163,184,0.06)',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={e => {
                    (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(7,182,213,0.3)';
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(148,163,184,0.06)';
                  }}
                >
                  <div style={{
                    width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0,
                    boxShadow: device.status === 'up' ? `0 0 6px ${color}` : device.status === 'down' ? `0 0 6px ${color}` : undefined,
                  }} />
                  <span style={{
                    fontSize: 11, color: '#94a3b8', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {device.hostname || device.management_ip}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Golden Signals Row */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>monitoring</span>
          Golden Signals (Fleet Averages)
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, justifyItems: 'center' }}>
          <CircularGauge
            value={goldenSignals.avgCpu}
            label="Avg CPU %"
            color={goldenSignals.avgCpu > 80 ? '#ef4444' : goldenSignals.avgCpu > 60 ? '#f59e0b' : '#22c55e'}
          />
          <CircularGauge
            value={goldenSignals.avgMem}
            label="Avg Mem %"
            color={goldenSignals.avgMem > 85 ? '#ef4444' : goldenSignals.avgMem > 70 ? '#f59e0b' : '#22c55e'}
          />
          <CircularGauge
            value={goldenSignals.avgLatency}
            label="Avg RTT ms"
            color={goldenSignals.avgLatency > 100 ? '#ef4444' : goldenSignals.avgLatency > 50 ? '#f59e0b' : '#07b6d5'}
            max={200}
          />
          <CircularGauge
            value={goldenSignals.avgLoss}
            label="Avg Loss %"
            color={goldenSignals.avgLoss > 5 ? '#ef4444' : goldenSignals.avgLoss > 1 ? '#f59e0b' : '#22c55e'}
          />
        </div>
      </div>

      {/* Charts Row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Vendor Distribution Donut */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>donut_small</span>
            Vendor Distribution
          </h3>
          {vendorData.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No device data</div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <ResponsiveContainer width="50%" height={180}>
                <PieChart>
                  <Pie
                    data={vendorData}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={70}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {vendorData.map((_entry, index) => (
                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#0f2023', border: '1px solid rgba(7,182,213,0.2)', borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: '#e2e8f0' }}
                    itemStyle={{ color: '#94a3b8' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                {vendorData.map((v, i) => (
                  <div key={v.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: '#94a3b8', flex: 1 }}>{v.name}</span>
                    <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>{v.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Profile Distribution Bar Chart */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>bar_chart</span>
            Profile Distribution
          </h3>
          {profileData.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No profile data</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={profileData} layout="vertical" margin={{ left: 0, right: 16, top: 0, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={100} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#0f2023', border: '1px solid rgba(7,182,213,0.2)', borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: '#e2e8f0' }}
                  cursor={{ fill: 'rgba(7,182,213,0.06)' }}
                />
                <Bar dataKey="count" fill="#07b6d5" radius={[0, 4, 4, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Collector Health */}
      {health && (
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>health_and_safety</span>
            Collector Health
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[
              { label: 'Status', value: health.status, color: health.status === 'healthy' ? '#22c55e' : '#f59e0b' },
              { label: 'Devices', value: String(health.device_count), color: '#e2e8f0' },
              { label: 'Configs', value: String(health.discovery_config_count), color: '#e2e8f0' },
              { label: 'Profiles', value: String(health.profile_count), color: '#e2e8f0' },
            ].map(item => (
              <div key={item.label} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.value}</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default NDMOverviewTab;
