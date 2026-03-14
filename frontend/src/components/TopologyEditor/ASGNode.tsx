import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface ASGNodeData {
  label: string;
  minCapacity?: number;
  maxCapacity?: number;
  desiredCapacity?: number;
  launchTemplate?: string;
  deviceType: string;
}

const ASGNode: React.FC<NodeProps<ASGNodeData>> = ({ data, selected }) => {
  const min = data.minCapacity ?? 0;
  const desired = data.desiredCapacity ?? 0;
  const max = data.maxCapacity ?? 0;
  const capacityLabel = `${min}/${desired}/${max}`;

  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(16,185,129,0.05)', borderColor: selected ? '#10b981' : '#065f46' }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#10b981] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#10b981] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#10b981] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#10b981] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={250} minHeight={160}
        style={{ background: '#10b981', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* Capacity badge top-right */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#065f46', color: '#10b981', border: '1px solid #059669' }}>
        {capacityLabel}
      </div>

      {/* Name top-left */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#1a1814', color: '#10b981', border: '1px solid #065f46' }}>
        {data.label}
      </div>

      {/* Launch template at bottom */}
      <div className="absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#64748b' }}>
        {data.launchTemplate ? `Template: ${data.launchTemplate}` : 'ASG'}
      </div>
    </div>
  );
};

export default memo(ASGNode);
