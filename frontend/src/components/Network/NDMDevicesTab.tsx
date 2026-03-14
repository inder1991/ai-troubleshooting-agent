import React, { useState, useMemo, useCallback } from 'react';
import type { MonitoredDevice } from '../../types';
import { deleteMonitoredDevice, testMonitoredDevice, pingMonitoredDevice, exportDevices, importDevices, bulkDeleteDevices, bulkValidate } from '../../services/api';
import AddDeviceForm from './AddDeviceForm';
import { useDebounce } from '../../hooks/useDebounce';
import { showToast } from './Toast';

interface NDMDevicesTabProps {
  devices: MonitoredDevice[];
  onSelectDevice: (id: string) => void;
  onReload: () => void;
}

type GroupByOption = 'none' | 'vendor' | 'device_type' | 'profile' | 'tag_prefix';
type SortField = 'hostname' | 'status' | 'vendor' | 'last_collected';
type SortDir = 'asc' | 'desc';

const STATUS_COLOR: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#8a7e6b',
};

const STATUS_ORDER: Record<string, number> = {
  down: 0,
  unreachable: 1,
  new: 2,
  up: 3,
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(224,159,62,0.04)', border: '1px solid rgba(224,159,62,0.12)',
  borderRadius: 10, padding: 20,
};

const btnStyle: React.CSSProperties = {
  padding: 4, background: 'transparent', border: '1px solid rgba(148,163,184,0.15)',
  borderRadius: 4, color: '#8a7e6b', cursor: 'pointer', display: 'flex', alignItems: 'center',
};

