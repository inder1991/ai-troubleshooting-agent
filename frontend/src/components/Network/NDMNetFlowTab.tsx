import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import {
  fetchTopTalkers, fetchFlowConversations, fetchFlowApplications,
  fetchFlowASN, fetchFlowVolumeTimeline, fetchProtocolBreakdown,
} from '../../services/api';
import type { FlowConversation, FlowApplication, FlowASN, FlowVolumePoint } from '../../types';

const CHART_COLORS = ['#07b6d5', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#84cc16'];

const TIME_RANGES = [
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '6h', value: '6h' },
  { label: '24h', value: '24h' },
];

const cardStyle: React.CSSProperties = {
  background: 'rgba(7,182,213,0.04)', border: '1px solid rgba(7,182,213,0.12)',
  borderRadius: 10, padding: 20,
};

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
};

interface TopTalker {
  ip: string;
  bytes: number;
  packets: number;
  flows: number;
}

interface ProtocolEntry {
  protocol: string;
  bytes: number;
  packets: number;
  percentage: number;
}

interface DrillFilter {
  field: string;
  value: string;
}

const NDMNetFlowTab: React.FC = () => {
  const [timeRange, setTimeRange] = useState('1h');
  const [topTalkers, setTopTalkers] = useState<TopTalker[]>([]);
  const [conversations, setConversations] = useState<FlowConversation[]>([]);
  const [applications, setApplications] = useState<FlowApplication[]>([]);
  const [asnData, setAsnData] = useState<FlowASN[]>([]);
  const [volumeTimeline, setVolumeTimeline] = useState<FlowVolumePoint[]>([]);
  const [protocols, setProtocols] = useState<ProtocolEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [drillFilter, setDrillFilter] = useState<DrillFilter | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [talkersRes, convsRes, appsRes, asnRes, volRes, protoRes] = await Promise.all([
        fetchTopTalkers(timeRange, 10).catch(() => ({ talkers: [] })),
        fetchFlowConversations(timeRange, 20).catch(() => ({ conversations: [] })),
        fetchFlowApplications(timeRange, 10).catch(() => ({ applications: [] })),
        fetchFlowASN(timeRange, 10).catch(() => ({ asn_data: [] })),
        fetchFlowVolumeTimeline(timeRange, timeRange === '5m' ? '10s' : timeRange === '15m' ? '30s' : '1m').catch(() => ({ timeline: [] })),
        fetchProtocolBreakdown(timeRange).catch(() => ({ protocols: [] })),
      ]);

      setTopTalkers(talkersRes.talkers || []);
      setConversations(convsRes.conversations || []);
      setApplications(appsRes.applications || []);
      setAsnData(asnRes.asn_data || []);
      setVolumeTimeline(volRes.timeline || []);
      setProtocols(protoRes.protocols || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load NetFlow data');
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => { loadData(); }, [loadData]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Filter conversations based on drill-through
  const filteredConversations = useMemo(() => {
    if (!drillFilter) return conversations;
    return conversations.filter(conv => {
      switch (drillFilter.field) {
        case 'src_ip':
          return conv.src_ip === drillFilter.value;
        case 'dst_ip':
          return conv.dst_ip === drillFilter.value;
        case 'ip':
          return conv.src_ip === drillFilter.value || conv.dst_ip === drillFilter.value;
        default:
          return true;
      }
    });
  }, [conversations, drillFilter]);

  const tooltipStyle = {
    contentStyle: { background: '#0f2023', border: '1px solid rgba(7,182,213,0.2)', borderRadius: 6, fontSize: 12 } as React.CSSProperties,
    labelStyle: { color: '#e2e8f0' } as React.CSSProperties,
    itemStyle: { color: '#94a3b8' } as React.CSSProperties,
  };

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>progress_activity</span>
        Loading NetFlow data...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Time Range Selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {TIME_RANGES.map(tr => (
            <button
              key={tr.value}
              onClick={() => setTimeRange(tr.value)}
              style={{
                padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                border: timeRange === tr.value ? '1px solid #07b6d5' : '1px solid rgba(148,163,184,0.15)',
                background: timeRange === tr.value ? 'rgba(7,182,213,0.15)' : 'transparent',
                color: timeRange === tr.value ? '#07b6d5' : '#94a3b8',
                cursor: 'pointer',
              }}
            >
              {tr.label}
            </button>
          ))}
        </div>
        <button
          onClick={loadData}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '6px 12px', borderRadius: 6, fontSize: 12,
            border: '1px solid rgba(7,182,213,0.2)', background: 'transparent',
            color: '#07b6d5', cursor: 'pointer',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
          Refresh
        </button>
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* Grid: Top Talkers + Applications */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Top Talkers Bar Chart */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>leaderboard</span>
            Top Talkers
            <span style={{ fontSize: 10, color: '#64748b', fontWeight: 400, marginLeft: 4 }}>(click bar to filter)</span>
          </h3>
          {topTalkers.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No flow data available</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={topTalkers.slice(0, 10)} layout="vertical" margin={{ left: 10, right: 16, top: 0, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatBytes(v)} />
                <YAxis type="category" dataKey="ip" width={110} tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'monospace' }} axisLine={false} tickLine={false} />
                <Tooltip {...tooltipStyle} formatter={(value: number) => formatBytes(value)} />
                <Bar
                  dataKey="bytes"
                  fill="#07b6d5"
                  radius={[0, 4, 4, 0]}
                  barSize={14}
                  cursor="pointer"
                  onClick={(_data: unknown) => {
                    const ip = (_data as Record<string, unknown>)?.ip as string;
                    if (ip) {
                      setDrillFilter(prev =>
                        prev?.field === 'ip' && prev?.value === ip
                          ? null
                          : { field: 'ip', value: ip }
                      );
                    }
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Applications Donut */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>apps</span>
            Applications
          </h3>
          {applications.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No application data</div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <ResponsiveContainer width="50%" height={200}>
                <PieChart>
                  <Pie data={applications} cx="50%" cy="50%" innerRadius={35} outerRadius={65} paddingAngle={2} dataKey="bytes">
                    {applications.map((_e, i) => (
                      <Cell key={`cell-${i}`} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip {...tooltipStyle} formatter={(value: number) => formatBytes(value)} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                {applications.slice(0, 8).map((app, i) => (
                  <div key={app.app_name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: CHART_COLORS[i % CHART_COLORS.length], flexShrink: 0 }} />
                    <span style={{ fontSize: 11, color: '#94a3b8', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{app.app_name}</span>
                    <span style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 600 }}>{app.percentage.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Flow Volume Timeline */}
      <div style={cardStyle}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>timeline</span>
          Flow Volume Timeline
        </h3>
        {volumeTimeline.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 32, color: '#64748b', fontSize: 13 }}>No timeline data</div>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={volumeTimeline} margin={{ left: 10, right: 16, top: 8, bottom: 0 }}>
              <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={(v: string) => {
                  try { return new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return v; }
                }}
              />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatBytes(v)} />
              <Tooltip {...tooltipStyle} formatter={(value: number) => formatBytes(value)}
                labelFormatter={(label: string) => { try { return new Date(label).toLocaleString(); } catch { return label; } }}
              />
              <Line type="monotone" dataKey="bytes" stroke="#07b6d5" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="packets" stroke="#22c55e" strokeWidth={1} dot={false} opacity={0.5} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Bottom Grid: Conversations + ASN + Protocol */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        {/* Conversations Table */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>swap_horiz</span>
            Conversations
          </h3>

          {/* Drill-through filter chip */}
          {drillFilter && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 500,
              background: 'rgba(7,182,213,0.12)', color: '#07b6d5',
              border: '1px solid rgba(7,182,213,0.25)',
              marginBottom: 8,
            }}>
              <span className="material-symbols-outlined" style={{ fontSize: 13 }}>filter_alt</span>
              Filtered by: {drillFilter.field} = {drillFilter.value}
              <button
                onClick={() => setDrillFilter(null)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: '#07b6d5', padding: 0, display: 'flex', alignItems: 'center',
                  marginLeft: 2,
                }}
                title="Clear filter"
              >
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
              </button>
            </div>
          )}

          {filteredConversations.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#64748b', fontSize: 12 }}>
              {drillFilter ? 'No conversations match this filter' : 'No conversations'}
            </div>
          ) : (
            <div style={{ maxHeight: 260, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.12)' }}>
                    {['Source', 'Destination', 'Bytes', 'Flows'].map(h => (
                      <th key={h} style={{ padding: '4px 6px', textAlign: 'left', fontSize: 10, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredConversations.slice(0, 15).map((conv, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(148,163,184,0.05)' }}>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{conv.src_ip}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>{conv.dst_ip}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#e2e8f0' }}>{formatBytes(conv.bytes)}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#64748b' }}>{conv.flows}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ASN/Geo Table */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>public</span>
            ASN / Geo
          </h3>
          {asnData.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#64748b', fontSize: 12 }}>No ASN data</div>
          ) : (
            <div style={{ maxHeight: 260, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.12)' }}>
                    {['ASN', 'Bytes', 'Packets', 'Flows'].map(h => (
                      <th key={h} style={{ padding: '4px 6px', textAlign: 'left', fontSize: 10, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {asnData.slice(0, 15).map((asn, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(148,163,184,0.05)' }}>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#07b6d5', fontFamily: 'monospace' }}>AS{asn.asn}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#e2e8f0' }}>{formatBytes(asn.bytes)}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#94a3b8' }}>{asn.packets.toLocaleString()}</td>
                      <td style={{ padding: '4px 6px', fontSize: 11, color: '#64748b' }}>{asn.flows}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Protocol Breakdown */}
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>cable</span>
            Protocol Breakdown
          </h3>
          {protocols.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: '#64748b', fontSize: 12 }}>No protocol data</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {protocols.slice(0, 8).map((proto, i) => (
                <div key={proto.protocol}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 500 }}>{proto.protocol}</span>
                    <span style={{ fontSize: 11, color: '#64748b' }}>{proto.percentage.toFixed(1)}% ({formatBytes(proto.bytes)})</span>
                  </div>
                  <div style={{ width: '100%', height: 6, borderRadius: 3, background: 'rgba(148,163,184,0.1)', overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.min(proto.percentage, 100)}%`, height: '100%', borderRadius: 3,
                      background: CHART_COLORS[i % CHART_COLORS.length],
                    }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default NDMNetFlowTab;
