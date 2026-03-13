import React, { useState, useEffect, useCallback } from 'react';
import {
  listCloudAccounts,
  listCloudResources,
  listCloudSyncJobs,
  triggerCloudSync,
} from '../../services/api';
import type { CloudAccount, CloudResource, CloudSyncJob } from '../../types';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

/* ---------- design tokens ---------- */

const COLORS = {
  bg: '#0f2023',
  primary: '#07b6d5',
  cardBg: 'rgba(7,182,213,0.04)',
  cardBorder: 'rgba(7,182,213,0.12)',
  textPrimary: '#e2e8f0',
  textSecondary: '#94a3b8',
  textMuted: '#475569',
  inputBg: 'rgba(7,182,213,0.06)',
  inputBorder: 'rgba(7,182,213,0.18)',
  danger: '#ef4444',
  success: '#22c55e',
  warning: '#f59e0b',
} as const;

/* ---------- style objects ---------- */

const styles = {
  page: {
    minHeight: '100vh',
    backgroundColor: COLORS.bg,
    color: COLORS.textPrimary,
    padding: '24px 32px',
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 24,
  } as React.CSSProperties,

  headerIcon: {
    fontSize: 28,
    color: COLORS.primary,
  } as React.CSSProperties,

  headerTitle: {
    fontSize: 22,
    fontWeight: 600,
    color: COLORS.textPrimary,
    margin: 0,
    flex: 1,
  } as React.CSSProperties,

  filtersRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 12,
    alignItems: 'center',
    marginBottom: 20,
  } as React.CSSProperties,

  filterGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
  } as React.CSSProperties,

  filterLabel: {
    fontSize: 10,
    fontWeight: 600,
    color: COLORS.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  } as React.CSSProperties,

  select: {
    background: COLORS.inputBg,
    border: `1px solid ${COLORS.inputBorder}`,
    borderRadius: 5,
    padding: '7px 10px',
    fontSize: 13,
    color: COLORS.textPrimary,
    outline: 'none',
    minWidth: 160,
  } as React.CSSProperties,

  tabBar: {
    display: 'flex',
    gap: 4,
    borderBottom: `1px solid ${COLORS.cardBorder}`,
    marginBottom: 20,
    overflowX: 'auto' as const,
  } as React.CSSProperties,

  tab: (active: boolean): React.CSSProperties => ({
    padding: '10px 16px',
    fontSize: 12,
    fontWeight: active ? 600 : 400,
    color: active ? COLORS.primary : COLORS.textSecondary,
    background: active ? 'rgba(7,182,213,0.08)' : 'transparent',
    border: 'none',
    borderBottom: active ? `2px solid ${COLORS.primary}` : '2px solid transparent',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s ease',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
  }),

  card: {
    background: COLORS.cardBg,
    border: `1px solid ${COLORS.cardBorder}`,
    borderRadius: 8,
    padding: 20,
  } as React.CSSProperties,

  toolbar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  } as React.CSSProperties,

  count: {
    fontSize: 12,
    color: COLORS.textSecondary,
  } as React.CSSProperties,

  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
    fontSize: 13,
  } as React.CSSProperties,

  th: {
    textAlign: 'left' as const,
    padding: '10px 12px',
    color: COLORS.textSecondary,
    fontWeight: 500,
    fontSize: 12,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
    borderBottom: `1px solid ${COLORS.cardBorder}`,
  } as React.CSSProperties,

  td: {
    padding: '10px 12px',
    borderBottom: '1px solid rgba(7,182,213,0.06)',
    color: COLORS.textPrimary,
  } as React.CSSProperties,

  btnPrimary: {
    background: COLORS.primary,
    color: COLORS.bg,
    border: 'none',
    borderRadius: 6,
    padding: '8px 18px',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'opacity 0.15s ease',
  } as React.CSSProperties,

  empty: {
    textAlign: 'center' as const,
    padding: '40px 0',
    color: COLORS.textMuted,
    fontSize: 13,
  } as React.CSSProperties,

  error: {
    padding: '10px 14px',
    borderRadius: 8,
    backgroundColor: 'rgba(239,68,68,0.08)',
    border: '1px solid rgba(239,68,68,0.2)',
    color: '#f87171',
    fontSize: 13,
    marginBottom: 16,
  } as React.CSSProperties,

  syncFooter: {
    marginTop: 16,
    padding: '12px 16px',
    borderRadius: 8,
    background: 'rgba(7,182,213,0.03)',
    border: `1px solid ${COLORS.cardBorder}`,
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 20,
    alignItems: 'center',
    fontSize: 12,
    color: COLORS.textSecondary,
  } as React.CSSProperties,

  tag: {
    display: 'inline-block',
    padding: '2px 6px',
    borderRadius: 4,
    fontSize: 11,
    background: 'rgba(7,182,213,0.10)',
    color: COLORS.primary,
    marginRight: 4,
    marginBottom: 2,
  } as React.CSSProperties,

  tierBadge: (tier: number): React.CSSProperties => ({
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 4,
    fontSize: 11,
    fontWeight: 600,
    background:
      tier === 1
        ? 'rgba(34,197,94,0.12)'
        : tier === 2
          ? 'rgba(7,182,213,0.12)'
          : 'rgba(245,158,11,0.12)',
    color:
      tier === 1 ? COLORS.success : tier === 2 ? COLORS.primary : COLORS.warning,
  }),
};

