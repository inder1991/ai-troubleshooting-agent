import React, { useEffect, useState, useCallback } from 'react';
import {
  listVPCs,
  createVPC,
  listRouteTables,
  createRouteTable,
  listVPCPeerings,
  createVPCPeering,
  listTransitGateways,
  createTransitGateway,
  listVPNTunnels,
  createVPNTunnel,
  listDirectConnects,
  createDirectConnect,
} from '../../services/api';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

/* ---------- style constants ---------- */

const COLOR_BG = '#0f2023';
const COLOR_PRIMARY = '#07b6d5';

const styles = {
  page: {
    minHeight: '100vh',
    backgroundColor: COLOR_BG,
    color: '#e2e8f0',
    padding: '32px 40px',
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 28,
  } as React.CSSProperties,

  headerIcon: {
    fontFamily: 'Material Symbols Outlined',
    fontSize: 32,
    color: COLOR_PRIMARY,
  } as React.CSSProperties,

  headerTitle: {
    fontSize: 24,
    fontWeight: 700,
    letterSpacing: '-0.02em',
    color: '#f1f5f9',
  } as React.CSSProperties,

  tabBar: {
    display: 'flex',
    gap: 6,
    marginBottom: 24,
    flexWrap: 'wrap' as const,
  } as React.CSSProperties,

  tab: (active: boolean): React.CSSProperties => ({
    padding: '8px 18px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    transition: 'all 0.15s ease',
    backgroundColor: active ? 'rgba(7,182,213,0.15)' : 'transparent',
    color: active ? COLOR_PRIMARY : '#94a3b8',
  }),

  card: {
    backgroundColor: 'rgba(7,182,213,0.04)',
    border: '1px solid rgba(7,182,213,0.12)',
    borderRadius: 12,
    padding: 24,
  } as React.CSSProperties,

  addBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 18px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    backgroundColor: COLOR_PRIMARY,
    color: COLOR_BG,
    marginBottom: 20,
  } as React.CSSProperties,

  table: {
    width: '100%',
    borderCollapse: 'collapse' as const,
  } as React.CSSProperties,

  th: {
    textAlign: 'left' as const,
    padding: '10px 14px',
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    color: '#64748b',
    borderBottom: '1px solid rgba(7,182,213,0.10)',
  } as React.CSSProperties,

  td: {
    padding: '10px 14px',
    fontSize: 13,
    color: '#cbd5e1',
    borderBottom: '1px solid rgba(7,182,213,0.06)',
  } as React.CSSProperties,

  formRow: {
    display: 'flex',
    gap: 10,
    alignItems: 'flex-end',
    flexWrap: 'wrap' as const,
    marginBottom: 20,
  } as React.CSSProperties,

  formGroup: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
  } as React.CSSProperties,

  label: {
    fontSize: 11,
    fontWeight: 600,
    color: '#64748b',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  } as React.CSSProperties,

  input: {
    padding: '8px 12px',
    borderRadius: 6,
    border: '1px solid rgba(7,182,213,0.15)',
    backgroundColor: 'rgba(7,182,213,0.06)',
    color: '#e2e8f0',
    fontSize: 13,
    outline: 'none',
    minWidth: 140,
  } as React.CSSProperties,

  btnPrimary: {
    padding: '8px 18px',
    borderRadius: 6,
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    backgroundColor: COLOR_PRIMARY,
    color: COLOR_BG,
  } as React.CSSProperties,

  btnCancel: {
    padding: '8px 18px',
    borderRadius: 6,
    border: '1px solid rgba(7,182,213,0.15)',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    backgroundColor: 'transparent',
    color: '#94a3b8',
  } as React.CSSProperties,

  empty: {
    padding: 24,
    textAlign: 'center' as const,
    color: '#475569',
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
};

/* ---------- types ---------- */

type TabKey = 'vpcs' | 'routeTables' | 'peerings' | 'transitGateways' | 'vpnTunnels' | 'directConnects';

