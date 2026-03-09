import React, { useState, useMemo, useCallback } from 'react';
import type { MonitoredDevice } from '../../types';
import { deleteMonitoredDevice, testMonitoredDevice, pingMonitoredDevice } from '../../services/api';
import AddDeviceForm from './AddDeviceForm';
import { useDebounce } from '../../hooks/useDebounce';
import { showToast } from './Toast';

interface NDMDevicesTabProps {
  devices: MonitoredDevice[];
  onSelectDevice: (id: string) => void;
  onReload: () => void;
}

type GroupByOption = 'none' | 'vendor' | 'device_type' | 'profile' | 'tag_prefix';

const STATUS_COLOR: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#94a3b8',
};

const cardStyle: React.CSSProperties = {
  background: 'rgba(7,182,213,0.04)', border: '1px solid rgba(7,182,213,0.12)',
  borderRadius: 10, padding: 20,
};

const btnStyle: React.CSSProperties = {
  padding: 4, background: 'transparent', border: '1px solid rgba(148,163,184,0.15)',
  borderRadius: 4, color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center',
};

const NDMDevicesTab: React.FC<NDMDevicesTabProps> = ({ devices, onSelectDevice, onReload }) => {
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [groupBy, setGroupBy] = useState<GroupByOption>('none');
  const [showAddDevice, setShowAddDevice] = useState(false);

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

  const filtered = useMemo(() => {
    if (!debouncedSearch) return devices;
    const s = debouncedSearch.toLowerCase();
    return devices.filter(d =>
      d.hostname.toLowerCase().includes(s) || d.management_ip.includes(s)
      || d.vendor.toLowerCase().includes(s) || (d.matched_profile || '').toLowerCase().includes(s)
      || d.tags.some(t => t.toLowerCase().includes(s))
    );
  }, [devices, debouncedSearch]);

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
    const statusColor = STATUS_COLOR[device.status] || '#94a3b8';
    const rtt = device.last_ping?.rtt_avg;
    const loss = device.last_ping?.packet_loss_pct;

    return (
      <tr
        key={device.device_id}
        onClick={() => onSelectDevice(device.device_id)}
        style={{ borderBottom: '1px solid rgba(148,163,184,0.08)', cursor: 'pointer', transition: 'background 0.1s' }}
        onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'rgba(7,182,213,0.04)'; }}
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
        <td style={{ padding: '10px 8px', color: '#e2e8f0', fontSize: 13, fontWeight: 500 }}>
          {device.hostname || device.management_ip}
        </td>
        <td style={{ padding: '10px 8px', color: '#94a3b8', fontSize: 13, fontFamily: 'monospace' }}>
          {device.management_ip}
        </td>
        <td style={{ padding: '10px 8px', color: '#94a3b8', fontSize: 12, textTransform: 'capitalize' }}>
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
                background: 'rgba(148,163,184,0.1)', color: '#94a3b8',
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
        <td style={{ padding: '10px 8px', color: '#94a3b8', fontSize: 12 }}>
          {rtt !== undefined && rtt > 0 ? `${rtt.toFixed(1)}ms` : '-'}
        </td>
        <td style={{ padding: '10px 8px', color: '#94a3b8', fontSize: 12 }}>
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

  const tableHeaders = ['Status', 'Hostname', 'IP', 'Vendor', 'Profile', 'Tags', 'Last Collected', 'RTT', 'Loss', 'Actions'];

  const renderTable = (deviceList: MonitoredDevice[]) => (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.15)' }}>
            {tableHeaders.map(h => (
              <th key={h} style={{
                padding: '8px 8px', textAlign: 'left', fontSize: 11, color: '#64748b',
                fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
              }}>
                {h}
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
    padding: '6px 12px', background: 'rgba(7,182,213,0.06)',
    border: '1px solid rgba(7,182,213,0.15)', borderRadius: 6, color: '#e2e8f0',
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
                width: '100%', padding: '8px 12px 8px 34px', background: 'rgba(7,182,213,0.06)',
                border: '1px solid rgba(7,182,213,0.15)', borderRadius: 6, color: '#e2e8f0',
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
        <button
          onClick={() => setShowAddDevice(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', background: '#07b6d5', border: 'none', borderRadius: 6,
            color: '#0f2023', cursor: 'pointer', fontSize: 12, fontWeight: 600,
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
          Add Device
        </button>
      </div>

      {/* Add Device Form */}
      {showAddDevice && (
        <div style={cardStyle}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18, color: '#07b6d5' }}>add_circle</span>
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
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: 0 }}>
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
                <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ textTransform: 'capitalize' }}>{groupName}</span>
                  <span style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 10,
                    background: 'rgba(7,182,213,0.15)', color: '#07b6d5',
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
