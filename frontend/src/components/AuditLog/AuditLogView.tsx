import React, { useState, useEffect, useCallback } from 'react';
import { fetchAuditLog } from '../../services/api';
import type { AuditLogEntry } from '../../types';

// ── Constants ────────────────────────────────────────────────────────

const ACTION_OPTIONS = ['', 'create', 'update', 'delete', 'login', 'logout', 'execute', 'export', 'import'];
const ENTITY_TYPE_OPTIONS = ['', 'session', 'device', 'alert', 'rule', 'user', 'campaign', 'network', 'config'];
const LIMIT_OPTIONS = [25, 50, 100];

// ── Styles ───────────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  backgroundColor: 'rgba(224,159,62,0.04)',
  border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10,
};

const thStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#64748b',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  padding: '10px 8px',
  textAlign: 'left',
  whiteSpace: 'nowrap',
};

const tdStyle: React.CSSProperties = {
  padding: '8px',
  fontSize: 12,
  color: '#e8e0d4',
  borderTop: '1px solid rgba(224,159,62,0.08)',
};

const inputStyle: React.CSSProperties = {
  backgroundColor: 'rgba(15,32,35,0.8)',
  border: '1px solid rgba(224,159,62,0.18)',
  borderRadius: 6,
  color: '#e8e0d4',
  fontSize: 12,
  padding: '6px 10px',
  outline: 'none',
};

const btnStyle: React.CSSProperties = {
  padding: '6px 16px',
  borderRadius: 6,
  fontSize: 12,
  fontWeight: 600,
  cursor: 'pointer',
  border: '1px solid rgba(224,159,62,0.25)',
  backgroundColor: 'rgba(224,159,62,0.08)',
  color: '#e09f3e',
  transition: 'background-color 150ms',
};

const btnDisabledStyle: React.CSSProperties = {
  ...btnStyle,
  opacity: 0.4,
  cursor: 'not-allowed',
};

// ── Component ────────────────────────────────────────────────────────

