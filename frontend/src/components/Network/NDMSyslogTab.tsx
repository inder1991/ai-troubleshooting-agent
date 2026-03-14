import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { MonitoredDevice, SyslogEntry } from '../../types';
import { fetchSyslogEntries, fetchSyslogSummary } from '../../services/api';
import { useDebounce } from '../../hooks/useDebounce';

interface NDMSyslogTabProps {
  devices: MonitoredDevice[];
}

const SEVERITY_COLORS: Record<string, { bg: string; text: string }> = {
  emergency:  { bg: 'rgba(239,68,68,0.2)',  text: '#ef4444' },
  alert:      { bg: 'rgba(239,68,68,0.18)', text: '#ef4444' },
  critical:   { bg: 'rgba(239,68,68,0.15)', text: '#ef4444' },
  error:      { bg: 'rgba(249,115,22,0.15)', text: '#f97316' },
  warning:    { bg: 'rgba(245,158,11,0.15)', text: '#f59e0b' },
  notice:     { bg: 'rgba(224,159,62,0.12)',  text: '#e09f3e' },
  info:       { bg: 'rgba(148,163,184,0.1)', text: '#8a7e6b' },
  debug:      { bg: 'rgba(100,116,139,0.1)', text: '#64748b' },
};

const SEVERITY_OPTIONS = ['all', 'emergency', 'alert', 'critical', 'error', 'warning', 'notice', 'info', 'debug'];
const FACILITY_OPTIONS = ['all', 'kern', 'user', 'mail', 'daemon', 'auth', 'syslog', 'lpr', 'news', 'uucp', 'cron', 'local0', 'local1', 'local2', 'local3', 'local4', 'local5', 'local6', 'local7'];

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

const selectStyle: React.CSSProperties = {
  padding: '6px 10px', background: 'rgba(224,159,62,0.06)',
  border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
  fontSize: 12, outline: 'none', cursor: 'pointer',
};

