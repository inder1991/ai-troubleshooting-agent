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
        padding: '8px 12px',
        minWidth: 140,
        maxWidth: 200,
        boxShadow: isHighlighted
          ? '0 0 12px rgba(224,159,62,0.3)'
          : data.isBlastTarget
            ? '0 0 12px rgba(239,68,68,0.3)'
            : 'none',
        transition: 'border-color 200ms, box-shadow 200ms',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#3d3528', border: 'none', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: '#3d3528', border: 'none', width: 6, height: 6 }} />
      <Handle type="target" position={Position.Left} style={{ background: '#3d3528', border: 'none', width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: '#3d3528', border: 'none', width: 6, height: 6 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="material-symbols-outlined" style={{ color: statusColor, fontSize: 18 }}>
          {icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: 'white', fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {data.label}
          </div>
          <div style={{ color: '#8a7e6b', fontSize: 9 }}>{data.vendor}</div>
        </div>
        <span style={{
          width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
          background: statusColor,
          boxShadow: data.status === 'critical' ? `0 0 6px ${statusColor}` : 'none',
          animation: data.status === 'critical' ? 'pulse 2s ease-in-out infinite' : 'none',
        }} />
      </div>
      {data.ip && (
        <div style={{ color: '#64748b', fontSize: 9, marginTop: 4, fontFamily: 'monospace' }}>{data.ip}</div>
      )}
      {data.haRole && (
        <div style={{
          color: data.haRole === 'active' ? '#10b981' : '#64748b',
          fontSize: 8, marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          {data.haRole}
        </div>
      )}
    </div>
  );
});

LiveDeviceNode.displayName = 'LiveDeviceNode';
export default LiveDeviceNode;