/* ---------- resource type tabs ---------- */

const RESOURCE_TABS = [
  { id: 'vpc', label: 'VPCs', icon: 'cloud' },
  { id: 'subnet', label: 'Subnets', icon: 'lan' },
  { id: 'security_group', label: 'Security Groups', icon: 'security' },
  { id: 'nacl', label: 'NACLs', icon: 'shield' },
  { id: 'route_table', label: 'Route Tables', icon: 'route' },
  { id: 'eni', label: 'ENIs', icon: 'settings_input_component' },
  { id: 'instance', label: 'Instances', icon: 'dns' },
  { id: 'elb', label: 'Load Balancers', icon: 'mediation' },
  { id: 'nat_gateway', label: 'NAT Gateways', icon: 'nat' },
  { id: 'vpc_peering', label: 'VPC Peerings', icon: 'hub' },
];

/* ---------- helpers ---------- */

function formatTimestamp(ts: string | null): string {
  if (!ts) return '--';
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

function parseTags(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, string>;
    }
    return {};
  } catch {
    return {};
  }
}

function syncStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return COLORS.success;
    case 'running':
    case 'queued':
      return COLORS.primary;
    case 'failed':
      return COLORS.danger;
    case 'paused':
      return COLORS.warning;
    default:
      return COLORS.textSecondary;
  }
}

/* ---------- main component ---------- */

