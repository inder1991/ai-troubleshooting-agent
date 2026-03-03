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
         style={{ backgroundColor: 'rgba(245,158,11,0.05)', borderColor: selected ? '#f59e0b' : '#78350f',
                  minWidth: 250, minHeight: 180 }}>
      <Handle type="source" position={Position.Top} id="top"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Left} id="left"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-3 !h-3 !bg-[#f59e0b] !border-2 !border-[#0a0f13] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={250} minHeight={180}
        style={{ background: 'transparent', border: 'none' }}>
        <div className="absolute bottom-0 right-0 w-3 h-3 cursor-se-resize"
             style={{ borderRight: '2px solid #f59e0b', borderBottom: '2px solid #f59e0b' }} />
      </NodeResizeControl>

      {/* Standard badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-[9px] font-mono font-bold"
           style={{ backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        {standardLabels[data.complianceStandard || ''] || 'Compliance'}
      </div>

      {/* Zone name */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold"
           style={{ backgroundColor: '#0f2023', color: '#f59e0b', border: '1px solid #78350f' }}>
        {data.label}
      </div>
    </div>
  );
};

export default memo(ComplianceZoneNode);
