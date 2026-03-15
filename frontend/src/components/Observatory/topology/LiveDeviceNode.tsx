import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  critical: '#ef4444',
  unreachable: '#ef4444',
  stale: '#94a3b8',
  unknown: '#94a3b8',
  initializing: '#e09f3e',
};

// Each device TYPE gets its own accent color — recognizable at a glance
const TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  FIREWALL:          { icon: 'local_fire_department', color: '#ef4444', label: 'Firewall' },
  ROUTER:            { icon: 'router',               color: '#3b82f6', label: 'Router' },
  SWITCH:            { icon: 'device_hub',           color: '#10b981', label: 'Switch' },
  LOAD_BALANCER:     { icon: 'balance',              color: '#a855f7', label: 'Load Balancer' },
  HOST:              { icon: 'dns',                  color: '#64748b', label: 'Server' },
  TRANSIT_GATEWAY:   { icon: 'hub',                  color: '#f59e0b', label: 'Transit GW' },
  CLOUD_GATEWAY:     { icon: 'cloud_sync',           color: '#06b6d4', label: 'Cloud GW' },
  NAT_GATEWAY:       { icon: 'swap_horiz',           color: '#06b6d4', label: 'NAT GW' },
  VIRTUAL_APPLIANCE: { icon: 'memory',               color: '#8b5cf6', label: 'Virtual' },
  PROXY:             { icon: 'vpn_lock',             color: '#f59e0b', label: 'Proxy' },
  VPN_CONCENTRATOR:  { icon: 'vpn_key',              color: '#06b6d4', label: 'VPN' },
  SDWAN_EDGE:        { icon: 'lan',                  color: '#10b981', label: 'SD-WAN' },
};

const DEFAULT_CONFIG = { icon: 'dns', color: '#64748b', label: 'Device' };

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
    // Operational metrics
    cpuPct?: number | null;
    memoryPct?: number | null;
    sessionCount?: number | null;
    sessionMax?: number | null;
    threatHits?: number | null;
    sslTps?: number | null;
    poolHealth?: string | null;
    bgpPeers?: string | null;
    routeCount?: number | null;
  };
  selected: boolean;
}

const LiveDeviceNode: React.FC<LiveDeviceNodeProps> = memo(({ data, selected }) => {
  const statusColor = STATUS_COLORS[data.status] || STATUS_COLORS.unknown;
  const typeConfig = TYPE_CONFIG[data.deviceType] || DEFAULT_CONFIG;
  const isHighlighted = data.isOnPath || data.isBlastTarget || selected;

  // Highlighted = amber glow, blast = red glow, otherwise status border
  const borderColor = isHighlighted ? '#e09f3e' : data.isBlastTarget ? '#ef4444' : statusColor;
  const shadowColor = isHighlighted ? 'rgba(224,159,62,0.4)' : data.isBlastTarget ? 'rgba(239,68,68,0.4)' : 'none';

  return (
    <div style={{
      background: '#1e1b15',
      borderRadius: 8,
      overflow: 'hidden',
      minWidth: 150,
      maxWidth: 200,
      border: `1.5px solid ${borderColor}`,
      boxShadow: shadowColor !== 'none' ? `0 0 12px ${shadowColor}` : '0 1px 4px rgba(0,0,0,0.3)',
      transition: 'border-color 300ms, box-shadow 300ms',
    }}>
      {/* Colored top accent bar — device TYPE color */}
      <div style={{
        height: 3,
        background: typeConfig.color,
        opacity: 0.8,
      }} />

      {/* Invisible handles */}
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="target" position={Position.Left} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />

      <div style={{ padding: '8px 10px 6px' }}>
        {/* Icon + Name row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6,
            background: `${typeConfig.color}18`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span className="material-symbols-outlined" style={{
              fontSize: 20, color: typeConfig.color,
            }}>
              {typeConfig.icon}
            </span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              color: 'white', fontSize: 11, fontWeight: 600,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {data.label}
            </div>
            <div style={{ color: '#8a7e6b', fontSize: 9 }}>
              {data.vendor || typeConfig.label}
            </div>
          </div>
          {/* Status dot */}
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: statusColor,
            boxShadow: data.status === 'critical' ? `0 0 6px ${statusColor}` : 'none',
            animation: data.status === 'critical' ? 'pulse 2s ease-in-out infinite' : 'none',
          }} />
        </div>

        {/* Bottom row: type badge + HA role + IP */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4, marginTop: 6,
          fontSize: 8, color: '#64748b',
        }}>
          <span style={{
            background: `${typeConfig.color}20`,
            color: typeConfig.color,
            padding: '1px 5px',
            borderRadius: 3,
            fontWeight: 700,
            fontSize: 8,
            letterSpacing: '0.03em',
          }}>
            {typeConfig.label}
          </span>
          {data.haRole && (
            <span style={{ color: data.haRole === 'active' ? '#22c55e' : '#64748b', fontWeight: 600 }}>
              {data.haRole}
            </span>
          )}
          <span style={{ flex: 1 }} />
          {data.ip && (
            <span style={{ fontFamily: 'monospace', fontSize: 8, color: '#64748b' }}>
              {data.ip}
            </span>
          )}
        </div>

        {/* Operational metrics micro-bar (only when data available) */}
        {(data.cpuPct != null || data.sessionCount != null || data.poolHealth || data.bgpPeers) && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, marginTop: 4,
            paddingTop: 4, borderTop: '1px solid #2a2520',
            fontSize: 8, color: '#64748b',
          }}>
            {/* CPU micro-bar for all devices */}
            {data.cpuPct != null && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ fontSize: 7 }}>CPU</span>
                <div style={{ width: 30, height: 4, background: '#2a2520', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(data.cpuPct, 100)}%`, height: '100%', borderRadius: 2,
                    background: data.cpuPct > 90 ? '#ef4444' : data.cpuPct > 70 ? '#f59e0b' : '#22c55e',
                    transition: 'width 500ms, background 500ms',
                  }} />
                </div>
                <span style={{ fontFamily: 'monospace', color: data.cpuPct > 80 ? '#f59e0b' : '#64748b' }}>
                  {data.cpuPct.toFixed(0)}%
                </span>
              </div>
            )}

            {/* Firewall: session count */}
            {data.sessionCount != null && (
              <span style={{ color: '#94a3b8' }}>
                {data.sessionCount > 1000 ? `${(data.sessionCount/1000).toFixed(0)}K` : data.sessionCount} sess
              </span>
            )}

            {/* LB: pool health */}
            {data.poolHealth && (
              <span style={{ color: data.poolHealth.startsWith(data.poolHealth.split('/')[1]) ? '#22c55e' : '#f59e0b' }}>
                {'\u{1F7E2}'} {data.poolHealth}
              </span>
            )}

            {/* Router: BGP peers */}
            {data.bgpPeers && (
              <span style={{ color: '#94a3b8' }}>
                BGP {data.bgpPeers}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

LiveDeviceNode.displayName = 'LiveDeviceNode';
export default LiveDeviceNode;
