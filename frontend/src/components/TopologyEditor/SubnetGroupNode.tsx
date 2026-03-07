import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface SubnetGroupData {
  label: string;
  cidr?: string;
  deviceType: string;
}

const SubnetGroupNode: React.FC<NodeProps<SubnetGroupData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(7,182,213,0.05)', borderColor: selected ? '#07b6d5' : '#224349' }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#07b6d5] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={200} minHeight={150}
        style={{ background: '#07b6d5', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* CIDR label at top */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#0f2023', color: '#07b6d5', border: '1px solid #224349' }}>
        {data.cidr || data.label}
      </div>

      {/* Subnet name */}
      <div className="absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#64748b' }}>
        {data.label}
      </div>
    </div>
  );
};

export default memo(SubnetGroupNode);
