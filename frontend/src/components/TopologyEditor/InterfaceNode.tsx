import React, { memo } from 'react';
import { Handle, Position, type NodeProps, NodeResizeControl } from 'reactflow';

interface InterfaceNodeData {
  name: string;
  ip?: string;
  role: string;
  zone?: string;
  parentDeviceId: string;
  parentDeviceName?: string;
  subnetId?: string;
}

const roleColors: Record<string, string> = {
  management: '#3b82f6',
  inside: '#22c55e',
  outside: '#ef4444',
  dmz: '#f59e0b',
  sync: '#64748b',
  loopback: '#a855f7',
};

const roleLabels: Record<string, string> = {
  management: 'MGT',
  inside: 'IN',
  outside: 'OUT',
  dmz: 'DMZ',
  sync: 'SYNC',
  loopback: 'LO',
};

const InterfaceNode: React.FC<NodeProps<InterfaceNodeData>> = ({ data, selected }) => {
  const color = roleColors[data.role] || '#07b6d5';
  const roleLabel = roleLabels[data.role] || data.role?.toUpperCase().slice(0, 3) || 'IF';

  return (
    <div className="relative group w-full h-full">
      <NodeResizeControl minWidth={60} minHeight={28}
        style={{ background: color, width: '8px', height: '8px', borderRadius: '2px' }}
      />

      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: color }} />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: color }} />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: color }} />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: color }} />

      <div
        className="w-full h-full flex items-center justify-center gap-1.5 px-2 py-1 rounded border transition-all"
        style={{
          backgroundColor: selected ? '#162a2e' : '#0f2023',
          borderColor: selected ? color : '#224349',
          borderLeftWidth: '3px',
          borderLeftColor: color,
        }}
      >
        {/* Port icon */}
        <span
          className="material-symbols-outlined shrink-0"
          style={{ fontFamily: 'Material Symbols Outlined', fontSize: '14px', color }}
        >
          settings_ethernet
        </span>

        {/* Name + role inline, IP + parent shown when space allows */}
        <div className="flex flex-col gap-0 min-w-0 overflow-hidden">
          <div className="flex items-center gap-1">
            <span className="text-[9px] font-mono font-semibold truncate" style={{ color: '#e2e8f0' }}>
              {data.name || 'eth0'}
            </span>
            <span
              className="text-[6px] font-mono font-bold px-1 py-px rounded leading-none shrink-0"
              style={{ backgroundColor: color + '25', color, border: `1px solid ${color}50` }}
            >
              {roleLabel}
            </span>
          </div>
          {data.ip && (
            <span className="text-[7px] font-mono leading-none truncate" style={{ color: '#64748b' }}>
              {data.ip}
            </span>
          )}
          {data.parentDeviceName && (
            <span className="text-[6px] font-mono leading-none truncate" style={{ color: '#475569' }}>
              ↳ {data.parentDeviceName}
            </span>
          )}
        </div>
      </div>
    </div>
  );
};

export default memo(InterfaceNode);
