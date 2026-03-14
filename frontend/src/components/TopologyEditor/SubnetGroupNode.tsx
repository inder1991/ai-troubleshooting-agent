import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface SubnetGroupData {
  label: string;
  cidr?: string;
  deviceType: string;
  _source?: 'live' | 'planned';
  _locked?: boolean;
}

const SubnetGroupNode: React.FC<NodeProps<SubnetGroupData>> = ({ data, selected }) => {
  const isPlanned = data._source === 'planned';
  const isLive = data._source === 'live';

  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{
           backgroundColor: 'rgba(224,159,62,0.05)',
           borderColor: isPlanned ? '#f59e0b' : selected ? '#e09f3e' : '#3d3528',
           opacity: isPlanned ? 0.85 : 1,
         }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#e09f3e] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={200} minHeight={150}
        style={{ background: '#e09f3e', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* Live lock icon */}
      {isLive && (
        <div className="absolute -top-1.5 -left-1.5" style={{ zIndex: 10 }}>
          <span className="material-symbols-outlined text-[10px]" style={{ color: '#64748b' }}>lock</span>
        </div>
      )}

      {/* Planned badge */}
      {isPlanned && (
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 px-1.5 py-px rounded text-[7px] font-mono font-bold"
             style={{ zIndex: 20, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
          PLANNED
        </div>
      )}

      {/* CIDR label at top */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#1a1814', color: '#e09f3e', border: '1px solid #3d3528' }}>
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
