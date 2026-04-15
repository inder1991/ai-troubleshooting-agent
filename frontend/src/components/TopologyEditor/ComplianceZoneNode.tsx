import React, { memo } from 'react';
import { Handle, Position, NodeProps, NodeResizeControl } from 'reactflow';

interface ComplianceZoneData {
  label: string;
  complianceStandard?: string;
  deviceType: string;
  _source?: 'live' | 'planned';
  _locked?: boolean;
}

const standardLabels: Record<string, string> = {
  pci_dss: 'PCI-DSS', soc2: 'SOC2', hipaa: 'HIPAA', custom: 'Custom',
};

const ComplianceZoneNode: React.FC<NodeProps<ComplianceZoneData>> = ({ data, selected }) => {
  const isPlanned = data._source === 'planned';
  const isLive = data._source === 'live';

  return (
    <div className="relative w-full h-full rounded-lg border-2 border-dashed group"
         style={{
           backgroundColor: 'rgba(245,158,11,0.05)',
           borderColor: isPlanned ? '#f59e0b' : selected ? '#f59e0b' : '#78350f',
           opacity: isPlanned ? 0.85 : 1,
         }}>
      <Handle type="target" position={Position.Top} id="top"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Bottom} id="bottom"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="target" position={Position.Left} id="left"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />
      <Handle type="source" position={Position.Right} id="right"
        className="!w-2.5 !h-2.5 !bg-[#f59e0b] !border !border-[#3a5a60] opacity-0 group-hover:opacity-100 transition-opacity" />

      <NodeResizeControl minWidth={250} minHeight={180}
        style={{ background: '#f59e0b', width: '8px', height: '8px', borderRadius: '2px' }}
      />

      {/* Live lock icon */}
      {isLive && (
        <div className="absolute -top-1.5 -left-1.5" style={{ zIndex: 10 }}>
          <span className="material-symbols-outlined text-body-xs" style={{ color: '#64748b' }}>lock</span>
        </div>
      )}

      {/* Planned badge */}
      {isPlanned && (
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 px-1.5 py-px rounded text-[7px] font-mono font-bold"
             style={{ zIndex: 20, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
          PLANNED
        </div>
      )}

      {/* Standard badge */}
      <div className="absolute top-0 right-3 -translate-y-1/2 px-2 py-0.5 rounded text-body-xs font-mono font-bold"
           style={{ zIndex: 10, backgroundColor: '#78350f', color: '#f59e0b', border: '1px solid #92400e' }}>
        {standardLabels[data.complianceStandard || ''] || 'Compliance'}
      </div>

      {/* Zone name */}
      <div className="absolute top-0 left-3 -translate-y-1/2 px-2 py-0.5 rounded text-body-xs font-mono font-semibold"
           style={{ zIndex: 10, backgroundColor: '#1a1814', color: '#f59e0b', border: '1px solid #78350f' }}>
        {data.label}
      </div>
    </div>
  );
};

export default memo(ComplianceZoneNode);
