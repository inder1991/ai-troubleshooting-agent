import React, { useState, useEffect, useCallback } from 'react';
import {
  listFirewallRules,
  createFirewallRule,
  listNATRules,
  createNATRule,
  listNACLs,
  createNACL,
  listLoadBalancers,
  createLoadBalancer,
  listSecVLANs,
  createSecVLAN,
  listMPLSCircuits,
  createMPLSCircuit,
  listComplianceZones,
  createComplianceZone,
} from '../../services/api';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

// ---------------------------------------------------------------------------
// Style constants
// ---------------------------------------------------------------------------

const COLORS = {
  bg: '#0f2023',
  primary: '#07b6d5',
  cardBg: 'rgba(7,182,213,0.04)',
  cardBorder: 'rgba(7,182,213,0.12)',
  textPrimary: '#e2e8f0',
  textSecondary: '#94a3b8',
  inputBg: 'rgba(7,182,213,0.06)',
  inputBorder: 'rgba(7,182,213,0.18)',
  danger: '#ef4444',
} as const;

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
  } as React.CSSProperties,
  tabBar: {
    display: 'flex',
    gap: 4,
    borderBottom: `1px solid ${COLORS.cardBorder}`,
    marginBottom: 20,
    overflowX: 'auto' as const,
  } as React.CSSProperties,
  tab: (active: boolean): React.CSSProperties => ({
    padding: '10px 18px',
    fontSize: 13,
    fontWeight: active ? 600 : 400,
    color: active ? COLORS.primary : COLORS.textSecondary,
    background: active ? 'rgba(7,182,213,0.08)' : 'transparent',
    border: 'none',
    borderBottom: active ? `2px solid ${COLORS.primary}` : '2px solid transparent',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all 0.15s ease',
  }),
  card: {
    background: COLORS.cardBg,
    border: `1px solid ${COLORS.cardBorder}`,
    borderRadius: 8,
    padding: 20,
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
    borderBottom: `1px solid rgba(7,182,213,0.06)`,
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
  btnSecondary: {
    background: 'transparent',
    color: COLORS.textSecondary,
    border: `1px solid ${COLORS.cardBorder}`,
    borderRadius: 6,
    padding: '8px 18px',
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'opacity 0.15s ease',
  } as React.CSSProperties,
  formRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 10,
    alignItems: 'flex-end',
    marginTop: 16,
  } as React.CSSProperties,
  formField: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
    flex: '1 1 140px',
  } as React.CSSProperties,
  label: {
    fontSize: 11,
    fontWeight: 500,
    color: COLORS.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  } as React.CSSProperties,
  input: {
    background: COLORS.inputBg,
    border: `1px solid ${COLORS.inputBorder}`,
    borderRadius: 5,
    padding: '7px 10px',
    fontSize: 13,
    color: COLORS.textPrimary,
    outline: 'none',
  } as React.CSSProperties,
  select: {
    background: COLORS.inputBg,
    border: `1px solid ${COLORS.inputBorder}`,
    borderRadius: 5,
    padding: '7px 10px',
    fontSize: 13,
    color: COLORS.textPrimary,
    outline: 'none',
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
  error: {
    color: COLORS.danger,
    fontSize: 13,
    marginTop: 8,
  } as React.CSSProperties,
  empty: {
    textAlign: 'center' as const,
    padding: '32px 0',
    color: COLORS.textSecondary,
    fontSize: 13,
  } as React.CSSProperties,
};

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

interface FieldDef {
  key: string;
  label: string;
  type: 'text' | 'number' | 'select';
  options?: string[];
  placeholder?: string;
}

interface TabDef {
  id: string;
  label: string;
  columns: string[];
  fields: FieldDef[];
  listFn: () => Promise<unknown>;
  createFn: (data: Record<string, unknown>) => Promise<unknown>;
}

