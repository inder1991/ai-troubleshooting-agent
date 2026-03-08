import React, { useState, useMemo } from 'react';
import type { IPAMSubnet } from '../../types';

interface Props {
  subnets: IPAMSubnet[];
  onSelectSubnet: (subnetId: string) => void;
  selectedSubnetId: string;
  onContextMenu?: (e: React.MouseEvent, subnetId: string, cidr: string) => void;
}

type SortKey = 'cidr' | 'region' | 'vlan_id' | 'utilization_pct' | 'environment';

export default function IPAMSubnetsTable({ subnets, onSelectSubnet, selectedSubnetId, onContextMenu }: Props) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('utilization_pct');
  const [sortAsc, setSortAsc] = useState(false);

  const filtered = useMemo(() => {
    let list = subnets;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (s) =>
          s.cidr.toLowerCase().includes(q) ||
          (s.region || '').toLowerCase().includes(q) ||
          (s.description || '').toLowerCase().includes(q) ||
          (s.zone_id || '').toLowerCase().includes(q)
      );
    }
    list = [...list].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === 'string' && typeof bv === 'string')
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortAsc ? Number(av) - Number(bv) : Number(bv) - Number(av);
    });
    return list;
  }, [subnets, search, sortKey, sortAsc]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null;
    return (
      <span className="material-symbols-outlined text-xs ml-0.5">
        {sortAsc ? 'arrow_upward' : 'arrow_downward'}
      </span>
    );
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
          Subnets Overview
        </h3>
        <input
          type="text"
          placeholder="Filter subnets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1 bg-[#0f2023] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-500 w-56 focus:outline-none focus:border-cyan-500"
        />
      </div>
      <div className="max-h-[280px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#132a2f]">
            <tr className="text-left text-xs text-slate-500 uppercase tracking-wider">
              <th className="py-2 px-3 cursor-pointer" onClick={() => handleSort('cidr')}>
                CIDR <SortIcon col="cidr" />
              </th>
              <th className="py-2 px-3 cursor-pointer" onClick={() => handleSort('region')}>
                Region <SortIcon col="region" />
              </th>
              <th className="py-2 px-3">Zone</th>
              <th className="py-2 px-3 cursor-pointer" onClick={() => handleSort('vlan_id')}>
                VLAN <SortIcon col="vlan_id" />
              </th>
              <th className="py-2 px-3 cursor-pointer" onClick={() => handleSort('utilization_pct')}>
                Utilization <SortIcon col="utilization_pct" />
              </th>
              <th className="py-2 px-3">Gateway</th>
              <th className="py-2 px-3 cursor-pointer" onClick={() => handleSort('environment')}>
                Env <SortIcon col="environment" />
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => {
              const pct = s.utilization_pct ?? 0;
              const barColor = pct >= 80 ? 'bg-red-500' : pct >= 50 ? 'bg-amber-500' : 'bg-emerald-500';
              const isSelected = s.id === selectedSubnetId;
              return (
                <tr
                  key={s.id}
                  onClick={() => onSelectSubnet(s.id)}
                  onContextMenu={onContextMenu ? (e) => onContextMenu(e, s.id, s.cidr) : undefined}
                  className={`border-t border-[#1e3a40]/50 cursor-pointer hover:bg-[#1e3a40]/30 transition-colors ${
                    isSelected ? 'bg-[#1e3a40]/50' : ''
                  }`}
                >
                  <td className="py-2 px-3 font-mono text-cyan-300">{s.cidr}</td>
                  <td className="py-2 px-3 text-slate-400">{s.region || s.site || '-'}</td>
                  <td className="py-2 px-3 text-slate-400">{s.zone_id || '-'}</td>
                  <td className="py-2 px-3 text-slate-400">{s.vlan_id || '-'}</td>
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${barColor}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-400 w-8 text-right">{pct}%</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 font-mono text-slate-500 text-xs">{s.gateway_ip || '-'}</td>
                  <td className="py-2 px-3">
                    {s.environment && (
                      <span className="px-1.5 py-0.5 rounded text-xs bg-[#1e3a40] text-slate-300">
                        {s.environment}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="py-6 text-center text-slate-500 text-sm">
                  No subnets found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
