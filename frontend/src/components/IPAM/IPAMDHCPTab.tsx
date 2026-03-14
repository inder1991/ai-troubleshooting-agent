import React, { useState, useEffect } from 'react';
import { fetchDHCPScopes, createDHCPScope, deleteDHCPScope } from '../../services/api';
import type { DHCPScope } from '../../types';

export default function IPAMDHCPTab() {
  const [scopes, setScopes] = useState<DHCPScope[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', scope_cidr: '', server_ip: '', subnet_id: '' });

  const loadScopes = () => {
    setLoading(true);
    fetchDHCPScopes()
      .then(data => setScopes(data.scopes || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadScopes(); }, []);

  const handleCreate = async () => {
    if (!form.name || !form.scope_cidr) return;
    await createDHCPScope(form);
    setShowCreate(false);
    setForm({ name: '', scope_cidr: '', server_ip: '', subnet_id: '' });
    loadScopes();
  };

  const handleDelete = async (id: string) => {
    await deleteDHCPScope(id);
    loadScopes();
  };

  const getUtilPct = (s: DHCPScope) =>
    s.total_leases > 0 ? Math.round((s.active_leases / s.total_leases) * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white">DHCP Scopes</h3>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-sm transition"
        >
          {showCreate ? 'Cancel' : 'Add Scope'}
        </button>
      </div>

      {showCreate && (
        <div className="bg-gray-800/50 rounded-lg p-4 space-y-3 border border-gray-700">
          <div className="grid grid-cols-2 gap-3">
            <input placeholder="Scope Name" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
            <input placeholder="CIDR (e.g. 10.0.1.0/24)" value={form.scope_cidr} onChange={e => setForm(f => ({...f, scope_cidr: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono" />
            <input placeholder="DHCP Server IP" value={form.server_ip} onChange={e => setForm(f => ({...f, server_ip: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono" />
            <input placeholder="Linked Subnet ID (optional)" value={form.subnet_id} onChange={e => setForm(f => ({...f, subnet_id: e.target.value}))}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white" />
          </div>
          <button onClick={handleCreate} className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm">Create</button>
        </div>
      )}

      {loading ? (
        <div className="text-gray-400 text-center py-8">Loading DHCP scopes...</div>
      ) : scopes.length === 0 ? (
        <div className="text-gray-500 text-center py-8">No DHCP scopes configured</div>
      ) : (
        <div className="space-y-2">
          {scopes.map(s => (
            <div key={s.id} className="bg-gray-800/50 rounded-lg p-4 border border-gray-700 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-white font-medium text-sm">{s.name}</span>
                  <span className="text-gray-500 font-mono text-xs">{s.scope_cidr}</span>
                  {s.server_ip && <span className="text-gray-600 text-xs">Server: {s.server_ip}</span>}
                </div>
                <div className="flex items-center gap-4 mt-2">
                  <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        getUtilPct(s) > 90 ? 'bg-red-500' : getUtilPct(s) > 70 ? 'bg-yellow-500' : 'bg-emerald-500'
                      }`}
                      style={{ width: `${getUtilPct(s)}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 min-w-[80px]">
                    {s.active_leases}/{s.total_leases} ({getUtilPct(s)}%)
                  </span>
                </div>
              </div>
              <button onClick={() => handleDelete(s.id)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
