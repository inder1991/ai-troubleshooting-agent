import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

interface DeviceNodeData {
  label: string;
  deviceType: string;
  ip?: string;
  vendor?: string;
  zone?: string;
  vlan?: number;
  description?: string;
  location?: string;
  status?: 'healthy' | 'degraded' | 'down';
  interfaces?: Array<{
    id: string;
    name: string;
    ip: string;
    role: string;
    zone: string;
  }>;
}

const deviceIcons: Record<string, string> = {
  router: 'router',
  switch: 'swap_horiz',
  firewall: 'local_fire_department',
  workload: 'memory',
  cloud_gateway: 'cloud',
  zone: 'shield',
  vpc: 'cloud_circle',
  transit_gateway: 'hub',
  load_balancer: 'dns',
  vpn_tunnel: 'vpn_lock',
  direct_connect: 'cable',
  nacl: 'checklist',
  vlan: 'label',
  mpls: 'conversion_path',
  compliance_zone: 'verified_user',
};

const statusColors: Record<string, string> = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  down: '#ef4444',
};

const deviceColors: Record<string, string> = {
  firewall: '#ef4444',
  vpc: '#3b82f6',
  transit_gateway: '#a855f7',
  load_balancer: '#22c55e',
  vpn_tunnel: '#f97316',
  direct_connect: '#eab308',
  nacl: '#ef4444',
  vlan: '#14b8a6',
  mpls: '#a855f7',
  compliance_zone: '#f59e0b',
};

const typeAbbreviations: Record<string, string> = {
  firewall: 'FW',
  router: 'RTR',
  switch: 'SW',
  load_balancer: 'LB',
  transit_gateway: 'TGW',
  vpn_tunnel: 'VPN',
  direct_connect: 'DX',
  nacl: 'ACL',
  vlan: 'VLAN',
  mpls: 'MPLS',
  cloud_gateway: 'CGW',
  workload: 'WL',
  vpc: 'VPC',
  compliance_zone: 'CZ',
  zone: 'ZONE',
};

const roleColors: Record<string, string> = {
  inside: '#22c55e',
  outside: '#ef4444',
  dmz: '#f59e0b',
  management: '#3b82f6',
  sync: '#64748b',
  loopback: '#a855f7',
};

const DeviceNode: React.FC<NodeProps<DeviceNodeData>> = ({ data, selected }) => {
  const isFirewall = data.deviceType === 'firewall';
  const icon = deviceIcons[data.deviceType] || 'devices';
  const statusColor = statusColors[data.status || 'healthy'] || '#22c55e';
  const typeAbbr = typeAbbreviations[data.deviceType] || data.deviceType?.toUpperCase().slice(0, 3);

  return (
    <div className="relative group">
      {/* 4 handles — visible on hover, act as both source + target */}
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <div
        className="flex flex-col items-center gap-1.5 p-3 rounded-lg border-2 transition-all min-w-[80px]"
        style={{
          backgroundColor: selected ? '#162a2e' : '#0f2023',
          borderColor: selected ? '#07b6d5' : '#224349',
          borderRadius: isFirewall ? '12px' : '8px',
          clipPath: isFirewall
            ? 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)'
            : undefined,
          padding: isFirewall ? '20px 16px' : undefined,
        }}
      >
        {/* Status dot */}
        <div
          className="absolute top-1 right-1 w-2 h-2 rounded-full"
          style={{ backgroundColor: statusColor }}
        />

        {/* Icon */}
        <span
          className="material-symbols-outlined text-2xl"
          style={{
            fontFamily: 'Material Symbols Outlined',
            color: deviceColors[data.deviceType] || (isFirewall ? '#ef4444' : '#f59e0b'),
          }}
        >
          {icon}
        </span>

        {/* Device type badge */}
        {typeAbbr && (
          <span
            className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded-full leading-none"
            style={{
              backgroundColor: 'rgba(7,182,213,0.15)',
              color: '#07b6d5',
              border: '1px solid rgba(7,182,213,0.3)',
            }}
          >
            {typeAbbr}
          </span>
        )}

        {/* Label */}
        <span
          className="text-[10px] font-mono font-medium text-center leading-tight max-w-[70px] truncate"
          style={{ color: '#e2e8f0' }}
        >
          {data.label}
        </span>

        {/* IP */}
        {data.ip && (
          <span
            className="text-[9px] font-mono"
            style={{ color: '#64748b' }}
          >
            {data.ip}
          </span>
        )}

        {/* Zone label */}
        {data.zone && (
          <span
            className="text-[8px] font-mono truncate max-w-[70px]"
            style={{ color: '#4a7a80' }}
          >
            {data.zone}
          </span>
        )}

        {/* Interfaces */}
        {data.interfaces && data.interfaces.length > 0 && (
          <>
            <div className="w-full border-t mt-1 pt-1" style={{ borderColor: '#224349' }} />
            {data.interfaces.map((iface, idx) => (
              <div key={iface.id || idx} className="flex items-center gap-1.5 w-full px-1">
                <div
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: roleColors[iface.role] || '#64748b' }}
                />
                <span className="text-[8px] font-mono truncate" style={{ color: '#94a3b8' }}>
                  {iface.name}
                </span>
                <span className="text-[7px] font-mono ml-auto" style={{ color: '#475569' }}>
                  {iface.role ? iface.role.slice(0, 3).toUpperCase() : ''}
                </span>
                <Handle
                  type="source"
                  position={Position.Right}
                  id={`iface-${iface.id || idx}`}
                  className="!w-2 !h-2 !bg-[#07b6d5] !border !border-[#0a0f13] !right-[-8px]"
                  style={{ top: 'auto', position: 'relative' }}
                />
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
};

export default memo(DeviceNode);
