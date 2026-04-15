import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

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
  _source?: 'live' | 'planned';
  _locked?: boolean;
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
  nat_gateway: 'nat',
  internet_gateway: 'language',
  lambda: 'functions',
  route_table: 'route',
  security_group: 'shield_lock',
  elastic_ip: 'pin_drop',
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
  nat_gateway: '#10b981',
  internet_gateway: '#3b82f6',
  lambda: '#f97316',
  route_table: '#a855f7',
  security_group: '#ef4444',
  elastic_ip: '#eab308',
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
  nat_gateway: 'NAT',
  internet_gateway: 'IGW',
  lambda: 'FN',
  route_table: 'RT',
  security_group: 'SG',
  elastic_ip: 'EIP',
};

const DeviceNode: React.FC<NodeProps<DeviceNodeData>> = ({ data, selected }) => {
  const isFirewall = data.deviceType === 'firewall';
  const icon = deviceIcons[data.deviceType] || 'devices';
  const statusColor = statusColors[data.status || 'healthy'] || '#22c55e';
  const typeAbbr = typeAbbreviations[data.deviceType] || data.deviceType?.toUpperCase().slice(0, 3);
  const accentColor = deviceColors[data.deviceType] || '#e09f3e';
  const isPlanned = data._source === 'planned';
  const isLive = data._source === 'live';

  return (
    <div className="relative group w-full h-full" style={{ opacity: isPlanned ? 0.85 : 1 }}>
      {/* Resize control */}
      <NodeResizeControl minWidth={56} minHeight={40}
        style={{ background: accentColor, width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* 4 directional handles — top+left=target, bottom+right=source */}
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <div
        className="w-full h-full flex flex-col items-center justify-center gap-0.5 p-1.5 rounded border transition-all"
        style={{
          backgroundColor: selected ? '#1e1b15' : '#1a1814',
          borderColor: isPlanned ? '#f59e0b' : selected ? '#e09f3e' : '#3d3528',
          borderRadius: isFirewall ? '12px' : '6px',
          borderWidth: isFirewall ? '2px' : '1px',
          borderStyle: isPlanned ? 'dashed' : isFirewall ? 'double' : 'solid',
        }}
      >
        {/* Status dot */}
        <div
          className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: statusColor }}
        />

        {/* Live lock icon */}
        {isLive && (
          <div className="absolute -top-1.5 -left-1.5" style={{ zIndex: 10 }}>
            <span className="material-symbols-outlined text-body-xs" style={{ color: '#64748b' }}>lock</span>
          </div>
        )}

        {/* Planned badge */}
        {isPlanned && (
          <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-1.5 py-px rounded text-[7px] font-mono font-bold"
               style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
            PLANNED
          </div>
        )}

        {/* Icon + type badge inline */}
        <div className="flex items-center gap-1">
          <span
            className="material-symbols-outlined text-base text-[16px]"
            style={{ color: accentColor }}
          >
            {icon}
          </span>
          {typeAbbr && (
            <span
              className="text-[7px] font-mono font-bold px-1 py-px rounded-full leading-none"
              style={{
                backgroundColor: 'rgba(224,159,62,0.15)',
                color: '#e09f3e',
                border: '1px solid rgba(224,159,62,0.3)',
              }}
            >
              {typeAbbr}
            </span>
          )}
        </div>

        {/* Label */}
        <span
          className="text-body-xs font-mono font-medium text-center leading-tight max-w-[100px] truncate"
          style={{ color: '#e8e0d4' }}
        >
          {data.label}
        </span>

        {/* IP */}
        {data.ip && (
          <span className="text-chrome font-mono leading-none" style={{ color: '#64748b' }}>
            {data.ip}
          </span>
        )}

        {/* Zone */}
        {data.zone && (
          <span className="text-[7px] font-mono truncate max-w-[80px] leading-none" style={{ color: '#4a7a80' }}>
            {data.zone}
          </span>
        )}
      </div>
    </div>
  );
};

export default memo(DeviceNode);
