import React, { useState, useEffect, useMemo } from 'react';
import type { MonitoredDevice, InterfaceMetrics } from '../../types';
import { fetchDeviceInterfaces, exportInterfaces } from '../../services/api';
import { useDebounce } from '../../hooks/useDebounce';

interface NDMInterfacesTabProps {
  devices: MonitoredDevice[];
}

interface DeviceInterface extends InterfaceMetrics {
  device_id: string;
  device_hostname: string;
}

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10, padding: 20,
};

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
};

const formatSpeed = (speedMbps: number): string => {
  if (speedMbps >= 1000) return `${(speedMbps / 1000).toFixed(0)} Gbps`;
  return `${speedMbps} Mbps`;
};

const NDMInterfacesTab: React.FC<NDMInterfacesTabProps> = ({ devices }) => {
  const [allInterfaces, setAllInterfaces] = useState<DeviceInterface[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [sortField, setSortField] = useState<'utilization_pct' | 'in_errors' | 'out_errors' | 'speed'>('utilization_pct');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [statusFilter, setStatusFilter] = useState<'all' | 'up' | 'down'>('all');

  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      setError('');
      const results: DeviceInterface[] = [];

      const promises = devices.map(async (device) => {
        try {
          const resp = await fetchDeviceInterfaces(device.device_id);
          const interfaces: InterfaceMetrics[] = resp.interfaces || [];
          interfaces.forEach(iface => {
            results.push({
              ...iface,
              device_id: device.device_id,
              device_hostname: device.hostname || device.management_ip,
            });
          });
        } catch {
          // skip devices that fail
        }
      });

      await Promise.all(promises);
      setAllInterfaces(results);
      setLoading(false);
    };

    if (devices.length > 0) {
      fetchAll();
    } else {
      setAllInterfaces([]);
      setLoading(false);
    }
  }, [devices]);

  const filtered = useMemo(() => {
    let list = allInterfaces;
    if (statusFilter !== 'all') {
      list = list.filter(i => i.status === statusFilter);
    }
    if (debouncedSearch) {
      const s = debouncedSearch.toLowerCase();
      list = list.filter(i =>
        i.name.toLowerCase().includes(s) || i.device_hostname.toLowerCase().includes(s)
      );
    }
    list.sort((a, b) => {
      const aVal = a[sortField] ?? 0;
      const bVal = b[sortField] ?? 0;
      return sortDir === 'desc' ? (bVal as number) - (aVal as number) : (aVal as number) - (bVal as number);
    });
    return list;
  }, [allInterfaces, debouncedSearch, sortField, sortDir, statusFilter]);

  const handleExportCSV = async () => {
    try {
      const blob = await exportInterfaces('csv');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'interfaces.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const saturationStats = useMemo(() => {
    const critical = allInterfaces.filter(i => i.utilization_pct > 95).length;
    const warning = allInterfaces.filter(i => i.utilization_pct > 85 && i.utilization_pct <= 95).length;
    const healthy = allInterfaces.filter(i => i.utilization_pct <= 85).length;
    const errorInterfaces = allInterfaces.filter(i => i.in_errors > 0 || i.out_errors > 0).length;
    return { critical, warning, healthy, errorInterfaces, total: allInterfaces.length };
  }, [allInterfaces]);

  const getRowBg = (util: number): string => {
    if (util > 95) return 'rgba(239,68,68,0.08)';
    if (util > 85) return 'rgba(245,158,11,0.08)';
    return 'transparent';
  };

  const sortIcon = (field: typeof sortField) => {
    if (sortField !== field) return 'unfold_more';
    return sortDir === 'desc' ? 'arrow_downward' : 'arrow_upward';
  };

  if (loading) {
    return (
      <div style={{ padding: 32, color: '#8a7e6b', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ animation: 'spin 1s linear infinite' }}>progress_activity</span>
        Fetching interface data from {devices.length} devices...
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Interfaces', value: saturationStats.total, color: '#e8e0d4', icon: 'settings_ethernet' },
          { label: 'Healthy (<85%)', value: saturationStats.healthy, color: '#22c55e', icon: 'check_circle' },
          { label: 'Warning (>85%)', value: saturationStats.warning, color: '#f59e0b', icon: 'warning' },
          { label: 'Critical (>95%)', value: saturationStats.critical, color: '#ef4444', icon: 'error' },
          { label: 'With Errors', value: saturationStats.errorInterfaces, color: '#a855f7', icon: 'bug_report' },
        ].map(card => (
          <div key={card.label} style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <span className="material-symbols-outlined" style={{ fontSize: 18, color: card.color }}>{card.icon}</span>
              <span style={{ fontSize: 11, color: '#64748b' }}>{card.label}</span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: card.color }}>{card.value}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 360 }}>
          <span className="material-symbols-outlined" style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            fontSize: 18, color: '#64748b',
          }}>search</span>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by interface or device..."
            style={{
              width: '100%', padding: '8px 12px 8px 34px', background: 'rgba(224,159,62,0.06)',
              border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
              fontSize: 12, outline: 'none',
            }}
          />
        </div>
        <button
          onClick={handleExportCSV}
          style={{ display: 'flex', alignItems: 'center', gap: 4, background: 'rgba(224,159,62,0.08)', border: '1px solid rgba(224,159,62,0.2)', borderRadius: 8, color: '#e09f3e', padding: '6px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>download</span>
          Export CSV
        </button>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['all', 'up', 'down'] as const).map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              style={{
                padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 500,
                border: statusFilter === s ? '1px solid #e09f3e' : '1px solid rgba(148,163,184,0.15)',
                background: statusFilter === s ? 'rgba(224,159,62,0.15)' : 'transparent',
                color: statusFilter === s ? '#e09f3e' : '#8a7e6b',
                cursor: 'pointer', textTransform: 'capitalize',
              }}
            >
              {s === 'all' ? 'All Status' : s}
            </button>
          ))}
        </div>
      </div>

      {error && <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* Interface Table */}
      <div style={cardStyle}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, display: 'block', marginBottom: 8 }}>settings_ethernet</span>
            {allInterfaces.length === 0 ? 'No interface data available.' : 'No interfaces match your filters.'}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.15)' }}>
                  {[
                    { key: 'device', label: 'Device', sortable: false },
                    { key: 'interface', label: 'Interface', sortable: false },
                    { key: 'status', label: 'Status', sortable: false },
                    { key: 'speed', label: 'Speed', sortable: true, field: 'speed' as const },
                    { key: 'in_octets', label: 'In Octets', sortable: false },
                    { key: 'out_octets', label: 'Out Octets', sortable: false },
                    { key: 'in_errors', label: 'In Errors', sortable: true, field: 'in_errors' as const },
                    { key: 'out_errors', label: 'Out Errors', sortable: true, field: 'out_errors' as const },
                    { key: 'utilization', label: 'Utilization', sortable: true, field: 'utilization_pct' as const },
                  ].map(col => (
                    <th
                      key={col.key}
                      onClick={col.sortable && col.field ? () => handleSort(col.field!) : undefined}
                      style={{
                        padding: '8px 8px', textAlign: 'left', fontSize: 11, color: '#64748b',
                        fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
                        cursor: col.sortable ? 'pointer' : 'default', userSelect: 'none',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        {col.label}
                        {col.sortable && col.field && (
                          <span className="material-symbols-outlined" style={{ fontSize: 14, color: sortField === col.field ? '#e09f3e' : '#475569' }}>
                            {sortIcon(col.field)}
                          </span>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((iface, idx) => (
                  <tr key={`${iface.device_id}-${iface.name}-${idx}`} style={{
                    borderBottom: '1px solid rgba(148,163,184,0.06)',
                    background: getRowBg(iface.utilization_pct),
                  }}>
                    <td style={{ padding: '8px 8px', fontSize: 12, color: '#e8e0d4', fontWeight: 500 }}>
                      {iface.device_hostname}
                    </td>
                    <td className="font-mono" style={{ padding: '8px 8px', fontSize: 12, color: '#8a7e6b' }}>
                      {iface.name}
                    </td>
                    <td style={{ padding: '8px 8px' }}>
                      <span style={{
                        fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600,
                        background: iface.status === 'up' ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                        color: iface.status === 'up' ? '#22c55e' : '#ef4444',
                      }}>
                        {iface.status}
                      </span>
                    </td>
                    <td style={{ padding: '8px 8px', fontSize: 12, color: '#8a7e6b' }}>
                      {iface.speed > 0 ? formatSpeed(iface.speed) : '-'}
                    </td>
                    <td className="font-mono" style={{ padding: '8px 8px', fontSize: 12, color: '#8a7e6b' }}>
                      {formatBytes(iface.in_octets)}
                    </td>
                    <td className="font-mono" style={{ padding: '8px 8px', fontSize: 12, color: '#8a7e6b' }}>
                      {formatBytes(iface.out_octets)}
                    </td>
                    <td style={{ padding: '8px 8px', fontSize: 12, color: iface.in_errors > 0 ? '#ef4444' : '#64748b', fontWeight: iface.in_errors > 0 ? 600 : 400 }}>
                      {iface.in_errors.toLocaleString()}
                    </td>
                    <td style={{ padding: '8px 8px', fontSize: 12, color: iface.out_errors > 0 ? '#ef4444' : '#64748b', fontWeight: iface.out_errors > 0 ? 600 : 400 }}>
                      {iface.out_errors.toLocaleString()}
                    </td>
                    <td style={{ padding: '8px 8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{
                          width: 60, height: 6, borderRadius: 3,
                          background: 'rgba(148,163,184,0.1)', overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${Math.min(iface.utilization_pct, 100)}%`, height: '100%', borderRadius: 3,
                            background: iface.utilization_pct > 95 ? '#ef4444' : iface.utilization_pct > 85 ? '#f59e0b' : '#e09f3e',
                            transition: 'width 0.3s ease',
                          }} />
                        </div>
                        <span style={{
                          fontSize: 12, fontWeight: 600, minWidth: 36,
                          color: iface.utilization_pct > 95 ? '#ef4444' : iface.utilization_pct > 85 ? '#f59e0b' : '#8a7e6b',
                        }}>
                          {iface.utilization_pct.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default NDMInterfacesTab;
