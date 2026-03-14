import React, { useMemo, useState, useEffect, useRef } from 'react';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { MonitoredDevice, DiscoveryConfig, DeviceProfileSummary, CollectorHealthStatus } from '../../types';
import DiscoveryConfigForm from './DiscoveryConfigForm';
import { deleteDiscoveryConfig, triggerDiscoveryScan } from '../../services/api';

interface NDMOverviewTabProps {
  devices: MonitoredDevice[];
  configs: DiscoveryConfig[];
  profiles: DeviceProfileSummary[];
  health: CollectorHealthStatus | null;
  onSelectDevice: (id: string) => void;
  onReload: () => void;
}

const CHART_COLORS = ['#e09f3e', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16'];

const STATUS_COLOR: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#8a7e6b',
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)',
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
        <text x={cx} y={cy - 4} textAnchor="middle" fill="#e8e0d4" fontSize={16} fontWeight={700}>
          {value.toFixed(0)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#64748b" fontSize={9}>{label}</text>
      </svg>
    </div>
  );
};

const NDMOverviewTab: React.FC<NDMOverviewTabProps> = ({ devices, configs, profiles, health, onSelectDevice, onReload }) => {
  const [showAddConfig, setShowAddConfig] = useState(false);
  const discoverySectionRef = useRef<HTMLDivElement>(null);

  const timeAgo = (ts: number | null) => {
    if (!ts) return 'Never';
    const sec = Math.floor((Date.now() / 1000) - ts);
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    return `${Math.floor(sec / 3600)}h ago`;
  };

  const handleDeleteConfig = async (configId: string) => {
    try {
      await deleteDiscoveryConfig(configId);
      onReload();
    } catch { /* toast could go here */ }
  };

  const handleScanConfig = async (configId: string) => {
    try {
      await triggerDiscoveryScan(configId);
      onReload();
    } catch { /* toast could go here */ }
  };
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
    { label: 'Total Devices', value: devices.length, color: '#e8e0d4', icon: 'devices' },
    { label: 'Up', value: upCount, color: '#22c55e', icon: 'check_circle' },
    { label: 'Down', value: downCount, color: '#ef4444', icon: 'cancel' },
    { label: 'Unreachable', value: unreachableCount, color: '#f59e0b', icon: 'warning' },
    { label: 'Discovery Configs', value: configs.length, color: '#e09f3e', icon: 'radar' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Cards Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        {summaryCards.map(card => {
          const isDiscoveryCard = card.label === 'Discovery Configs';
          return (
            <div
              key={card.label}
              style={{ ...cardStyle, cursor: isDiscoveryCard ? 'pointer' : undefined }}
              onClick={isDiscoveryCard ? () => discoverySectionRef.current?.scrollIntoView({ behavior: 'smooth' }) : undefined}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 20, color: card.color }}>{card.icon}</span>
                <span style={{ fontSize: 12, color: '#64748b' }}>{card.label}</span>
              </div>
              <div style={{ fontSize: 28, fontWeight: 700, color: card.color }}>{card.value}</div>
            </div>
          );
        })}
      </div>

      {/* Discovery Networks Section */}
      <div ref={discoverySectionRef} style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>radar</span>
            Discovery Networks
          </h3>
          <button
            onClick={() => setShowAddConfig(v => !v)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600,
              border: 'none', cursor: 'pointer',
              background: showAddConfig ? 'rgba(148,163,184,0.1)' : '#e09f3e',
              color: showAddConfig ? '#8a7e6b' : '#1a1814',
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>{showAddConfig ? 'close' : 'add'}</span>
            {showAddConfig ? 'Cancel' : 'Add Network'}
          </button>
        </div>

        {showAddConfig && (
          <div style={{
            background: 'rgba(224,159,62,0.03)', border: '1px solid rgba(224,159,62,0.1)',
            borderRadius: 8, padding: 16, marginBottom: 12,
          }}>
            <DiscoveryConfigForm
              onSuccess={() => { setShowAddConfig(false); onReload(); }}
              onCancel={() => setShowAddConfig(false)}
            />
          </div>
        )}

        {configs.length === 0 && !showAddConfig ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#64748b', fontSize: 13 }}>
            No discovery networks configured — add one to automatically find SNMP devices on your network.
          </div>
        ) : configs.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.1)' }}>
                  {['CIDR Range', 'Version', 'Found', 'Last Scan', ''].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: '#64748b', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {configs.map(cfg => (
                  <tr key={cfg.config_id} style={{ borderBottom: '1px solid rgba(148,163,184,0.06)' }}>
                    <td style={{ padding: '8px 10px', color: '#e8e0d4', fontFamily: 'monospace' }}>{cfg.cidr}</td>
                    <td style={{ padding: '8px 10px', color: '#8a7e6b' }}>v{cfg.snmp_version}</td>
                    <td style={{ padding: '8px 10px', color: '#e8e0d4', fontWeight: 600 }}>{cfg.devices_found}</td>
                    <td style={{ padding: '8px 10px', color: '#8a7e6b' }}>{timeAgo(cfg.last_scan)}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right', display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => handleScanConfig(cfg.config_id)}
                        title="Scan Now"
                        style={{
                          background: 'none', border: '1px solid rgba(224,159,62,0.2)', borderRadius: 4,
                          color: '#e09f3e', cursor: 'pointer', padding: '3px 6px', display: 'flex', alignItems: 'center',
                        }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
                      </button>
                      <button
                        onClick={() => handleDeleteConfig(cfg.config_id)}
                        title="Delete"
                        style={{
                          background: 'none', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 4,
                          color: '#ef4444', cursor: 'pointer', padding: '3px 6px', display: 'flex', alignItems: 'center',
                        }}
                      >
                        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Device Health Grid */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>grid_view</span>
          Device Health Grid
        </h3>
        {devices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#64748b', fontSize: 13 }}>
            No devices to display. Add devices to see the health grid.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
            {devices.map(device => {
              const color = STATUS_COLOR[device.status] || '#8a7e6b';
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
                    (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(224,159,62,0.3)';
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
                    fontSize: 11, color: '#8a7e6b', overflow: 'hidden',
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
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 16px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>monitoring</span>
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
            color={goldenSignals.avgLatency > 100 ? '#ef4444' : goldenSignals.avgLatency > 50 ? '#f59e0b' : '#e09f3e'}
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
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>donut_small</span>
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
                    contentStyle={{ background: '#1a1814', border: '1px solid rgba(224,159,62,0.2)', borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: '#e8e0d4' }}
                    itemStyle={{ color: '#8a7e6b' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                {vendorData.map((v, i) => (
                  <div key={v.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: '#8a7e6b', flex: 1 }}>{v.name}</span>
                    <span style={{ fontSize: 12, color: '#e8e0d4', fontWeight: 600 }}>{v.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Profile Distribution Bar Chart */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>bar_chart</span>
            Profile Distribution
          </h3>
          {profileData.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No profile data</div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={profileData} layout="vertical" margin={{ left: 0, right: 16, top: 0, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={100} tick={{ fill: '#8a7e6b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: '#1a1814', border: '1px solid rgba(224,159,62,0.2)', borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: '#e8e0d4' }}
                  cursor={{ fill: 'rgba(224,159,62,0.06)' }}
                />
                <Bar dataKey="count" fill="#e09f3e" radius={[0, 4, 4, 0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Collector Health */}
      {health && (
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>health_and_safety</span>
            Collector Health
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
            {[
              { label: 'Status', value: health.status, color: health.status === 'healthy' ? '#22c55e' : '#f59e0b' },
              { label: 'Devices', value: String(health.device_count), color: '#e8e0d4' },
              { label: 'Configs', value: String(health.discovery_config_count), color: '#e8e0d4' },
              { label: 'Profiles', value: String(health.profile_count), color: '#e8e0d4' },
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
