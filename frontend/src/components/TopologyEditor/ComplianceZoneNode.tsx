import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface ComplianceZoneData {
  label: string;
  complianceStandard?: string;
  deviceType: string;
}

const standardLabels: Record<string, string> = {
  pci_dss: 'PCI-DSS', soc2: 'SOC2', hipaa: 'HIPAA', custom: 'Custom',
};

const ComplianceZoneNode: React.FC<NodeProps<ComplianceZoneData>> = ({ data, selected }) => {
  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{ backgroundColor: 'rgba(245,158,11,0.05)', borderColor: selected ? '#f59e0b' : '#78350f', pointerEvents: 'none' }}>
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

      <NodeResizeControl minWidth={250} minHeight={180}
        style={{ background: '#f59e0b', width: '8px', height: '8px', borderRadius: '2px', pointerEvents: 'auto' }}
      />

      {/* Standard badge */}
      <div className="container-interactive absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        {standardLabels[data.complianceStandard || ''] || 'Compliance'}
      </div>

      {/* Zone name */}
      <div className="container-interactive absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#0f2023', color: '#f59e0b', border: '1px solid #78350f' }}>
        {data.label}
      </div>
    </div>
  );
};

export default memo(ComplianceZoneNode);
