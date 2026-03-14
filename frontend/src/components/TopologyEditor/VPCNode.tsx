import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface VPCNodeData {
  label: string;
  cidr?: string;
  cloudProvider?: string;
  region?: string;
  deviceType: string;
  _source?: 'live' | 'planned';
  _locked?: boolean;
}

const providerLabels: Record<string, string> = {
  aws: 'AWS', azure: 'Azure', gcp: 'GCP', oci: 'OCI',
};

const VPCNode: React.FC<NodeProps<VPCNodeData>> = ({ data, selected }) => {
  const isPlanned = data._source === 'planned';
  const isLive = data._source === 'live';

  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{
           backgroundColor: 'rgba(59,130,246,0.05)',
           borderColor: isPlanned ? '#f59e0b' : selected ? '#3b82f6' : '#1e3a5f',
           opacity: isPlanned ? 0.85 : 1,
         }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#3b82f6] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#3b82f6] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#3b82f6] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#3b82f6] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={300} minHeight={200}
        style={{ background: '#3b82f6', width: '8px', height: '8px', borderRadius: '2px' }}
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

      {/* Provider badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#1e3a5f', color: '#3b82f6', border: '1px solid #2563eb' }}>
        {providerLabels[data.cloudProvider || ''] || 'Cloud'}
      </div>

      {/* CIDR label */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#1a1814', color: '#3b82f6', border: '1px solid #1e3a5f' }}>
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
