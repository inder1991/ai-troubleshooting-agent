import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

const STATUS_COLORS: Record<string, string> = {
  healthy: '#10b981',
  degraded: '#f59e0b',
  critical: '#ef4444',
  unreachable: '#ef4444',
  stale: '#64748b',
  unknown: '#64748b',
};

const DEVICE_ICONS: Record<string, string> = {
  ROUTER: 'router',
  SWITCH: 'switch',
  FIREWALL: 'security',
  LOAD_BALANCER: 'dns',
  HOST: 'cloud',
  TRANSIT_GATEWAY: 'hub',
  CLOUD_GATEWAY: 'cloud',
  VIRTUAL_APPLIANCE: 'memory',
  PROXY: 'vpn_lock',
  VPN_CONCENTRATOR: 'vpn_key',
};

const TYPE_ABBREV: Record<string, string> = {
  ROUTER: 'RTR',
  SWITCH: 'SW',
  FIREWALL: 'FW',
  LOAD_BALANCER: 'LB',
  HOST: 'HOST',
  TRANSIT_GATEWAY: 'TGW',
  CLOUD_GATEWAY: 'CGW',
  VIRTUAL_APPLIANCE: 'VA',
  PROXY: 'PRX',
  VPN_CONCENTRATOR: 'VPN',
};

const TYPE_BADGE_COLORS: Record<string, string> = {
  FIREWALL: '#ef4444',
  ROUTER: '#3b82f6',
  SWITCH: '#10b981',
  LOAD_BALANCER: '#8b5cf6',
  TRANSIT_GATEWAY: '#f59e0b',
  HOST: '#64748b',
  PROXY: '#f59e0b',
};

interface LiveDeviceNodeProps {
  data: {
    label: string;
    deviceType: string;
    ip: string;
    vendor: string;
    role: string;
    group: string;
    status: string;
    haRole: string;
    isOnPath?: boolean;
    isBlastTarget?: boolean;
  };
  selected: boolean;
}

const LiveDeviceNode: React.FC<LiveDeviceNodeProps> = memo(({ data, selected }) => {
  const statusColor = STATUS_COLORS[data.status] || STATUS_COLORS.unknown;
  const icon = DEVICE_ICONS[data.deviceType] || 'dns';
  const isHighlighted = data.isOnPath || data.isBlastTarget || selected;

  return (
    <div
      style={{
        background: '#1e1b15',
        border: `2px solid ${isHighlighted ? '#e09f3e' : statusColor}`,
        borderRadius: 8,
        padding: '6px 10px',
        minWidth: 150,
        maxWidth: 220,
        boxShadow: isHighlighted
          ? '0 0 12px rgba(224,159,62,0.3)'
          : data.isBlastTarget
            ? '0 0 12px rgba(239,68,68,0.3)'
            : 'none',
        transition: 'border-color 200ms, box-shadow 200ms',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none', width: 8, height: 8 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none', width: 8, height: 8 }} />
      <Handle type="target" position={Position.Left} style={{ background: 'transparent', border: 'none', width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: 'transparent', border: 'none', width: 8, height: 8 }} />

      {/* Top: Type badge + status dot */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.05em',
          color: TYPE_BADGE_COLORS[data.deviceType] || '#64748b',
          textTransform: 'uppercase',
        }}>
          {TYPE_ABBREV[data.deviceType] || data.deviceType}
        </span>
        <span style={{
          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
          background: statusColor,
          boxShadow: data.status === 'critical' ? `0 0 8px ${statusColor}` : 'none',
        }} />
      </div>

      {/* Icon + Name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ color: statusColor, fontSize: 22 }}>
          {icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: 'white', fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {data.label}
          </div>
          <div style={{ color: '#8a7e6b', fontSize: 9 }}>{data.vendor}</div>
        </div>
      </div>

      {/* IP + HA */}
      {(data.ip || data.haRole) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 }}>
          {data.ip && <span style={{ color: '#64748b', fontSize: 9, fontFamily: 'monospace' }}>{data.ip}</span>}
          {data.haRole && (
            <span style={{ color: data.haRole === 'active' ? '#10b981' : '#64748b', fontSize: 8, textTransform: 'uppercase', fontWeight: 600 }}>
              {data.haRole}
            </span>
          )}
        </div>
      )}
    </div>
  );
});

LiveDeviceNode.displayName = 'LiveDeviceNode';
export default LiveDeviceNode;
