import React, { useState, useEffect, useCallback } from 'react';
import type { MonitoredDevice, TrapEvent } from '../../types';
import { fetchTrapEvents, fetchTrapSummary } from '../../services/api';

interface NDMTrapsTabProps {
  devices: MonitoredDevice[];
}

const SEVERITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: 'rgba(239,68,68,0.15)', text: '#ef4444', border: 'rgba(239,68,68,0.3)' },
  major:    { bg: 'rgba(249,115,22,0.15)', text: '#f97316', border: 'rgba(249,115,22,0.3)' },
  minor:    { bg: 'rgba(245,158,11,0.12)', text: '#f59e0b', border: 'rgba(245,158,11,0.3)' },
  warning:  { bg: 'rgba(245,158,11,0.1)',  text: '#eab308', border: 'rgba(245,158,11,0.2)' },
  info:     { bg: 'rgba(59,130,246,0.1)',   text: '#3b82f6', border: 'rgba(59,130,246,0.2)' },
};

const KNOWN_OIDS: Record<string, string> = {
  '1.3.6.1.6.3.1.1.5.3': 'linkDown',
  '1.3.6.1.6.3.1.1.5.4': 'linkUp',
  '1.3.6.1.6.3.1.1.5.1': 'coldStart',
  '1.3.6.1.6.3.1.1.5.2': 'warmStart',
  '1.3.6.1.6.3.1.1.5.5': 'authenticationFailure',
  '1.3.6.1.2.1.11.0.3': 'snmpTrapEnterprise',
  '1.3.6.1.4.1.9.9.43.2.0.1': 'ciscoConfigChange',
  '1.3.6.1.4.1.9.9.13.3.0.1': 'ciscoEnvMonTemp',
};

const TIME_RANGES = [
  { label: '15m', seconds: 900 },
  { label: '1h', seconds: 3600 },
  { label: '6h', seconds: 21600 },
  { label: '24h', seconds: 86400 },
  { label: '7d', seconds: 604800 },
];

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10, padding: 20,
};