const TABS: TabDef[] = [
  {
    id: 'firewall',
    label: 'Firewall Rules',
    columns: ['Name', 'Action', 'Source', 'Destination', 'Port', 'Protocol', 'Priority'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'Rule name' },
      { key: 'action', label: 'Action', type: 'select', options: ['allow', 'deny'] },
      { key: 'source', label: 'Source', type: 'text', placeholder: '0.0.0.0/0' },
      { key: 'destination', label: 'Destination', type: 'text', placeholder: '10.0.0.0/8' },
      { key: 'port', label: 'Port', type: 'text', placeholder: '443' },
      { key: 'protocol', label: 'Protocol', type: 'text', placeholder: 'tcp' },
      { key: 'priority', label: 'Priority', type: 'number', placeholder: '100' },
    ],
    listFn: listFirewallRules,
    createFn: createFirewallRule,
  },
  {
    id: 'nat',
    label: 'NAT Rules',
    columns: ['Name', 'Type', 'Source', 'Destination', 'Translated'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'NAT rule name' },
      { key: 'type', label: 'Type', type: 'select', options: ['snat', 'dnat'] },
      { key: 'source', label: 'Source', type: 'text', placeholder: '10.0.1.0/24' },
      { key: 'destination', label: 'Destination', type: 'text', placeholder: '0.0.0.0/0' },
      { key: 'translated', label: 'Translated', type: 'text', placeholder: '203.0.113.1' },
    ],
    listFn: listNATRules,
    createFn: createNATRule,
  },
  {
    id: 'nacl',
    label: 'NACLs',
    columns: ['Name', 'VPC ID', 'Rules Count'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'NACL name' },
      { key: 'vpc_id', label: 'VPC ID', type: 'text', placeholder: 'vpc-abc123' },
      { key: 'rules_count', label: 'Rules Count', type: 'number', placeholder: '0' },
    ],
    listFn: listNACLs,
    createFn: createNACL,
  },
  {
    id: 'lb',
    label: 'Load Balancers',
    columns: ['Name', 'Type', 'DNS Name', 'Status', 'Target Groups'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'LB name' },
      { key: 'type', label: 'Type', type: 'select', options: ['alb', 'nlb', 'clb'] },
      { key: 'dns_name', label: 'DNS Name', type: 'text', placeholder: 'lb.example.com' },
      { key: 'status', label: 'Status', type: 'text', placeholder: 'active' },
      { key: 'target_groups', label: 'Target Groups', type: 'number', placeholder: '1' },
    ],
    listFn: listLoadBalancers,
    createFn: createLoadBalancer,
  },
  {
    id: 'vlan',
    label: 'VLANs',
    columns: ['VLAN ID', 'Name', 'CIDR', 'Description'],
    fields: [
      { key: 'vlan_id', label: 'VLAN ID', type: 'number', placeholder: '100' },
      { key: 'name', label: 'Name', type: 'text', placeholder: 'VLAN name' },
      { key: 'cidr', label: 'CIDR', type: 'text', placeholder: '10.100.0.0/24' },
      { key: 'description', label: 'Description', type: 'text', placeholder: 'Description' },
    ],
    listFn: listSecVLANs,
    createFn: createSecVLAN,
  },
  {
    id: 'mpls',
    label: 'MPLS',
    columns: ['Name', 'Label', 'Bandwidth', 'Status', 'Endpoints'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'Circuit name' },
      { key: 'label', label: 'Label', type: 'number', placeholder: '1000' },
      { key: 'bandwidth', label: 'Bandwidth', type: 'text', placeholder: '1Gbps' },
      { key: 'status', label: 'Status', type: 'text', placeholder: 'active' },
      { key: 'endpoints', label: 'Endpoints', type: 'text', placeholder: 'A,B' },
    ],
    listFn: listMPLSCircuits,
    createFn: createMPLSCircuit,
  },
  {
    id: 'compliance',
    label: 'Compliance Zones',
    columns: ['Name', 'Level', 'Description', 'Device Count'],
    fields: [
      { key: 'name', label: 'Name', type: 'text', placeholder: 'Zone name' },
      { key: 'level', label: 'Level', type: 'text', placeholder: 'high' },
      { key: 'description', label: 'Description', type: 'text', placeholder: 'Description' },
      { key: 'device_count', label: 'Device Count', type: 'number', placeholder: '0' },
    ],
    listFn: listComplianceZones,
    createFn: createComplianceZone,
  },
];

// ---------------------------------------------------------------------------
// Column key mapping: column header -> data key
// ---------------------------------------------------------------------------

function colToKey(col: string): string {
  const map: Record<string, string> = {
    'Name': 'name',
    'Action': 'action',
    'Source': 'source',
    'Destination': 'destination',
    'Port': 'port',
    'Protocol': 'protocol',
    'Priority': 'priority',
    'Type': 'type',
    'Translated': 'translated',
    'VPC ID': 'vpc_id',
    'Rules Count': 'rules_count',
    'DNS Name': 'dns_name',
    'Status': 'status',
    'Target Groups': 'target_groups',
    'VLAN ID': 'vlan_id',
    'CIDR': 'cidr',
    'Description': 'description',
    'Label': 'label',
    'Bandwidth': 'bandwidth',
    'Endpoints': 'endpoints',
    'Level': 'level',
    'Device Count': 'device_count',
  };
  return map[col] ?? col.toLowerCase().replace(/\s+/g, '_');
}

