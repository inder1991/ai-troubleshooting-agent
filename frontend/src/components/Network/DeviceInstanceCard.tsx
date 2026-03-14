import React from 'react';
import type { MonitoredDevice } from '../../types';

interface DeviceInstanceCardProps {
  device: MonitoredDevice;
  onTest: (id: string) => void;
  onDelete: (id: string) => void;
  onPing: (id: string) => void;
}

const STATUS_DOT: Record<string, string> = {
  up: '#22c55e',
  down: '#ef4444',
  unreachable: '#f59e0b',
  new: '#8a7e6b',
};

const DeviceInstanceCard: React.FC<DeviceInstanceCardProps> = ({ device, onTest, onDelete, onPing }) => {
  const statusColor = STATUS_DOT[device.status] || '#8a7e6b';
  const rtt = device.last_ping?.rtt_avg;
  const loss = device.last_ping?.packet_loss_pct;

  return (
    <tr style={{ borderBottom: '1px solid rgba(148,163,184,0.08)' }}>
      {/* Status */}
      <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: statusColor,
            boxShadow: device.status === 'up' ? `0 0 6px ${statusColor}` : undefined,
          }} />
          <span style={{ fontSize: 12, color: '#8a7e6b' }}>
            {rtt !== undefined && rtt > 0 ? `${rtt.toFixed(1)}ms` : ''}
          </span>
        </div>
      </td>

      {/* Source */}
      <td style={{ padding: '10px 8px' }}>
        <span style={{
          fontSize: 11, padding: '2px 6px', borderRadius: 4, fontWeight: 500,
          background: device.discovered ? 'rgba(168,85,247,0.15)' : 'rgba(224,159,62,0.15)',
          color: device.discovered ? '#a855f7' : '#e09f3e',
        }}>
          {device.discovered ? 'Auto' : 'Manual'}
        </span>
      </td>

      {/* Hostname */}
      <td style={{ padding: '10px 8px', color: '#e8e0d4', fontSize: 13, fontWeight: 500 }}>
        {device.hostname || device.management_ip}
      </td>

      {/* IP */}
      <td className="font-mono" style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 13 }}>
        {device.management_ip}
      </td>

      {/* Profile */}
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

      {/* Protocols */}
      <td style={{ padding: '10px 8px' }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {device.protocols.filter(p => p.enabled).map(p => (
            <span key={p.protocol} style={{
              fontSize: 10, padding: '1px 5px', borderRadius: 3, textTransform: 'uppercase',
              background: 'rgba(224,159,62,0.1)', color: '#e09f3e', fontWeight: 600,
            }}>
              {p.protocol}
            </span>
          ))}
        </div>
      </td>

      {/* Vendor */}
      <td style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 12, textTransform: 'capitalize' }}>
        {device.vendor || '-'}
      </td>

      {/* Tags */}
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

      {/* Packet Loss */}
      <td style={{ padding: '10px 8px', color: '#8a7e6b', fontSize: 12 }}>
        {loss !== undefined ? `${loss.toFixed(0)}%` : '-'}
      </td>

      {/* Last Collection */}
      <td style={{ padding: '10px 8px', color: '#64748b', fontSize: 12 }}>
        {device.last_collected
          ? new Date(device.last_collected * 1000).toLocaleTimeString()
          : 'Never'}
      </td>

      {/* Actions */}
      <td style={{ padding: '10px 8px' }}>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => onTest(device.device_id)} title="Test SNMP" style={btnStyle}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>speed</span>
          </button>
          <button onClick={() => onPing(device.device_id)} title="Ping" style={btnStyle}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>network_ping</span>
          </button>
          <button onClick={() => onDelete(device.device_id)} title="Remove" style={{ ...btnStyle, color: '#ef4444' }}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
          </button>
        </div>
      </td>
    </tr>
  );
};

const btnStyle: React.CSSProperties = {
  padding: 4, background: 'transparent', border: '1px solid rgba(148,163,184,0.15)',
  borderRadius: 4, color: '#8a7e6b', cursor: 'pointer', display: 'flex', alignItems: 'center',
};

export default DeviceInstanceCard;