const AuditLogView: React.FC = () => {
  // Filter state
  const [action, setAction] = useState('');
  const [user, setUser] = useState('');
  const [entityType, setEntityType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [limit, setLimit] = useState(25);

  // Data state
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (currentOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAuditLog({
        action: action || undefined,
        user: user || undefined,
        entity_type: entityType || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit,
        offset: currentOffset,
      });
      setEntries(Array.isArray(data) ? data : data.items ?? []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch audit log');
    } finally {
      setLoading(false);
    }
  }, [action, user, entityType, dateFrom, dateTo, limit]);

  // Load on mount and when filters / offset change
  useEffect(() => {
    load(offset);
  }, [load, offset]);

  const handleApplyFilters = () => {
    setOffset(0);
    load(0);
  };

  const handlePrev = () => {
    const newOffset = Math.max(0, offset - limit);
    setOffset(newOffset);
  };

  const handleNext = () => {
    setOffset(offset + limit);
  };

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-2 mb-6">
          <span
            className="material-symbols-outlined text-xl"
            style={{ color: '#e09f3e' }}
          >
            history
          </span>
          <h1 className="text-xl font-bold text-white">Audit Log</h1>
        </div>

        {/* Filter Bar */}
        <div style={cardStyle} className="p-4 mb-5">
          <div className="flex flex-wrap items-end gap-3">
            {/* Action */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Action</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
                style={{ ...inputStyle, minWidth: 120 }}
              >
                <option value="">All</option>
                {ACTION_OPTIONS.filter(Boolean).map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>

            {/* User */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>User</label>
              <input
                type="text"
                placeholder="Filter by user..."
                value={user}
                onChange={(e) => setUser(e.target.value)}
                style={{ ...inputStyle, minWidth: 140 }}
              />
            </div>

            {/* Entity Type */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Entity Type</label>
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
                style={{ ...inputStyle, minWidth: 120 }}
              >
                <option value="">All</option>
                {ENTITY_TYPE_OPTIONS.filter(Boolean).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* Date From */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>From</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                style={inputStyle}
              />
            </div>

            {/* Date To */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>To</label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                style={inputStyle}
              />
            </div>

            {/* Limit */}
            <div className="flex flex-col gap-1">
              <label style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Limit</label>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                style={{ ...inputStyle, minWidth: 70 }}
              >
                {LIMIT_OPTIONS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>

            {/* Apply */}
            <button
              onClick={handleApplyFilters}
              style={btnStyle}
              onMouseEnter={(e) => { (e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.18)'); }}
              onMouseLeave={(e) => { (e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.08)'); }}
            >
              <span className="flex items-center gap-1">
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>filter_alt</span>
                Apply
              </span>
            </button>
          </div>
        </div>

        {/* Content Area */}
        {loading && (
          <div className="flex items-center justify-center py-20">
            <span
              className="material-symbols-outlined animate-spin text-3xl"
              style={{ color: '#e09f3e' }}
            >
              progress_activity
            </span>
          </div>
        )}

        {error && !loading && (
          <div
            style={{
              ...cardStyle,
              borderColor: 'rgba(239,68,68,0.3)',
              backgroundColor: 'rgba(239,68,68,0.06)',
            }}
            className="p-4 text-center"
          >
            <span className="material-symbols-outlined text-red-400 mr-2" style={{ fontSize: 16, verticalAlign: 'middle' }}>
              error
            </span>
            <span style={{ color: '#fca5a5', fontSize: 13 }}>{error}</span>
          </div>
        )}

        {!loading && !error && entries.length === 0 && (
          <div style={cardStyle} className="p-10 text-center">
            <span
              className="material-symbols-outlined mb-2"
              style={{ fontSize: 36, color: '#334155', display: 'block' }}
            >
              receipt_long
            </span>
            <p style={{ color: '#64748b', fontSize: 13 }}>No audit log entries found.</p>
          </div>
        )}

        {!loading && !error && entries.length > 0 && (
          <div style={{ ...cardStyle, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={thStyle}>Timestamp</th>
                  <th style={thStyle}>User</th>
                  <th style={thStyle}>Action</th>
                  <th style={thStyle}>Entity Type</th>
                  <th style={thStyle}>Entity ID</th>
                  <th style={thStyle}>Details</th>
                  <th style={thStyle}>IP</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    style={{ transition: 'background-color 150ms' }}
                    onMouseEnter={(e) => { (e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.06)'); }}
                    onMouseLeave={(e) => { (e.currentTarget.style.backgroundColor = 'transparent'); }}
                  >
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: 11 }}>
                      {entry.timestamp}
                    </td>
                    <td style={tdStyle}>{entry.user}</td>
                    <td style={tdStyle}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          backgroundColor: actionColor(entry.action).bg,
                          color: actionColor(entry.action).fg,
                        }}
                      >
                        {entry.action}
                      </span>
                    </td>
                    <td style={tdStyle}>{entry.entity_type}</td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{entry.entity_id}</td>
                    <td style={{ ...tdStyle, maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {entry.details}
                    </td>
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11 }}>{entry.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && !error && (
          <div className="flex items-center justify-between mt-4">
            <span style={{ fontSize: 12, color: '#64748b' }}>
              Showing {entries.length} entries (offset {offset})
            </span>
            <div className="flex gap-2">
              <button
                onClick={handlePrev}
                disabled={offset === 0}
                style={offset === 0 ? btnDisabledStyle : btnStyle}
                onMouseEnter={(e) => { if (offset !== 0) e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.18)'; }}
                onMouseLeave={(e) => { if (offset !== 0) e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.08)'; }}
              >
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>chevron_left</span>
                  Previous
                </span>
              </button>
              <button
                onClick={handleNext}
                disabled={entries.length < limit}
                style={entries.length < limit ? btnDisabledStyle : btnStyle}
                onMouseEnter={(e) => { if (entries.length >= limit) e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.18)'; }}
                onMouseLeave={(e) => { if (entries.length >= limit) e.currentTarget.style.backgroundColor = 'rgba(224,159,62,0.08)'; }}
              >
                <span className="flex items-center gap-1">
                  Next
                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>chevron_right</span>
                </span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Helpers ──────────────────────────────────────────────────────────

function actionColor(action: string): { bg: string; fg: string } {
  switch (action) {
    case 'create':
      return { bg: 'rgba(16,185,129,0.15)', fg: '#34d399' };
    case 'delete':
      return { bg: 'rgba(239,68,68,0.15)', fg: '#f87171' };
    case 'update':
      return { bg: 'rgba(224,159,62,0.15)', fg: '#e09f3e' };
    case 'login':
    case 'logout':
      return { bg: 'rgba(168,85,247,0.15)', fg: '#c084fc' };
    case 'execute':
      return { bg: 'rgba(245,158,11,0.15)', fg: '#fbbf24' };
    case 'export':
    case 'import':
      return { bg: 'rgba(59,130,246,0.15)', fg: '#60a5fa' };
    default:
      return { bg: 'rgba(100,116,139,0.15)', fg: '#8a7e6b' };
  }
}

export default AuditLogView;
