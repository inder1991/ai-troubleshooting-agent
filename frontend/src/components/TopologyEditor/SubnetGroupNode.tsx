import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface SubnetGroupData {
  label: string;
  cidr?: string;
  deviceType: string;
}

const SubnetGroupNode: React.FC<NodeProps<SubnetGroupData>> = ({ data, selected }) => {
  return (
    <div
      className="relative w-full h-full rounded-lg border-2 border-dashed group"
      style={{
        backgroundColor: 'rgba(7,182,213,0.05)',
        borderColor: selected ? '#07b6d5' : '#224349',
        minWidth: 200,
        minHeight: 150,
      }}
    >
      {/* 4 handles — visible on hover */}
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#07b6d5] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl
        minWidth={200}
        minHeight={150}
        style={{
          background: 'transparent',
          border: 'none',
        }}
      >
        <div
          className="absolute bottom-0 right-0 w-3 h-3 cursor-se-resize"
          style={{ borderRight: '2px solid #07b6d5', borderBottom: '2px solid #07b6d5' }}
        />
      </NodeResizeControl>

      {/* CIDR label at top */}
      <div
        className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
        style={{
          backgroundColor: '#0f2023',
          color: '#07b6d5',
          border: '1px solid #224349',
        }}
      >
        {data.cidr || data.label}
      </div>

      {/* Subnet name */}
      <div
        className="absolute bottom-2 left-3 text-[10px] font-mono"
        style={{ color: '#64748b' }}
      >
        {data.label}
      </div>
    </div>
  );
};

export default memo(SubnetGroupNode);
