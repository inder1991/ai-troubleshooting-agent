import React, { memo } from 'react';
import { Handle, Position, NodeResizeControl, type NodeProps } from 'reactflow';

const HAGroupNode: React.FC<NodeProps> = ({ data, selected }) => {
  const mode = (data.haMode as string) || 'active_passive';
  const modeLabel = mode === 'active_active' ? 'A/A' : mode === 'vrrp' ? 'VRRP' : 'A/P';
  const vips = (data.virtualIps as string) || '';
  const isPlanned = (data._source as string) === 'planned';
  const isLive = (data._source as string) === 'live';

  return (
    <div
      className="relative w-full h-full rounded-lg border-2 border-dashed group"
      style={{
        borderColor: isPlanned ? '#f59e0b' : selected ? '#f59e0b' : '#92400e',
        backgroundColor: 'rgba(245,158,11,0.05)',
        opacity: isPlanned ? 0.85 : 1,
      }}
    >
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={280} minHeight={140}
        style={{ background: '#f59e0b', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* Live lock icon */}
      {isLive && (
        <div className="absolute -top-1.5 -left-1.5" style={{ zIndex: 10 }}>
          <span className="material-symbols-outlined text-body-xs" style={{ color: '#64748b' }}>lock</span>
        </div>
      )}

      {/* Planned badge */}
      {isPlanned && (
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 px-1.5 py-px rounded text-[7px] font-mono font-bold"
             style={{ zIndex: 20, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
          PLANNED
        </div>
      )}

      {/* Mode badge top-right */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-body-xs font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        HA: {modeLabel}
      </div>

      {/* Name top-left */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-body-xs font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#1a1814', color: '#f59e0b', border: '1px solid #92400e' }}>
        <span
          className="material-symbols-outlined text-xs mr-1 align-middle text-[12px]"
          style={{ color: '#f59e0b' }}
        >
          sync
        </span>
        {data.label || 'HA Group'}
      </div>

      {/* VIP at bottom */}
      {vips && (
        <div className="absolute bottom-2 left-3 text-body-xs font-mono" style={{ color: '#8a7e6b' }}>
          VIP: {vips}
        </div>
      )}
    </div>
  );
};

export default memo(HAGroupNode);
