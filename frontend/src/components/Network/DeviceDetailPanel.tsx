import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import type { MonitoredDevice, InterfaceMetrics, SyslogEntry, TrapEvent, DeviceMetricsSnapshot, DeviceMetricsHistory } from '../../types';
import {
  fetchDeviceMetricsSnapshot,
  fetchDeviceMetricsHistory,
  fetchDeviceInterfaces,
  fetchDeviceSyslog,
  fetchDeviceTraps,
} from '../../services/api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------
interface DeviceDetailPanelProps {
  device: MonitoredDevice;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------
const panelStyle: React.CSSProperties = {
  position: 'fixed',
  right: 0,
  top: 0,
  bottom: 0,
  width: 520,
  background: '#0a1a1f',
  borderLeft: '1px solid rgba(7,182,213,0.2)',
  zIndex: 1000,
  overflowY: 'auto',
  padding: '20px 24px',
  boxShadow: '-4px 0 24px rgba(0,0,0,0.5)',
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.4)',
  zIndex: 999,
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(7,182,213,0.04)',
  border: '1px solid rgba(7,182,213,0.12)',
  borderRadius: 10,
  padding: 20,
};

const tabBtnBase: React.CSSProperties = {
  border: 'none',
  cursor: 'pointer',
  padding: '6px 14px',
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 600,
  transition: 'all .15s',
};

type TabKey = 'overview' | 'metrics' | 'interfaces' | 'syslog' | 'traps';

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'info' },
  { key: 'metrics', label: 'Metrics', icon: 'monitoring' },
  { key: 'interfaces', label: 'Interfaces', icon: 'settings_ethernet' },
  { key: 'syslog', label: 'Syslog', icon: 'article' },
  { key: 'traps', label: 'Traps', icon: 'notification_important' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const statusColors: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#07b6d5',
};

const severityColors: Record<string, string> = {
  emergency: '#ef4444',
  alert: '#ef4444',
  critical: '#ef4444',
  error: '#f97316',
  warning: '#eab308',
  notice: '#07b6d5',
  info: '#94a3b8',
  debug: '#64748b',
  // Trap severities
  major: '#ef4444',
  minor: '#f59e0b',
};

