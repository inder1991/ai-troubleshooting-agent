import React, { useState, useEffect, useCallback, useMemo } from 'react';
import type { AdapterInstanceStatus } from '../../types';
import { listAdapterInstances, deleteAdapterInstance, refreshAdapterInstance } from '../../services/api';
import AdapterInstanceForm from './AdapterInstanceForm';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

const STATUS_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  connected: { bg: 'rgba(34,197,94,0.15)', text: '#22c55e', label: 'Connected' },
  stale: { bg: 'rgba(245,158,11,0.15)', text: '#f59e0b', label: 'Stale' },
  auth_failed: { bg: 'rgba(239,68,68,0.15)', text: '#ef4444', label: 'Auth Failed' },
  unreachable: { bg: 'rgba(239,68,68,0.15)', text: '#ef4444', label: 'Unreachable' },
  not_configured: { bg: 'rgba(148,163,184,0.15)', text: '#94a3b8', label: 'Not Configured' },
};

const VENDOR_LABELS: Record<string, string> = {
  palo_alto: 'Palo Alto',
  aws_sg: 'AWS SG',
  azure_nsg: 'Azure NSG',
  oracle_nsg: 'Oracle NSG',
  zscaler: 'Zscaler',
};

const NetworkAdaptersView: React.FC = () => {
  const [adapters, setAdapters] = useState<AdapterInstanceStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editInstance, setEditInstance] = useState<AdapterInstanceStatus | null>(null);
  const [refreshingId, setRefreshingId] = useState<string | null>(null);

  const loadAdapters = useCallback(async () => {
    try {
      const data = await listAdapterInstances();
      setAdapters(data.adapters as AdapterInstanceStatus[]);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load adapters');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAdapters();
    const interval = setInterval(loadAdapters, 30000);
    return () => clearInterval(interval);
  }, [loadAdapters]);

  const filtered = useMemo(() => {
    if (!search) return adapters;
    const q = search.toLowerCase();
    return adapters.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        a.vendor.toLowerCase().includes(q) ||
        a.api_endpoint.toLowerCase().includes(q) ||
        (a.status || '').toLowerCase().includes(q)
    );
  }, [adapters, search]);

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this adapter instance?')) return;
    try {
      await deleteAdapterInstance(id);
      await loadAdapters();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleRefresh = async (id: string) => {
    setRefreshingId(id);
    try {
      await refreshAdapterInstance(id);
      await loadAdapters();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed');
    } finally {
      setRefreshingId(null);
    }
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditInstance(null);
    loadAdapters();
  };

  const summary = useMemo(() => {
    const total = adapters.length;
    const connected = adapters.filter((a) => a.status === 'connected').length;
    const issues = adapters.filter((a) => ['stale', 'unreachable', 'auth_failed'].includes(a.status)).length;
    return { total, connected, issues };
  }, [adapters]);

  const thClass = 'text-left text-xs font-semibold text-slate-400 uppercase tracking-wider px-4 py-3';
  const tdClass = 'px-4 py-3 text-sm font-mono';

  return (
    <div className="flex-1 overflow-auto p-6" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Network Adapters</h1>
          <p className="text-sm text-slate-400 mt-1">Manage firewall adapter instances across vendors</p>
        </div>
        <button
          onClick={() => { setEditInstance(null); setShowForm(true); }}
          className="flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023' }}
        >
          <span className="material-symbols-outlined text-base">add</span>
          Add Adapter
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'Total Instances', value: summary.total, color: '#07b6d5' },
          { label: 'Connected', value: summary.connected, color: '#22c55e' },
          { label: 'Issues', value: summary.issues, color: summary.issues > 0 ? '#f59e0b' : '#94a3b8' },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-lg border p-4"
            style={{ backgroundColor: 'rgba(15,32,35,0.8)', borderColor: '#224349' }}
          >
            <p className="text-xs text-slate-400 uppercase tracking-wider">{card.label}</p>
            <p className="text-2xl font-bold font-mono mt-1" style={{ color: card.color }}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          placeholder="Search adapters..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-sm px-3 py-2 rounded-lg border text-sm font-mono text-white placeholder-slate-500 focus:outline-none focus:border-[#07b6d5]"
          style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}
        />
      </div>

      {error && (
        <div className="mb-4 px-4 py-2 rounded border text-sm" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: '#ef4444', color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading adapters...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12">
          <span className="material-symbols-outlined text-4xl text-slate-600 mb-2 block">
            settings_input_component
          </span>
          <p className="text-slate-400 text-sm">
            {adapters.length === 0 ? 'No adapters configured yet. Click "Add Adapter" to get started.' : 'No adapters match your search.'}
          </p>
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden" style={{ borderColor: '#224349' }}>
          <table className="w-full">
            <thead style={{ backgroundColor: '#0a1214' }}>
              <tr>
                <th className={thClass}>Label</th>
                <th className={thClass}>Vendor</th>
                <th className={thClass}>Endpoint</th>
                <th className={thClass}>Status</th>
                <th className={thClass}>Device Groups</th>
                <th className={thClass}>Last Refresh</th>
                <th className={thClass}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((adapter) => {
                const statusStyle = STATUS_COLORS[adapter.status] || STATUS_COLORS.not_configured;
                return (
                  <tr
                    key={adapter.instance_id}
                    className="border-t hover:bg-white/[0.02] transition-colors"
                    style={{ borderColor: '#224349' }}
                  >
                    <td className={`${tdClass} text-white font-semibold`}>{adapter.label}</td>
                    <td className={tdClass}>
                      <span className="px-2 py-0.5 rounded text-xs font-semibold" style={{ backgroundColor: 'rgba(7,182,213,0.1)', color: '#07b6d5' }}>
                        {VENDOR_LABELS[adapter.vendor] || adapter.vendor}
                      </span>
                    </td>
                    <td className={`${tdClass} text-slate-300`}>
                      {adapter.api_endpoint ? (
                        <span className="truncate max-w-[200px] inline-block">{adapter.api_endpoint}</span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className={tdClass}>
                      <span className="px-2 py-0.5 rounded text-xs font-semibold" style={{ backgroundColor: statusStyle.bg, color: statusStyle.text }}>
                        {statusStyle.label}
                      </span>
                    </td>
                    <td className={`${tdClass} text-slate-300`}>
                      {adapter.device_groups && adapter.device_groups.length > 0
                        ? adapter.device_groups.join(', ')
                        : <span className="text-slate-500">—</span>}
                    </td>
                    <td className={`${tdClass} text-slate-400`}>
                      {adapter.last_refresh
                        ? new Date(adapter.last_refresh).toLocaleTimeString()
                        : <span className="text-slate-500">Never</span>}
                    </td>
                    <td className={tdClass}>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => { setEditInstance(adapter); setShowForm(true); }}
                          className="p-1.5 rounded hover:bg-white/5 transition-colors text-slate-400 hover:text-[#07b6d5]"
                          title="Edit"
                        >
                          <span className="material-symbols-outlined text-base">edit</span>
                        </button>
                        <button
                          onClick={() => handleRefresh(adapter.instance_id)}
                          disabled={refreshingId === adapter.instance_id}
                          className="p-1.5 rounded hover:bg-white/5 transition-colors text-slate-400 hover:text-[#22c55e] disabled:opacity-40"
                          title="Refresh"
                        >
                          <span
                            className={`material-symbols-outlined text-base ${refreshingId === adapter.instance_id ? 'animate-spin' : ''}`}
                          >
                            refresh
                          </span>
                        </button>
                        <button
                          onClick={() => handleDelete(adapter.instance_id)}
                          className="p-1.5 rounded hover:bg-white/5 transition-colors text-slate-400 hover:text-[#ef4444]"
                          title="Delete"
                        >
                          <span className="material-symbols-outlined text-base">delete</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal Form */}
      {showForm && (
        <AdapterInstanceForm
          instance={editInstance}
          onClose={handleFormClose}
        />
      )}
      <NetworkChatDrawer view="network-adapters" />
    </div>
  );
};

export default NetworkAdaptersView;
