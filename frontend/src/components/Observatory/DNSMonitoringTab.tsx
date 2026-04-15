import React, { useState, useEffect, useCallback } from 'react';
import {
  getDNSConfig,
  addDNSServer,
  removeDNSServer,
  addDNSHostname,
  removeDNSHostname,
  queryDNS,
  getDNSMetrics,
  getDNSNXDomain,
} from '../../services/api';
import type {
  DNSServer,
  DNSWatchedHostname,
  DNSMetrics,
  DNSQueryResult,
  DNSNXDomainEntry,
} from '../../types';

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)',
  border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10,
  padding: 20,
};

const inputStyle: React.CSSProperties = {
  background: '#0a1a1e',
  border: '1px solid #3d3528',
  borderRadius: 6,
  padding: '6px 10px',
  color: '#e8e0d4',
  fontSize: 12,
  fontFamily: 'monospace',
  outline: 'none',
};

const btnPrimary: React.CSSProperties = {
  background: 'rgba(224,159,62,0.15)',
  border: '1px solid #e09f3e',
  borderRadius: 6,
  padding: '6px 14px',
  color: '#e09f3e',
  fontSize: 12,
  fontFamily: 'monospace',
  cursor: 'pointer',
};

const btnDanger: React.CSSProperties = {
  background: 'rgba(239,68,68,0.10)',
  border: '1px solid rgba(239,68,68,0.3)',
  borderRadius: 6,
  padding: '4px 10px',
  color: '#ef4444',
  fontSize: 11,
  fontFamily: 'monospace',
  cursor: 'pointer',
};

const thStyle: React.CSSProperties = {
  color: '#64748b',
  fontSize: 10,
  fontFamily: 'monospace',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  padding: '6px 8px',
  borderBottom: '1px solid #3d3528',
  textAlign: 'left',
};

const tdStyle: React.CSSProperties = {
  color: '#e8e0d4',
  fontSize: 12,
  fontFamily: 'monospace',
  padding: '8px',
  borderBottom: '1px solid rgba(34,67,73,0.3)',
};

const RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'TXT'] as const;

const statusColor = (status: string) => {
  switch (status) {
    case 'up': return '#22c55e';
    case 'down': return '#ef4444';
    default: return '#64748b';
  }
};

