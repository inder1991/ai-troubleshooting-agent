import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
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
  createRegion,
  createSite,
  createVRF,
  createAddressBlock,
  fetchRegions,
  fetchSites,
  fetchVRFs,
  fetchAddressBlocks,
  updateRegion,
  deleteRegion,
  updateSite,
  deleteSite,
  updateVRF,
  deleteVRF,
  deleteAddressBlock,
} from '../../services/api';
import IPAMStatCards from './IPAMStatCards';
import IPAMHierarchyTree from './IPAMHierarchyTree';
import IPAMSubnetDetail from './IPAMSubnetDetail';
import IPAMSubnetsTable from './IPAMSubnetsTable';
import IPAMDHCPTab from './IPAMDHCPTab';
import IPAMReportBuilder from './IPAMReportBuilder';
import SubnetCalculatorPage from './SubnetCalculatorPage';
import IPAMAllocationWizard from './IPAMAllocationWizard';
import IPAMVLANTab from './IPAMVLANTab';
import IPAMAddressSpaceMap from './IPAMAddressSpaceMap';
import NetworkChatDrawer from '../NetworkChat/NetworkChatDrawer';

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

  // Hierarchy management dialogs
  const [showCreateRegion, setShowCreateRegion] = useState(false);
  const [showCreateSite, setShowCreateSite] = useState(false);
  const [showCreateVRF, setShowCreateVRF] = useState(false);
  const [showCreateBlock, setShowCreateBlock] = useState(false);
  const [showManageMenu, setShowManageMenu] = useState(false);

  // Hierarchy node context menu & edit dialogs
  const [nodeCtxMenu, setNodeCtxMenu] = useState<{ x: number; y: number; id: string; type: string; label: string } | null>(null);
  const [editNode, setEditNode] = useState<{ id: string; type: string; label: string } | null>(null);

  // Active tab
  const [activeTab, setActiveTab] = useState<'overview' | 'dhcp' | 'vlans' | 'reports' | 'calculator'>('overview');
  const [selectedBlockId, setSelectedBlockId] = useState<string>('');

  // Allocation wizard
  const [allocTarget, setAllocTarget] = useState<{ id: string; cidr: string } | null>(null);

  // Detail refresh key to avoid double fetch on utilization change (B5)
  const [detailRefreshKey, setDetailRefreshKey] = useState(0);

  // Blur timer ref to prevent leak (B6)
  const blurTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Confirm dialog state (B10)
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
  }>({ open: false, title: '', message: '', onConfirm: () => {} });

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

  // Cleanup blur timer on unmount (B6)
  useEffect(() => {
    return () => {
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!selectedSubnetId) { setSelectedSubnet(null); return; }
    fetchSubnetDetail(selectedSubnetId)
      .then((s) => setSelectedSubnet(s))
      .catch(() => setSelectedSubnet(null));
  }, [selectedSubnetId, detailRefreshKey]);

  // Global search with debounce + AbortController (B2)
  useEffect(() => {
    if (!globalSearch || globalSearch.length < 2) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await globalIPSearch(globalSearch, controller.signal);
        setSearchResults(res.results || []);
        setSearchOpen(true);
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          console.error('Search error:', e);
          setSearchResults([]);
        }
      }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [globalSearch]);

  // Close context menus on click anywhere
  useEffect(() => {
    if (!ctxMenu && !nodeCtxMenu) return;
    const handler = () => { setCtxMenu(null); setNodeCtxMenu(null); };
    window.addEventListener('click', handler);
    return () => window.removeEventListener('click', handler);
  }, [ctxMenu, nodeCtxMenu]);

  const handleSelectSubnet = (id: string) => { setSelectedSubnetId(id); setSelectedBlockId(''); };

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
        vrf_id: data.vrf_id || 'default',
        site_id: data.site_id || '',
        cloud_provider: data.cloud_provider || '',
        vpc_id: data.vpc_id || '',
        subnet_role: data.subnet_role || '',
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

  const handleCreateRegion = async (data: Record<string, unknown>) => {
    try {
      await createRegion(data);
      setShowCreateRegion(false);
      await loadAll();
      addToast('Region created');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Failed to create region', 'error');
    }
  };

  const handleCreateSite = async (data: Record<string, unknown>) => {
    try {
      await createSite(data);
      setShowCreateSite(false);
      await loadAll();
      addToast('Site created');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Failed to create site', 'error');
    }
  };

  const handleCreateVRF = async (data: Record<string, unknown>) => {
    try {
      await createVRF(data);
      setShowCreateVRF(false);
      await loadAll();
      addToast('VRF created');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Failed to create VRF', 'error');
    }
  };

  const handleCreateBlock = async (data: Record<string, unknown>) => {
    try {
      await createAddressBlock(data);
      setShowCreateBlock(false);
      await loadAll();
      addToast('Address block created');
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : 'Failed to create address block', 'error');
    }
  };

  const handleNodeContextMenu = (e: React.MouseEvent, nodeId: string, nodeType: string, label: string) => {
    e.preventDefault();
    const x = Math.min(e.clientX, window.innerWidth - 180);
    const y = Math.min(e.clientY, window.innerHeight - 180);
    setNodeCtxMenu({ x, y, id: nodeId, type: nodeType, label });
  };

  const handleEditNode = async (nodeId: string, nodeType: string, data: Record<string, unknown>) => {
    try {
      if (nodeType === 'region') await updateRegion(nodeId, data);
      else if (nodeType === 'site') await updateSite(nodeId, data);
      else if (nodeType === 'vrf') await updateVRF(nodeId, data);
      setEditNode(null);
      await loadAll();
      addToast(`${nodeType.charAt(0).toUpperCase() + nodeType.slice(1)} updated`);
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : `Failed to update ${nodeType}`, 'error');
    }
  };

  const handleDeleteNode = async (nodeId: string, nodeType: string) => {
    try {
      if (nodeType === 'region') await deleteRegion(nodeId);
      else if (nodeType === 'site') await deleteSite(nodeId);
      else if (nodeType === 'vrf') await deleteVRF(nodeId);
      else if (nodeType === 'address_block') await deleteAddressBlock(nodeId);
      await loadAll();
      addToast(`${nodeType.replace('_', ' ')} deleted`);
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : `Failed to delete ${nodeType}`, 'error');
    }
  };

  const handleSubnetContext = (e: React.MouseEvent, subnetId: string, cidr: string) => {
    e.preventDefault();
    const x = Math.min(e.clientX, window.innerWidth - 180);
    const y = Math.min(e.clientY, window.innerHeight - 180);
    setCtxMenu({ x, y, subnetId, cidr });
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
          <span className="material-symbols-outlined text-2xl text-amber-400">lan</span>
          <h1 className="text-xl font-bold text-slate-100">Manage Subnets & IP Addresses</h1>
          <span className="text-xs text-slate-400 mt-1">
            {stats.total_subnets} subnets &middot; {stats.total_ips.toLocaleString()} IPs
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Global Search */}
          <div className="relative">
            <div className="flex items-center bg-[#1a1814] border border-[#1e3a40] rounded px-2.5">
              <span className="material-symbols-outlined text-sm text-slate-400">search</span>
              <input
                type="text"
                placeholder="Search for IP Address..."
                value={globalSearch}
                onChange={(e) => setGlobalSearch(e.target.value)}
                onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
                onBlur={() => { blurTimerRef.current = setTimeout(() => setSearchOpen(false), 200); }}
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
                    <span className="font-mono text-sm text-amber-300">{String(r.address)}</span>
                    <span className="text-xs text-slate-400">{String(r.hostname || '-')}</span>
                    <span className="text-xs text-slate-400">{String(r.mac_address || '')}</span>
                    <span className="ml-auto text-body-xs text-slate-400 font-mono">{String(r.subnet_cidr || '')}</span>
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
            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 rounded text-sm text-white hover:bg-amber-500"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Subnet
          </button>
          {/* Manage dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowManageMenu((p) => !p)}
              onBlur={() => setTimeout(() => setShowManageMenu(false), 150)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#132a2f] border border-[#1e3a40] rounded text-sm text-slate-300 hover:bg-[#1e3a40]"
            >
              <span className="material-symbols-outlined text-sm">add</span>
              Manage
              <span className="material-symbols-outlined text-xs">arrow_drop_down</span>
            </button>
            {showManageMenu && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-[#132a2f] border border-[#1e3a40] rounded-lg shadow-xl w-48 py-1">
                {([
                  { label: 'Add Region', icon: 'public', action: () => { setShowCreateRegion(true); setShowManageMenu(false); } },
                  { label: 'Add Site', icon: 'domain', action: () => { setShowCreateSite(true); setShowManageMenu(false); } },
                  { label: 'Add VRF', icon: 'route', action: () => { setShowCreateVRF(true); setShowManageMenu(false); } },
                  { label: 'Add Address Block', icon: 'grid_view', action: () => { setShowCreateBlock(true); setShowManageMenu(false); } },
                ] as const).map((item) => (
                  <button
                    key={item.label}
                    onMouseDown={item.action}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-slate-300 hover:bg-[#1e3a40]"
                  >
                    <span className="material-symbols-outlined text-sm text-slate-400">{item.icon}</span>
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex items-center gap-1 border-b border-[#1e3a40]">
        {([
          { key: 'overview', label: 'Overview', icon: 'dashboard' },
          { key: 'dhcp', label: 'DHCP Scopes', icon: 'router' },
          { key: 'vlans', label: 'VLANs', icon: 'lan' },
          { key: 'reports', label: 'Reports', icon: 'assessment' },
          { key: 'calculator', label: 'Calculator', icon: 'calculate' },
        ] as const).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-amber-400 text-amber-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <span className="material-symbols-outlined text-sm">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'dhcp' && <div className="flex-1 overflow-y-auto"><IPAMDHCPTab /></div>}
      {activeTab === 'vlans' && <div className="flex-1 overflow-y-auto p-4"><IPAMVLANTab /></div>}
      {activeTab === 'reports' && <div className="flex-1 overflow-y-auto"><IPAMReportBuilder /></div>}
      {activeTab === 'calculator' && <div className="flex-1 overflow-y-auto"><SubnetCalculatorPage /></div>}

      {activeTab === 'overview' && <>
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
              <div className="text-center text-slate-400 py-8 text-sm">Loading...</div>
            ) : (
              <IPAMHierarchyTree
                tree={tree}
                selectedSubnetId={selectedSubnetId}
                onSelectSubnet={handleSelectSubnet}
                onSelectNode={(nodeId, nodeType) => {
                  if (nodeType === 'address_block') {
                    setSelectedBlockId(nodeId);
                    setSelectedSubnetId('');
                  }
                }}
                onContextMenu={handleSubnetContext}
                onNodeContextMenu={handleNodeContextMenu}
              />
            )}
          </div>
        </div>

        {/* Detail Panel */}
        <div className="flex-1 bg-[#132a2f] border border-[#1e3a40] rounded-lg overflow-hidden flex flex-col">
          <div className="px-4 py-2 border-b border-[#1e3a40] text-xs font-semibold text-slate-400 uppercase tracking-wider">
            {selectedSubnet ? `Subnet: ${selectedSubnet.cidr}` : selectedBlockId ? 'Address Block' : 'Select a subnet'}
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {selectedSubnet ? (
              <IPAMSubnetDetail
                subnet={selectedSubnet}
                onUtilizationChange={() => {
                  loadAll();
                  setDetailRefreshKey(prev => prev + 1);
                }}
                addToast={addToast}
              />
            ) : selectedBlockId ? (
              <IPAMAddressSpaceMap blockId={selectedBlockId} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-slate-400">
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
                      <div className="w-full h-1.5 bg-wr-inset rounded-full overflow-hidden mt-0.5">
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
                <div className="text-xs text-slate-400 text-center py-2">No subnets</div>
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
                      <div className="text-body-xs text-slate-400">
                        {f.utilization_pct}% used
                        {f.days_until_full !== null && ` · ~${f.days_until_full}d to full`}
                      </div>
                    </div>
                    <span className={`text-body-xs px-1.5 py-0.5 rounded font-semibold ${
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
                    <span className="text-body-xs text-red-400 ml-auto">{c.cnt} subnets</span>
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
                      <span className="text-body-xs text-slate-300 truncate">{m.detail}</span>
                    </div>
                    {m.address && (
                      <span className="font-mono text-body-xs text-slate-400 ml-3">{m.address}</span>
                    )}
                  </div>
                ))}
                {dnsMismatches.length > 6 && (
                  <div className="text-body-xs text-slate-400 text-center">
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
                <div key={i} className="flex items-start gap-2 text-body-xs py-1 border-b border-[#1e3a40]/30">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1 flex-shrink-0 ${
                    e.new_status === 'assigned' ? 'bg-amber-400' :
                    e.new_status === 'reserved' ? 'bg-blue-400' :
                    e.new_status === 'available' ? 'bg-emerald-400' :
                    e.new_status === 'deprecated' ? 'bg-slate-500' : 'bg-slate-600'
                  }`} />
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-slate-300">{e.address}</span>
                    <span className="text-slate-400 ml-1">{e.action}</span>
                    {e.timestamp && (
                      <div className="text-body-xs text-slate-500 truncate">
                        {new Date(e.timestamp).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {events.length === 0 && (
                <div className="text-xs text-slate-400 text-center py-2">No events yet</div>
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

      </>}

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
          <button
            onClick={() => {
              setAllocTarget({ id: ctxMenu.subnetId, cidr: ctxMenu.cidr });
              setCtxMenu(null);
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
          >
            <span className="material-symbols-outlined text-sm">space_dashboard</span>
            Find Available Space
          </button>
          <div className="border-t border-[#1e3a40] my-1" />
          <button
            onClick={() => {
              const subnetId = ctxMenu.subnetId;
              const cidr = ctxMenu.cidr;
              setCtxMenu(null);
              setConfirmDialog({
                open: true,
                title: 'Delete Subnet',
                message: `Are you sure you want to delete subnet ${cidr}? All IP addresses will be removed.`,
                onConfirm: () => {
                  handleDeleteSubnet(subnetId);
                  setConfirmDialog(prev => ({ ...prev, open: false }));
                },
              });
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/20"
          >
            <span className="material-symbols-outlined text-sm">delete</span>
            Delete Subnet
          </button>
        </div>
      )}

      {/* Hierarchy Node Context Menu */}
      {nodeCtxMenu && (
        <div
          className="fixed z-[100] bg-[#132a2f] border border-[#1e3a40] rounded-lg shadow-xl py-1 min-w-[160px]"
          style={{ left: nodeCtxMenu.x, top: nodeCtxMenu.y }}
        >
          {nodeCtxMenu.type !== 'address_block' && (
            <button
              onClick={() => {
                setEditNode({ id: nodeCtxMenu.id, type: nodeCtxMenu.type, label: nodeCtxMenu.label });
                setNodeCtxMenu(null);
              }}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
            >
              <span className="material-symbols-outlined text-sm">edit</span>
              Edit {nodeCtxMenu.type}
            </button>
          )}
          <button
            onClick={() => {
              const { id, type, label } = nodeCtxMenu;
              setNodeCtxMenu(null);
              setConfirmDialog({
                open: true,
                title: `Delete ${type.replace('_', ' ')}`,
                message: `Are you sure you want to delete "${label}"? This cannot be undone.`,
                onConfirm: () => {
                  handleDeleteNode(id, type);
                  setConfirmDialog(prev => ({ ...prev, open: false }));
                },
              });
            }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/20"
          >
            <span className="material-symbols-outlined text-sm">delete</span>
            Delete {nodeCtxMenu.type.replace('_', ' ')}
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
      {allocTarget && (
        <IPAMAllocationWizard
          parentSubnetId={allocTarget.id}
          parentCidr={allocTarget.cidr}
          onClose={() => setAllocTarget(null)}
          onCreated={() => { setAllocTarget(null); loadAll(); addToast('Subnet allocated'); }}
        />
      )}
      {showCreateRegion && (
        <CreateRegionDialog onClose={() => setShowCreateRegion(false)} onCreate={handleCreateRegion} />
      )}
      {showCreateSite && (
        <CreateSiteDialog onClose={() => setShowCreateSite(false)} onCreate={handleCreateSite} />
      )}
      {showCreateVRF && (
        <CreateVRFDialog onClose={() => setShowCreateVRF(false)} onCreate={handleCreateVRF} />
      )}
      {showCreateBlock && (
        <CreateAddressBlockDialog onClose={() => setShowCreateBlock(false)} onCreate={handleCreateBlock} />
      )}
      {editNode && (
        <EditNodeDialog
          nodeId={editNode.id}
          nodeType={editNode.type}
          currentName={editNode.label}
          onClose={() => setEditNode(null)}
          onSave={(data) => handleEditNode(editNode.id, editNode.type, data)}
        />
      )}

      {/* Confirm Dialog (B10) */}
      {confirmDialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#252118] border border-amber-900/50 rounded-xl p-6 max-w-md shadow-xl">
            <h3 className="text-lg font-semibold text-white mb-2">{confirmDialog.title}</h3>
            <p className="text-gray-300 mb-6">{confirmDialog.message}</p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
                className="px-4 py-2 rounded-lg bg-gray-700 text-gray-200 hover:bg-gray-600 transition"
              >
                Cancel
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-500 transition"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
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
      <NetworkChatDrawer view="ipam" />
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
          <p className="text-xs text-slate-400 mt-2">
            CSV with columns: ip, subnet, device, zone, vlan, region, environment
          </p>
        </div>
        {status && (
          <div className={`text-sm mb-3 ${status.startsWith('Error') ? 'text-red-400' : 'text-amber-400'}`}>
            {status}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => file && onImport(file)}
            disabled={!file}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
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
  const ipNum = ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) >>> 0;
  const mask = prefix === 0 ? 0 : (~((1 << (32 - prefix)) - 1)) >>> 0;
  const network = (ipNum & mask) >>> 0;
  const broadcast = (network | ~mask) >>> 0;
  const numToStr = (n: number) =>
    `${(n >>> 24) & 0xff}.${(n >>> 16) & 0xff}.${(n >>> 8) & 0xff}.${n & 0xff}`;
  const hosts = prefix >= 31 ? (prefix === 32 ? 1 : 2) : (1 << (32 - prefix)) - 2;
  return { valid: true, network: numToStr(network), broadcast: numToStr(broadcast), hosts, prefix };
}

function CreateSubnetDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, string>) => void }) {
  const [form, setForm] = useState({
    cidr: '', region: '', zone_id: '', gateway_ip: '',
    vlan_id: '', environment: '', description: '', site: 'default',
    cloud_provider: '', vpc_id: '', vrf_id: 'default', subnet_role: '',
    site_id: '',
  });
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const cidrInfo = form.cidr ? parseCIDRInfo(form.cidr) : null;

  const [regionOptions, setRegionOptions] = useState<{ id: string; name: string }[]>([]);
  const [siteOptions, setSiteOptions] = useState<{ id: string; name: string }[]>([]);
  const [vrfOptions, setVrfOptions] = useState<{ id: string; name: string }[]>([]);
  const [blockOptions, setBlockOptions] = useState<{ id: string; cidr: string; vrf_id: string }[]>([]);

  useEffect(() => {
    fetchRegions().then((res) => setRegionOptions(res.regions || res || [])).catch(() => {});
    fetchSites().then((res) => setSiteOptions(res.sites || res || [])).catch(() => {});
    fetchVRFs().then((res) => setVrfOptions(res.vrfs || res || [])).catch(() => {});
    fetchAddressBlocks().then((res) => setBlockOptions(res.blocks || res || [])).catch(() => {});
  }, []);

  // Validate subnet CIDR fits within an address block for the selected VRF
  const vrfBlocks = blockOptions.filter((b) => b.vrf_id === form.vrf_id);
  const cidrFitsBlock = (() => {
    if (!cidrInfo || !form.cidr || vrfBlocks.length === 0) return true; // no blocks = no constraint
    const subnetInfo = parseCIDRInfo(form.cidr);
    if (!subnetInfo) return true;
    for (const blk of vrfBlocks) {
      const blkInfo = parseCIDRInfo(blk.cidr);
      if (!blkInfo || !blkInfo.prefix || !subnetInfo.prefix) continue;
      // Check if subnet is within block: block prefix must be shorter and network must match
      if (subnetInfo.prefix >= blkInfo.prefix) {
        const blkParts = blk.cidr.split('/')[0].split('.').map(Number);
        const subParts = form.cidr.split('/')[0].split('.').map(Number);
        const blkNum = ((blkParts[0] << 24) | (blkParts[1] << 16) | (blkParts[2] << 8) | blkParts[3]) >>> 0;
        const subNum = ((subParts[0] << 24) | (subParts[1] << 16) | (subParts[2] << 8) | subParts[3]) >>> 0;
        const mask = blkInfo.prefix === 0 ? 0 : (~((1 << (32 - blkInfo.prefix)) - 1)) >>> 0;
        if ((blkNum & mask) === (subNum & mask)) return true;
      }
    }
    return false;
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[460px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">Create Subnet</h3>
        <div className="space-y-3">
          {[
            { key: 'cidr', label: 'CIDR *', placeholder: '10.10.1.0/24' },
            { key: 'gateway_ip', label: 'Gateway IP', placeholder: '10.10.1.1' },
            { key: 'zone_id', label: 'Zone', placeholder: 'VPC-1' },
            { key: 'vlan_id', label: 'VLAN', placeholder: '100' },
            { key: 'environment', label: 'Environment', placeholder: 'prod' },
            { key: 'vpc_id', label: 'VPC ID', placeholder: 'vpc-0abc123' },
            { key: 'description', label: 'Description', placeholder: 'Web tier subnet' },
          ].map((f) => (
            <div key={f.key} className="flex items-center gap-3">
              <label className="text-xs text-slate-400 w-24 text-right">{f.label}</label>
              <input
                value={form[f.key as keyof typeof form]}
                onChange={(e) => set(f.key, e.target.value)}
                placeholder={f.placeholder}
                className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
              />
            </div>
          ))}
          {/* Region dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Region</label>
            <select
              value={form.region}
              onChange={(e) => set('region', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">— Select region —</option>
              {regionOptions.map((r) => (
                <option key={r.id} value={r.name}>{r.name}</option>
              ))}
            </select>
          </div>
          {/* Site dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Site</label>
            <select
              value={form.site_id}
              onChange={(e) => {
                const selected = siteOptions.find((s) => s.id === e.target.value);
                setForm((p) => ({ ...p, site_id: e.target.value, site: selected?.name || 'default' }));
              }}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">default</option>
              {siteOptions.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          {/* VRF dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">VRF</label>
            <select
              value={form.vrf_id}
              onChange={(e) => set('vrf_id', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="default">default</option>
              {vrfOptions.filter((v) => v.id !== 'default').map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>
          {/* Cloud Provider dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Provider</label>
            <select
              value={form.cloud_provider}
              onChange={(e) => set('cloud_provider', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">On-Premises</option>
              <option value="aws">AWS</option>
              <option value="azure">Azure</option>
              <option value="gcp">GCP</option>
              <option value="oci">OCI</option>
            </select>
          </div>
          {/* Subnet Role dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Role</label>
            <select
              value={form.subnet_role}
              onChange={(e) => set('subnet_role', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">None</option>
              <option value="server">Server</option>
              <option value="storage">Storage</option>
              <option value="voice">Voice</option>
              <option value="dmz">DMZ</option>
              <option value="management">Management</option>
              <option value="user">User</option>
              <option value="iot">IoT</option>
            </select>
          </div>
          {/* CIDR Calculator */}
          {form.cidr && cidrInfo && (
            <div className="ml-[108px] p-2.5 bg-[#1a1814] border border-[#1e3a40] rounded text-xs space-y-1">
              <div className="text-slate-400 font-semibold uppercase tracking-wider mb-1">CIDR Info</div>
              <div className="flex justify-between">
                <span className="text-slate-400">Network:</span>
                <span className="font-mono text-slate-300">{cidrInfo.network}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Broadcast:</span>
                <span className="font-mono text-slate-300">{cidrInfo.broadcast}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Usable hosts:</span>
                <span className="font-mono text-amber-300">{cidrInfo.hosts?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Prefix:</span>
                <span className="font-mono text-slate-300">/{cidrInfo.prefix}</span>
              </div>
            </div>
          )}
          {form.cidr && !cidrInfo && (
            <div className="ml-[108px] text-xs text-red-400">Invalid CIDR notation</div>
          )}
          {form.cidr && cidrInfo && !cidrFitsBlock && (
            <div className="ml-[108px] text-xs text-red-400">
              Subnet does not fit within any address block in this VRF ({vrfBlocks.map((b) => b.cidr).join(', ')})
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => form.cidr && cidrInfo && cidrFitsBlock && onCreate(form)}
            disabled={!form.cidr || !cidrInfo || !cidrFitsBlock}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
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
          <span className="material-symbols-outlined text-lg text-amber-400">call_split</span>
          Split Subnet
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 bg-[#1a1814] rounded border border-[#1e3a40]">
            <span className="text-xs text-slate-400">Source</span>
            <span className="font-mono text-sm text-amber-300">{cidr}</span>
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
                className="flex-1 accent-amber-500"
              />
              <span className="font-mono text-sm text-slate-200 w-8 text-center">/{newPrefix}</span>
            </div>
          </div>
          <div className="p-3 bg-[#1a1814] rounded border border-[#1e3a40] text-xs space-y-1.5">
            <div className="flex justify-between">
              <span className="text-slate-400">Subnets created:</span>
              <span className="font-mono text-amber-300">{subnetCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Hosts per subnet:</span>
              <span className="font-mono text-slate-300">{hostsPerSubnet.toLocaleString()}</span>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => onSplit(newPrefix)}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500"
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
          <span className="material-symbols-outlined text-lg text-amber-400">merge</span>
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
                selected.has(s.id) ? 'bg-amber-900/20' : ''
              }`}
            >
              <input
                type="checkbox"
                checked={selected.has(s.id)}
                onChange={() => toggle(s.id)}
                className="accent-amber-500"
              />
              <span className="font-mono text-sm text-amber-300">{s.cidr}</span>
              <span className="text-xs text-slate-400 ml-auto">{s.region || s.site || ''}</span>
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
              className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
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
    cloud_provider: subnet.cloud_provider || '',
    vpc_id: subnet.vpc_id || '',
    vrf_id: subnet.vrf_id || 'default',
    subnet_role: subnet.subnet_role || '',
  });
  const set = (k: string, v: string) => setForm((p) => ({ ...p, [k]: v }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[440px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-1">Edit Subnet</h3>
        <div className="font-mono text-amber-300 text-sm mb-4">{subnet.cidr}</div>
        <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
          {[
            { key: 'gateway_ip', label: 'Gateway IP' },
            { key: 'region', label: 'Region' },
            { key: 'zone_id', label: 'Zone' },
            { key: 'vlan_id', label: 'VLAN' },
            { key: 'environment', label: 'Environment' },
            { key: 'site', label: 'Site' },
            { key: 'vpc_id', label: 'VPC ID' },
            { key: 'vrf_id', label: 'VRF' },
            { key: 'description', label: 'Description' },
          ].map((f) => (
            <div key={f.key} className="flex items-center gap-3">
              <label className="text-xs text-slate-400 w-24 text-right">{f.label}</label>
              <input
                value={form[f.key as keyof typeof form]}
                onChange={(e) => set(f.key, e.target.value)}
                className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
              />
            </div>
          ))}
          {/* Cloud Provider dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Provider</label>
            <select
              value={form.cloud_provider}
              onChange={(e) => set('cloud_provider', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">On-Premises</option>
              <option value="aws">AWS</option>
              <option value="azure">Azure</option>
              <option value="gcp">GCP</option>
              <option value="oci">OCI</option>
            </select>
          </div>
          {/* Subnet Role dropdown */}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Role</label>
            <select
              value={form.subnet_role}
              onChange={(e) => set('subnet_role', e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">None</option>
              <option value="server">Server</option>
              <option value="storage">Storage</option>
              <option value="voice">Voice</option>
              <option value="dmz">DMZ</option>
              <option value="management">Management</option>
              <option value="user">User</option>
              <option value="iot">IoT</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => onSave({
              ...form,
              vlan_id: parseInt(form.vlan_id || '0', 10),
              cloud_provider: form.cloud_provider,
              vpc_id: form.vpc_id,
              vrf_id: form.vrf_id,
              subnet_role: form.subnet_role,
            })}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500"
          >Save</button>
        </div>
      </div>
    </div>
  );
}

// ── Create Region Dialog ──

function CreateRegionDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, unknown>) => void }) {
  const [name, setName] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[400px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-amber-400">public</span>
          Create Region
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="US-East"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => name.trim() && onCreate({ name: name.trim() })}
            disabled={!name.trim()}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
          >Create</button>
        </div>
      </div>
    </div>
  );
}

// ── Create Site Dialog ──

function CreateSiteDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, unknown>) => void }) {
  const [name, setName] = useState('');
  const [regionId, setRegionId] = useState('');
  const [siteType, setSiteType] = useState('datacenter');
  const [regions, setRegions] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    fetchRegions().then((res) => setRegions(res.regions || res || [])).catch(() => {});
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[420px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-amber-400">domain</span>
          Create Site
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="DC-East-1"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Region</label>
            <select
              value={regionId}
              onChange={(e) => setRegionId(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">— Select region —</option>
              {regions.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Type</label>
            <select
              value={siteType}
              onChange={(e) => setSiteType(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="datacenter">Datacenter</option>
              <option value="branch">Branch</option>
              <option value="cloud">Cloud</option>
              <option value="colo">Colo</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => name.trim() && onCreate({ name: name.trim(), region_id: regionId || undefined, site_type: siteType })}
            disabled={!name.trim()}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
          >Create</button>
        </div>
      </div>
    </div>
  );
}

// ── Create VRF Dialog ──

function CreateVRFDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, unknown>) => void }) {
  const [name, setName] = useState('');
  const [rd, setRd] = useState('');
  const [description, setDescription] = useState('');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[420px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-amber-400">route</span>
          Create VRF
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="production"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">RD</label>
            <input
              value={rd}
              onChange={(e) => setRd(e.target.value)}
              placeholder="65000:100"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-24 text-right">Description</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Production routing domain"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => name.trim() && onCreate({ name: name.trim(), rd: rd || undefined, description: description || undefined })}
            disabled={!name.trim()}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
          >Create</button>
        </div>
      </div>
    </div>
  );
}

// ── Create Address Block Dialog ──

function CreateAddressBlockDialog({
  onClose, onCreate,
}: { onClose: () => void; onCreate: (data: Record<string, unknown>) => void }) {
  const [cidr, setCidr] = useState('');
  const [vrfId, setVrfId] = useState('');
  const [siteId, setSiteId] = useState('');
  const [rir, setRir] = useState('private');
  const [vrfs, setVrfs] = useState<{ id: string; name: string }[]>([]);
  const [sites, setSites] = useState<{ id: string; name: string }[]>([]);

  useEffect(() => {
    fetchVRFs().then((res) => setVrfs(res.vrfs || res || [])).catch(() => {});
    fetchSites().then((res) => setSites(res.sites || res || [])).catch(() => {});
  }, []);

  const cidrInfo = cidr ? parseCIDRInfo(cidr) : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[440px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-amber-400">grid_view</span>
          Create Address Block
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">CIDR *</label>
            <input
              value={cidr}
              onChange={(e) => setCidr(e.target.value)}
              placeholder="10.0.0.0/8"
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
          {cidr && cidrInfo && (
            <div className="ml-[92px] p-2 bg-[#1a1814] border border-[#1e3a40] rounded text-xs space-y-1">
              <div className="flex justify-between"><span className="text-slate-400">Network:</span><span className="font-mono text-slate-300">{cidrInfo.network}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Hosts:</span><span className="font-mono text-amber-300">{cidrInfo.hosts?.toLocaleString()}</span></div>
            </div>
          )}
          {cidr && !cidrInfo && (
            <div className="ml-[92px] text-xs text-red-400">Invalid CIDR notation</div>
          )}
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">VRF</label>
            <select
              value={vrfId}
              onChange={(e) => setVrfId(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">— Select VRF —</option>
              {vrfs.map((v) => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Site</label>
            <select
              value={siteId}
              onChange={(e) => setSiteId(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="">— Select site —</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">RIR</label>
            <select
              value={rir}
              onChange={(e) => setRir(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 focus:outline-none focus:border-amber-500"
            >
              <option value="private">Private (RFC1918)</option>
              <option value="ARIN">ARIN</option>
              <option value="RIPE">RIPE</option>
              <option value="APNIC">APNIC</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => cidr && cidrInfo && onCreate({ cidr, vrf_id: vrfId || undefined, site_id: siteId || undefined, rir })}
            disabled={!cidr || !cidrInfo}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
          >Create</button>
        </div>
      </div>
    </div>
  );
}

// ── Edit Node Dialog (Region / Site / VRF) ──

function EditNodeDialog({
  nodeId: _nodeId, nodeType, currentName, onClose, onSave,
}: {
  nodeId: string;
  nodeType: string;
  currentName: string;
  onClose: () => void;
  onSave: (data: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState(currentName);

  const iconMap: Record<string, string> = { region: 'public', site: 'domain', vrf: 'route' };
  const label = nodeType.charAt(0).toUpperCase() + nodeType.slice(1);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[400px]">
        <h3 className="text-sm font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg text-amber-400">{iconMap[nodeType] || 'edit'}</span>
          Edit {label}
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs text-slate-400 w-20 text-right">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 px-3 py-1.5 bg-[#1a1814] border border-[#1e3a40] rounded text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
          <button
            onClick={() => name.trim() && onSave({ name: name.trim() })}
            disabled={!name.trim()}
            className="px-3 py-1.5 text-sm bg-amber-600 text-white rounded hover:bg-amber-500 disabled:opacity-40"
          >Save</button>
        </div>
      </div>
    </div>
  );
}