const NDMSyslogTab: React.FC<NDMSyslogTabProps> = ({ devices }) => {
  const [entries, setEntries] = useState<SyslogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [severityFilter, setSeverityFilter] = useState('all');
  const [facilityFilter, setFacilityFilter] = useState('all');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [timeRange, setTimeRange] = useState(3600);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [summary, setSummary] = useState<{ total: number; by_severity: Record<string, number>; top_facility: string; top_host: string } | null>(null);
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // WebSocket state
  const [isLive, setIsLive] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const bufferRef = useRef<SyslogEntry[]>([]);
  const isPausedRef = useRef(isPaused);

  // Keep isPausedRef in sync
  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  useEffect(() => {
    fetchSyslogSummary().then(setSummary).catch(() => {});
  }, []);

  // Map device IPs to hostnames for correlation
  const deviceMap = React.useMemo(() => {
    const map: Record<string, string> = {};
    devices.forEach(d => {
      map[d.management_ip] = d.hostname || d.management_ip;
      if (d.device_id) map[d.device_id] = d.hostname || d.management_ip;
    });
    return map;
  }, [devices]);

  const loadEntries = useCallback(async () => {
    try {
      const timeFrom = Math.floor(Date.now() / 1000) - timeRange;
      const filters: Record<string, unknown> = {
        time_from: timeFrom,
        limit: 200,
      };
      if (severityFilter !== 'all') filters.severity = severityFilter;
      if (facilityFilter !== 'all') filters.facility = facilityFilter;
      if (debouncedSearch.trim()) filters.search = debouncedSearch.trim();

      const resp = await fetchSyslogEntries(filters as Parameters<typeof fetchSyslogEntries>[0]);
      setEntries(resp.entries || []);
      setError('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch syslog');
    } finally {
      setLoading(false);
    }
  }, [severityFilter, facilityFilter, debouncedSearch, timeRange]);

  useEffect(() => { loadEntries(); }, [loadEntries]);

  // WebSocket connection
  useEffect(() => {
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
          setIsLive(true);
        };

        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.type === 'syslog_event' && data.entry) {
              if (isPausedRef.current) {
                bufferRef.current.push(data.entry);
              } else {
                setEntries(prev => [data.entry, ...prev].slice(0, 500));
              }
            }
          } catch {
            // Ignore unparseable messages
          }
        };

        ws.onclose = () => {
          setIsLive(false);
          wsRef.current = null;
          // Try to reconnect after 5s
          reconnectTimeout = setTimeout(connect, 5000);
        };

        ws.onerror = () => {
          setIsLive(false);
        };

        wsRef.current = ws;
      } catch {
        setIsLive(false);
      }
    };

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Polling fallback when WebSocket is not live
  useEffect(() => {
    if (refreshRef.current) clearInterval(refreshRef.current);
    if (!isLive && autoRefresh) {
      refreshRef.current = setInterval(loadEntries, 10000);
    }
    return () => {
      if (refreshRef.current) clearInterval(refreshRef.current);
    };
  }, [isLive, autoRefresh, loadEntries]);

  // Resume: flush buffer
  const handleResume = () => {
    const buffered = bufferRef.current;
    if (buffered.length > 0) {
      setEntries(prev => [...buffered.reverse(), ...prev].slice(0, 500));
      bufferRef.current = [];
    }
    setIsPaused(false);
  };

  const getSeverityStyle = (severity: string): { bg: string; text: string } => {
    const key = severity.toLowerCase();
    return SEVERITY_COLORS[key] || SEVERITY_COLORS.info;
  };

  const formatTimestamp = (ts: number): string => {
    return new Date(ts * 1000).toLocaleString([], {
      month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };

  // Severity summary counts
  const severityCounts = React.useMemo(() => {
    const counts: Record<string, number> = {};
    entries.forEach(e => {
      const key = e.severity.toLowerCase();
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [entries]);

  const bufferedCount = isPaused ? bufferRef.current.length : 0;

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#8a7e6b', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>progress_activity</span>
        Loading syslog entries...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Cards */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Total Entries</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', fontFamily: 'monospace' }}>{summary.total.toLocaleString()}</div>
          </div>
          {Object.entries(summary.by_severity).map(([sev, count]) => (
            <div key={sev} style={{ flex: 1, minWidth: 100, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
              <div style={{ fontSize: 11, color: sev === 'critical' ? '#ef4444' : sev === 'warning' ? '#f59e0b' : '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>{sev}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#e8e0d4', fontFamily: 'monospace' }}>{count}</div>
            </div>
          ))}
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Top Facility</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e0d4', fontFamily: 'monospace' }}>{summary.top_facility || '—'}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)', borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#e09f3e', fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>Top Host</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e0d4', fontFamily: 'monospace' }}>{summary.top_host || '—'}</div>
          </div>
        </div>
      )}

      {/* Severity Summary Bar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {Object.entries(SEVERITY_COLORS).map(([sev, colors]) => {
          const count = severityCounts[sev] || 0;
          if (count === 0 && sev !== 'critical' && sev !== 'error' && sev !== 'warning') return null;
          return (
            <div key={sev} style={{
              padding: '4px 12px', borderRadius: 6, fontSize: 12,
              background: colors.bg, color: colors.text, fontWeight: 500,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{ textTransform: 'capitalize' }}>{sev}</span>
              <span style={{ fontWeight: 700 }}>{count}</span>
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
          <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)} style={selectStyle}>
            {SEVERITY_OPTIONS.map(s => (
              <option key={s} value={s} style={{ background: '#1a1814' }}>{s === 'all' ? 'All' : s}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 12, color: '#64748b' }}>Facility:</span>
          <select value={facilityFilter} onChange={e => setFacilityFilter(e.target.value)} style={selectStyle}>
            {FACILITY_OPTIONS.map(f => (
              <option key={f} value={f} style={{ background: '#1a1814' }}>{f === 'all' ? 'All' : f}</option>
            ))}
          </select>
        </div>

        <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
          <span className="material-symbols-outlined" style={{
            position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)',
            fontSize: 16, color: '#64748b',
          }}>search</span>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search messages..."
            style={{
              width: '100%', padding: '6px 10px 6px 30px', background: 'rgba(224,159,62,0.06)',
              border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
              fontSize: 12, outline: 'none',
            }}
          />
        </div>

        {/* Live / Polling indicator */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 5,
          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: isLive ? 'rgba(34,197,94,0.12)' : 'rgba(245,158,11,0.12)',
          color: isLive ? '#22c55e' : '#f59e0b',
          border: `1px solid ${isLive ? 'rgba(34,197,94,0.3)' : 'rgba(245,158,11,0.3)'}`,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: isLive ? '#22c55e' : '#f59e0b',
            boxShadow: isLive ? '0 0 6px #22c55e' : undefined,
            animation: isLive ? 'pulse-green 2s ease-in-out infinite' : undefined,
          }} />
          {isLive ? 'LIVE' : 'POLLING'}
        </div>

        {/* Pause / Resume button */}
        <button
          onClick={() => isPaused ? handleResume() : setIsPaused(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 5,
            padding: '5px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600,
            border: isPaused ? '1px solid rgba(245,158,11,0.3)' : '1px solid rgba(148,163,184,0.2)',
            background: isPaused ? 'rgba(245,158,11,0.1)' : 'transparent',
            color: isPaused ? '#f59e0b' : '#8a7e6b',
            cursor: 'pointer',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
            {isPaused ? 'play_arrow' : 'pause'}
          </span>
          {isPaused ? `Resume${bufferedCount > 0 ? ` (${bufferedCount} buffered)` : ''}` : 'Pause'}
        </button>

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

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#8a7e6b', cursor: 'pointer' }}>
          <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
          Auto-refresh
          {autoRefresh && !isLive && (
            <span className="material-symbols-outlined" style={{ fontSize: 14, color: '#22c55e', animation: 'spin 2s linear infinite' }}>sync</span>
          )}
        </label>
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* Log Viewer Table */}
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: 0 }}>
            Syslog Entries ({entries.length})
          </h3>
        </div>

        {entries.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, display: 'block', marginBottom: 8 }}>article</span>
            No syslog entries match your filters.
          </div>
        ) : (
          <div style={{ maxHeight: 600, overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.12)', position: 'sticky', top: 0, background: 'rgba(15,32,35,0.95)' }}>
                  {['Timestamp', 'Severity', 'Hostname', 'Facility', 'App', 'Message'].map(h => (
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
                {entries.map((entry, idx) => {
                  const sevStyle = getSeverityStyle(entry.severity);
                  const deviceHostname = deviceMap[entry.device_ip] || deviceMap[entry.device_id || ''] || entry.hostname;

                  return (
                    <tr key={entry.event_id || idx} style={{
                      borderBottom: '1px solid rgba(148,163,184,0.05)',
                      animation: idx === 0 && isLive && !isPaused ? 'fadeIn 0.3s ease-in' : undefined,
                    }}>
                      <td className="font-mono" style={{ padding: '6px 8px', fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>
                        {formatTimestamp(entry.timestamp)}
                      </td>
                      <td style={{ padding: '6px 8px' }}>
                        <span style={{
                          fontSize: 10, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
                          background: sevStyle.bg, color: sevStyle.text, textTransform: 'uppercase',
                        }}>
                          {entry.severity}
                        </span>
                      </td>
                      <td style={{ padding: '6px 8px' }}>
                        <span style={{
                          fontSize: 11, padding: '2px 6px', borderRadius: 4,
                          background: 'rgba(224,159,62,0.1)', color: '#e09f3e',
                          cursor: 'pointer',
                        }}>
                          {deviceHostname}
                        </span>
                      </td>
                      <td style={{ padding: '6px 8px', fontSize: 11, color: '#64748b' }}>
                        {entry.facility}
                      </td>
                      <td style={{ padding: '6px 8px', fontSize: 11, color: '#8a7e6b' }}>
                        {entry.app_name}
                      </td>
                      <td style={{
                        padding: '6px 8px', fontSize: 12, color: '#e8e0d4',
                        maxWidth: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }} title={entry.message}>
                        {entry.message}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Inline keyframe for fade-in animation */}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; background: rgba(224,159,62,0.08); }
          to { opacity: 1; background: transparent; }
        }
        @keyframes pulse-green {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
};

export default NDMSyslogTab;