const DNSMonitoringTab: React.FC = () => {
  // --- State ---
  const [servers, setServers] = useState<DNSServer[]>([]);
  const [hostnames, setHostnames] = useState<DNSWatchedHostname[]>([]);
  const [metrics, setMetrics] = useState<DNSMetrics | null>(null);
  const [nxdomainEntries, setNxdomainEntries] = useState<DNSNXDomainEntry[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add-server form
  const [newServerIp, setNewServerIp] = useState('');
  const [newServerName, setNewServerName] = useState('');
  const [addingServer, setAddingServer] = useState(false);

  // Add-hostname form
  const [newHostname, setNewHostname] = useState('');
  const [newRecordType, setNewRecordType] = useState<string>('A');
  const [addingHostname, setAddingHostname] = useState(false);

  // Ad-hoc query
  const [queryHostname, setQueryHostname] = useState('');
  const [queryRecordType, setQueryRecordType] = useState<string>('A');
  const [queryServer, setQueryServer] = useState<string>('');
  const [queryResult, setQueryResult] = useState<DNSQueryResult | null>(null);
  const [querying, setQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);

  // --- Data fetching ---
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [configResp, metricsResp, nxResp] = await Promise.all([
        getDNSConfig(),
        getDNSMetrics(),
        getDNSNXDomain(),
      ]);
      setServers(configResp.servers || []);
      setHostnames(configResp.hostnames || []);
      setMetrics(metricsResp);
      setNxdomainEntries(nxResp.entries || nxResp || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load DNS data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // --- Handlers ---
  const handleAddServer = async () => {
    if (!newServerIp.trim()) return;
    setAddingServer(true);
    try {
      await addDNSServer({ ip: newServerIp.trim(), name: newServerName.trim() || undefined });
      setNewServerIp('');
      setNewServerName('');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add server');
    } finally {
      setAddingServer(false);
    }
  };

  const handleRemoveServer = async (id: string) => {
    try {
      await removeDNSServer(id);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove server');
    }
  };

  const handleAddHostname = async () => {
    if (!newHostname.trim()) return;
    setAddingHostname(true);
    try {
      await addDNSHostname({ hostname: newHostname.trim(), record_type: newRecordType });
      setNewHostname('');
      setNewRecordType('A');
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add hostname');
    } finally {
      setAddingHostname(false);
    }
  };

  const handleRemoveHostname = async (hostname: string) => {
    try {
      await removeDNSHostname(hostname);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove hostname');
    }
  };

  const handleQuery = async () => {
    if (!queryHostname.trim()) return;
    setQuerying(true);
    setQueryError(null);
    setQueryResult(null);
    try {
      const result = await queryDNS(
        queryHostname.trim(),
        queryRecordType,
        queryServer || undefined,
      );
      setQueryResult(result);
    } catch (err) {
      setQueryError(err instanceof Error ? err.message : 'Query failed');
    } finally {
      setQuerying(false);
    }
  };

  // --- Render helpers ---
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span
          className="material-symbols-outlined text-3xl animate-spin"
          style={{ color: '#e09f3e' }}
        >
          progress_activity
        </span>
        <span className="ml-3 text-sm font-mono" style={{ color: '#64748b' }}>
          Loading DNS data...
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-auto px-6 py-4 space-y-6">
      {/* Global error banner */}
      {error && (
        <div
          className="flex items-center gap-2 rounded-lg px-4 py-3"
          style={{
            background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.25)',
          }}
        >
          <span className="material-symbols-outlined text-base" style={{ color: '#ef4444' }}>
            error
          </span>
          <span className="text-xs font-mono" style={{ color: '#ef4444' }}>
            {error}
          </span>
          <button
            onClick={() => setError(null)}
            className="ml-auto text-xs font-mono"
            style={{ color: '#64748b', cursor: 'pointer', background: 'none', border: 'none' }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Section 1: DNS Servers */}
      <div style={cardStyle}>
        <div className="flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-lg" style={{ color: '#e09f3e' }}>
            dns
          </span>
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
            DNS Servers
          </span>
          <span className="text-xs font-mono ml-auto" style={{ color: '#64748b' }}>
            {servers.length} configured
          </span>
        </div>

        {servers.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>IP Address</th>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Status</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {servers.map((s) => (
                <tr key={s.id}>
                  <td style={tdStyle}>{s.ip}</td>
                  <td style={{ ...tdStyle, color: '#8a7e6b' }}>{s.name || '--'}</td>
                  <td style={tdStyle}>
                    <span className="flex items-center gap-1.5">
                      <span
                        className="inline-block w-2 h-2 rounded-full"
                        style={{ backgroundColor: statusColor(s.status) }}
                      />
                      <span style={{ color: statusColor(s.status), fontSize: 11 }}>
                        {s.status.toUpperCase()}
                      </span>
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    <button style={btnDanger} onClick={() => handleRemoveServer(s.id)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center py-6 gap-3">
            <span className="material-symbols-outlined text-3xl" style={{ color: '#3d3528' }}>dns</span>
            <div className="text-xs font-mono text-center space-y-1">
              <div style={{ color: '#e8e0d4' }}>No DNS servers configured</div>
              <div style={{ color: '#64748b' }}>Add probe targets below to monitor resolution latency and availability</div>
            </div>
            <div className="text-body-xs font-mono space-y-0.5 text-left" style={{ color: '#7a7060' }}>
              <div>• On-Prem AD DNS — <span style={{ color: '#07b6d5' }}>10.1.40.100</span></div>
              <div>• AWS Route 53 — <span style={{ color: '#07b6d5' }}>vpc-shared-services resolver</span></div>
            </div>
          </div>
        )}

        {/* Add server form */}
        <div
          className="flex items-center gap-2 mt-4 pt-4"
          style={{ borderTop: '1px solid rgba(34,67,73,0.4)' }}
        >
          <input
            type="text"
            placeholder="IP address"
            value={newServerIp}
            onChange={(e) => setNewServerIp(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
            onKeyDown={(e) => e.key === 'Enter' && handleAddServer()}
          />
          <input
            type="text"
            placeholder="Name (optional)"
            value={newServerName}
            onChange={(e) => setNewServerName(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
            onKeyDown={(e) => e.key === 'Enter' && handleAddServer()}
          />
          <button
            style={{ ...btnPrimary, opacity: addingServer ? 0.5 : 1 }}
            onClick={handleAddServer}
            disabled={addingServer}
          >
            {addingServer ? 'Adding...' : 'Add Server'}
          </button>
        </div>
      </div>

      {/* Section 2: Watched Hostnames */}
      <div style={cardStyle}>
        <div className="flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-lg" style={{ color: '#e09f3e' }}>
            language
          </span>
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
            Watched Hostnames
          </span>
          <span className="text-xs font-mono ml-auto" style={{ color: '#64748b' }}>
            {hostnames.length} tracked
          </span>
        </div>

        {hostnames.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Hostname</th>
                <th style={thStyle}>Record Type</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {hostnames.map((h) => (
                <tr key={`${h.hostname}-${h.record_type}`}>
                  <td style={tdStyle}>{h.hostname}</td>
                  <td style={tdStyle}>
                    <span
                      className="inline-block px-2 py-0.5 rounded text-body-xs font-mono font-bold"
                      style={{
                        background: 'rgba(224,159,62,0.12)',
                        color: '#e09f3e',
                      }}
                    >
                      {h.record_type}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    <button style={btnDanger} onClick={() => handleRemoveHostname(h.hostname)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-xs font-mono py-4 text-center" style={{ color: '#64748b' }}>
            No watched hostnames. Add one to start monitoring.
          </div>
        )}

        {/* Add hostname form */}
        <div
          className="flex items-center gap-2 mt-4 pt-4"
          style={{ borderTop: '1px solid rgba(34,67,73,0.4)' }}
        >
          <input
            type="text"
            placeholder="Hostname (e.g. api.example.com)"
            value={newHostname}
            onChange={(e) => setNewHostname(e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
            onKeyDown={(e) => e.key === 'Enter' && handleAddHostname()}
          />
          <select
            value={newRecordType}
            onChange={(e) => setNewRecordType(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            {RECORD_TYPES.map((rt) => (
              <option key={rt} value={rt}>{rt}</option>
            ))}
          </select>
          <button
            style={{ ...btnPrimary, opacity: addingHostname ? 0.5 : 1 }}
            onClick={handleAddHostname}
            disabled={addingHostname}
          >
            {addingHostname ? 'Adding...' : 'Add Hostname'}
          </button>
        </div>
      </div>

      {/* Section 3: DNS Health Gauges */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <span className="material-symbols-outlined text-lg" style={{ color: '#e09f3e' }}>
            monitor_heart
          </span>
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
            DNS Health
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Avg Resolution Latency */}
          <div style={cardStyle}>
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-base" style={{ color: '#f59e0b' }}>
                speed
              </span>
              <span className="text-body-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#64748b' }}>
                Avg Resolution Latency
              </span>
            </div>
            <div className="text-2xl font-mono font-bold" style={{
              color: metrics && metrics.avg_latency_ms > 200 ? '#ef4444'
                : metrics && metrics.avg_latency_ms > 100 ? '#f59e0b'
                : '#22c55e',
            }}>
              {metrics ? `${metrics.avg_latency_ms.toFixed(1)} ms` : '--'}
            </div>
            <div className="text-body-xs font-mono mt-1" style={{ color: '#64748b' }}>
              {metrics ? `${metrics.total_queries} total queries` : 'No data'}
            </div>
          </div>

          {/* NXDOMAIN Count */}
          <div style={cardStyle}>
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-base" style={{ color: '#ef4444' }}>
                block
              </span>
              <span className="text-body-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#64748b' }}>
                NXDOMAIN Count
              </span>
            </div>
            <div className="text-2xl font-mono font-bold" style={{
              color: metrics && metrics.nxdomain_count > 50 ? '#ef4444'
                : metrics && metrics.nxdomain_count > 10 ? '#f59e0b'
                : '#22c55e',
            }}>
              {metrics ? metrics.nxdomain_count : '--'}
            </div>
            <div className="text-body-xs font-mono mt-1" style={{ color: '#64748b' }}>
              Failed lookups
            </div>
          </div>

          {/* Success Rate */}
          <div style={cardStyle}>
            <div className="flex items-center gap-2 mb-2">
              <span className="material-symbols-outlined text-base" style={{ color: '#22c55e' }}>
                check_circle
              </span>
              <span className="text-body-xs font-mono font-bold uppercase tracking-wider" style={{ color: '#64748b' }}>
                Success Rate
              </span>
            </div>
            <div className="text-2xl font-mono font-bold" style={{
              color: metrics && metrics.success_rate < 0.9 ? '#ef4444'
                : metrics && metrics.success_rate < 0.95 ? '#f59e0b'
                : '#22c55e',
            }}>
              {metrics ? `${(metrics.success_rate * 100).toFixed(1)}%` : '--'}
            </div>
            {/* Mini progress bar */}
            {metrics && (
              <div
                className="mt-2 h-1.5 rounded-full overflow-hidden"
                style={{ background: 'rgba(34,67,73,0.4)' }}
              >
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${metrics.success_rate * 100}%`,
                    background: metrics.success_rate < 0.9 ? '#ef4444'
                      : metrics.success_rate < 0.95 ? '#f59e0b'
                      : '#22c55e',
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Section 4: Ad-hoc Query Tool */}
      <div style={cardStyle}>
        <div className="flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-lg" style={{ color: '#e09f3e' }}>
            travel_explore
          </span>
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
            Ad-hoc DNS Query
          </span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            placeholder="Hostname to query"
            value={queryHostname}
            onChange={(e) => setQueryHostname(e.target.value)}
            style={{ ...inputStyle, flex: 2, minWidth: 180 }}
            onKeyDown={(e) => e.key === 'Enter' && handleQuery()}
          />
          <select
            value={queryRecordType}
            onChange={(e) => setQueryRecordType(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            {RECORD_TYPES.map((rt) => (
              <option key={rt} value={rt}>{rt}</option>
            ))}
          </select>
          <select
            value={queryServer}
            onChange={(e) => setQueryServer(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer', minWidth: 140 }}
          >
            <option value="">Any server</option>
            {servers.map((s) => (
              <option key={s.id} value={s.ip}>
                {s.name ? `${s.name} (${s.ip})` : s.ip}
              </option>
            ))}
          </select>
          <button
            style={{ ...btnPrimary, opacity: querying ? 0.5 : 1 }}
            onClick={handleQuery}
            disabled={querying}
          >
            <span className="flex items-center gap-1">
              <span className="material-symbols-outlined text-sm">search</span>
              {querying ? 'Querying...' : 'Query'}
            </span>
          </button>
        </div>

        {/* Query error */}
        {queryError && (
          <div
            className="mt-3 rounded px-3 py-2 text-xs font-mono"
            style={{ background: 'rgba(239,68,68,0.08)', color: '#ef4444' }}
          >
            {queryError}
          </div>
        )}

        {/* Query result */}
        {queryResult && (
          <div
            className="mt-4 rounded-lg p-4"
            style={{
              background: '#0a1a1e',
              border: '1px solid #3d3528',
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold" style={{ color: '#e8e0d4' }}>
                  {queryResult.hostname}
                </span>
                <span
                  className="inline-block px-2 py-0.5 rounded text-body-xs font-mono font-bold"
                  style={{ background: 'rgba(224,159,62,0.12)', color: '#e09f3e' }}
                >
                  {queryResult.record_type}
                </span>
              </div>
              <div className="flex items-center gap-3 text-body-xs font-mono" style={{ color: '#64748b' }}>
                <span>Server: {queryResult.server_ip}</span>
                <span>Latency: {queryResult.latency_ms.toFixed(1)} ms</span>
                <span
                  className="px-1.5 py-0.5 rounded"
                  style={{
                    background: queryResult.status === 'NOERROR'
                      ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                    color: queryResult.status === 'NOERROR' ? '#22c55e' : '#ef4444',
                  }}
                >
                  {queryResult.status}
                </span>
              </div>
            </div>

            {queryResult.records.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Value</th>
                    <th style={{ ...thStyle, textAlign: 'right' }}>TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {queryResult.records.map((r, i) => (
                    <tr key={i}>
                      <td style={tdStyle}>{r.value}</td>
                      <td style={{ ...tdStyle, textAlign: 'right', color: '#64748b' }}>{r.ttl}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="text-xs font-mono text-center py-2" style={{ color: '#64748b' }}>
                No records returned.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Section 5: NXDOMAIN Summary */}
      <div style={cardStyle}>
        <div className="flex items-center gap-2 mb-4">
          <span className="material-symbols-outlined text-lg" style={{ color: '#ef4444' }}>
            report
          </span>
          <span className="text-sm font-mono font-bold" style={{ color: '#e8e0d4' }}>
            NXDOMAIN Summary
          </span>
          <span className="text-xs font-mono ml-auto" style={{ color: '#64748b' }}>
            {nxdomainEntries.length} hostnames
          </span>
        </div>

        {nxdomainEntries.length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Hostname</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Count</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Last Seen</th>
              </tr>
            </thead>
            <tbody>
              {nxdomainEntries.map((entry) => (
                <tr key={entry.hostname}>
                  <td style={tdStyle}>{entry.hostname}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>
                    <span
                      className="inline-block px-2 py-0.5 rounded text-body-xs font-mono font-bold"
                      style={{
                        background: entry.count > 20
                          ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                        color: entry.count > 20 ? '#ef4444' : '#f59e0b',
                      }}
                    >
                      {entry.count}
                    </span>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right', color: '#64748b', fontSize: 11 }}>
                    {new Date(entry.last_seen).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center justify-center py-8">
            <span className="material-symbols-outlined text-3xl mb-2" style={{ color: '#3d3528' }}>
              check_circle
            </span>
            <span className="text-xs font-mono" style={{ color: '#64748b' }}>
              No NXDOMAIN entries recorded.
            </span>
          </div>
        )}
      </div>

      {/* Footer summary */}
      <div
        className="text-xs font-mono py-2"
        style={{ color: '#4a5568', borderTop: '1px solid #3d3528' }}
      >
        {servers.length} server{servers.length !== 1 ? 's' : ''} &middot;{' '}
        {hostnames.length} watched hostname{hostnames.length !== 1 ? 's' : ''} &middot;{' '}
        {metrics ? `${metrics.total_queries} total queries` : 'No metrics'}
      </div>
    </div>
  );
};

export default DNSMonitoringTab;