export function CloudResourcesView() {
  /* --- state --- */
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [selectedRegion, setSelectedRegion] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>(RESOURCE_TABS[0].id);
  const [resources, setResources] = useState<CloudResource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncJobs, setSyncJobs] = useState<CloudSyncJob[]>([]);
  const [syncing, setSyncing] = useState(false);

  /* --- derived: unique regions from selected account --- */
  const regionOptions: string[] = (() => {
    if (!selectedAccountId) {
      const all = accounts.flatMap((a) => a.regions ?? []);
      return [...new Set(all)].sort();
    }
    const account = accounts.find((a) => a.account_id === selectedAccountId);
    return account?.regions ? [...new Set(account.regions)].sort() : [];
  })();

  /* --- load accounts on mount --- */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listCloudAccounts();
        if (!cancelled) {
          const list = Array.isArray(data) ? data : [];
          setAccounts(list as CloudAccount[]);
          if (list.length > 0 && !selectedAccountId) {
            setSelectedAccountId((list[0] as CloudAccount).account_id);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load accounts');
        }
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* --- load resources when filters change --- */
  const loadResources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {
        account_id?: string;
        region?: string;
        resource_type?: string;
        limit?: number;
      } = {
        resource_type: activeTab,
        limit: 200,
      };
      if (selectedAccountId) params.account_id = selectedAccountId;
      if (selectedRegion) params.region = selectedRegion;

      const data = await listCloudResources(params);
      const list = Array.isArray(data) ? data : [];
      setResources(list as CloudResource[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load resources');
      setResources([]);
    } finally {
      setLoading(false);
    }
  }, [selectedAccountId, selectedRegion, activeTab]);

  useEffect(() => {
    loadResources();
  }, [loadResources]);

  /* --- load sync jobs for selected account --- */
  useEffect(() => {
    if (!selectedAccountId) {
      setSyncJobs([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await listCloudSyncJobs(selectedAccountId);
        if (!cancelled) {
          const list = Array.isArray(data) ? data : [];
          setSyncJobs(list as CloudSyncJob[]);
        }
      } catch {
        // sync jobs are informational; silently ignore errors
      }
    })();
    return () => { cancelled = true; };
  }, [selectedAccountId]);

  /* --- sync now handler --- */
  const handleSyncNow = async () => {
    if (!selectedAccountId || syncing) return;
    setSyncing(true);
    setError(null);
    try {
      await triggerCloudSync(selectedAccountId);
      // Refresh sync jobs and resources after a short delay to let the sync start
      setTimeout(async () => {
        try {
          const [jobsData] = await Promise.all([
            listCloudSyncJobs(selectedAccountId),
            loadResources(),
          ]);
          const list = Array.isArray(jobsData) ? jobsData : [];
          setSyncJobs(list as CloudSyncJob[]);
        } catch {
          // best effort
        }
        setSyncing(false);
      }, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to trigger sync');
      setSyncing(false);
    }
  };

  /* --- latest sync job for footer --- */
  const latestJob: CloudSyncJob | null = syncJobs.length > 0 ? syncJobs[0] : null;

  /* --- render --- */
  return (
    <div style={styles.page}>
      {/* Header row */}
      <div style={styles.header}>
        <span className="material-symbols-outlined" style={styles.headerIcon}>
          cloud
        </span>
        <h1 style={styles.headerTitle}>Cloud Resources</h1>
        <button
          style={{
            ...styles.btnPrimary,
            opacity: syncing || !selectedAccountId ? 0.5 : 1,
            pointerEvents: syncing || !selectedAccountId ? 'none' : 'auto',
          }}
          onClick={handleSyncNow}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            sync
          </span>
          {syncing ? 'Syncing...' : 'Sync Now'}
        </button>
      </div>

      {/* Filter row */}
      <div style={styles.filtersRow}>
        {/* Account selector */}
        <div style={styles.filterGroup}>
          <span style={styles.filterLabel}>Account</span>
          <select
            style={styles.select}
            value={selectedAccountId}
            onChange={(e) => {
              setSelectedAccountId(e.target.value);
              setSelectedRegion('');
            }}
          >
            <option value="">All Accounts</option>
            {accounts.map((acct) => (
              <option key={acct.account_id} value={acct.account_id}>
                {acct.display_name} ({acct.provider})
              </option>
            ))}
          </select>
        </div>

        {/* Region filter */}
        <div style={styles.filterGroup}>
          <span style={styles.filterLabel}>Region</span>
          <select
            style={styles.select}
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
          >
            <option value="">All Regions</option>
            {regionOptions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        {/* Account status badge */}
        {selectedAccountId && (() => {
          const acct = accounts.find((a) => a.account_id === selectedAccountId);
          if (!acct) return null;
          const statusColor =
            acct.last_sync_status === 'ok'
              ? COLORS.success
              : acct.last_sync_status === 'error'
                ? COLORS.danger
                : acct.last_sync_status === 'paused'
                  ? COLORS.warning
                  : COLORS.textMuted;
          return (
            <div style={{ ...styles.filterGroup, justifyContent: 'flex-end' }}>
              <span style={styles.filterLabel}>Sync Status</span>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: statusColor,
                  textTransform: 'uppercase',
                  padding: '7px 0',
                }}
              >
                {acct.last_sync_status}
              </span>
            </div>
          );
        })()}
      </div>

      {/* Resource type tab bar */}
      <div style={styles.tabBar}>
        {RESOURCE_TABS.map((tab) => (
          <button
            key={tab.id}
            style={styles.tab(activeTab === tab.id)}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              {tab.icon}
            </span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error banner */}
      {error && <div style={styles.error}>{error}</div>}

      {/* Resources table */}
      <div style={styles.card}>
        <div style={styles.toolbar}>
          <span style={styles.count}>
            {loading ? 'Loading...' : `${resources.length} resource${resources.length !== 1 ? 's' : ''}`}
          </span>
          <button
            style={{
              ...styles.btnPrimary,
              background: 'transparent',
              color: COLORS.textSecondary,
              border: `1px solid ${COLORS.cardBorder}`,
              padding: '6px 14px',
              fontSize: 12,
              opacity: loading ? 0.5 : 1,
            }}
            onClick={loadResources}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
              refresh
            </span>
            Refresh
          </button>
        </div>

        {!loading && resources.length === 0 && !error ? (
          <div style={styles.empty}>
            <span
              className="material-symbols-outlined"
              style={{ fontSize: 40, color: COLORS.textMuted, display: 'block', marginBottom: 8 }}
            >
              cloud_off
            </span>
            No {RESOURCE_TABS.find((t) => t.id === activeTab)?.label ?? 'resources'} found.
            {!selectedAccountId && ' Select an account and trigger a sync to discover resources.'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Name</th>
                  <th style={styles.th}>Native ID</th>
                  <th style={styles.th}>Region</th>
                  <th style={styles.th}>Tags</th>
                  <th style={styles.th}>Last Seen</th>
                  <th style={styles.th}>Sync Tier</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan={6}
                      style={{ ...styles.td, textAlign: 'center', color: COLORS.textSecondary, padding: 24 }}
                    >
                      Loading resources...
                    </td>
                  </tr>
                ) : (
                  resources.map((res) => {
                    const tags = parseTags(res.tags);
                    const tagEntries = Object.entries(tags);
                    return (
                      <tr
                        key={res.resource_id}
                        style={{ transition: 'background 0.1s ease' }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLTableRowElement).style.background =
                            'rgba(7,182,213,0.05)';
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLTableRowElement).style.background = 'transparent';
                        }}
                      >
                        <td style={styles.td}>
                          <span style={{ fontWeight: 500 }}>
                            {res.name || <span style={{ color: COLORS.textMuted }}>--</span>}
                          </span>
                        </td>
                        <td style={{ ...styles.td, fontFamily: 'monospace', fontSize: 12 }}>
                          {res.native_id}
                        </td>
                        <td style={styles.td}>{res.region}</td>
                        <td style={styles.td}>
                          {tagEntries.length === 0 ? (
                            <span style={{ color: COLORS.textMuted }}>--</span>
                          ) : (
                            <span>
                              {tagEntries.slice(0, 3).map(([k, v]) => (
                                <span key={k} style={styles.tag}>
                                  {k}: {v}
                                </span>
                              ))}
                              {tagEntries.length > 3 && (
                                <span style={{ ...styles.tag, background: 'rgba(7,182,213,0.06)' }}>
                                  +{tagEntries.length - 3}
                                </span>
                              )}
                            </span>
                          )}
                        </td>
                        <td style={{ ...styles.td, fontSize: 12 }}>
                          {formatTimestamp(res.last_seen_ts)}
                        </td>
                        <td style={styles.td}>
                          <span style={styles.tierBadge(res.sync_tier)}>
                            T{res.sync_tier}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Sync status footer */}
      {latestJob && (
        <div style={styles.syncFooter}>
          <span>
            <span className="material-symbols-outlined" style={{ fontSize: 14, verticalAlign: 'middle', marginRight: 4 }}>
              info
            </span>
            Last sync:
          </span>
          <span>
            Status:{' '}
            <span style={{ color: syncStatusColor(latestJob.status), fontWeight: 600 }}>
              {latestJob.status}
            </span>
          </span>
          <span>Tier {latestJob.tier}</span>
          <span>Seen: {latestJob.items_seen}</span>
          <span>Created: {latestJob.items_created}</span>
          <span>Updated: {latestJob.items_updated}</span>
          <span>Deleted: {latestJob.items_deleted}</span>
          {latestJob.finished_at && (
            <span>Finished: {formatTimestamp(latestJob.finished_at)}</span>
          )}
        </div>
      )}

      <NetworkChatDrawer view="cloud-resources" />
    </div>
  );
}

export default CloudResourcesView;
