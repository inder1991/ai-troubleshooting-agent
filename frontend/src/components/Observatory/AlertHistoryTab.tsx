import React, { useState, useEffect, useCallback } from 'react';
import { fetchAlertHistory } from '../../services/api';
import { AlertHistoryEntry } from '../../types';

const severityColors: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#e09f3e',
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)',
  border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10,
  padding: 20,
};

const LIMIT_OPTIONS = [25, 50, 100, 200];
const AUTO_REFRESH_MS = 30_000;

const AlertHistoryTab: React.FC = () => {
  const [entries, setEntries] = useState<AlertHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [severity, setSeverity] = useState<string>('all');
  const [entitySearch, setEntitySearch] = useState('');
  const [state, setState] = useState<string>('all');
  const [limit, setLimit] = useState<number>(50);

  const loadData = useCallback(async () => {
    try {
      setError(null);
      setLoading(true);
      const data = await fetchAlertHistory({
        severity: severity !== 'all' ? severity : undefined,
        entity_id: entitySearch.trim() || undefined,
        state: state !== 'all' ? state : undefined,
        limit,
      });
      setEntries(Array.isArray(data) ? data : data.alerts ?? []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch alert history';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [severity, entitySearch, state, limit]);

  // Initial load + re-fetch when filters change
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(loadData, AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  const formatTimestamp = (ts: number): string => {
    return new Date(ts * 1000).toLocaleString();
  };

  const formatDuration = (seconds?: number): string => {
    if (seconds == null) return '--';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  };

  const selectStyle: React.CSSProperties = {
    backgroundColor: '#0a1a1e',
    border: '1px solid #3d3528',
    borderRadius: 6,
    color: '#e8e0d4',
    padding: '6px 10px',
    fontSize: 12,
    fontFamily: 'monospace',
    outline: 'none',
  };

  const inputStyle: React.CSSProperties = {
    ...selectStyle,
    minWidth: 180,
  };

  const thStyle: React.CSSProperties = {
    textAlign: 'left',
    padding: '8px 12px',
    fontSize: 10,
    fontFamily: 'monospace',
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: '#64748b',
    borderBottom: '1px solid #3d3528',
    whiteSpace: 'nowrap',
  };

  const tdStyle: React.CSSProperties = {
    padding: '8px 12px',
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#e8e0d4',
    borderBottom: '1px solid rgba(34,67,73,0.5)',
    whiteSpace: 'nowrap',
  };

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="material-symbols-outlined" style={{ color: '#e09f3e', fontSize: 22 }}>
            history
          </span>
          <span style={{ fontSize: 16, fontFamily: 'monospace', fontWeight: 700, color: '#e8e0d4' }}>
            Alert History
          </span>
          <span
            style={{
              fontSize: 10,
              fontFamily: 'monospace',
              color: '#64748b',
              backgroundColor: '#0a1a1e',
              padding: '2px 8px',
              borderRadius: 4,
              border: '1px solid #3d3528',
            }}
          >
            {entries.length} entries
          </span>
        </div>
        <button
          onClick={loadData}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            background: 'none',
            border: '1px solid #3d3528',
            borderRadius: 6,
            color: '#64748b',
            padding: '4px 10px',
            fontSize: 11,
            fontFamily: 'monospace',
            cursor: 'pointer',
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>refresh</span>
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div style={{ ...cardStyle, padding: 14, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12 }}>
        <span className="material-symbols-outlined" style={{ color: '#64748b', fontSize: 18 }}>
          filter_alt
        </span>

        {/* Severity */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <label style={{ fontSize: 9, fontFamily: 'monospace', color: '#4a5568', textTransform: 'uppercase' }}>
            Severity
          </label>
          <select
            value={severity}
            onChange={e => setSeverity(e.target.value)}
            style={selectStyle}
          >
            <option value="all">All</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
        </div>

        {/* Entity search */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <label style={{ fontSize: 9, fontFamily: 'monospace', color: '#4a5568', textTransform: 'uppercase' }}>
            Entity
          </label>
          <input
            type="text"
            value={entitySearch}
            onChange={e => setEntitySearch(e.target.value)}
            placeholder="Search entity..."
            style={inputStyle}
          />
        </div>

        {/* State */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <label style={{ fontSize: 9, fontFamily: 'monospace', color: '#4a5568', textTransform: 'uppercase' }}>
            State
          </label>
          <select
            value={state}
            onChange={e => setState(e.target.value)}
            style={selectStyle}
          >
            <option value="all">All</option>
            <option value="firing">Firing</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>

        {/* Limit */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <label style={{ fontSize: 9, fontFamily: 'monospace', color: '#4a5568', textTransform: 'uppercase' }}>
            Limit
          </label>
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            style={selectStyle}
          >
            {LIMIT_OPTIONS.map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            ...cardStyle,
            padding: 14,
            borderColor: '#ef444440',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span className="material-symbols-outlined" style={{ color: '#ef4444', fontSize: 18 }}>
            error
          </span>
          <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#ef4444' }}>{error}</span>
          <button
            onClick={loadData}
            style={{
              marginLeft: 'auto',
              background: 'none',
              border: '1px solid #ef444440',
              borderRadius: 6,
              color: '#ef4444',
              padding: '4px 10px',
              fontSize: 11,
              fontFamily: 'monospace',
              cursor: 'pointer',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && entries.length === 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '48px 0',
          }}
        >
          <span
            className="material-symbols-outlined"
            style={{ color: '#e09f3e', fontSize: 32, animation: 'spin 1.5s linear infinite' }}
          >
            progress_activity
          </span>
          <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#64748b', marginTop: 12 }}>
            Loading alert history...
          </span>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && entries.length === 0 && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '48px 0',
          }}
        >
          <span className="material-symbols-outlined" style={{ color: '#3d3528', fontSize: 36 }}>
            check_circle
          </span>
          <span style={{ fontSize: 12, fontFamily: 'monospace', color: '#64748b', marginTop: 12 }}>
            No alert history entries match the current filters
          </span>
        </div>
      )}

      {/* Table */}
      {entries.length > 0 && (
        <div style={{ ...cardStyle, padding: 0, overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Timestamp</th>
                <th style={thStyle}>Severity</th>
                <th style={thStyle}>Entity</th>
                <th style={thStyle}>Metric</th>
                <th style={thStyle}>Message</th>
                <th style={thStyle}>State</th>
                <th style={thStyle}>Duration</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => {
                const sevColor = severityColors[entry.severity] || '#64748b';
                const isFiring = entry.state === 'firing';
                return (
                  <tr
                    key={entry.id}
                    style={{ transition: 'background 0.15s' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(224,159,62,0.06)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                  >
                    {/* Timestamp */}
                    <td style={{ ...tdStyle, color: '#8a7e6b', fontSize: 11 }}>
                      {formatTimestamp(entry.timestamp)}
                    </td>

                    {/* Severity badge */}
                    <td style={tdStyle}>
                      <span
                        style={{
                          display: 'inline-block',
                          fontSize: 9,
                          fontWeight: 700,
                          fontFamily: 'monospace',
                          textTransform: 'uppercase',
                          padding: '2px 6px',
                          borderRadius: 4,
                          backgroundColor: `${sevColor}20`,
                          color: sevColor,
                        }}
                      >
                        {entry.severity}
                      </span>
                    </td>

                    {/* Entity */}
                    <td style={tdStyle}>{entry.entity_id}</td>

                    {/* Metric */}
                    <td style={{ ...tdStyle, color: '#e09f3e' }}>{entry.metric}</td>

                    {/* Message */}
                    <td
                      style={{
                        ...tdStyle,
                        whiteSpace: 'normal',
                        maxWidth: 320,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        color: '#8a7e6b',
                      }}
                    >
                      {entry.message}
                    </td>

                    {/* State */}
                    <td style={tdStyle}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 10,
                          fontWeight: 600,
                          fontFamily: 'monospace',
                          textTransform: 'uppercase',
                          color: isFiring ? '#ef4444' : '#22c55e',
                        }}
                      >
                        <span
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            backgroundColor: isFiring ? '#ef4444' : '#22c55e',
                            display: 'inline-block',
                          }}
                        />
                        {entry.state}
                      </span>
                    </td>

                    {/* Duration */}
                    <td style={{ ...tdStyle, color: '#64748b' }}>
                      {formatDuration(entry.duration)}
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

export default AlertHistoryTab;
