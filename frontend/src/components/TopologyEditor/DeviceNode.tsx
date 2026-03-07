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
  const accentColor = deviceColors[data.deviceType] || '#07b6d5';

  return (
    <div className="relative group w-full h-full">
      {/* Resize control */}
      <NodeResizeControl minWidth={56} minHeight={40}
        style={{ background: accentColor, width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* 4 directional handles — top+left=target, bottom+right=source */}
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <div
        className="w-full h-full flex flex-col items-center justify-center gap-0.5 p-1.5 rounded border transition-all"
        style={{
          backgroundColor: selected ? '#162a2e' : '#0f2023',
          borderColor: selected ? '#07b6d5' : '#224349',
          borderRadius: isFirewall ? '12px' : '6px',
          borderWidth: isFirewall ? '2px' : '1px',
          borderStyle: isFirewall ? 'double' : 'solid',
        }}
      >
        {/* Status dot */}
        <div
          className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: statusColor }}
        />

        {/* Icon + type badge inline */}
        <div className="flex items-center gap-1">
          <span
            className="material-symbols-outlined text-base"
            style={{
              fontFamily: 'Material Symbols Outlined',
              fontSize: '16px',
              color: accentColor,
            }}
          >
            {icon}
          </span>
          {typeAbbr && (
            <span
              className="text-[7px] font-mono font-bold px-1 py-px rounded-full leading-none"
              style={{
                backgroundColor: 'rgba(7,182,213,0.15)',
                color: '#07b6d5',
                border: '1px solid rgba(7,182,213,0.3)',
              }}
            >
              {typeAbbr}
            </span>
          )}
        </div>

        {/* Label */}
        <span
          className="text-[9px] font-mono font-medium text-center leading-tight max-w-[100px] truncate"
          style={{ color: '#e2e8f0' }}
        >
          {data.label}
        </span>

        {/* IP */}
        {data.ip && (
          <span className="text-[8px] font-mono leading-none" style={{ color: '#64748b' }}>
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
