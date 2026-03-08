import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import type { IPAddress, IPAMSubnet, IPAMDevice, IPAuditEvent, IPCorrelationChain } from '../../types';
import {
  fetchIPs, reserveIP, assignIP, releaseIP, updateIP,
  fetchIPAMDevices, bulkUpdateIPStatus, fetchNextAvailableIP,
  fetchIPAuditLog, scanSubnet, fetchIPCorrelation,
} from '../../services/api';
import IPAMSubnetHeatmap from './IPAMSubnetHeatmap';

interface Props {
  subnet: IPAMSubnet;
  onUtilizationChange: () => void;
  addToast?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const statusConfig: Record<string, { color: string; bg: string; label: string; dot: string }> = {
  available: { color: 'text-emerald-400', bg: 'bg-emerald-400/10', label: 'Available', dot: 'bg-emerald-400' },
  reserved: { color: 'text-blue-400', bg: 'bg-blue-400/10', label: 'Reserved', dot: 'bg-blue-400' },
  assigned: { color: 'text-cyan-400', bg: 'bg-cyan-400/10', label: 'Used', dot: 'bg-cyan-400' },
  deprecated: { color: 'text-slate-500', bg: 'bg-slate-500/10', label: 'Deprecated', dot: 'bg-slate-500' },
};

type ViewTab = 'table' | 'chart' | 'heatmap';

export default function IPAMSubnetDetail({ subnet, onUtilizationChange, addToast }: Props) {
  const [ips, setIps] = useState<IPAddress[]>([]);
  const [devices, setDevices] = useState<IPAMDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [actionMenuId, setActionMenuId] = useState<string>('');
  const [assignDialogId, setAssignDialogId] = useState<string>('');
  const [assignDeviceId, setAssignDeviceId] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeTab, setActiveTab] = useState<ViewTab>('table');
  const [bulkAction, setBulkAction] = useState('');
  const [historyIp, setHistoryIp] = useState<IPAddress | null>(null);
  const [historyEvents, setHistoryEvents] = useState<IPAuditEvent[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<any>(null);
  const [correlationChain, setCorrelationChain] = useState<IPCorrelationChain | null>(null);
  const [correlationLoading, setCorrelationLoading] = useState(false);

  // Pagination state (B1)
  const [page, setPage] = useState(0);
  const pageSize = 100;
  const [totalCount, setTotalCount] = useState(0);

  // Ref to track current ips for stale closure prevention (B3)
  const ipsRef = useRef(ips);
  useEffect(() => { ipsRef.current = ips; }, [ips]);

  const loadIPs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchIPs({
        subnet_id: subnet.id,
        status: statusFilter || undefined,
        search: search || undefined,
        offset: page * pageSize,
        limit: pageSize,
      });
      setIps(res.ips || []);
      setTotalCount(res.total_count ?? res.ips?.length ?? 0);
    } catch {
      /* ignore */
    }
    setLoading(false);
  }, [subnet.id, statusFilter, search, page]);

  // Reset page when filter/search/subnet changes
  useEffect(() => {
    setPage(0);
  }, [subnet.id, statusFilter, search]);

  useEffect(() => {
    loadIPs();
    setSelectedIds(new Set());
  }, [loadIPs]);

  useEffect(() => {
    fetchIPAMDevices().then((r) => setDevices(r.devices || [])).catch((err) => {
      console.error('Failed to load devices:', err);
      addToast?.('Failed to load devices', 'error');
    });
  }, [addToast]);

  const handleAction = async (ipId: string, action: string) => {
    setActionMenuId('');
    try {
      if (action === 'reserve') {
        await reserveIP(ipId);
        addToast?.('IP reserved');
      } else if (action === 'release') {
        await releaseIP(ipId);
        addToast?.('IP released');
      } else if (action === 'deprecate') {
        await updateIP(ipId, { status: 'deprecated' });
        addToast?.('IP deprecated');
      } else if (action === 'assign') {
        setAssignDialogId(ipId);
        return;
      } else if (action === 'history') {
        const ip = ipsRef.current.find((i) => i.id === ipId);
        if (ip) openHistory(ip);
        return;
      } else if (action === 'trace') {
        const ip = ipsRef.current.find((i) => i.id === ipId);
        if (ip) openCorrelation(ip);
        return;
      }
      await loadIPs();
      onUtilizationChange();
    } catch {
      addToast?.('Action failed', 'error');
    }
  };

  const openHistory = async (ip: IPAddress) => {
    setHistoryIp(ip);
    setHistoryLoading(true);
    try {
      const res = await fetchIPAuditLog(ip.id, 50);
      setHistoryEvents(res.events || []);
    } catch {
      setHistoryEvents([]);
    }
    setHistoryLoading(false);
  };

  const openCorrelation = async (ip: IPAddress) => {
    setCorrelationLoading(true);
    try {
      const chain = await fetchIPCorrelation(ip.id);
      setCorrelationChain(chain);
    } catch {
      setCorrelationChain(null);
      addToast?.('Failed to load correlation', 'error');
    }
    setCorrelationLoading(false);
  };

  const handleAssignConfirm = async () => {
    if (!assignDialogId || !assignDeviceId) return;
    try {
      await assignIP(assignDialogId, assignDeviceId);
      setAssignDialogId('');
      setAssignDeviceId('');
      await loadIPs();
      onUtilizationChange();
      addToast?.('IP assigned to device');
    } catch {
      addToast?.('Failed to assign IP', 'error');
    }
  };

  const handleBulkAction = async () => {
    if (!bulkAction || selectedIds.size === 0) return;
    try {
      const count = selectedIds.size;
      await bulkUpdateIPStatus(Array.from(selectedIds), bulkAction);
      setSelectedIds(new Set());
      setBulkAction('');
      await loadIPs();
      onUtilizationChange();
      addToast?.(`${count} IPs updated to ${bulkAction}`);
    } catch {
      addToast?.('Bulk update failed', 'error');
    }
  };

  const handleNextAvailable = async () => {
    try {
      const ip = await fetchNextAvailableIP(subnet.id);
      if (ip?.address) {
        setSearch(ip.address);
      }
    } catch {
      /* ignore */
    }
  };

  const handleScanSubnet = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const result = await scanSubnet(subnet.id);
      setScanResult(result);
      addToast?.(`Scan complete: ${result.alive_count} alive hosts found, ${result.updated_ips} IPs updated`);
      await loadIPs();
      onUtilizationChange();
    } catch {
      addToast?.('Subnet scan failed', 'error');
    }
    setScanning(false);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === selectableIps.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(selectableIps.map((ip) => ip.id)));
    }
  };

  const selectableIps = useMemo(
    () => ips.filter((ip) => ip.ip_type !== 'network' && ip.ip_type !== 'broadcast'),
    [ips],
  );

  const getActions = (ip: IPAddress): { label: string; action: string }[] => {
    const history = { label: 'View History', action: 'history' };
    switch (ip.status) {
      case 'available':
        return [
          { label: 'Reserve', action: 'reserve' },
          { label: 'Assign to Device', action: 'assign' },
          history,
        ];
      case 'reserved':
        return [
          { label: 'Assign to Device', action: 'assign' },
          { label: 'Release', action: 'release' },
          history,
        ];
      case 'assigned':
        return [
          { label: 'Trace', action: 'trace' },
          { label: 'Release', action: 'release' },
          { label: 'Deprecate', action: 'deprecate' },
          history,
        ];
      case 'deprecated':
        return [{ label: 'Release', action: 'release' }, history];
      default:
        return [history];
    }
  };

  const utilPct = subnet.utilization_pct ?? 0;
  const barColor = utilPct >= 80 ? 'bg-red-500' : utilPct >= 50 ? 'bg-amber-500' : 'bg-emerald-500';

  // Chart view data
  const chartData = useMemo(() => {
    const counts = { available: 0, assigned: 0, reserved: 0, deprecated: 0 };
    ips.forEach((ip) => {
      if (ip.status in counts) counts[ip.status as keyof typeof counts]++;
    });
    return counts;
  }, [ips]);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-mono font-bold text-slate-100">{subnet.cidr}</h3>
          <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
            {subnet.region && <span>Region: {subnet.region}</span>}
            {subnet.zone_id && <span>Zone: {subnet.zone_id}</span>}
            {subnet.vlan_id > 0 && <span>VLAN: {subnet.vlan_id}</span>}
            {subnet.vrf_id && subnet.vrf_id !== 'default' && (
              <span className="px-1.5 py-0.5 rounded bg-purple-900/30 text-purple-300 border border-purple-700/30">
                VRF: {subnet.vrf_id}
              </span>
            )}
            {subnet.subnet_role && (
              <span className="px-1.5 py-0.5 rounded bg-[#1e3a40] text-slate-300">
                {subnet.subnet_role}
              </span>
            )}
            {subnet.environment && (
              <span className="px-1.5 py-0.5 rounded bg-[#1e3a40] text-cyan-300">
                {subnet.environment}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleScanSubnet}
            disabled={scanning}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300 hover:bg-[#1e3a40] hover:text-cyan-300 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className={`material-symbols-outlined text-sm ${scanning ? 'animate-spin' : ''}`}>
              {scanning ? 'progress_activity' : 'radar'}
            </span>
            {scanning ? 'Scanning...' : 'Scan Subnet'}
          </button>
          <div className="text-right text-sm">
            <span className="text-slate-400">
              {subnet.assigned ?? 0}/{subnet.total ?? 0} used
            </span>
          </div>
        </div>
      </div>

      {/* Utilization bar */}
      <div className="w-full h-4 bg-slate-700/50 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(utilPct, 100)}%` }}
        />
      </div>
      <div className="flex justify-between text-xs text-slate-500">
        <span>{utilPct}% utilized</span>
        <span>{subnet.available ?? 0} available</span>
      </div>

      {/* Scan Results Banner */}
      {scanResult && (
        <div className="flex items-center justify-between px-3 py-2 bg-cyan-900/20 border border-cyan-700/30 rounded text-xs">
          <div className="flex items-center gap-2 text-cyan-300">
            <span className="material-symbols-outlined text-sm">check_circle</span>
            <span>
              Scan complete: {scanResult.total_scanned} scanned, {scanResult.alive_count} alive, {scanResult.updated_ips} updated
            </span>
          </div>
          <button
            onClick={() => setScanResult(null)}
            className="text-slate-500 hover:text-slate-300"
          >
            <span className="material-symbols-outlined text-sm">close</span>
          </button>
        </div>
      )}

      {/* Tabs: IP ADDRESS VIEW | CHART VIEW */}
      <div className="flex items-center border-b border-[#1e3a40]">
        <button
          onClick={() => setActiveTab('table')}
          className={`px-4 py-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === 'table'
              ? 'border-cyan-400 text-cyan-300'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          IP Address View
        </button>
        <button
          onClick={() => setActiveTab('chart')}
          className={`px-4 py-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === 'chart'
              ? 'border-cyan-400 text-cyan-300'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          Chart View
        </button>
        <button
          onClick={() => setActiveTab('heatmap')}
          className={`px-4 py-2 text-xs font-semibold uppercase tracking-wider border-b-2 transition-colors ${
            activeTab === 'heatmap'
              ? 'border-cyan-400 text-cyan-300'
              : 'border-transparent text-slate-500 hover:text-slate-300'
          }`}
        >
          Heatmap
        </button>
      </div>

      {activeTab === 'heatmap' ? (
        <IPAMSubnetHeatmap subnetId={subnet.id} subnetCidr={subnet.cidr} ips={ips} />
      ) : activeTab === 'chart' ? (
        /* Chart View — utilization breakdown */
        <div className="py-6">
          <div className="grid grid-cols-2 gap-4 max-w-md mx-auto">
            {Object.entries(chartData).map(([status, count]) => {
              const sc = statusConfig[status] || statusConfig.available;
              const pct = ips.length > 0 ? Math.round((count / ips.length) * 100) : 0;
              return (
                <div key={status} className="flex items-center gap-3 p-3 bg-[#0f2023] rounded-lg border border-[#1e3a40]">
                  <div className={`w-3 h-3 rounded-full ${sc.dot}`} />
                  <div className="flex-1">
                    <div className="text-xs text-slate-400 uppercase">{sc.label}</div>
                    <div className="text-lg font-bold text-slate-200">{count}</div>
                  </div>
                  <div className="text-sm text-slate-500">{pct}%</div>
                </div>
              );
            })}
          </div>
          {/* Visual bar breakdown */}
          <div className="mt-6 flex h-8 rounded-lg overflow-hidden border border-[#1e3a40]">
            {Object.entries(chartData).map(([status, count]) => {
              if (count === 0) return null;
              const pct = ips.length > 0 ? (count / ips.length) * 100 : 0;
              const sc = statusConfig[status];
              return (
                <div
                  key={status}
                  className={`${sc?.dot || 'bg-slate-600'} flex items-center justify-center text-xs text-white font-semibold`}
                  style={{ width: `${pct}%` }}
                  title={`${sc?.label}: ${count} (${Math.round(pct)}%)`}
                >
                  {pct > 8 ? `${Math.round(pct)}%` : ''}
                </div>
              );
            })}
          </div>
          <div className="flex justify-center gap-4 mt-3">
            {Object.entries(chartData).map(([status]) => {
              const sc = statusConfig[status];
              return (
                <div key={status} className="flex items-center gap-1.5 text-xs text-slate-400">
                  <div className={`w-2 h-2 rounded-full ${sc?.dot}`} />
                  {sc?.label}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* IP Address Table View */
        <>
          {/* Toolbar — matches SolarWinds style */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <button
              onClick={handleNextAvailable}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300 hover:bg-[#1e3a40] hover:text-cyan-300"
            >
              <span className="material-symbols-outlined text-sm">add_circle</span>
              Next Available
            </button>
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-1.5 ml-2">
                <span className="text-slate-400">{selectedIds.size} selected</span>
                <select
                  value={bulkAction}
                  onChange={(e) => setBulkAction(e.target.value)}
                  className="px-2 py-1 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300"
                >
                  <option value="">Set Status...</option>
                  <option value="available">Available</option>
                  <option value="reserved">Reserved</option>
                  <option value="deprecated">Deprecated</option>
                </select>
                <button
                  onClick={handleBulkAction}
                  disabled={!bulkAction}
                  className="px-2 py-1 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
                >
                  Apply
                </button>
              </div>
            )}
            <div className="flex-1" />
            <span className="text-slate-500">Filter:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-2 py-1.5 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300 focus:outline-none"
            >
              <option value="">ALL</option>
              <option value="available">Available</option>
              <option value="assigned">Used</option>
              <option value="reserved">Reserved</option>
              <option value="deprecated">Deprecated</option>
            </select>
            <input
              type="text"
              placeholder="Search IP, hostname, MAC..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 px-2.5 py-1.5 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* IP Grid Table */}
          {loading ? (
            <div className="text-center text-slate-500 py-8">Loading IPs...</div>
          ) : ips.length === 0 ? (
            <div className="text-center text-slate-500 py-8 text-sm">
              No IPs found. Populate this subnet first.
            </div>
          ) : (
            <>
            <div className="max-h-[400px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-[#132a2f] z-10">
                  <tr className="text-left text-xs text-slate-500 uppercase tracking-wider">
                    <th className="py-2 px-2 w-8">
                      <input
                        type="checkbox"
                        checked={selectedIds.size > 0 && selectedIds.size === selectableIps.length}
                        onChange={toggleSelectAll}
                        className="accent-cyan-500"
                      />
                    </th>
                    <th className="py-2 px-2">Address</th>
                    <th className="py-2 px-2 w-24">Status</th>
                    <th className="py-2 px-2">MAC</th>
                    <th className="py-2 px-2">Vendor</th>
                    <th className="py-2 px-2">Hostname</th>
                    <th className="py-2 px-2">Device</th>
                    <th className="py-2 px-2 w-16">Type</th>
                    <th className="py-2 px-2 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {ips.map((ip) => {
                    const sc = statusConfig[ip.status] || statusConfig.available;
                    const device = ip.assigned_device_id
                      ? devices.find((d) => d.id === ip.assigned_device_id)
                      : null;
                    const isSelectable = ip.ip_type !== 'network' && ip.ip_type !== 'broadcast';
                    const isSelected = selectedIds.has(ip.id);
                    return (
                      <tr
                        key={ip.id}
                        className={`border-t border-[#1e3a40]/50 hover:bg-[#1e3a40]/30 transition-colors ${
                          ip.status === 'deprecated' ? 'opacity-50' : ''
                        } ${isSelected ? 'bg-cyan-900/20' : ''}`}
                      >
                        <td className="py-1.5 px-2">
                          {isSelectable && (
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleSelect(ip.id)}
                              className="accent-cyan-500"
                            />
                          )}
                        </td>
                        <td className="py-1.5 px-2 font-mono text-slate-300">
                          {ip.address}
                        </td>
                        <td className="py-1.5 px-2">
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs ${sc.bg} ${sc.color}`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                            {sc.label}
                          </span>
                        </td>
                        <td className="py-1.5 px-2 font-mono text-slate-500 text-xs">
                          {ip.mac_address || '-'}
                        </td>
                        <td className="py-1.5 px-2 text-slate-400 text-xs">
                          {ip.vendor || '-'}
                        </td>
                        <td className={`py-1.5 px-2 text-slate-400 text-xs ${ip.status === 'deprecated' ? 'line-through' : ''}`}>
                          {ip.hostname || '-'}
                        </td>
                        <td className="py-1.5 px-2 text-slate-400 text-xs">
                          {device ? device.name : ip.assigned_device_id || '-'}
                        </td>
                        <td className="py-1.5 px-2 text-slate-500 text-xs">{ip.ip_type}</td>
                        <td className="py-1.5 px-2 relative">
                          {isSelectable && (
                            <>
                              <button
                                onClick={() => setActionMenuId(actionMenuId === ip.id ? '' : ip.id)}
                                className="text-slate-500 hover:text-slate-300"
                              >
                                <span className="material-symbols-outlined text-sm">more_vert</span>
                              </button>
                              {actionMenuId === ip.id && (
                                <div className="absolute right-0 top-8 z-50 bg-[#132a2f] border border-[#1e3a40] rounded shadow-lg min-w-[140px]">
                                  {getActions(ip).map((a) => (
                                    <button
                                      key={a.action}
                                      onClick={() => handleAction(ip.id, a.action)}
                                      className="w-full text-left px-3 py-1.5 text-sm text-slate-300 hover:bg-[#1e3a40]"
                                    >
                                      {a.label}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Pagination Controls (B1) */}
            {totalCount > pageSize && (
              <div className="flex items-center justify-between mt-3 text-xs text-slate-400">
                <span>
                  Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalCount)} of {totalCount}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="px-2.5 py-1 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300 hover:bg-[#1e3a40] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="text-slate-300">
                    Page {page + 1} of {Math.ceil(totalCount / pageSize)}
                  </span>
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    disabled={(page + 1) * pageSize >= totalCount}
                    className="px-2.5 py-1 bg-[#0f2023] border border-[#1e3a40] rounded text-slate-300 hover:bg-[#1e3a40] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
            </>
          )}
        </>
      )}

      {/* Assign Dialog */}
      {assignDialogId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-96">
            <h4 className="text-sm font-semibold text-slate-200 mb-3">Assign IP to Device</h4>
            <select
              value={assignDeviceId}
              onChange={(e) => setAssignDeviceId(e.target.value)}
              className="w-full px-3 py-2 bg-[#0f2023] border border-[#1e3a40] rounded text-sm text-slate-200 mb-4"
            >
              <option value="">Select device...</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setAssignDialogId(''); setAssignDeviceId(''); }}
                className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={handleAssignConfirm}
                disabled={!assignDeviceId}
                className="px-3 py-1.5 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-40"
              >
                Assign
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Correlation Trace Modal */}
      {(correlationChain || correlationLoading) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[420px]">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-sm font-semibold text-slate-200">IP Correlation Trace</h4>
              <button onClick={() => setCorrelationChain(null)} className="text-slate-500 hover:text-slate-300">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            {correlationLoading ? (
              <div className="text-center text-slate-500 py-8 text-sm">Loading...</div>
            ) : correlationChain ? (
              <div className="space-y-1 text-sm font-mono">
                <div className="flex items-center gap-2 p-2 bg-[#0f2023] rounded">
                  <span className="text-cyan-400">IP</span>
                  <span className="text-slate-300">{correlationChain.ip.address}</span>
                  <span className={`ml-auto text-xs px-1.5 py-0.5 rounded ${
                    correlationChain.ip.status === 'assigned' ? 'bg-cyan-400/10 text-cyan-400' : 'bg-slate-600/30 text-slate-400'
                  }`}>{correlationChain.ip.status}</span>
                  {correlationChain.ip.owner_team && (
                    <span className="text-xs text-slate-500">{correlationChain.ip.owner_team}</span>
                  )}
                </div>
                {correlationChain.interface && (
                  <div className="flex items-center gap-2 p-2 bg-[#0f2023] rounded ml-4">
                    <span className="text-blue-400">Interface</span>
                    <span className="text-slate-300">{correlationChain.interface.name}</span>
                    <span className={`ml-auto text-xs ${correlationChain.interface.status === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {correlationChain.interface.status}
                    </span>
                  </div>
                )}
                {correlationChain.device && (
                  <div className="flex items-center gap-2 p-2 bg-[#0f2023] rounded ml-8">
                    <span className="text-amber-400">Device</span>
                    <span className="text-slate-300">{correlationChain.device.name}</span>
                    <span className={`ml-auto text-xs ${correlationChain.device.status === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {correlationChain.device.status} {correlationChain.device.latency_ms > 0 && `(${correlationChain.device.latency_ms.toFixed(1)}ms)`}
                    </span>
                  </div>
                )}
                {correlationChain.vlan && (
                  <div className="flex items-center gap-2 p-2 bg-[#0f2023] rounded ml-12">
                    <span className="text-purple-400">VLAN</span>
                    <span className="text-slate-300">{correlationChain.vlan.vlan_number} - {correlationChain.vlan.name}</span>
                  </div>
                )}
                {correlationChain.subnet && (
                  <div className="flex items-center gap-2 p-2 bg-[#0f2023] rounded ml-16">
                    <span className="text-emerald-400">Subnet</span>
                    <span className="text-slate-300">{correlationChain.subnet.cidr}</span>
                    <span className="ml-auto text-xs text-slate-500">{correlationChain.subnet.utilization_pct}%</span>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* IP History Modal */}
      {historyIp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#132a2f] border border-[#1e3a40] rounded-lg p-6 w-[480px] max-h-[500px] flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h4 className="text-sm font-semibold text-slate-200">IP History</h4>
                <span className="font-mono text-cyan-300 text-sm">{historyIp.address}</span>
              </div>
              <button
                onClick={() => setHistoryIp(null)}
                className="text-slate-500 hover:text-slate-300"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {historyLoading ? (
                <div className="text-center text-slate-500 py-8 text-sm">Loading...</div>
              ) : historyEvents.length === 0 ? (
                <div className="text-center text-slate-500 py-8 text-sm">No history available</div>
              ) : (
                <div className="space-y-2">
                  {historyEvents.map((evt, i) => (
                    <div key={i} className="flex items-start gap-3 p-2.5 bg-[#0f2023] border border-[#1e3a40] rounded">
                      <div className="flex flex-col items-center gap-1 flex-shrink-0">
                        <span className={`w-2.5 h-2.5 rounded-full ${
                          evt.new_status === 'assigned' ? 'bg-cyan-400' :
                          evt.new_status === 'reserved' ? 'bg-blue-400' :
                          evt.new_status === 'available' ? 'bg-emerald-400' :
                          evt.new_status === 'deprecated' ? 'bg-slate-500' : 'bg-slate-600'
                        }`} />
                        {i < historyEvents.length - 1 && (
                          <div className="w-px h-6 bg-[#1e3a40]" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-slate-200 font-medium">{evt.action}</span>
                          {evt.old_status && evt.new_status && (
                            <span className="text-xs text-slate-500">
                              {evt.old_status} → {evt.new_status}
                            </span>
                          )}
                        </div>
                        {evt.details && (
                          <div className="text-xs text-slate-400 mt-0.5">{evt.details}</div>
                        )}
                        {evt.device_id && (
                          <div className="text-xs text-slate-500 mt-0.5">Device: {evt.device_id}</div>
                        )}
                        {evt.timestamp && (
                          <div className="text-[10px] text-slate-600 mt-1">
                            {new Date(evt.timestamp).toLocaleString()}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
