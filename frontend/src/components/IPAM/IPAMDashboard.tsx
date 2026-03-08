import React, { useEffect, useState, useCallback, useMemo } from 'react';
import type {
  IPAMStats, IPAMTreeNode, IPAMSubnet, IPAuditEvent, IPConflict,
  DNSMismatch, CapacityForecast,
} from '../../types';
import {
  fetchIPAMStats,
  fetchIPAMTree,
  fetchSubnetUtilization,
  fetchSubnetDetail,
  uploadIPAM,
  populateSubnetIPs,
  createSubnet,
  globalIPSearch,
  fetchIPConflicts,
  fetchIPAuditLog,
  exportIPAMCSV,
  deleteSubnet,
  splitSubnet,
  mergeSubnets,
  updateSubnet,
  fetchDNSMismatches,
  fetchCapacityForecast,
} from '../../services/api';
import IPAMStatCards from './IPAMStatCards';
import IPAMHierarchyTree from './IPAMHierarchyTree';
import IPAMSubnetDetail from './IPAMSubnetDetail';
import IPAMSubnetsTable from './IPAMSubnetsTable';

const emptyStats: IPAMStats = {
  total_subnets: 0, total_ips: 0, assigned_ips: 0,
  available_ips: 0, reserved_ips: 0, deprecated_ips: 0,
  overall_utilization_pct: 0,
};

// ── Toast system ──
interface Toast { id: number; message: string; type: 'success' | 'error' | 'info' }
let toastCounter = 0;

// ── Context menu ──
interface CtxMenu {
  x: number;
  y: number;
  subnetId: string;
  cidr: string;
}