// ---------------------------------------------------------------------------
// Generic resource tab component
// ---------------------------------------------------------------------------

interface ResourceTabProps {
  tab: TabDef;
}

function ResourceTab({ tab }: ResourceTabProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await tab.listFn();
      const items = Array.isArray(data) ? data : (data as Record<string, unknown>)?.items ?? (data as Record<string, unknown>)?.data ?? [];
      setRows(items as Record<string, unknown>[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    const empty: Record<string, string> = {};
    tab.fields.forEach((f) => {
      empty[f.key] = f.type === 'select' && f.options?.length ? f.options[0] : '';
    });
    setFormData(empty);
  };

  const handleToggleForm = () => {
    if (!showForm) resetForm();
    setShowForm((v) => !v);
  };

  const handleChange = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {};
      tab.fields.forEach((f) => {
        const raw = formData[f.key] ?? '';
        payload[f.key] = f.type === 'number' ? (raw === '' ? 0 : Number(raw)) : raw;
      });
      await tab.createFn(payload);
      setShowForm(false);
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create resource');
    } finally {
      setSubmitting(false);
    }
  };

  const renderCellValue = (value: unknown): string => {
    if (value === null || value === undefined) return '--';
    if (Array.isArray(value)) return value.join(', ');
    return String(value);
  };

  return (
    <div style={styles.card}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <span style={styles.count}>
          {loading ? 'Loading...' : `${rows.length} record${rows.length !== 1 ? 's' : ''}`}
        </span>
        <button
          style={showForm ? styles.btnSecondary : styles.btnPrimary}
          onClick={handleToggleForm}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
            {showForm ? 'close' : 'add'}
          </span>
          {showForm ? 'Cancel' : 'Add'}
        </button>
      </div>

      {/* Inline add form */}
      {showForm && (
        <div
          style={{
            background: 'rgba(7,182,213,0.03)',
            border: `1px solid ${COLORS.cardBorder}`,
            borderRadius: 6,
            padding: 16,
            marginBottom: 16,
          }}
        >
          <div style={styles.formRow}>
            {tab.fields.map((f) => (
              <div key={f.key} style={styles.formField}>
                <label style={styles.label}>{f.label}</label>
                {f.type === 'select' ? (
                  <select
                    style={styles.select}
                    value={formData[f.key] ?? ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                  >
                    {f.options?.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    style={styles.input}
                    type={f.type === 'number' ? 'number' : 'text'}
                    placeholder={f.placeholder}
                    value={formData[f.key] ?? ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                  />
                )}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            <button
              style={{
                ...styles.btnPrimary,
                opacity: submitting ? 0.6 : 1,
                pointerEvents: submitting ? 'none' : 'auto',
              }}
              onClick={handleSubmit}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                check
              </span>
              {submitting ? 'Saving...' : 'Save'}
            </button>
            <button style={styles.btnSecondary} onClick={handleToggleForm}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && <div style={styles.error}>{error}</div>}

      {/* Table */}
      {!loading && rows.length === 0 && !error ? (
        <div style={styles.empty}>No records found. Click "Add" to create one.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={styles.table}>
            <thead>
              <tr>
                {tab.columns.map((col) => (
                  <th key={col} style={styles.th}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td
                    colSpan={tab.columns.length}
                    style={{ ...styles.td, textAlign: 'center', color: COLORS.textSecondary }}
                  >
                    Loading...
                  </td>
                </tr>
              ) : (
                rows.map((row, idx) => (
                  <tr
                    key={(row.id as string) ?? idx}
                    style={{
                      transition: 'background 0.1s ease',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background =
                        'rgba(7,182,213,0.05)';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLTableRowElement).style.background = 'transparent';
                    }}
                  >
                    {tab.columns.map((col) => (
                      <td key={col} style={styles.td}>
                        {renderCellValue(row[colToKey(col)])}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const SecurityResourcesView: React.FC = () => {
  const [activeTab, setActiveTab] = useState(TABS[0].id);
  const currentTab = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <span className="material-symbols-outlined" style={styles.headerIcon}>
          security
        </span>
        <h1 style={styles.headerTitle}>Security Resources</h1>
      </div>

      {/* Tab bar */}
      <div style={styles.tabBar}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            style={styles.tab(activeTab === tab.id)}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active tab content -- keyed to force remount on tab switch */}
      <ResourceTab key={currentTab.id} tab={currentTab} />
      <NetworkChatDrawer view="security-resources" />
    </div>
  );
};

export default SecurityResourcesView;
