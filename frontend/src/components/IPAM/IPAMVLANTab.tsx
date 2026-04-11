import React, { useEffect, useState } from 'react';
import type { VLANInfo } from '../../types';
import { fetchVLANs, fetchVLANInterfaces } from '../../services/api';

interface InterfaceRow {
  id: string;
  name: string;
  ip: string;
  device_id: string;
  zone_id: string;
}

export default function IPAMVLANTab() {
  const [vlans, setVlans] = useState<VLANInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedVlan, setSelectedVlan] = useState<VLANInfo | null>(null);
  const [interfaces, setInterfaces] = useState<InterfaceRow[]>([]);
  const [ifaceLoading, setIfaceLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchVLANs()
      .then((res) => setVlans(res.vlans || []))
      .catch(() => setVlans([]))
      .finally(() => setLoading(false));
  }, []);

  const handleSelectVlan = async (vlan: VLANInfo) => {
    setSelectedVlan(vlan);
    setIfaceLoading(true);
    try {
      const res = await fetchVLANInterfaces(vlan.id);
      setInterfaces(res.interfaces || []);
    } catch {
      setInterfaces([]);
    }
    setIfaceLoading(false);
  };

  if (loading) {
    return <div className="text-center text-slate-400 py-8 text-sm">Loading VLANs...</div>;
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* VLAN list */}
      <div>
        <h3 className="text-sm font-semibold text-slate-200 mb-3">VLANs ({vlans.length})</h3>
        {vlans.length === 0 ? (
          <div className="text-sm text-slate-400 py-4">No VLANs configured.</div>
        ) : (
          <div className="max-h-[500px] overflow-y-auto space-y-1">
            {vlans.map((vlan) => (
              <button
                key={vlan.id}
                onClick={() => handleSelectVlan(vlan)}
                className={`w-full text-left flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                  selectedVlan?.id === vlan.id
                    ? 'bg-[#1e3a40] border-l-2 border-amber-400'
                    : 'hover:bg-[#1e3a40]/50'
                }`}
              >
                <span className="font-mono text-amber-300 w-12 text-right">{vlan.vlan_number}</span>
                <span className="text-slate-300 flex-1 truncate">{vlan.name || '-'}</span>
                {vlan.vrf_id && vlan.vrf_id !== 'default' && (
                  <span className="text-body-xs px-1.5 py-0.5 rounded bg-purple-900/30 text-purple-300">
                    {vlan.vrf_id}
                  </span>
                )}
                {vlan.subnet_ids.length > 0 && (
                  <span className="text-body-xs text-slate-400">{vlan.subnet_ids.length} subnets</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* VLAN detail */}
      <div>
        {selectedVlan ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-sm text-slate-400">lan</span>
              <h3 className="text-sm font-semibold text-slate-200">
                VLAN {selectedVlan.vlan_number}: {selectedVlan.name}
              </h3>
            </div>
            {selectedVlan.description && (
              <p className="text-xs text-slate-400">{selectedVlan.description}</p>
            )}
            <div className="flex items-center gap-4 text-xs text-slate-400">
              {selectedVlan.vrf_id && <span>VRF: {selectedVlan.vrf_id}</span>}
              {selectedVlan.site_id && <span>Site: {selectedVlan.site_id}</span>}
            </div>

            {/* Linked subnets */}
            {selectedVlan.subnet_ids.length > 0 && (
              <div>
                <h4 className="text-xs text-slate-400 uppercase tracking-wider mb-1">Linked Subnets</h4>
                <div className="space-y-1">
                  {selectedVlan.subnet_ids.map((sid) => (
                    <div key={sid} className="text-xs text-slate-300 px-2 py-1 bg-[#1a1814] rounded">
                      {sid}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Interfaces */}
            <div>
              <h4 className="text-xs text-slate-400 uppercase tracking-wider mb-1">
                Interfaces ({interfaces.length})
              </h4>
              {ifaceLoading ? (
                <div className="text-xs text-slate-400 py-2">Loading...</div>
              ) : interfaces.length === 0 ? (
                <div className="text-xs text-slate-400 py-2">No interfaces on this VLAN.</div>
              ) : (
                <div className="max-h-[300px] overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-400 uppercase">
                        <th className="py-1 px-2">Name</th>
                        <th className="py-1 px-2">IP</th>
                        <th className="py-1 px-2">Device</th>
                        <th className="py-1 px-2">Zone</th>
                      </tr>
                    </thead>
                    <tbody>
                      {interfaces.map((iface) => (
                        <tr key={iface.id} className="border-t border-[#1e3a40]/50">
                          <td className="py-1.5 px-2 text-slate-300">{iface.name}</td>
                          <td className="py-1.5 px-2 font-mono text-slate-400">{iface.ip}</td>
                          <td className="py-1.5 px-2 text-slate-400">{iface.device_id}</td>
                          <td className="py-1.5 px-2 text-slate-400">{iface.zone_id || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-center text-slate-400 py-12 text-sm">
            Select a VLAN to view details
          </div>
        )}
      </div>
    </div>
  );
}
