import React, { memo } from 'react';
import { Handle, Position, NodeResizeControl, type NodeProps } from 'reactflow';

const HAGroupNode: React.FC<NodeProps> = ({ data, selected }) => {
  const mode = (data.haMode as string) || 'active_passive';
  const modeLabel = mode === 'active_active' ? 'A/A' : mode === 'vrrp' ? 'VRRP' : 'A/P';
  const vips = (data.virtualIps as string) || '';

  return (
    <div
      className="relative w-full h-full rounded-lg border-2 border-dashed group"
      style={{
        borderColor: selected ? '#f59e0b' : '#92400e',
        backgroundColor: 'rgba(245,158,11,0.05)',
        pointerEvents: 'none',
      }}
    >
      <Handle type="target" position={Position.Top} id="top"
        style={{ pointerEvents: 'auto' }}
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        style={{ pointerEvents: 'auto' }}
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        style={{ pointerEvents: 'auto' }}
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        style={{ pointerEvents: 'auto' }}
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={280} minHeight={140}
        style={{ background: '#f59e0b', width: '8px', height: '8px', borderRadius: '2px', pointerEvents: 'auto' }}
      />

      {/* Mode badge top-right */}
      <div className="container-interactive absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        HA: {modeLabel}
      </div>

      {/* Name top-left */}
      <div className="container-interactive absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#0f2023', color: '#f59e0b', border: '1px solid #92400e' }}>
        <span
          className="material-symbols-outlined text-xs mr-1 align-middle"
          style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b', fontSize: '12px' }}
        >
          sync
        </span>
        {data.label || 'HA Group'}
      </div>

      {/* VIP at bottom */}
      {vips && (
        <div className="container-interactive absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#94a3b8' }}>
          VIP: {vips}
        </div>
      )}
    </div>
  );
};

export default memo(HAGroupNode);