export default function IPAMDashboard() {
  const [stats, setStats] = useState<IPAMStats>(emptyStats);
  const [tree, setTree] = useState<IPAMTreeNode[]>([]);
  const [subnets, setSubnets] = useState<IPAMSubnet[]>([]);
  const [selectedSubnetId, setSelectedSubnetId] = useState('');
  const [selectedSubnet, setSelectedSubnet] = useState<IPAMSubnet | null>(null);
  const [loading, setLoading] = useState(true);
  const [showImport, setShowImport] = useState(false);
  const [showCreateSubnet, setShowCreateSubnet] = useState(false);
  const [importStatus, setImportStatus] = useState('');

  // Global search
  const [globalSearch, setGlobalSearch] = useState('');
  const [searchResults, setSearchResults] = useState<Record<string, unknown>[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  // Conflicts & events
  const [conflicts, setConflicts] = useState<IPConflict[]>([]);
  const [events, setEvents] = useState<IPAuditEvent[]>([]);

  // DNS mismatches & capacity forecast
  const [dnsMismatches, setDnsMismatches] = useState<DNSMismatch[]>([]);
  const [forecasts, setForecasts] = useState<CapacityForecast[]>([]);

  // Toasts
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Context menu
  const [ctxMenu, setCtxMenu] = useState<CtxMenu | null>(null);

  // Split/merge dialogs
  const [splitTarget, setSplitTarget] = useState<{ id: string; cidr: string } | null>(null);
  const [mergeOpen, setMergeOpen] = useState(false);

  // Edit subnet dialog
  const [editSubnet, setEditSubnet] = useState<IPAMSubnet | null>(null);

  const addToast = useCallback((message: string, type: Toast['type'] = 'success') => {
    const id = ++toastCounter;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, treeRes, utilRes, conflictsRes, eventsRes, dnsRes, forecastRes] = await Promise.all([
        fetchIPAMStats(),
        fetchIPAMTree(),
        fetchSubnetUtilization(),
        fetchIPConflicts().catch(() => ({ conflicts: [] })),
        fetchIPAuditLog(undefined, 25).catch(() => ({ events: [] })),
        fetchDNSMismatches().catch(() => ({ mismatches: [] })),
        fetchCapacityForecast().catch(() => ({ forecasts: [] })),
      ]);
      setStats(statsRes);
      setTree(treeRes.tree || []);
      setSubnets(utilRes.subnets || []);
      setConflicts(conflictsRes.conflicts || []);
      setEvents(eventsRes.events || []);
      setDnsMismatches(dnsRes.mismatches || []);
      setForecasts(forecastRes.forecasts || []);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    if (!selectedSubnetId) { setSelectedSubnet(null); return; }
    fetchSubnetDetail(selectedSubnetId)
      .then((s) => setSelectedSubnet(s))
      .catch(() => setSelectedSubnet(null));
  }, [selectedSubnetId]);

  // Global search with debounce
  useEffect(() => {
    if (!globalSearch || globalSearch.length < 2) {
      setSearchResults([]); setSearchOpen(false); return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await globalIPSearch(globalSearch);
        setSearchResults(res.results || []);
        setSearchOpen(true);
      } catch { setSearchResults([]); }
    }, 300);
    return () => clearTimeout(timer);
  }, [globalSearch]);

  // Close context menu on click anywhere
  useEffect(() => {
    if (!ctxMenu) return;
    const handler = () => setCtxMenu(null);
    window.addEventListener('click', handler);
    return () => window.removeEventListener('click', handler);
  }, [ctxMenu]);

  const handleSelectSubnet = (id: string) => setSelectedSubnetId(id);

  const handleImport = async (file: File) => {
    setImportStatus('Importing...');
    try {
      const result = await uploadIPAM(file);
      const s = result.stats || result;
      const devCount = s.devices_added ?? s.devices_imported ?? 0;
      const subCount = s.subnets_added ?? s.subnets_imported ?? 0;
      const ipCount = s.ips_populated ?? 0;
      setImportStatus(`Imported ${devCount} devices, ${subCount} subnets, ${ipCount} IPs populated`);
      await loadAll();
      addToast(`Import complete: ${subCount} subnets, ${ipCount} IPs`);
      setTimeout(() => setShowImport(false), 2000);
    } catch (e: unknown) {
      setImportStatus(`Error: ${e instanceof Error ? e.message : 'Unknown error'}`);
      addToast('Import failed', 'error');
    }
  };

  const handleCreateSubnet = async (data: Record<string, string>) => {
    try {
      const result = await createSubnet({
        cidr: data.cidr,
        region: data.region,
        zone_id: data.zone_id,
        gateway_ip: data.gateway_ip,
        vlan_id: parseInt(data.vlan_id || '0', 10),
        environment: data.environment,
        description: data.description,
        site: data.site,
      });
      if (result.subnet?.id) {
        await populateSubnetIPs(result.subnet.id);
      }
      setShowCreateSubnet(false);
      await loadAll();
      addToast(`Subnet ${data.cidr} created`);
    } catch {
      addToast('Failed to create subnet', 'error');
    }
  };

  const handleExportCSV = async () => {
    try {
      const csvData = await exportIPAMCSV();
      const blob = new Blob([csvData], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ipam-export-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      addToast('CSV exported');
    } catch {
      addToast('Export failed', 'error');
    }
  };

  const handleDeleteSubnet = async (subnetId: string) => {
    try {
      await deleteSubnet(subnetId);
      if (selectedSubnetId === subnetId) setSelectedSubnetId('');
      await loadAll();
      addToast('Subnet deleted');
    } catch {
      addToast('Failed to delete subnet', 'error');
    }
  };

  const handleSplit = async (subnetId: string, newPrefix: number) => {
    try {
      await splitSubnet(subnetId, newPrefix);
      setSplitTarget(null);
      if (selectedSubnetId === subnetId) setSelectedSubnetId('');
      await loadAll();
      addToast('Subnet split successfully');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Split failed', 'error');
    }
  };

  const handleMerge = async (subnetIds: string[]) => {
    try {
      await mergeSubnets(subnetIds);
      setMergeOpen(false);
      setSelectedSubnetId('');
      await loadAll();
      addToast('Subnets merged successfully');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Merge failed', 'error');
    }
  };

  const handleEditSubnet = async (subnetId: string, data: Record<string, unknown>) => {
    try {
      await updateSubnet(subnetId, data);
      setEditSubnet(null);
      await loadAll();
      if (selectedSubnetId === subnetId) {
        fetchSubnetDetail(subnetId).then((s) => setSelectedSubnet(s)).catch(() => {});
      }
      addToast('Subnet updated');
    } catch {
      addToast('Failed to update subnet', 'error');
    }
  };

  const handleSubnetContext = (e: React.MouseEvent, subnetId: string, cidr: string) => {
    e.preventDefault();
    setCtxMenu({ x: e.clientX, y: e.clientY, subnetId, cidr });
  };

  // Top 10 subnets by utilization
  const top10Subnets = useMemo(() =>
    [...subnets].sort((a, b) => (b.utilization_pct ?? 0) - (a.utilization_pct ?? 0)).slice(0, 10),
    [subnets]
  );

  // Critical forecasts
  const criticalForecasts = useMemo(() =>
    forecasts.filter((f) => f.risk_level !== 'ok').sort((a, b) => {
      const order = { critical: 0, warning: 1, ok: 2 };
      return order[a.risk_level] - order[b.risk_level];
    }).slice(0, 8),
    [forecasts]
  );

  return (
    <div className="h-full flex flex-col gap-3 p-4 overflow-hidden">
      {/* Header with Global Search */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-2xl text-cyan-400">lan</span>
          <h1 className="text-xl font-bold text-slate-100">Manage Subnets & IP Addresses</h1>
          <span className="text-xs text-slate-500 mt-1">
            {stats.total_subnets} subnets &middot; {stats.total_ips.toLocaleString()} IPs
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Global Search */}
          <div className="relative">
            <div className="flex items-center bg-[#0f2023] border border-[#1e3a40] rounded px-2.5">
              <span className="material-symbols-outlined text-sm text-slate-500">search</span>
              <input
                type="text"
                placeholder="Search for IP Address..."
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
                onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
                onBlur={() => setTimeout(() => setSearchOpen(false), 200)}
                className="w-56 px-2 py-1.5 bg-transparent text-sm text-slate-200 placeholder-slate-500 focus:outline-none"
              />
            </div>
            {searchOpen && searchResults.length > 0 && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-[#132a2f] border border-[#1e3a40] rounded-lg shadow-xl w-[400px] max-h-[300px] overflow-y-auto">
                <div className="px-3 py-2 border-b border-[#1e3a40] text-xs text-slate-400 font-semibold">
                  {searchResults.length} results
                </div>
                {searchResults.map((r, i) => (
                  <button
                    key={i}
                    className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[#1e3a40] border-b border-[#1e3a40]/50"
                    onMouseDown={() => {
                      const subId = r.subnet_id as string;
                      if (subId) handleSelectSubnet(subId);
                      setGlobalSearch('');
                      setSearchOpen(false);
                    }}
                  >
                    <span className="font-mono text-sm text-cyan-300">{String(r.address)}</span>
                    <span className="text-xs text-slate-400">{String(r.hostname || '-')}</span>
                    <span className="text-xs text-slate-500">{String(r.mac_address || '')}</span>
                    <span className="ml-auto text-[10px] text-slate-500 font-mono">{String(r.subnet_cidr || '')}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#132a2f] border border-[#1e3a40] rounded text-sm text-slate-300 hover:bg-[#1e3a40]"
            title="Export IPAM as CSV"
          >
            <span className="material-symbols-outlined text-sm">download</span>
            Export
          </button>
          <button
            onClick={() => setShowImport(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#132a2f] border border-[#1e3a40] rounded text-sm text-slate-300 hover:bg-[#1e3a40]"
          >
            <span className="material-symbols-outlined text-sm">upload_file</span>
            Import
          </button>
          <button
            onClick={() => setMergeOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#132a2f] border border-[#1e3a40] rounded text-sm text-slate-300 hover:bg-[#1e3a40]"
            title="Merge subnets"
          >
            <span className="material-symbols-outlined text-sm">merge</span>
            Merge
          </button>
          <button
            onClick={() => setShowCreateSubnet(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 rounded text-sm text-white hover:bg-cyan-500"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Subnet
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <IPAMStatCards stats={stats} />

      {/* Main Content: Tree + Detail + Widgets */}
      <div className="flex-1 flex gap-3 min-h-0">
        {/* Tree Panel */}
        <div className="w-60 flex-shrink-0 bg-[#132a2f] border border-[#1e3a40] rounded-lg overflow-hidden flex flex-col">
          <div className="px-3 py-2 border-b border-[#1e3a40] flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              IP Networks
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {loading ? (
              <div className="text-center text-slate-500 py-8 text-sm">Loading...</div>
            ) : (
              <IPAMHierarchyTree
                tree={tree}
                selectedSubnetId={selectedSubnetId}
                onSelectSubnet={handleSelectSubnet}
                onContextMenu={handleSubnetContext}
              />
            )}
          </div>
        </div>

        {/* Detail Panel */}
        <div className="flex-1 bg-[#132a2f] border border-[#1e3a40] rounded-lg overflow-hidden flex flex-col">
          <div className="px-4 py-2 border-b border-[#1e3a40] text-xs font-semibold text-slate-400 uppercase tracking-wider">
            {selectedSubnet ? `Subnet: ${selectedSubnet.cidr}` : 'Select a subnet'}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {selectedSubnet ? (
              <IPAMSubnetDetail
                subnet={selectedSubnet}
                onUtilizationChange={() => {
                  loadAll();
                  fetchSubnetDetail(selectedSubnetId)
                    .then((s) => setSelectedSubnet(s))
                    .catch(() => {});
                }}
                addToast={addToast}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-500">
                <span className="material-symbols-outlined text-4xl mb-2">hub</span>
                <p className="text-sm">Select a subnet from the hierarchy tree</p>
                <p className="text-xs mt-1">to view IP addresses and utilization</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Sidebar: Widgets */}
        <div className="w-64 flex-shrink-0 flex flex-col gap-3 overflow-y-auto">
          {/* Top 10 Subnets */}
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Top 10 Subnets by % Used
            </h4>
            <div className="space-y-1.5">
              {top10Subnets.map((s) => {
                const pct = s.utilization_pct ?? 0;
                const color = pct >= 80 ? 'bg-red-500' : pct >= 50 ? 'bg-amber-500' : 'bg-emerald-500';
                return (
                  <button
                    key={s.id}
                    onClick={() => handleSelectSubnet(s.id)}
                    onContextMenu={(e) => handleSubnetContext(e, s.id, s.cidr)}
                    className={`w-full flex items-center gap-2 text-left hover:bg-[#1e3a40] rounded px-1.5 py-1 ${
                      s.id === selectedSubnetId ? 'bg-[#1e3a40]' : ''
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-xs text-slate-300 truncate">{s.cidr}</div>
                      <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden mt-0.5">
                        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
                      </div>
                    </div>
                    <span className={`text-xs font-semibold w-8 text-right ${
                      pct >= 80 ? 'text-red-400' : pct >= 50 ? 'text-amber-400' : 'text-emerald-400'
                    }`}>{pct}%</span>
                  </button>
                );
              })}
              {top10Subnets.length === 0 && (
                <div className="text-xs text-slate-500 text-center py-2">No subnets</div>
              )}
            </div>
          </div>

          {/* Capacity Forecast */}
          {criticalForecasts.length > 0 && (
            <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm text-amber-400">trending_up</span>
                Capacity Forecast
              </h4>
              <div className="space-y-1.5">
                {criticalForecasts.map((f, i) => (
                  <button
                    key={i}
                    onClick={() => handleSelectSubnet(f.subnet_id)}
                    className="w-full flex items-center gap-2 text-left hover:bg-[#1e3a40] rounded px-1.5 py-1"
                  >
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      f.risk_level === 'critical' ? 'bg-red-500' : 'bg-amber-500'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-xs text-slate-300 truncate">{f.cidr}</div>
                      <div className="text-[10px] text-slate-500">
                        {f.utilization_pct}% used
                        {f.days_until_full !== null && ` · ~${f.days_until_full}d to full`}
                      </div>
                    </div>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                      f.risk_level === 'critical'
                        ? 'bg-red-900/30 text-red-400'
                        : 'bg-amber-900/30 text-amber-400'
                    }`}>{f.risk_level.toUpperCase()}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* IP Conflicts */}
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <span className="material-symbols-outlined text-sm text-amber-400">warning</span>
              IP Conflicts
            </h4>
            {conflicts.length > 0 ? (
              <div className="space-y-1.5">
                {conflicts.slice(0, 5).map((c, i) => (
                  <div key={i} className="flex items-center gap-2 px-1.5 py-1 bg-red-900/20 border border-red-900/30 rounded">
                    <span className="font-mono text-xs text-red-300">{c.address}</span>
                    <span className="text-[10px] text-red-400 ml-auto">{c.cnt} subnets</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs text-emerald-400 py-1">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                No conflicts detected
              </div>
            )}
          </div>

          {/* DNS Mismatches */}
          {dnsMismatches.length > 0 && (
            <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3">
              <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm text-orange-400">dns</span>
                DNS Mismatches
              </h4>
              <div className="space-y-1.5">
                {dnsMismatches.slice(0, 6).map((m, i) => (
                  <div key={i} className="px-1.5 py-1 bg-orange-900/10 border border-orange-900/20 rounded">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        m.type === 'missing_hostname' ? 'bg-orange-400' : 'bg-amber-400'
                      }`} />
                      <span className="text-[11px] text-slate-300 truncate">{m.detail}</span>
                    </div>
                    {m.address && (
                      <span className="font-mono text-[10px] text-slate-500 ml-3">{m.address}</span>
                    )}
                  </div>
                ))}
                {dnsMismatches.length > 6 && (
                  <div className="text-[10px] text-slate-500 text-center">
                    +{dnsMismatches.length - 6} more
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Recent Events */}
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3 flex-1 min-h-0 overflow-hidden flex flex-col">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Recent Events
            </h4>
            <div className="flex-1 overflow-y-auto space-y-1">
              {events.slice(0, 15).map((e, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] py-1 border-b border-[#1e3a40]/30">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                    e.new_status === 'assigned' ? 'bg-cyan-400' :
                    e.new_status === 'reserved' ? 'bg-blue-400' :
                    e.new_status === 'available' ? 'bg-emerald-400' :
                    e.new_status === 'deprecated' ? 'bg-slate-500' : 'bg-slate-600'
                  }`} />
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-slate-300">{e.address}</span>
                    <span className="text-slate-500 ml-1">{e.action}</span>
                    {e.timestamp && (
                      <div className="text-[10px] text-slate-600 truncate">
                        {new Date(e.timestamp).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {events.length === 0 && (
                <div className="text-xs text-slate-500 text-center py-2">No events yet</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Subnets Table */}
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-3">
        <IPAMSubnetsTable
          subnets={subnets}
          selectedSubnetId={selectedSubnetId}
          onSelectSubnet={handleSelectSubnet}
          onContextMenu={handleSubnetContext}
        />
      </div>

      {/* Context Menu */}
      {ctxMenu && (
        <div
          className="fixed z-[100] bg-[#132a2f] border border-[#1e3a40] rounded-lg shadow-xl py-1 min-w-[160px]"
          style={{ left: ctxMenu.x, top: ctxMenu.y }}
        >
          <button
            onClick={() => {
              handleSelectSubnet(ctxMenu.subnetId);
              setCtxMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
          >
            <span className="material-symbols-outlined text-sm">visibility</span>
            View IPs
          </button>
          <button
            onClick={() => {
              const sub = subnets.find((s) => s.id === ctxMenu.subnetId);
              if (sub) setEditSubnet(sub);
              setCtxMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
          >
            <span className="material-symbols-outlined text-sm">edit</span>
            Edit Subnet
          </button>
          <button
            onClick={() => {
              setSplitTarget({ id: ctxMenu.subnetId, cidr: ctxMenu.cidr });
              setCtxMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
          >
            <span className="material-symbols-outlined text-sm">call_split</span>
            Split Subnet
          </button>
          <div className="border-t border-[#1e3a40] my-1" />
          <button
            onClick={() => {
              if (confirm(`Delete subnet ${ctxMenu.cidr}? All IPs will be removed.`)) {
                handleDeleteSubnet(ctxMenu.subnetId);
              }
              setCtxMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/20"
          >
            <span className="material-symbols-outlined text-sm">delete</span>
            Delete Subnet
          </button>
        </div>
      )}

      {/* Dialogs */}
      {showImport && (
        <ImportDialog
          onClose={() => { setShowImport(false); setImportStatus(''); }}
          onImport={handleImport}
          status={importStatus}
        />
      )}
      {showCreateSubnet && (
        <CreateSubnetDialog
          onClose={() => setShowCreateSubnet(false)}
          onCreate={handleCreateSubnet}
        />
      )}
      {splitTarget && (
        <SplitSubnetDialog
          cidr={splitTarget.cidr}
          onClose={() => setSplitTarget(null)}
          onSplit={(prefix) => handleSplit(splitTarget.id, prefix)}
        />
      )}
      {mergeOpen && (
        <MergeSubnetsDialog
          subnets={subnets}
          onClose={() => setMergeOpen(false)}
          onMerge={handleMerge}
        />
      )}
      {editSubnet && (
        <EditSubnetDialog
          subnet={editSubnet}
          onClose={() => setEditSubnet(null)}
          onSave={(data) => handleEditSubnet(editSubnet.id, data)}
        />
      )}

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-[200] flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-xl text-sm animate-[slideIn_0.3s_ease-out] ${
              t.type === 'error' ? 'bg-red-900/90 text-red-200 border border-red-800' :
              t.type === 'info' ? 'bg-blue-900/90 text-blue-200 border border-blue-800' :
              'bg-emerald-900/90 text-emerald-200 border border-emerald-800'
            }`}
          >
            <span className="material-symbols-outlined text-sm">
              {t.type === 'error' ? 'error' : t.type === 'info' ? 'info' : 'check_circle'}
            </span>
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Import Dialog ──

function ImportDialog({
  onClose, onImport, status,
}: { onClose: () => void; onImport: (file: File) => void; status: string }) {
  const [file, setFile] = useState<File | null>(null);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[420px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">Import IPAM Data</h3>
        <div className="border-2 border-dashed border-[#1e3a40] rounded-lg p-6 text-center mb-4">
          <input
            type="file" accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm text-slate-300"
          />
          <p className="text-xs text-slate-500 mt-2">
            CSV with columns: ip, subnet, device, zone, vlan, region, environment
          </p>
        </div>
        {status && (
          <div className={`text-sm mb-3 ${status.startsWith('Error') ? 'text-red-400' : 'text-cyan-400'}`}>
            {status}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => file && onImport(file)}
            disabled={!file}
            className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
          >Import</button>
        </div>
      </div>
    </div>
  );
}

// ── Create Subnet Dialog with CIDR Calculator ──

function parseCIDRInfo(cidr: string): { valid: boolean; network?: string; broadcast?: string; hosts?: number; prefix?: number } | null {
  const m = cidr.match(/^(\d+\.\d+\.\d+\.\d+)\/(\d+)$/);
  if (!m) return null;
  const parts = m[1].split('.').map(Number);
  if (parts.some((p) => p < 0 || p > 255)) return null;
  const prefix = parseInt(m[2], 10);
  if (prefix < 0 || prefix > 32) return null;
  const ipNum = (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3];
  const mask = prefix === 0 ? 0 : ~((1 << (32 - prefix)) - 1);
  const network = ipNum & mask;
  const broadcast = network | ~mask;
  const numToStr = (n: number) =>
    `${(n >>> 24) & 0xff}.${(n >>> 16) & 0xff}.${(n >>> 8) & 0xff}.${n & 0xff}`;
  const hosts = prefix >= 31 ? (prefix === 32 ? 1 : 2) : (1 << (32 - prefix)) - 2;
  return { valid: true, network: numToStr(network), broadcast: numToStr(broadcast >>> 0), hosts, prefix };
}

function CreateSubnetDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, string>) => void }) {
  const [form, setForm] = useState({
    cidr: '', region: '', zone_id: '', gateway_ip: '',
    vlan_id: '', environment: '', description: '', site: '',
  });
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const cidrInfo = form.cidr ? parseCIDRInfo(form.cidr) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[460px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">Create Subnet</h3>
        <div className="space-y-3">
          {[
            { key: 'cidr', label: 'CIDR *', placeholder: '10.10.1.0/24' },
            { key: 'gateway_ip', label: 'Gateway IP', placeholder: '10.10.1.1' },
            { key: 'region', label: 'Region', placeholder: 'US-East' },
            { key: 'zone_id', label: 'Zone', placeholder: 'VPC-1' },
            { key: 'vlan_id', label: 'VLAN', placeholder: '100' },
            { key: 'environment', label: 'Environment', placeholder: 'prod' },
            { key: 'site', label: 'Site', placeholder: 'DC-East-1' },
            { key: 'description', label: 'Description', placeholder: 'Web tier subnet' },
          ].map((f) => (
            <div key={f.key} className="flex items-center gap-3">
              <label className="text-xs text-slate-400 w-24 text-right">{f.label}</label>
              <input
                value={form[f.key as keyof typeof form]}
                onChange={(e) => set(f.key, e.target.value)}
                placeholder={f.placeholder}
                className="flex-1 px-3 py-1.5 bg-[#0f2023] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500"
              />
            </div>
          ))}
          {/* CIDR Calculator */}
          {form.cidr && cidrInfo && (
            <div className="ml-[108px] p-2.5 bg-[#0f2023] border border-[#1e3a40] rounded text-xs space-y-1">
              <div className="text-slate-400 font-semibold uppercase tracking-wider mb-1">CIDR Info</div>
              <div className="flex justify-between">
                <span className="text-slate-500">Network:</span>
                <span className="font-mono text-slate-300">{cidrInfo.network}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Broadcast:</span>
                <span className="font-mono text-slate-300">{cidrInfo.broadcast}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Usable hosts:</span>
                <span className="font-mono text-cyan-300">{cidrInfo.hosts?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Prefix:</span>
                <span className="font-mono text-slate-300">/{cidrInfo.prefix}</span>
              </div>
            </div>
          )}
          {form.cidr && !cidrInfo && (
            <div className="ml-[108px] text-xs text-red-400">Invalid CIDR notation</div>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => form.cidr && cidrInfo && onCreate(form)}
            disabled={!form.cidr || !cidrInfo}
            className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
          >Create & Populate</button>
        </div>
      </div>
    </div>
  );
}

// ── Split Subnet Dialog ──

function SplitSubnetDialog({
  cidr, onClose, onSplit,
}: { cidr: string; onClose: () => void; onSplit: (newPrefix: number) => void }) {
  const info = parseCIDRInfo(cidr);
  const currentPrefix = info?.prefix ?? 24;
  const [newPrefix, setNewPrefix] = useState(currentPrefix + 1);
  const subnetCount = 1 << (newPrefix - currentPrefix);
  const hostsPerSubnet = newPrefix >= 31 ? (newPrefix === 32 ? 1 : 2) : (1 << (32 - newPrefix)) - 2;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[400px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-cyan-400">call_split</span>
          Split Subnet
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 bg-[#0f2023] rounded border border-[#1e3a40]">
            <span className="text-xs text-slate-400">Source</span>
            <span className="font-mono text-sm text-cyan-300">{cidr}</span>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1.5">New prefix length</label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={currentPrefix + 1}
                max={Math.min(currentPrefix + 4, 30)}
                value={newPrefix}
                onChange={(e) => setNewPrefix(parseInt(e.target.value, 10))}
                className="flex-1 accent-cyan-500"
              />
              <span className="font-mono text-sm text-slate-200 w-8 text-center">/{newPrefix}</span>
            </div>
          </div>
          <div className="p-3 bg-[#0f2023] rounded border border-[#1e3a40] text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-slate-500">Subnets created:</span>
              <span className="font-mono text-cyan-300">{subnetCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Hosts per subnet:</span>
              <span className="font-mono text-slate-300">{hostsPerSubnet.toLocaleString()}</span>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => onSplit(newPrefix)}
            className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500"
          >Split into {subnetCount} subnets</button>
        </div>
      </div>
    </div>
  );
}

// ── Merge Subnets Dialog ──

function MergeSubnetsDialog({
  subnets, onClose, onMerge,
}: { subnets: IPAMSubnet[]; onClose: () => void; onMerge: (ids: string[]) => void }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[480px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-cyan-400">merge</span>
          Merge Subnets
        </h3>
        <p className="text-xs text-slate-400 mb-3">
          Select 2 or more adjacent subnets to merge into a supernet.
        </p>
        <div className="max-h-[300px] overflow-y-auto border border-[#1e3a40] rounded">
          {subnets.map((s) => (
            <label
              key={s.id}
              className={`flex items-center gap-3 px-3 py-2 border-b border-[#1e3a40]/50 cursor-pointer hover:bg-[#1e3a40]/30 ${
                selected.has(s.id) ? 'bg-cyan-900/20' : ''
              }`}
            >
              <input
                type="checkbox"
                checked={selected.has(s.id)}
                onChange={() => toggle(s.id)}
                className="accent-cyan-500"
              />
              <span className="font-mono text-sm text-cyan-300">{s.cidr}</span>
              <span className="text-xs text-slate-500 ml-auto">{s.region || s.site || ''}</span>
            </label>
          ))}
        </div>
        <div className="flex justify-between items-center mt-4">
          <span className="text-xs text-slate-400">{selected.size} selected</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
            <button
              onClick={() => onMerge(Array.from(selected))}
              disabled={selected.size < 2}
              className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
            >Merge {selected.size} Subnets</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Edit Subnet Dialog ──

function EditSubnetDialog({
  subnet, onClose, onSave,
}: { subnet: IPAMSubnet; onClose: () => void; onSave: (data: Record<string, unknown>) => void }) {
  const [form, setForm] = useState({
    region: subnet.region || '',
    zone_id: subnet.zone_id || '',
    gateway_ip: subnet.gateway_ip || '',
    vlan_id: String(subnet.vlan_id || ''),
    environment: subnet.environment || '',
    description: subnet.description || '',
    site: subnet.site || '',
  });
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[440px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-1">Edit Subnet</h3>
        <div className="font-mono text-cyan-300 text-sm mb-4">{subnet.cidr}</div>
        <div className="space-y-3">
          {[
            { key: 'gateway_ip', label: 'Gateway IP' },
            { key: 'region', label: 'Region' },
            { key: 'zone_id', label: 'Zone' },
            { key: 'vlan_id', label: 'VLAN' },
            { key: 'environment', label: 'Environment' },
            { key: 'site', label: 'Site' },
            { key: 'description', label: 'Description' },
          ].map((f) => (
            <div key={f.key} className="flex items-center gap-3">
              <label className="text-xs text-slate-400 w-24 text-right">{f.label}</label>
              <input
                value={form[f.key as keyof typeof form]}
                onChange={(e) => set(f.key, e.target.value)}
                className="flex-1 px-3 py-1.5 bg-[#0f2023] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => onSave({
              ...form,
              vlan_id: parseInt(form.vlan_id || '0', 10),
            })}
            className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500"
          >Save</button>
        </div>
      </div>
    </div>
  );
}
