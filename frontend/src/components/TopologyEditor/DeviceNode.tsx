import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';

interface DeviceNodeData {
  label: string;
  deviceType: string;
  ip?: string;
  vendor?: string;
  zone?: string;
  status?: 'healthy' | 'degraded' | 'down';
}

const deviceIcons: Record<string, string> = {
  router: 'router',
  switch: 'swap_horiz',
  firewall: 'local_fire_department',
  workload: 'memory',
  cloud_gateway: 'cloud',
  zone: 'shield',
};

const statusColors: Record<string, string> = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  down: '#ef4444',
};

const DeviceNode: React.FC<NodeProps<DeviceNodeData>> = ({ data, selected }) => {
  const isFirewall = data.deviceType === 'firewall';
  const icon = deviceIcons[data.deviceType] || 'devices';
  const statusColor = statusColors[data.status || 'healthy'] || '#22c55e';

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
            color: isFirewall ? '#ef4444' : '#f59e0b',
          }}
        >
          {icon}
        </span>

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
      </div>
    </div>
  );
};

export default memo(DeviceNode);