interface TabDef {
  key: TabKey;
  label: string;
}

const TABS: TabDef[] = [
  { key: 'vpcs', label: 'VPCs' },
  { key: 'routeTables', label: 'Route Tables' },
  { key: 'peerings', label: 'Peerings' },
  { key: 'transitGateways', label: 'Transit Gateways' },
  { key: 'vpnTunnels', label: 'VPN Tunnels' },
  { key: 'directConnects', label: 'Direct Connects' },
];

/* ---------- helper: form field ---------- */

function FormField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={styles.formGroup}>
      <span style={styles.label}>{label}</span>
      <input
        style={styles.input}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
      />
    </div>
  );
}

/* ---------- VPCs tab ---------- */

function VPCsTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', cidr: '', region: '', provider: '', status: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listVPCs();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load VPCs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createVPC(form);
      setForm({ name: '', cidr: '', region: '', provider: '', status: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create VPC');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add VPC
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <FormField label="CIDR" value={form.cidr} onChange={(v) => setForm({ ...form, cidr: v })} />
          <FormField label="Region" value={form.region} onChange={(v) => setForm({ ...form, region: v })} />
          <FormField label="Provider" value={form.provider} onChange={(v) => setForm({ ...form, provider: v })} />
          <FormField label="Status" value={form.status} onChange={(v) => setForm({ ...form, status: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No VPCs found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>CIDR</th>
              <th style={styles.th}>Region</th>
              <th style={styles.th}>Provider</th>
              <th style={styles.th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.name ?? '')}</td>
                <td style={styles.td}>{String(item.cidr ?? '')}</td>
                <td style={styles.td}>{String(item.region ?? '')}</td>
                <td style={styles.td}>{String(item.provider ?? '')}</td>
                <td style={styles.td}>{String(item.status ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- Route Tables tab ---------- */

function RouteTablesTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', vpc_id: '', routes_count: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listRouteTables();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load route tables');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createRouteTable({ ...form, routes_count: Number(form.routes_count) || 0 });
      setForm({ name: '', vpc_id: '', routes_count: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create route table');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add Route Table
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <FormField label="VPC ID" value={form.vpc_id} onChange={(v) => setForm({ ...form, vpc_id: v })} />
          <FormField label="Routes Count" value={form.routes_count} onChange={(v) => setForm({ ...form, routes_count: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No route tables found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>VPC ID</th>
              <th style={styles.th}>Routes Count</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.name ?? '')}</td>
                <td style={styles.td}>{String(item.vpc_id ?? '')}</td>
                <td style={styles.td}>{String(item.routes_count ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- Peerings tab ---------- */

function PeeringsTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ requester_vpc: '', accepter_vpc: '', status: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listVPCPeerings();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load peerings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createVPCPeering(form);
      setForm({ requester_vpc: '', accepter_vpc: '', status: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create peering');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add Peering
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Requester VPC" value={form.requester_vpc} onChange={(v) => setForm({ ...form, requester_vpc: v })} />
          <FormField label="Accepter VPC" value={form.accepter_vpc} onChange={(v) => setForm({ ...form, accepter_vpc: v })} />
          <FormField label="Status" value={form.status} onChange={(v) => setForm({ ...form, status: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No peerings found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Requester VPC</th>
              <th style={styles.th}>Accepter VPC</th>
              <th style={styles.th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.requester_vpc ?? '')}</td>
                <td style={styles.td}>{String(item.accepter_vpc ?? '')}</td>
                <td style={styles.td}>{String(item.status ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- Transit Gateways tab ---------- */

function TransitGatewaysTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', region: '', attachments: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listTransitGateways();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load transit gateways');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createTransitGateway({ ...form, attachments: Number(form.attachments) || 0 });
      setForm({ name: '', region: '', attachments: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create transit gateway');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add Transit Gateway
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <FormField label="Region" value={form.region} onChange={(v) => setForm({ ...form, region: v })} />
          <FormField label="Attachments" value={form.attachments} onChange={(v) => setForm({ ...form, attachments: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No transit gateways found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Region</th>
              <th style={styles.th}>Attachments</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.name ?? '')}</td>
                <td style={styles.td}>{String(item.region ?? '')}</td>
                <td style={styles.td}>{String(item.attachments ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- VPN Tunnels tab ---------- */

function VPNTunnelsTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', status: '', remote_ip: '', local_ip: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listVPNTunnels();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load VPN tunnels');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createVPNTunnel(form);
      setForm({ name: '', status: '', remote_ip: '', local_ip: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create VPN tunnel');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add VPN Tunnel
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <FormField label="Status" value={form.status} onChange={(v) => setForm({ ...form, status: v })} />
          <FormField label="Remote IP" value={form.remote_ip} onChange={(v) => setForm({ ...form, remote_ip: v })} />
          <FormField label="Local IP" value={form.local_ip} onChange={(v) => setForm({ ...form, local_ip: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No VPN tunnels found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Remote IP</th>
              <th style={styles.th}>Local IP</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.name ?? '')}</td>
                <td style={styles.td}>{String(item.status ?? '')}</td>
                <td style={styles.td}>{String(item.remote_ip ?? '')}</td>
                <td style={styles.td}>{String(item.local_ip ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- Direct Connects tab ---------- */

function DirectConnectsTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', bandwidth: '', location: '', status: '' });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const data = await listDirectConnects();
      setItems(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load direct connects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      setError('');
      await createDirectConnect(form);
      setForm({ name: '', bandwidth: '', location: '', status: '' });
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create direct connect');
    }
  };

  return (
    <div>
      {error && <div style={styles.error}>{error}</div>}
      <button style={styles.addBtn} onClick={() => setShowForm((s) => !s)}>
        <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
        Add Direct Connect
      </button>
      {showForm && (
        <div style={styles.formRow}>
          <FormField label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
          <FormField label="Bandwidth" value={form.bandwidth} onChange={(v) => setForm({ ...form, bandwidth: v })} />
          <FormField label="Location" value={form.location} onChange={(v) => setForm({ ...form, location: v })} />
          <FormField label="Status" value={form.status} onChange={(v) => setForm({ ...form, status: v })} />
          <button style={styles.btnPrimary} onClick={handleCreate}>Create</button>
          <button style={styles.btnCancel} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}
      {loading ? (
        <div style={styles.empty}>Loading...</div>
      ) : items.length === 0 ? (
        <div style={styles.empty}>No direct connects found.</div>
      ) : (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Bandwidth</th>
              <th style={styles.th}>Location</th>
              <th style={styles.th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td style={styles.td}>{String(item.name ?? '')}</td>
                <td style={styles.td}>{String(item.bandwidth ?? '')}</td>
                <td style={styles.td}>{String(item.location ?? '')}</td>
                <td style={styles.td}>{String(item.status ?? '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/* ---------- tab content map ---------- */

const TAB_CONTENT: Record<TabKey, React.FC> = {
  vpcs: VPCsTab,
  routeTables: RouteTablesTab,
  peerings: PeeringsTab,
  transitGateways: TransitGatewaysTab,
  vpnTunnels: VPNTunnelsTab,
  directConnects: DirectConnectsTab,
};

/* ---------- main component ---------- */

export default function CloudResourcesView() {
  const [activeTab, setActiveTab] = useState<TabKey>('vpcs');
  const ActiveContent = TAB_CONTENT[activeTab];

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <span className="material-symbols-outlined" style={styles.headerIcon}>
          cloud
        </span>
        <h1 style={styles.headerTitle}>Cloud Resources</h1>
      </div>

      {/* Tab bar */}
      <div style={styles.tabBar}>
        {TABS.map((tab) => (
          <button
            key={tab.key}
            style={styles.tab(activeTab === tab.key)}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active tab content */}
      <div style={styles.card}>
        <ActiveContent />
      </div>
      <NetworkChatDrawer view="cloud-resources" />
    </div>
  );
}
