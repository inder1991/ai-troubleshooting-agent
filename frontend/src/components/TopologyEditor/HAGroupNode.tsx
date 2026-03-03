import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

const HAGroupNode: React.FC<NodeProps> = ({ data }) => {
  const mode = (data.haMode as string) || 'active_passive';
  const modeLabel = mode === 'active_active' ? 'A/A' : mode === 'vrrp' ? 'VRRP' : 'A/P';
  const vips = (data.virtualIps as string) || '';

  return (
    <div
      className="rounded-lg border-2 border-dashed p-3 relative"
      style={{
        minWidth: 280,
        minHeight: 140,
        borderColor: '#f59e0b',
        backgroundColor: 'rgba(245,158,11,0.05)',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#f59e0b' }} />
      <Handle type="source" position={Position.Right} style={{ background: '#f59e0b' }} />

      <div className="flex items-center gap-2 mb-1">
        <span
          className="material-symbols-outlined text-sm"
          style={{ fontFamily: 'Material Symbols Outlined', color: '#f59e0b' }}
        >
          sync
        </span>
        <span className="text-xs font-mono font-bold" style={{ color: '#f59e0b' }}>
          HA: {modeLabel}
        </span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
          {data.label || 'HA Group'}
        </span>
      </div>
      {vips && (
        <div className="text-[10px] font-mono" style={{ color: '#94a3b8' }}>
          VIP: {vips}
        </div>
      )}
    </div>
  );
};

export default memo(HAGroupNode);
