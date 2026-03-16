import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  critical: '#ef4444',
  unreachable: '#ef4444',
  stale: '#6b7280',
  unknown: '#6b7280',
  initializing: '#e09f3e',
};

const TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  FIREWALL:          { icon: 'local_fire_department', color: '#ef4444', label: 'FW' },
  ROUTER:            { icon: 'router',               color: '#3b82f6', label: 'RTR' },
  SWITCH:            { icon: 'device_hub',           color: '#10b981', label: 'SW' },
  LOAD_BALANCER:     { icon: 'balance',              color: '#a855f7', label: 'LB' },
  HOST:              { icon: 'dns',                  color: '#6b7280', label: 'SRV' },
  TRANSIT_GATEWAY:   { icon: 'hub',                  color: '#f59e0b', label: 'TGW' },
  CLOUD_GATEWAY:     { icon: 'cloud_sync',           color: '#06b6d4', label: 'GW' },
  NAT_GATEWAY:       { icon: 'swap_horiz',           color: '#06b6d4', label: 'NAT' },
  VIRTUAL_APPLIANCE: { icon: 'memory',               color: '#8b5cf6', label: 'VA' },
  PROXY:             { icon: 'vpn_lock',             color: '#f59e0b', label: 'PRX' },
  VPN_CONCENTRATOR:  { icon: 'vpn_key',              color: '#06b6d4', label: 'VPN' },
  SDWAN_EDGE:        { icon: 'lan',                  color: '#10b981', label: 'SDWAN' },
};

const DEFAULT_CONFIG = { icon: 'dns', color: '#6b7280', label: 'DEV' };

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
  const isCritical = data.status === 'critical' || data.status === 'unreachable';
  const isHighlighted = data.isOnPath || data.isBlastTarget || selected;

  // Critical = red border + red glow. Blast = red. Path/selected = amber. Normal = subtle.
  const borderColor = isCritical ? '#ef4444'
    : data.isBlastTarget ? '#ef4444'
    : isHighlighted ? '#e09f3e'
    : '#2a2520';

  const shadow = isCritical ? '0 0 16px rgba(239,68,68,0.5)'
    : data.isBlastTarget ? '0 0 12px rgba(239,68,68,0.3)'
    : isHighlighted ? '0 0 12px rgba(224,159,62,0.3)'
    : 'none';

  return (
    <div
      style={{
        background: isCritical ? '#1a0f0f' : '#15130f',
        borderRadius: 6,
        overflow: 'hidden',
        width: 170,
        border: `1.5px solid ${borderColor}`,
        boxShadow: shadow,
        transition: 'border-color 200ms, box-shadow 200ms',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      {/* Handles — invisible */}
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="target" position={Position.Left} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right} style={{ background: 'transparent', border: 'none', width: 1, height: 1 }} />

      <div style={{ padding: '7px 9px 6px' }}>
        {/* Row 1: Icon + Name + Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            className="material-symbols-outlined"
            style={{
              fontSize: 18,
              color: typeConfig.color,
              opacity: 0.9,
              flexShrink: 0,
            }}
          >
            {typeConfig.icon}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              color: '#e8e0d4',
              fontSize: 11,
              fontWeight: 600,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              lineHeight: 1.3,
            }}>
              {data.label}
            </div>
          </div>
          {/* Status indicator — larger for critical */}
          <span
            style={{
              width: isCritical ? 10 : 7,
              height: isCritical ? 10 : 7,
              borderRadius: '50%',
              flexShrink: 0,
              background: statusColor,
              boxShadow: isCritical ? `0 0 8px ${statusColor}` : 'none',
            }}
            title={data.status}
          />
        </div>

        {/* Row 2: Type + HA + IP — compact metadata */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          marginTop: 4,
          fontSize: 10,
          color: '#7a7060',
          lineHeight: 1,
        }}>
          <span style={{
            background: `${typeConfig.color}18`,
            color: typeConfig.color,
            padding: '1px 4px',
            borderRadius: 3,
            fontWeight: 700,
            fontSize: 9,
            letterSpacing: '0.04em',
          }}>
            {typeConfig.label}
          </span>
          {data.haRole && (
            <span style={{
              color: data.haRole === 'active' ? '#22c55e' : '#6b7280',
              fontWeight: 600,
              fontSize: 9,
            }}>
              {data.haRole}
            </span>
          )}
          <span style={{ flex: 1 }} />
          {data.ip && (
            <span style={{ fontSize: 9, color: '#5a5348', fontFamily: 'ui-monospace, monospace' }}>
              {data.ip}
            </span>
          )}
        </div>

        {/* Row 3: Operational metrics (only when data present) */}
        {(data.cpuPct != null || data.sessionCount != null || data.poolHealth || data.bgpPeers) && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            marginTop: 4,
            paddingTop: 4,
            borderTop: '1px solid #1e1b15',
            fontSize: 9,
            color: '#6b7280',
          }}>
            {data.cpuPct != null && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <div style={{ width: 24, height: 3, background: '#1e1b15', borderRadius: 1, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(data.cpuPct, 100)}%`,
                    height: '100%',
                    borderRadius: 1,
                    background: data.cpuPct > 90 ? '#ef4444' : data.cpuPct > 70 ? '#f59e0b' : '#22c55e',
                    transition: 'width 400ms',
                  }} />
                </div>
                <span style={{
                  fontFamily: 'ui-monospace, monospace',
                  fontSize: 9,
                  color: data.cpuPct > 80 ? '#f59e0b' : '#5a5348',
                }}>
                  {data.cpuPct.toFixed(0)}%
                </span>
              </div>
            )}
            {data.sessionCount != null && (
              <span style={{ color: '#7a7060' }}>
                {data.sessionCount > 1000 ? `${(data.sessionCount / 1000).toFixed(0)}K` : data.sessionCount} sess
              </span>
            )}
            {data.poolHealth && (
              <span style={{ color: '#22c55e' }}>
                {data.poolHealth}
              </span>
            )}
            {data.bgpPeers && (
              <span style={{ color: '#7a7060' }}>
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
