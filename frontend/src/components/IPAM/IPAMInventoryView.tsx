import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { fetchIPAMDevices, fetchIPAMSubnets } from '../../services/api';
import IPAMUploadDialog from '../TopologyEditor/IPAMUploadDialog';

interface IPAMDevice {
  name: string;
  management_ip: string;
  device_type: string;
  zone_id: string;
  vlan_id: number;
  subnet: string;
  description: string;
  vendor: string;
  location: string;
}

interface IPAMSubnet {
  cidr: string;
  zone_id: string;
  vlan_id: number;
  gateway_ip: string;
  device_count: number;
  description: string;
  site: string;
}

const IPAMInventoryView: React.FC = () => {
  const [devices, setDevices] = useState<IPAMDevice[]>([]);
  const [subnets, setSubnets] = useState<IPAMSubnet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'devices' | 'subnets'>('devices');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [devRes, subRes] = await Promise.all([
        fetchIPAMDevices().catch(() => ({ devices: [] })),
        fetchIPAMSubnets().catch(() => ({ subnets: [] })),
      ]);
      setDevices(devRes.devices || devRes || []);
      setSubnets(subRes.subnets || subRes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load IPAM data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleImported = useCallback((_data: { nodes: unknown[]; edges: unknown[] }) => {
    setUploadOpen(false);
    loadData();
  }, [loadData]);

  const lowerSearch = search.toLowerCase();

  const filteredDevices = useMemo(() => {
    if (!lowerSearch) return devices;
    return devices.filter((d) =>
      [d.name, d.management_ip, d.device_type, d.zone_id, String(d.vlan_id), d.subnet, d.description, d.vendor, d.location]
        .some((v) => v?.toLowerCase().includes(lowerSearch))
    );
  }, [devices, lowerSearch]);

  const filteredSubnets = useMemo(() => {
    if (!lowerSearch) return subnets;
    return subnets.filter((s) =>
      [s.cidr, s.zone_id, String(s.vlan_id), s.gateway_ip, s.description, s.site]
        .some((v) => v?.toLowerCase().includes(lowerSearch))
    );
  }, [subnets, lowerSearch]);

  const thClass = 'text-left text-[11px] font-semibold uppercase tracking-wider py-2.5 px-3 border-b';
  const tdClass = 'py-2 px-3 text-[13px] font-mono border-b';

  return (
    <div className="flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: '#224349' }}>
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>dns</span>
          <h1 className="text-xl font-bold text-white">IPAM Inventory</h1>
        </div>
        <button
          onClick={() => setUploadOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-colors"
          style={{ backgroundColor: '#07b6d5', color: '#0f2023' }}
        >
          <span className="material-symbols-outlined text-[18px]" style={{ fontFamily: 'Material Symbols Outlined' }}>upload_file</span>
          Import IPAM
        </button>
      </div>

      {/* Summary Cards */}
      <div className="flex gap-4 px-6 py-4">
        <div className="flex-1 rounded-lg border px-4 py-3" style={{ backgroundColor: '#0a1a1e', borderColor: '#224349' }}>
          <div className="text-[11px] uppercase tracking-wider mb-1" style={{ color: '#64748b' }}>Total Devices</div>
          <div className="text-2xl font-bold font-mono" style={{ color: '#07b6d5' }}>{devices.length}</div>
        </div>
        <div className="flex-1 rounded-lg border px-4 py-3" style={{ backgroundColor: '#0a1a1e', borderColor: '#224349' }}>
          <div className="text-[11px] uppercase tracking-wider mb-1" style={{ color: '#64748b' }}>Total Subnets</div>
          <div className="text-2xl font-bold font-mono" style={{ color: '#07b6d5' }}>{subnets.length}</div>
        </div>
      </div>

      {/* Search + Tabs */}
      <div className="flex items-center gap-4 px-6 pb-3">
        <div className="relative flex-1 max-w-sm">
          <span
            className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px]"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#64748b' }}
          >search</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter devices and subnets..."
            className="w-full pl-10 pr-3 py-2 rounded-lg border text-sm font-mono outline-none focus:border-[#07b6d5]"
            style={{ backgroundColor: '#0a1a1e', borderColor: '#224349', color: '#e2e8f0' }}
          />
        </div>
        <div className="flex gap-1 rounded-lg p-0.5" style={{ backgroundColor: '#0a1a1e' }}>
          {(['devices', 'subnets'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize"
              style={activeTab === tab
                ? { backgroundColor: 'rgba(7,182,213,0.15)', color: '#07b6d5' }
                : { color: '#64748b' }
              }
            >
              {tab} ({tab === 'devices' ? filteredDevices.length : filteredSubnets.length})
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto px-6 pb-4">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-slate-500 text-sm">Loading IPAM data...</div>
        ) : error ? (
          <div className="flex items-center justify-center h-40 text-red-400 text-sm">{error}</div>
        ) : activeTab === 'devices' ? (
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ color: '#64748b', borderColor: '#224349' }}>
                <th className={thClass}>Name</th>
                <th className={thClass}>IP</th>
                <th className={thClass}>Type</th>
                <th className={thClass}>Zone</th>
                <th className={thClass}>VLAN</th>
                <th className={thClass}>Subnet</th>
                <th className={thClass}>Description</th>
              </tr>
            </thead>
            <tbody>
              {filteredDevices.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-500 text-sm">
                    {devices.length === 0 ? 'No devices imported yet. Click "Import IPAM" to get started.' : 'No devices match your filter.'}
                  </td>
                </tr>
              ) : (
                filteredDevices.map((d, i) => (
                  <tr key={i} className="hover:bg-[#162a2e] transition-colors" style={{ borderColor: '#224349' }}>
                    <td className={tdClass} style={{ color: '#e2e8f0' }}>{d.name}</td>
                    <td className={tdClass} style={{ color: '#07b6d5' }}>{d.management_ip}</td>
                    <td className={tdClass}>
                      <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold" style={{ backgroundColor: 'rgba(7,182,213,0.12)', color: '#07b6d5' }}>
                        {d.device_type}
                      </span>
                    </td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{d.zone_id || '-'}</td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{d.vlan_id || '-'}</td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{d.subnet || '-'}</td>
                    <td className={tdClass} style={{ color: '#64748b' }}>{d.description || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        ) : (
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ color: '#64748b', borderColor: '#224349' }}>
                <th className={thClass}>CIDR</th>
                <th className={thClass}>Zone</th>
                <th className={thClass}>VLAN</th>
                <th className={thClass}>Gateway</th>
                <th className={thClass}>Devices</th>
                <th className={thClass}>Description</th>
              </tr>
            </thead>
            <tbody>
              {filteredSubnets.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-500 text-sm">
                    {subnets.length === 0 ? 'No subnets imported yet.' : 'No subnets match your filter.'}
                  </td>
                </tr>
              ) : (
                filteredSubnets.map((s, i) => (
                  <tr key={i} className="hover:bg-[#162a2e] transition-colors" style={{ borderColor: '#224349' }}>
                    <td className={tdClass} style={{ color: '#07b6d5' }}>{s.cidr}</td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{s.zone_id || '-'}</td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{s.vlan_id || '-'}</td>
                    <td className={tdClass} style={{ color: '#e2e8f0' }}>{s.gateway_ip || '-'}</td>
                    <td className={tdClass} style={{ color: '#94a3b8' }}>{s.device_count ?? '-'}</td>
                    <td className={tdClass} style={{ color: '#64748b' }}>{s.description || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Upload Dialog */}
      <IPAMUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onImported={handleImported}
      />
    </div>
  );
};

export default IPAMInventoryView;