const NDMDevicesTab: React.FC<NDMDevicesTabProps> = ({ devices, onSelectDevice, onReload }) => {
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [groupBy, setGroupBy] = useState<GroupByOption>('none');
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [sortField, setSortField] = useState<SortField>('hostname');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [importing, setImporting] = useState(false);
  const [validating, setValidating] = useState(false);

  const handleDelete = useCallback(async (id: string) => {
    if (!confirm('Remove this device from monitoring?')) return;
    try { await deleteMonitoredDevice(id); onReload(); } catch { /* ignore */ }
  }, [onReload]);

  const handleTest = useCallback(async (id: string) => {
    try {
      const result = await testMonitoredDevice(id);
      const status = result.health?.status || 'unknown';
      const msg = result.health?.message || '';
      showToast(`SNMP Test: ${status}\n${msg}`, status === 'ok' ? 'success' : 'warning');
    } catch (err: unknown) {
      showToast(`Test failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error');
    }
  }, []);

  const handlePing = useCallback(async (id: string) => {
    try {
      const result = await pingMonitoredDevice(id);
      const p = result.ping;
      showToast(`Ping: ${p.reachable ? 'Reachable' : 'Unreachable'}\nRTT: ${p.rtt_avg.toFixed(1)}ms\nLoss: ${p.packet_loss_pct.toFixed(0)}%`, p.reachable ? 'success' : 'warning');
      onReload();
    } catch (err: unknown) {
      showToast(`Ping failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error');
    }
  }, [onReload]);

  const handleExportCSV = async () => {
    try {
      const blob = await exportDevices('csv');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'devices.csv';
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await importDevices(formData);
      onReload();
    } catch { /* ignore */ }
    setImporting(false);
    e.target.value = '';
  };

  const handleValidateAll = async () => {
    setValidating(true);
    try {
      await bulkValidate(devices.map((d: any) => ({ id: d.id || d.device_id })));
    } catch { /* ignore */ }
    setValidating(false);
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortIcon = (field: SortField) => {
    if (sortField !== field) return 'unfold_more';
    return sortDir === 'desc' ? 'arrow_downward' : 'arrow_upward';
  };

  const filtered = useMemo(() => {
    let list = devices;
    if (debouncedSearch) {
      const s = debouncedSearch.toLowerCase();
      list = list.filter(d =>
        d.hostname.toLowerCase().includes(s) || d.management_ip.includes(s)
        || d.vendor.toLowerCase().includes(s) || (d.matched_profile || '').toLowerCase().includes(s)
        || d.tags.some(t => t.toLowerCase().includes(s))
      );
    }

    // Sort the list
    const sorted = [...list].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (sortField) {
        case 'hostname':
          aVal = (a.hostname || a.management_ip).toLowerCase();
          bVal = (b.hostname || b.management_ip).toLowerCase();
          break;
        case 'status':
          aVal = STATUS_ORDER[a.status] ?? 99;
          bVal = STATUS_ORDER[b.status] ?? 99;
          break;
        case 'vendor':
          aVal = (a.vendor || '').toLowerCase();
          bVal = (b.vendor || '').toLowerCase();
          break;
        case 'last_collected':
          aVal = a.last_collected ?? 0;
          bVal = b.last_collected ?? 0;
          break;
        default:
          return 0;
      }

      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return sorted;
  }, [devices, debouncedSearch, sortField, sortDir]);

  const grouped = useMemo(() => {
    if (groupBy === 'none') return { '': filtered };
    const groups: Record<string, MonitoredDevice[]> = {};
    filtered.forEach(d => {
      let key: string;
      switch (groupBy) {
        case 'vendor': key = d.vendor || 'Unknown'; break;
        case 'device_type': key = d.os_family || 'Unknown'; break;
        case 'profile': key = d.matched_profile || 'Unmatched'; break;
        case 'tag_prefix': {
          const prefix = d.tags.length > 0 ? d.tags[0].split(':')[0] : 'Untagged';
          key = prefix;
          break;
        }
        default: key = '';
      }
      if (!groups[key]) groups[key] = [];
      groups[key].push(d);
    });
    return groups;
  }, [filtered, groupBy]);

  const renderDeviceRow = (device: MonitoredDevice) => {
    const statusColor = STATUS_COLOR[device.status] || '#8a7e6b';
    const rtt = device.last_ping?.rtt_avg;
    const loss = device.last_ping?.packet_loss_pct;

    return (
      <tr
        key={device.device_id}
        onClick={() => onSelectDevice(device.device_id)}
        style={{ borderBottom: '1px solid rgba(148,163,184,0.08)', cursor: 'pointer', transition: 'background 0.1s' }}
        onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'rgba(224,159,62,0.04)'; }}
        onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
      >
        <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%', background: statusColor,
              boxShadow: device.status === 'up' ? `0 0 6px ${statusColor}` : undefined,
            }} />
            <span style={{
              fontSize: 11, padding: '2px 6px', borderRadius: 4, fontWeight: 500,
              background: device.status === 'up' ? 'rgba(34,197,94,0.12)' : device.status === 'down' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
              color: statusColor,
            }}>
              {device.status}
            </span>
          </div>
        </td>
        <td style={{ padding: '10px 8px', color: '#e8e0d4', fontSize: 13, fontWeight: 500 }}>
          {device.hostname || device.management_ip}
        </td>
        <td className="font-mono" style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 13 }}>
          {device.management_ip}
        </td>
        <td style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 12, textTransform: 'capitalize' }}>
          {device.vendor || '-'}
        </td>
        <td style={{ padding: '10px 8px' }}>
          {device.matched_profile ? (
            <span style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 4, fontWeight: 500,
              background: 'rgba(34,197,94,0.12)', color: '#22c55e',
            }}>
              {device.matched_profile}
            </span>
          ) : (
            <span style={{ fontSize: 11, color: '#64748b' }}>unmatched</span>
          )}
        </td>
        <td style={{ padding: '10px 8px' }}>
          <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {device.tags.slice(0, 3).map(tag => (
              <span key={tag} style={{
                fontSize: 10, padding: '1px 5px', borderRadius: 3,
                background: 'rgba(148,163,184,0.1)', color: '#8a7e6b',
              }}>
                {tag}
              </span>
            ))}
            {device.tags.length > 3 && (
              <span style={{ fontSize: 10, color: '#64748b' }}>+{device.tags.length - 3}</span>
            )}
          </div>
        </td>
        <td style={{ padding: '10px 8px', color: '#64748b', fontSize: 12 }}>
          {device.last_collected
            ? new Date(device.last_collected * 1000).toLocaleTimeString()
            : 'Never'}
        </td>
        <td style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 12 }}>
          {rtt !== undefined && rtt > 0 ? `${rtt.toFixed(1)}ms` : '-'}
        </td>
        <td style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 12 }}>
          {loss !== undefined ? `${loss.toFixed(0)}%` : '-'}
        </td>
        <td style={{ padding: '10px 8px' }} onClick={e => e.stopPropagation()}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={() => handleTest(device.device_id)} title="Test SNMP" style={btnStyle}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>speed</span>
            </button>
            <button onClick={() => handlePing(device.device_id)} title="Ping" style={btnStyle}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>network_ping</span>
            </button>
            <button onClick={() => handleDelete(device.device_id)} title="Remove" style={{ ...btnStyle, color: '#ef4444' }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
            </button>
          </div>
        </td>
      </tr>
    );
  };

  const sortableHeaders: { label: string; field: SortField | null }[] = [
    { label: 'Status', field: 'status' },
    { label: 'Hostname', field: 'hostname' },
    { label: 'IP', field: null },
    { label: 'Vendor', field: 'vendor' },
    { label: 'Profile', field: null },
    { label: 'Tags', field: null },
    { label: 'Last Collected', field: 'last_collected' },
    { label: 'RTT', field: null },
    { label: 'Loss', field: null },
    { label: 'Actions', field: null },
  ];

  const renderTable = (deviceList: MonitoredDevice[]) => (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.15)' }}>
            {sortableHeaders.map(h => (
              <th
                key={h.label}
                onClick={h.field ? () => handleSort(h.field!) : undefined}
                style={{
                  padding: '8px 8px', textAlign: 'left', fontSize: 11, color: '#64748b',
                  fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
                  cursor: h.field ? 'pointer' : 'default',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                  {h.label}
                  {h.field && (
                    <span className="material-symbols-outlined" style={{
                      fontSize: 14,
                      color: sortField === h.field ? '#e09f3e' : '#475569',
                    }}>
                      {sortIcon(h.field)}
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {deviceList.map(renderDeviceRow)}
        </tbody>
      </table>
    </div>
  );

  const selectStyle: React.CSSProperties = {
    padding: '6px 12px', background: 'rgba(224,159,62,0.06)',
    border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
    fontSize: 12, outline: 'none', cursor: 'pointer',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flex: 1 }}>
          <div style={{ position: 'relative', flex: 1, maxWidth: 400 }}>
            <span className="material-symbols-outlined" style={{
              position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
              fontSize: 18, color: '#64748b',
            }}>search</span>
            <input
              value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search by hostname, IP, vendor, profile, tag..."
              style={{
                width: '100%', padding: '8px 12px 8px 34px', background: 'rgba(224,159,62,0.06)',
                border: '1px solid rgba(224,159,62,0.15)', borderRadius: 6, color: '#e8e0d4',
                fontSize: 12, outline: 'none',
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#64748b' }}>Group by:</span>
            <select value={groupBy} onChange={e => setGroupBy(e.target.value as GroupByOption)} style={selectStyle}>
              <option value="none">None</option>
              <option value="vendor">Vendor</option>
              <option value="device_type">Device Type</option>
              <option value="profile">Profile</option>
              <option value="tag_prefix">Tag Prefix</option>
            </select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={handleExportCSV}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', background: 'rgba(224,159,62,0.08)',
              border: '1px solid rgba(224,159,62,0.2)', borderRadius: 8,
              color: '#e09f3e', cursor: 'pointer', fontSize: 12, fontWeight: 600,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>download</span>
            Export CSV
          </button>
          <input type="file" accept=".csv,.json" style={{ display: 'none' }} id="device-import-input" onChange={handleImport} />
          <button
            onClick={() => document.getElementById('device-import-input')?.click()}
            disabled={importing}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', background: 'rgba(224,159,62,0.08)',
              border: '1px solid rgba(224,159,62,0.2)', borderRadius: 8,
              color: '#e09f3e', cursor: importing ? 'not-allowed' : 'pointer',
              fontSize: 12, fontWeight: 600, opacity: importing ? 0.5 : 1,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>upload</span>
            {importing ? 'Importing...' : 'Import'}
          </button>
          <button
            onClick={handleValidateAll}
            disabled={validating}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 12px', background: 'rgba(224,159,62,0.08)',
              border: '1px solid rgba(224,159,62,0.2)', borderRadius: 8,
              color: '#e09f3e', cursor: validating ? 'not-allowed' : 'pointer',
              fontSize: 12, fontWeight: 600, opacity: validating ? 0.5 : 1,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>verified</span>
            {validating ? 'Validating...' : 'Validate'}
          </button>
          <button
            onClick={() => setShowAddDevice(true)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', background: '#e09f3e', border: 'none', borderRadius: 6,
              color: '#1a1814', cursor: 'pointer', fontSize: 12, fontWeight: 600,
            }}
          >
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
            Add Device
          </button>
        </div>
      </div>

      {/* Add Device Form */}
      {showAddDevice && (
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#e09f3e' }}>add_circle</span>
            Add Individual Device
          </h3>
          <AddDeviceForm
            onSuccess={() => { setShowAddDevice(false); onReload(); }}
            onCancel={() => setShowAddDevice(false)}
          />
        </div>
      )}

      {/* Device Table / Grouped Tables */}
      {filtered.length === 0 ? (
        <div style={{ ...cardStyle, textAlign: 'center', padding: 48 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 48, color: '#334155', display: 'block', marginBottom: 12 }}>router</span>
          <div style={{ color: '#64748b', fontSize: 14 }}>
            {devices.length === 0 ? 'No devices monitored yet. Add a device to get started.' : 'No devices match your search.'}
          </div>
        </div>
      ) : groupBy === 'none' ? (
        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: 0 }}>
              All Devices ({filtered.length})
            </h3>
          </div>
          {renderTable(filtered)}
        </div>
      ) : (
        Object.entries(grouped)
          .sort(([, a], [, b]) => b.length - a.length)
          .map(([groupName, groupDevices]) => (
            <div key={groupName} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e8e0d4', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ textTransform: 'capitalize' }}>{groupName}</span>
                  <span style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 10,
                    background: 'rgba(224,159,62,0.15)', color: '#e09f3e',
                  }}>
                    {groupDevices.length}
                  </span>
                </h3>
              </div>
              {renderTable(groupDevices)}
            </div>
          ))
      )}
    </div>
  );
};

export default NDMDevicesTab;
