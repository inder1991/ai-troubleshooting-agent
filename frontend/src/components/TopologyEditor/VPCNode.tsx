import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface VPCNodeData {
  label: string;
  cidr?: string;
  cloudProvider?: string;
  region?: string;
  deviceType: string;
}

const providerLabels: Record<string, string> = {
  aws: 'AWS', azure: 'Azure', gcp: 'GCP', oci: 'OCI',
};

const VPCNode: React.FC<NodeProps<VPCNodeData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(59,130,246,0.05)', borderColor: selected ? '#3b82f6' : '#1e3a5f',
                  minWidth: 300, minHeight: 200 }}>
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#3b82f6] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={300} minHeight={200}
        style={{ background: 'transparent', border: 'none' }}>
        <div className="absolute bottom-0 right-0 w-3 h-3 cursor-se-resize"
             style={{ borderRight: '2px solid #3b82f6', borderBottom: '2px solid #3b82f6' }} />
      </NodeResizeControl>

      {/* Provider badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ backgroundColor: '#1e3a5f', color: '#3b82f6', border: '1px solid #2563eb' }}>
        {providerLabels[data.cloudProvider || ''] || 'Cloud'}
      </div>

      {/* CIDR label */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ backgroundColor: '#0f2023', color: '#3b82f6', border: '1px solid #1e3a5f' }}>
        {data.cidr || data.label}
      </div>

      {/* VPC name + region */}
      <div className="absolute bottom-2 left-3 text-[10px] font-mono" style={{ color: '#64748b' }}>
        {data.label}{data.region ? ` (${data.region})` : ''}
      </div>
    </div>
  );
};

export default memo(VPCNode);
