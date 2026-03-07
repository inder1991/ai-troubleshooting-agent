import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface AZNodeData {
  label: string;
  zoneName?: string;
  cloudProvider?: string;
  region?: string;
  deviceType: string;
}

const AZNode: React.FC<NodeProps<AZNodeData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(245,158,11,0.04)', borderColor: selected ? '#f59e0b' : '#92400e' }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={280} minHeight={180}
        style={{ background: '#f59e0b', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* AZ badge top-right */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        AZ
      </div>

      {/* Zone name top-left */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#0f2023', color: '#f59e0b', border: '1px solid #92400e' }}>
        {data.zoneName || data.label}
      </div>

      {/* Name + region at bottom */}
      <div className="absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#64748b' }}>
        {data.label}{data.region ? ` (${data.region})` : ''}
      </div>
    </div>
  );
};

export default memo(AZNode);
