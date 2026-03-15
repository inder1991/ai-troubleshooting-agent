import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',       // Bright green (not emerald — needs to pop)
  degraded: '#f59e0b',      // Amber
  critical: '#ef4444',      // Red
  unreachable: '#ef4444',
  stale: '#94a3b8',
  unknown: '#94a3b8',
  initializing: '#e09f3e',  // Warm amber — "starting up"
};

// SVG paths for network device icons (Cisco-style silhouettes)
const DEVICE_SVGS: Record<string, { path: string; viewBox: string }> = {
  ROUTER: {
    viewBox: '0 0 36 36',
    path: 'M18 4 L32 18 L18 32 L4 18 Z M18 10 L26 18 L18 26 L10 18 Z M14 18 L18 14 L22 18 L18 22 Z',
  },
  SWITCH: {
    viewBox: '0 0 36 36',
    path: 'M4 10 H32 V26 H4 Z M8 14 H12 V18 H8 Z M14 14 H18 V18 H14 Z M20 14 H24 V18 H20 Z M26 14 H30 V18 H26 Z M10 21 V24 M16 21 V24 M22 21 V24 M28 21 V24',
  },
  FIREWALL: {
    viewBox: '0 0 36 36',
    path: 'M4 6 H32 V30 H4 Z M4 14 H32 M4 22 H32 M12 6 V30 M20 6 V30 M28 6 V30',
  },
  LOAD_BALANCER: {
    viewBox: '0 0 36 36',
    path: 'M18 4 L4 18 H14 L8 32 H28 L22 18 H32 Z',
  },
  HOST: {
    viewBox: '0 0 36 36',
    path: 'M6 6 H30 V24 H6 Z M4 24 H32 V30 H4 Z M14 27 H22',
  },
  CLOUD_GATEWAY: {
    viewBox: '0 0 36 36',
    path: 'M8 24 C2 24 2 16 8 16 C8 10 14 6 20 8 C26 4 34 10 30 18 C34 18 34 24 28 24 Z M14 20 L18 16 L22 20 M18 16 V28',
  },
  TRANSIT_GATEWAY: {
    viewBox: '0 0 36 36',
    path: 'M18 4 L32 12 V24 L18 32 L4 24 V12 Z M18 4 V32 M4 12 L32 24 M32 12 L4 24',
  },
  PROXY: {
    viewBox: '0 0 36 36',
    path: 'M6 8 H30 V28 H6 Z M6 14 H30 M18 8 V28 M11 18 L15 22 L11 26 M25 18 L21 22 L25 26',
  },
};

const TYPE_ABBREV: Record<string, string> = {
  ROUTER: 'RTR', SWITCH: 'SW', FIREWALL: 'FW', LOAD_BALANCER: 'LB',
  HOST: 'SRV', TRANSIT_GATEWAY: 'TGW', CLOUD_GATEWAY: 'CGW',
  VIRTUAL_APPLIANCE: 'VA', PROXY: 'PRX', VPN_CONCENTRATOR: 'VPN',
  NAT_GATEWAY: 'NAT', SDWAN_EDGE: 'SDWAN', ACCESS_POINT: 'AP',
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
  const svgData = DEVICE_SVGS[data.deviceType] || DEVICE_SVGS.HOST;
  const typeAbbrev = TYPE_ABBREV[data.deviceType] || '?';
  const isHighlighted = data.isOnPath || data.isBlastTarget || selected;
  const iconColor = isHighlighted ? '#e09f3e' : statusColor;

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '4px 8px',
      filter: isHighlighted ? 'drop-shadow(0 0 8px rgba(224,159,62,0.5))' : data.status === 'critical' ? `drop-shadow(0 0 6px ${statusColor})` : 'none',
      cursor: 'pointer',
      transition: 'filter 200ms',
    }}>
      {/* Invisible handles for edge connections */}
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="target" position={Position.Left} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />

      {/* SVG Device Icon */}
      <svg width={36} height={36} viewBox={svgData.viewBox} style={{ overflow: 'visible' }}>
        <path d={svgData.path} fill="none" stroke={iconColor} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>

      {/* Device name */}
      <div style={{
        color: 'white', fontSize: 11, fontWeight: 600, marginTop: 4,
        textAlign: 'center', maxWidth: 120,
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        textShadow: '0 1px 3px rgba(0,0,0,0.8)',
      }}>
        {data.label}
      </div>

      {/* Vendor + Type + HA */}
      <div style={{
        color: '#8a7e6b', fontSize: 8, textAlign: 'center', marginTop: 1,
        display: 'flex', gap: 4, alignItems: 'center',
      }}>
        <span style={{ color: statusColor, fontWeight: 700 }}>{typeAbbrev}</span>
        {data.haRole && (
          <span style={{ color: data.haRole === 'active' ? '#22c55e' : '#64748b' }}>
            {data.haRole}
          </span>
        )}
      </div>
    </div>
  );
});

LiveDeviceNode.displayName = 'LiveDeviceNode';
export default LiveDeviceNode;
