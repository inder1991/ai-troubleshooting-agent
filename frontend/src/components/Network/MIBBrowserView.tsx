import React, { useState, useEffect, useRef, useCallback } from 'react';
import { mibLookup, mibBatchQuery, mibSearch } from '../../services/api';
import type { MIBEntry } from '../../types';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

// ---------------------------------------------------------------------------
// Inline useDebounce hook (300ms)
// ---------------------------------------------------------------------------
function useDebouncedCallback<T extends (...args: unknown[]) => void>(
  callback: T,
  delay = 300,
): T {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cbRef = useRef(callback);
  cbRef.current = callback;

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return useCallback(
    ((...args: unknown[]) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => cbRef.current(...args), delay);
    }) as unknown as T,
    [delay],
  );
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------
const cardStyle: React.CSSProperties = {
  background: 'rgba(7,182,213,0.04)',
  border: '1px solid rgba(7,182,213,0.12)',
  borderRadius: 10,
  padding: 20,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  background: 'rgba(7,182,213,0.06)',
  border: '1px solid rgba(7,182,213,0.15)',
  borderRadius: 8,
  color: '#e2e8f0',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'inherit',
  boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  color: '#64748b',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const STATUS_COLORS: Record<string, string> = {
  current: '#22c55e',
  deprecated: '#f59e0b',
  obsolete: '#ef4444',
  mandatory: '#07b6d5',
};

const ACCESS_COLORS: Record<string, string> = {
  'read-only': '#3b82f6',
  'read-write': '#22c55e',
  'read-create': '#a78bfa',
  'not-accessible': '#64748b',
  'accessible-for-notify': '#f59e0b',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
const MIBBrowserView: React.FC = () => {
  // --- Search state ---
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MIBEntry[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState('');

  // --- Detail state ---
  const [selectedEntry, setSelectedEntry] = useState<MIBEntry | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');

  // --- Batch state ---
  const [batchInput, setBatchInput] = useState('');
  const [batchResults, setBatchResults] = useState<MIBEntry[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState('');

  // ----- Debounced search -----
  const debouncedSearch = useDebouncedCallback(async (query: unknown) => {
    const q = query as string;
    if (!q.trim()) {
      setSearchResults([]);
      setSearchError('');
      return;
    }
    setSearchLoading(true);
    setSearchError('');
    try {
      const data = await mibSearch(q.trim());
      const entries: MIBEntry[] = data.results ?? data ?? [];
      setSearchResults(entries);
    } catch (err: unknown) {
      setSearchError(err instanceof Error ? err.message : 'Search failed');
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, 300);

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    debouncedSearch(value);
  };

  // ----- OID Detail -----
  const handleSelectResult = async (entry: MIBEntry) => {
    setDetailLoading(true);
    setDetailError('');
    setSelectedEntry(null);
    try {
      const data = await mibLookup(entry.oid);
      setSelectedEntry(data as MIBEntry);
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Lookup failed');
    } finally {
      setDetailLoading(false);
    }
  };

  // ----- Batch Query -----
  const handleBatchQuery = async () => {
    const oids = batchInput
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean);
    if (oids.length === 0) return;

    setBatchLoading(true);
    setBatchError('');
    setBatchResults([]);
    try {
      const data = await mibBatchQuery(oids);
      const entries: MIBEntry[] = data.results ?? data ?? [];
      setBatchResults(entries);
    } catch (err: unknown) {
      setBatchError(err instanceof Error ? err.message : 'Batch query failed');
    } finally {
      setBatchLoading(false);
    }
  };

  // ----- Render helpers -----
  const renderStatusBadge = (status: string) => {
    const color = STATUS_COLORS[status.toLowerCase()] || '#94a3b8';
    return (
      <span style={{
        fontSize: 10, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
        background: `${color}18`, color, textTransform: 'uppercase',
        border: `1px solid ${color}30`,
      }}>
        {status}
      </span>
    );
  };

  const renderAccessBadge = (access: string) => {
    const color = ACCESS_COLORS[access.toLowerCase()] || '#94a3b8';
    return (
      <span style={{
        fontSize: 10, padding: '2px 8px', borderRadius: 4, fontWeight: 600,
        background: `${color}18`, color,
        border: `1px solid ${color}30`,
      }}>
        {access}
      </span>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, minHeight: '100vh', background: '#0f2023' }}>
      {/* ===== Header ===== */}
      <div style={{
        padding: '20px 28px',
        borderBottom: '1px solid rgba(7,182,213,0.12)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span className="material-symbols-outlined" style={{ fontSize: 28, color: '#07b6d5' }}>
          manage_search
        </span>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#e2e8f0' }}>
          MIB Browser
        </h1>
      </div>

      {/* ===== Two-column layout ===== */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 20,
        padding: 24,
        flex: 1,
        alignItems: 'start',
      }}>
        {/* ========== LEFT COLUMN: Search + Results ========== */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Search Card */}
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>
                search
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                Search by OID or Name
              </span>
            </div>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                placeholder="e.g. 1.3.6.1.2.1.1 or sysDescr"
                value={searchQuery}
                onChange={e => handleSearchChange(e.target.value)}
                style={inputStyle}
              />
              {searchLoading && (
                <span
                  className="material-symbols-outlined"
                  style={{
                    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                    fontSize: 18, color: '#07b6d5',
                    animation: 'spin 1s linear infinite',
                  }}
                >
                  progress_activity
                </span>
              )}
            </div>
            {searchError && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#ef4444', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
                {searchError}
              </div>
            )}
          </div>

          {/* Results List */}
          <div style={{ ...cardStyle, padding: 0, maxHeight: 520, overflowY: 'auto' }}>
            <div style={{
              padding: '14px 20px', borderBottom: '1px solid rgba(7,182,213,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              position: 'sticky', top: 0, background: 'rgba(15,32,35,0.97)', zIndex: 1, borderRadius: '10px 10px 0 0',
            }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#07b6d5' }}>list</span>
                Results
              </span>
              <span style={{ fontSize: 11, color: '#64748b' }}>
                {searchResults.length} {searchResults.length === 1 ? 'entry' : 'entries'}
              </span>
            </div>

            {searchResults.length === 0 && !searchLoading && !searchError ? (
              <div style={{ textAlign: 'center', padding: 40, color: '#475569' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 36, display: 'block', marginBottom: 8 }}>
                  manage_search
                </span>
                <span style={{ fontSize: 13 }}>
                  {searchQuery ? 'No results found' : 'Enter an OID or name to search'}
                </span>
              </div>
            ) : (
              searchResults.map((entry, idx) => (
                <div
                  key={entry.oid + idx}
                  onClick={() => handleSelectResult(entry)}
                  style={{
                    padding: '12px 20px',
                    borderBottom: '1px solid rgba(148,163,184,0.06)',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                    borderLeft: selectedEntry?.oid === entry.oid ? '3px solid #07b6d5' : '3px solid transparent',
                    background: selectedEntry?.oid === entry.oid ? 'rgba(7,182,213,0.06)' : 'transparent',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'rgba(7,182,213,0.06)'; }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLDivElement).style.background =
                      selectedEntry?.oid === entry.oid ? 'rgba(7,182,213,0.06)' : 'transparent';
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
                    {entry.name}
                  </div>
                  <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#07b6d5', marginBottom: 4 }}>
                    {entry.oid}
                  </div>
                  <div style={{
                    fontSize: 11, color: '#94a3b8',
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                  }}>
                    {entry.description || 'No description'}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ========== RIGHT COLUMN: Detail + Batch ========== */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* OID Detail Panel */}
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>
                info
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                OID Detail
              </span>
            </div>

            {detailLoading ? (
              <div style={{ textAlign: 'center', padding: 32, color: '#94a3b8', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 20, animation: 'spin 1s linear infinite' }}>
                  progress_activity
                </span>
                Loading...
              </div>
            ) : detailError ? (
              <div style={{ padding: 20, color: '#ef4444', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
                {detailError}
              </div>
            ) : selectedEntry ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {/* OID */}
                <div>
                  <div style={labelStyle}>OID</div>
                  <div style={{
                    fontFamily: 'monospace', fontSize: 13, color: '#07b6d5', marginTop: 4,
                    padding: '6px 10px', background: 'rgba(7,182,213,0.06)', borderRadius: 6,
                    wordBreak: 'break-all',
                  }}>
                    {selectedEntry.oid}
                  </div>
                </div>
                {/* Name */}
                <div>
                  <div style={labelStyle}>Name</div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginTop: 4 }}>
                    {selectedEntry.name}
                  </div>
                </div>
                {/* Description */}
                <div>
                  <div style={labelStyle}>Description</div>
                  <div style={{
                    fontSize: 12, color: '#94a3b8', marginTop: 4, lineHeight: 1.6,
                    padding: '10px 12px', background: 'rgba(148,163,184,0.04)', borderRadius: 6,
                    border: '1px solid rgba(148,163,184,0.08)',
                    maxHeight: 160, overflowY: 'auto',
                  }}>
                    {selectedEntry.description || 'No description available'}
                  </div>
                </div>
                {/* Syntax */}
                <div>
                  <div style={labelStyle}>Syntax</div>
                  <div style={{
                    fontFamily: 'monospace', fontSize: 12, color: '#a78bfa', marginTop: 4,
                    padding: '4px 8px', background: 'rgba(167,139,250,0.08)', borderRadius: 4,
                    display: 'inline-block',
                  }}>
                    {selectedEntry.syntax || '--'}
                  </div>
                </div>
                {/* Access + Status row */}
                <div style={{ display: 'flex', gap: 24 }}>
                  <div>
                    <div style={labelStyle}>Access</div>
                    <div style={{ marginTop: 6 }}>
                      {selectedEntry.access ? renderAccessBadge(selectedEntry.access) : (
                        <span style={{ fontSize: 12, color: '#64748b' }}>--</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div style={labelStyle}>Status</div>
                    <div style={{ marginTop: 6 }}>
                      {selectedEntry.status ? renderStatusBadge(selectedEntry.status) : (
                        <span style={{ fontSize: 12, color: '#64748b' }}>--</span>
                      )}
                    </div>
                  </div>
                </div>
                {/* Children hint */}
                {selectedEntry.children && selectedEntry.children.length > 0 && (
                  <div style={{
                    marginTop: 4, padding: '8px 12px', background: 'rgba(7,182,213,0.05)',
                    borderRadius: 6, border: '1px solid rgba(7,182,213,0.1)',
                    fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span className="material-symbols-outlined" style={{ fontSize: 16, color: '#07b6d5' }}>
                      account_tree
                    </span>
                    {selectedEntry.children.length} child OID{selectedEntry.children.length > 1 ? 's' : ''}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: 32, color: '#475569' }}>
                <span className="material-symbols-outlined" style={{ fontSize: 36, display: 'block', marginBottom: 8 }}>
                  info
                </span>
                <span style={{ fontSize: 13 }}>
                  Select a search result to view details
                </span>
              </div>
            )}
          </div>

          {/* ===== Batch Query Tool ===== */}
          <div style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>
                playlist_add_check
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>
                Batch Query
              </span>
            </div>
            <textarea
              placeholder={"Paste OIDs, one per line:\n1.3.6.1.2.1.1.1\n1.3.6.1.2.1.1.5\n1.3.6.1.2.1.2.1"}
              value={batchInput}
              onChange={e => setBatchInput(e.target.value)}
              rows={5}
              style={{
                ...inputStyle,
                resize: 'vertical',
                minHeight: 90,
                lineHeight: 1.6,
              }}
            />
            <button
              onClick={handleBatchQuery}
              disabled={batchLoading || !batchInput.trim()}
              style={{
                marginTop: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                width: '100%',
                padding: '10px 0',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                border: '1px solid #07b6d5',
                background: batchLoading || !batchInput.trim() ? 'rgba(7,182,213,0.06)' : 'rgba(7,182,213,0.12)',
                color: batchLoading || !batchInput.trim() ? '#4a7a85' : '#07b6d5',
                cursor: batchLoading || !batchInput.trim() ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
              }}
            >
              {batchLoading ? (
                <>
                  <span className="material-symbols-outlined" style={{ fontSize: 18, animation: 'spin 1s linear infinite' }}>
                    progress_activity
                  </span>
                  Querying...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>send</span>
                  Query
                </>
              )}
            </button>

            {batchError && (
              <div style={{ marginTop: 10, fontSize: 12, color: '#ef4444', display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
                {batchError}
              </div>
            )}

            {/* Batch Results Table */}
            {batchResults.length > 0 && (
              <div style={{ marginTop: 16, maxHeight: 320, overflowY: 'auto', borderRadius: 8, border: '1px solid rgba(148,163,184,0.1)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{
                      borderBottom: '1px solid rgba(148,163,184,0.12)',
                      position: 'sticky', top: 0,
                      background: 'rgba(15,32,35,0.95)',
                    }}>
                      {['OID', 'Name', 'Syntax', 'Access', 'Status'].map(h => (
                        <th key={h} style={{
                          padding: '8px 10px', textAlign: 'left', fontSize: 10,
                          color: '#64748b', fontWeight: 600,
                          textTransform: 'uppercase', letterSpacing: '0.5px',
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {batchResults.map((entry, idx) => (
                      <tr
                        key={entry.oid + idx}
                        style={{
                          borderBottom: '1px solid rgba(148,163,184,0.05)',
                          cursor: 'pointer',
                        }}
                        onClick={() => {
                          setSelectedEntry(entry);
                          setDetailError('');
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'rgba(7,182,213,0.05)'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
                      >
                        <td style={{
                          padding: '8px 10px', fontFamily: 'monospace', fontSize: 11, color: '#07b6d5',
                          maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }} title={entry.oid}>
                          {entry.oid}
                        </td>
                        <td style={{ padding: '8px 10px', fontSize: 12, color: '#e2e8f0', fontWeight: 500 }}>
                          {entry.name}
                        </td>
                        <td style={{ padding: '8px 10px', fontFamily: 'monospace', fontSize: 11, color: '#a78bfa' }}>
                          {entry.syntax || '--'}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {entry.access ? renderAccessBadge(entry.access) : (
                            <span style={{ fontSize: 11, color: '#64748b' }}>--</span>
                          )}
                        </td>
                        <td style={{ padding: '8px 10px' }}>
                          {entry.status ? renderStatusBadge(entry.status) : (
                            <span style={{ fontSize: 11, color: '#64748b' }}>--</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
      <NetworkChatDrawer view="mib-browser" />
    </div>
  );
};

export default MIBBrowserView;