function formatSpeed(bps: number): string {
  if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(0)} Gbps`;
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(0)} Mbps`;
  if (bps >= 1_000) return `${(bps / 1_000).toFixed(0)} Kbps`;
  return `${bps} bps`;
}

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '--';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatOctets(octets: number): string {
  if (octets >= 1_000_000_000) return `${(octets / 1_000_000_000).toFixed(1)} GB`;
  if (octets >= 1_000_000) return `${(octets / 1_000_000).toFixed(1)} MB`;
  if (octets >= 1_000) return `${(octets / 1_000).toFixed(1)} KB`;
  return `${octets} B`;
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// CircularGauge (SVG)
// ---------------------------------------------------------------------------
const CircularGauge = ({
  value,
  label,
  color,
  unit = '%',
  max = 100,
}: {
  value: number | null;
  label: string;
  color: string;
  unit?: string;
  max?: number;
}) => {
  const pct = Math.min((value ?? 0) / max, 1);
  const r = 36;
  const cx = 44;
  const cy = 44;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - pct);
  return (
    <div style={{ textAlign: 'center' }}>
      <svg width={88} height={88}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(148,163,184,0.1)" strokeWidth={6} />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <text x={cx} y={cy - 4} textAnchor="middle" fill="#e2e8f0" fontSize={16} fontWeight={700}>
          {(value ?? 0).toFixed(0)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#64748b" fontSize={9}>
          {unit}
        </text>
      </svg>
      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{label}</div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Custom chart tooltip
// ---------------------------------------------------------------------------
const ChartTooltipContent = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: '#0f2023',
        border: '1px solid rgba(7,182,213,0.2)',
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 11,
      }}
    >
      <div style={{ color: '#94a3b8', marginBottom: 4 }}>{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ color: p.color, fontWeight: 600 }}>
          {p.name}: {p.value != null ? `${p.value.toFixed(1)}%` : '--'}
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const DeviceDetailPanel: React.FC<DeviceDetailPanelProps> = ({ device: deviceProp, onClose }) => {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // Data state — use the passed-in device directly
  const device = deviceProp;
  const deviceId = device.device_id;
  const [snapshot, setSnapshot] = useState<DeviceMetricsSnapshot | null>(null);
  const [history, setHistory] = useState<DeviceMetricsHistory | null>(null);
  const [interfaces, setInterfaces] = useState<InterfaceMetrics[]>([]);
  const [syslog, setSyslog] = useState<SyslogEntry[]>([]);
  const [traps, setTraps] = useState<TrapEvent[]>([]);
  const loading = false;
  const [metricsWindow, setMetricsWindow] = useState<string>('1h');

  // ---- Fetch tab-specific data ----
  useEffect(() => {
    if (activeTab === 'metrics') {
      fetchDeviceMetricsSnapshot(deviceId).then(setSnapshot).catch(console.error);
      fetchDeviceMetricsHistory(deviceId, metricsWindow).then(setHistory).catch(console.error);
    } else if (activeTab === 'interfaces') {
      fetchDeviceInterfaces(deviceId).then(setInterfaces).catch(console.error);
    } else if (activeTab === 'syslog') {
      fetchDeviceSyslog(deviceId).then(setSyslog).catch(console.error);
    } else if (activeTab === 'traps') {
      fetchDeviceTraps(deviceId).then(setTraps).catch(console.error);
    }
  }, [activeTab, deviceId, metricsWindow]);

  // ---- Close on Escape ----
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // ---- Build metrics chart data ----
  const chartData = React.useMemo(() => {
    if (!history) return [];
    return history.timestamps.map((ts, i) => ({
      time: ts,
      cpu: history.cpu_pct[i],
      mem: history.mem_pct[i],
    }));
  }, [history]);

  // =====================================================================
  // TAB RENDERERS
  // =====================================================================

  // ---- Overview ----
  const renderOverview = () => {
    if (!device) return null;

    const infoRows: [string, string | null | undefined][] = [
      ['Vendor', device.vendor],
      ['Model', device.model],
      ['OS Family', device.os_family],
      ['sysObjectID', device.sys_object_id],
      ['Matched Profile', device.matched_profile],
      ['Uptime', formatUptime(device.last_collected ? (Date.now() / 1000 - device.last_collected) : null)],
      ['Last Collected', device.last_collected ? formatTimestamp(device.last_collected) : null],
    ];

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Header card */}
        <div style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span
              className="material-symbols-outlined"
              style={{ fontSize: 28, color: '#07b6d5' }}
            >
              dns
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>
                {device.hostname}
              </div>
              <div style={{ fontSize: 13, color: '#64748b' }}>{device.management_ip}</div>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 5,
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '3px 10px',
                borderRadius: 999,
                background: `${statusColors[device.status] ?? '#64748b'}20`,
                color: statusColors[device.status] ?? '#64748b',
                border: `1px solid ${statusColors[device.status] ?? '#64748b'}40`,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: statusColors[device.status] ?? '#64748b',
                }}
              />
              {device.status}
            </span>
          </div>
        </div>

        {/* Info grid */}
        <div style={cardStyle}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#07b6d5',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 12,
            }}
          >
            Device Info
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 20px' }}>
            {infoRows.map(([label, val]) => (
              <div key={label}>
                <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 2 }}>
                  {label}
                </div>
                <div style={{ fontSize: 13, color: '#e2e8f0', wordBreak: 'break-all' }}>
                  {val ?? '--'}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Tags */}
        {device.tags.length > 0 && (
          <div style={cardStyle}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: '#07b6d5',
                textTransform: 'uppercase',
                letterSpacing: 1,
                marginBottom: 10,
              }}
            >
              Tags
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {device.tags.map((tag) => (
                <span
                  key={tag}
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '3px 10px',
                    borderRadius: 999,
                    background: 'rgba(7,182,213,0.1)',
                    color: '#07b6d5',
                    border: '1px solid rgba(7,182,213,0.2)',
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Protocols */}
        {device.protocols.length > 0 && (
          <div style={cardStyle}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: '#07b6d5',
                textTransform: 'uppercase',
                letterSpacing: 1,
                marginBottom: 10,
              }}
            >
              Protocols
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {device.protocols.map((p) => (
                <div
                  key={p.protocol}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 10px',
                    borderRadius: 6,
                    background: 'rgba(148,163,184,0.04)',
                    border: '1px solid rgba(148,163,184,0.08)',
                  }}
                >
                  <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 600, textTransform: 'uppercase' }}>
                    {p.protocol}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 10, color: '#64748b' }}>
                      Priority {p.priority}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: 999,
                        background: p.enabled ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.1)',
                        color: p.enabled ? '#22c55e' : '#64748b',
                      }}
                    >
                      {p.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Ping */}
        {device.last_ping && (
          <div style={cardStyle}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: '#07b6d5',
                textTransform: 'uppercase',
                letterSpacing: 1,
                marginBottom: 10,
              }}
            >
              Last Ping
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>
                  {device.last_ping.rtt_avg.toFixed(1)}
                </div>
                <div style={{ fontSize: 10, color: '#64748b' }}>RTT avg (ms)</div>
              </div>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>
                  {device.last_ping.rtt_max.toFixed(1)}
                </div>
                <div style={{ fontSize: 10, color: '#64748b' }}>RTT max (ms)</div>
              </div>
              <div>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    color: device.last_ping.packet_loss_pct > 0 ? '#ef4444' : '#22c55e',
                  }}
                >
                  {device.last_ping.packet_loss_pct.toFixed(1)}%
                </div>
                <div style={{ fontSize: 10, color: '#64748b' }}>Packet loss</div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ---- Metrics ----
  const renderMetrics = () => {
    const windowOptions = ['5m', '1h', '24h'];

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Gauges */}
        <div style={cardStyle}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#07b6d5',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 14,
            }}
          >
            Current
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-around' }}>
            <CircularGauge value={snapshot?.cpu_pct ?? null} label="CPU" color="#07b6d5" />
            <CircularGauge value={snapshot?.mem_pct ?? null} label="Memory" color="#22c55e" />
            <CircularGauge
              value={snapshot?.temperature ?? null}
              label="Temp"
              color="#f59e0b"
              unit="C"
              max={100}
            />
          </div>
        </div>

        {/* Time range toggle */}
        <div style={{ display: 'flex', gap: 6 }}>
          {windowOptions.map((w) => (
            <button
              key={w}
              onClick={() => setMetricsWindow(w)}
              style={{
                ...tabBtnBase,
                background: metricsWindow === w ? 'rgba(7,182,213,0.15)' : 'rgba(148,163,184,0.06)',
                color: metricsWindow === w ? '#07b6d5' : '#94a3b8',
                border: metricsWindow === w ? '1px solid rgba(7,182,213,0.3)' : '1px solid rgba(148,163,184,0.1)',
              }}
            >
              {w}
            </button>
          ))}
        </div>

        {/* CPU chart */}
        <div style={cardStyle}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#07b6d5',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 12,
            }}
          >
            CPU Usage
          </div>
          <div style={{ width: '100%', height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#64748b', fontSize: 9 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: '#64748b', fontSize: 9 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                  tickLine={false}
                  width={30}
                />
                <Tooltip content={<ChartTooltipContent />} />
                <Line
                  type="monotone"
                  dataKey="cpu"
                  name="CPU"
                  stroke="#07b6d5"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Memory chart */}
        <div style={cardStyle}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#22c55e',
              textTransform: 'uppercase',
              letterSpacing: 1,
              marginBottom: 12,
            }}
          >
            Memory Usage
          </div>
          <div style={{ width: '100%', height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis
                  dataKey="time"
                  tick={{ fill: '#64748b', fontSize: 9 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: '#64748b', fontSize: 9 }}
                  axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
                  tickLine={false}
                  width={30}
                />
                <Tooltip content={<ChartTooltipContent />} />
                <Line
                  type="monotone"
                  dataKey="mem"
                  name="Memory"
                  stroke="#22c55e"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    );
  };

  // ---- Interfaces ----
  const renderInterfaces = () => {
    const thStyle: React.CSSProperties = {
      textAlign: 'left',
      padding: '8px 8px',
      fontSize: 10,
      fontWeight: 700,
      color: '#64748b',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      borderBottom: '1px solid rgba(148,163,184,0.1)',
      whiteSpace: 'nowrap',
    };
    const tdStyle: React.CSSProperties = {
      padding: '7px 8px',
      fontSize: 12,
      color: '#e2e8f0',
      borderBottom: '1px solid rgba(148,163,184,0.06)',
      whiteSpace: 'nowrap',
    };

    const getRowBg = (util: number): string => {
      if (util >= 95) return 'rgba(239,68,68,0.08)';
      if (util >= 85) return 'rgba(245,158,11,0.08)';
      return 'transparent';
    };

    return (
      <div style={cardStyle}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: '#07b6d5',
            textTransform: 'uppercase',
            letterSpacing: 1,
            marginBottom: 12,
          }}
        >
          Interfaces ({interfaces.length})
        </div>
        {interfaces.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13, textAlign: 'center', padding: 20 }}>
            No interface data available
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Speed</th>
                  <th style={thStyle}>In</th>
                  <th style={thStyle}>Out</th>
                  <th style={thStyle}>Errors</th>
                  <th style={thStyle}>Util %</th>
                </tr>
              </thead>
              <tbody>
                {interfaces.map((iface) => {
                  const errTotal = iface.in_errors + iface.out_errors + iface.in_discards + iface.out_discards;
                  return (
                    <tr key={iface.name} style={{ background: getRowBg(iface.utilization_pct) }}>
                      <td style={{ ...tdStyle, fontWeight: 600, color: '#07b6d5' }}>{iface.name}</td>
                      <td style={tdStyle}>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            textTransform: 'uppercase',
                            padding: '2px 8px',
                            borderRadius: 999,
                            background: iface.status === 'up' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                            color: iface.status === 'up' ? '#22c55e' : '#ef4444',
                          }}
                        >
                          {iface.status}
                        </span>
                      </td>
                      <td style={tdStyle}>{formatSpeed(iface.speed)}</td>
                      <td style={tdStyle}>{formatOctets(iface.in_octets)}</td>
                      <td style={tdStyle}>{formatOctets(iface.out_octets)}</td>
                      <td
                        style={{
                          ...tdStyle,
                          color: errTotal > 0 ? '#f59e0b' : '#64748b',
                          fontWeight: errTotal > 0 ? 700 : 400,
                        }}
                      >
                        {errTotal}
                      </td>
                      <td
                        style={{
                          ...tdStyle,
                          fontWeight: 700,
                          color:
                            iface.utilization_pct >= 95
                              ? '#ef4444'
                              : iface.utilization_pct >= 85
                                ? '#f59e0b'
                                : iface.utilization_pct >= 50
                                  ? '#eab308'
                                  : '#22c55e',
                        }}
                      >
                        {iface.utilization_pct.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  // ---- Syslog ----
  const renderSyslog = () => {
    const thStyle: React.CSSProperties = {
      textAlign: 'left',
      padding: '8px 8px',
      fontSize: 10,
      fontWeight: 700,
      color: '#64748b',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      borderBottom: '1px solid rgba(148,163,184,0.1)',
      whiteSpace: 'nowrap',
    };
    const tdStyle: React.CSSProperties = {
      padding: '7px 8px',
      fontSize: 12,
      color: '#e2e8f0',
      borderBottom: '1px solid rgba(148,163,184,0.06)',
    };

    return (
      <div style={cardStyle}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: '#07b6d5',
            textTransform: 'uppercase',
            letterSpacing: 1,
            marginBottom: 12,
          }}
        >
          Syslog Entries ({syslog.length})
        </div>
        {syslog.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13, textAlign: 'center', padding: 20 }}>
            No syslog entries for this device
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Time</th>
                  <th style={thStyle}>Severity</th>
                  <th style={thStyle}>App</th>
                  <th style={thStyle}>Message</th>
                </tr>
              </thead>
              <tbody>
                {syslog.map((entry) => (
                  <tr key={entry.event_id}>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', fontSize: 11, color: '#94a3b8' }}>
                      {formatTimestamp(entry.timestamp)}
                    </td>
                    <td style={tdStyle}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          padding: '2px 8px',
                          borderRadius: 999,
                          background: `${severityColors[entry.severity] ?? '#64748b'}20`,
                          color: severityColors[entry.severity] ?? '#64748b',
                        }}
                      >
                        {entry.severity}
                      </span>
                    </td>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', fontWeight: 600, color: '#94a3b8' }}>
                      {entry.app_name || '--'}
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        maxWidth: 220,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={entry.message}
                    >
                      {entry.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  // ---- Traps ----
  const renderTraps = () => {
    const thStyle: React.CSSProperties = {
      textAlign: 'left',
      padding: '8px 8px',
      fontSize: 10,
      fontWeight: 700,
      color: '#64748b',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      borderBottom: '1px solid rgba(148,163,184,0.1)',
      whiteSpace: 'nowrap',
    };
    const tdStyle: React.CSSProperties = {
      padding: '7px 8px',
      fontSize: 12,
      color: '#e2e8f0',
      borderBottom: '1px solid rgba(148,163,184,0.06)',
    };

    return (
      <div style={cardStyle}>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: '#07b6d5',
            textTransform: 'uppercase',
            letterSpacing: 1,
            marginBottom: 12,
          }}
        >
          Trap Events ({traps.length})
        </div>
        {traps.length === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13, textAlign: 'center', padding: 20 }}>
            No trap events for this device
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Time</th>
                  <th style={thStyle}>Severity</th>
                  <th style={thStyle}>OID</th>
                  <th style={thStyle}>Value</th>
                </tr>
              </thead>
              <tbody>
                {traps.map((trap) => (
                  <tr key={trap.event_id}>
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', fontSize: 11, color: '#94a3b8' }}>
                      {formatTimestamp(trap.timestamp)}
                    </td>
                    <td style={tdStyle}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          padding: '2px 8px',
                          borderRadius: 999,
                          background: `${severityColors[trap.severity] ?? '#64748b'}20`,
                          color: severityColors[trap.severity] ?? '#64748b',
                        }}
                      >
                        {trap.severity}
                      </span>
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        fontFamily: 'monospace',
                        fontSize: 11,
                        maxWidth: 180,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={trap.oid}
                    >
                      {trap.oid}
                    </td>
                    <td
                      style={{
                        ...tdStyle,
                        maxWidth: 140,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={trap.value}
                    >
                      {trap.value}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  // =====================================================================
  // TAB CONTENT DISPATCHER
  // =====================================================================
  const tabContent: Record<TabKey, () => React.ReactNode> = {
    overview: renderOverview,
    metrics: renderMetrics,
    interfaces: renderInterfaces,
    syslog: renderSyslog,
    traps: renderTraps,
  };

  // =====================================================================
  // RENDER
  // =====================================================================
  return (
    <>
      {/* Overlay */}
      <div style={overlayStyle} onClick={onClose} />

      {/* Panel */}
      <div style={panelStyle}>
        {/* Close button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            background: 'rgba(148,163,184,0.08)',
            border: '1px solid rgba(148,163,184,0.15)',
            borderRadius: 8,
            cursor: 'pointer',
            padding: '4px 6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#94a3b8',
            transition: 'all .15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = '#e2e8f0';
            e.currentTarget.style.background = 'rgba(148,163,184,0.15)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = '#94a3b8';
            e.currentTarget.style.background = 'rgba(148,163,184,0.08)';
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
            close
          </span>
        </button>

        {/* Header */}
        <div style={{ marginBottom: 18, paddingRight: 36 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>
            {loading ? 'Loading...' : device?.hostname ?? deviceId}
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
            {device?.management_ip ?? ''}
          </div>
        </div>

        {/* Tab bar */}
        <div
          style={{
            display: 'flex',
            gap: 4,
            marginBottom: 18,
            borderBottom: '1px solid rgba(148,163,184,0.1)',
            paddingBottom: 10,
          }}
        >
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                ...tabBtnBase,
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                background:
                  activeTab === tab.key ? 'rgba(7,182,213,0.12)' : 'transparent',
                color: activeTab === tab.key ? '#07b6d5' : '#94a3b8',
                border:
                  activeTab === tab.key
                    ? '1px solid rgba(7,182,213,0.25)'
                    : '1px solid transparent',
              }}
              onMouseEnter={(e) => {
                if (activeTab !== tab.key) {
                  e.currentTarget.style.background = 'rgba(148,163,184,0.06)';
                }
              }}
              onMouseLeave={(e) => {
                if (activeTab !== tab.key) {
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                {tab.icon}
              </span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div>{tabContent[activeTab]()}</div>
      </div>
    </>
  );
};

export default DeviceDetailPanel;