const NDMTrapsTab: React.FC<NDMTrapsTabProps> = ({ devices }) => {
  const [traps, setTraps] = useState<TrapEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [timeRange, setTimeRange] = useState(3600);
  const [summary, setSummary] = useState<{ total: number; critical: number; warning: number; top_oid: string; top_device: string } | null>(null);

  // Map device IPs/IDs to hostnames
  const deviceMap = React.useMemo(() => {
    const map: Record<string, string> = {};
    devices.forEach(d => {
      map[d.management_ip] = d.hostname || d.management_ip;
      if (d.device_id) map[d.device_id] = d.hostname || d.management_ip;
    });
    return map;
  }, [devices]);

  const loadTraps = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const timeFrom = Math.floor(Date.now() / 1000) - timeRange;
      const filters: Parameters<typeof fetchTrapEvents>[0] = {
        time_from: timeFrom,
        limit: 200,
      };
      if (severityFilter !== 'all') filters.severity = severityFilter;

      const resp = await fetchTrapEvents(filters);
      const events: TrapEvent[] = resp.events || [];
      // Sort newest first
      events.sort((a, b) => b.timestamp - a.timestamp);
      setTraps(events);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch traps');
    } finally {
      setLoading(false);
    }
  }, [severityFilter, timeRange]);

  useEffect(() => { loadTraps(); }, [loadTraps]);

  useEffect(() => {
    fetchTrapSummary().then(setSummary).catch(() => {});
  }, []);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(loadTraps, 30000);
    return () => clearInterval(interval);
  }, [loadTraps]);

  const getSeverityStyle = (severity: string) => {
    return SEVERITY_STYLES[severity.toLowerCase()] || SEVERITY_STYLES.info;
  };

  const formatTimestamp = (ts: number): string => {
    return new Date(ts * 1000).toLocaleString([], {
      month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };

  const getOIDLabel = (oid: string): string | null => {
    return KNOWN_OIDS[oid] || null;
  };

  // Severity summary
  const severityCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    traps.forEach(t => {
      const key = t.severity.toLowerCase();
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [traps]);

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#8a7e6b', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>progress_activity</span>
        Loading trap events...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Trap Summary Cards */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Total Traps</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', fontFamily: 'monospace' }}>{summary.total.toLocaleString()}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Critical</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#ef4444', fontFamily: 'monospace' }}>{summary.critical}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Warning</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#f59e0b', fontFamily: 'monospace' }}>{summary.warning}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Top OID</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e0d4', fontFamily: 'monospace', wordBreak: 'break-all' }}>{summary.top_oid || '—'}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Top Device</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e0d4', fontFamily: 'monospace' }}>{summary.top_device || '—'}</div>
          </div>
        </div>
      )}

      {/* Severity Summary */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {Object.entries(SEVERITY_STYLES).map(([sev, styles]) => {
          const count = severityCounts[sev] || 0;
          return (
            <div key={sev} style={{
              padding: '6px 14px', borderRadius: 6, fontSize: 12,
              background: styles.bg, color: styles.text, fontWeight: 500,
              border: `1px solid ${styles.border}`,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <span style={{ textTransform: 'capitalize' }}>{sev}</span>
              <span style={{ fontWeight: 700, fontSize: 16 }}>{count}</span>
            </div>
          );
        })}
      </div>

      {/* Filter Bar */}
      <div style={{
        ...cardStyle, padding: '12px 16px',
        display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, color: '#64748b' }}>Severity:</span>
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value)}
            style={{
              padding: '6px 10px', background: 'rgba(224,159,62,0.06)',
              border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
              fontSize: 12, outline: 'none', cursor: 'pointer',
            }}
          >
            <option value="all" style={{ background: '#1a1814' }}>All</option>
            {Object.keys(SEVERITY_STYLES).map(s => (
              <option key={s} value={s} style={{ background: '#1a1814' }}>{s}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: 4 }}>
          {TIME_RANGES.map(tr => (
            <button
              key={tr.label}
              onClick={() => setTimeRange(tr.seconds)}
              style={{
                padding: '5px 10px', borderRadius: 5, fontSize: 11, fontWeight: 500,
                border: timeRange === tr.seconds ? '1px solid #e09f3e' : '1px solid rgba(148,163,184,0.12)',
                background: timeRange === tr.seconds ? 'rgba(224,159,62,0.12)' : 'transparent',
                color: timeRange === tr.seconds ? '#e09f3e' : '#8a7e6b',
                cursor: 'pointer',
              }}
            >
              {tr.label}
            </button>
          ))}
        </div>

        <div style={{ flex: 1 }} />

        <button
          onClick={loadTraps}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '6px 12px', borderRadius: 6, fontSize: 12,
            border: '1px solid rgba(224,159,62,0.2)', background: 'transparent',
            color: '#e09f3e', cursor: 'pointer',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>refresh</span>
          Refresh
        </button>
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* Trap Events Table */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>notification_important</span>
            Trap Events ({traps.length})
          </h3>
        </div>

        {traps.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, display: 'block', marginBottom: 8 }}>notification_important</span>
            No trap events in the selected time range.
          </div>
        ) : (
          <div style={{ maxHeight: 600, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.12)', position: 'sticky', top: 0, background: 'rgba(15,32,35,0.95)' }}>
                  {['Timestamp', 'Severity', 'Device', 'OID', 'Value'].map(h => (
                    <th key={h} style={{
                      padding: '8px 8px', textAlign: 'left', fontSize: 11, color: '#64748b',
                      fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {traps.map((trap, idx) => {
                  const sevStyle = getSeverityStyle(trap.severity);
                  const oidLabel = getOIDLabel(trap.oid);
                  const deviceName = deviceMap[trap.device_ip] || deviceMap[trap.device_id || ''] || trap.device_ip;

                  return (
                    <tr key={trap.event_id || idx} style={{
                      borderBottom: '1px solid rgba(148,163,184,0.05)',
                      borderLeft: `3px solid ${sevStyle.text}`,
                    }}>
                      <td className="font-mono" style={{ padding: '8px 8px', fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>
                        {formatTimestamp(trap.timestamp)}
                      </td>
                      <td style={{ padding: '8px 8px' }}>
                        <span style={{
                          fontSize: 10, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
                          background: sevStyle.bg, color: sevStyle.text, textTransform: 'uppercase',
                        }}>
                          {trap.severity}
                        </span>
                      </td>
                      <td style={{ padding: '8px 8px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <span style={{ fontSize: 12, color: '#e8e0d4', fontWeight: 500 }}>{deviceName}</span>
                          <span className="font-mono" style={{ fontSize: 10, color: '#64748b' }}>{trap.device_ip}</span>
                        </div>
                      </td>
                      <td style={{ padding: '8px 8px' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <span className="font-mono" style={{ fontSize: 11, color: '#8a7e6b' }} title={trap.oid}>
                            {trap.oid}
                          </span>
                          {oidLabel && (
                            <span style={{
                              fontSize: 10, padding: '1px 6px', borderRadius: 3,
                              background: 'rgba(224,159,62,0.1)', color: '#e09f3e',
                              display: 'inline-block', width: 'fit-content',
                            }}>
                              {oidLabel}
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{
                        padding: '8px 8px', fontSize: 12, color: '#e8e0d4',
                        maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }} title={trap.value}>
                        {trap.value}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default NDMTrapsTab;
